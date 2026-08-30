from __future__ import annotations

import csv
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .compiler import compile_markdown
from .config import DigestConfig
from .evidence import metadata_ledger
from .inventory import inventory
from .metadata import enrich_from_doi_registry, extract_publication_metadata
from .models import CompiledDigest, ParsedBundle, WorkbookSheet
from .parsers import extract_docx, extract_pdf, extract_workbook
from .profiles.base import ProfileContent, ProfileScore
from .profiles.classifier import choose_profile
from .profiles.universal import UniversalProfile
from .qa import evaluate_digest
from .repair import repair_digest
from .sections import segment_sections
from .selection import Candidate
from .text import normalize_prose


def _csv_sheet(path: Path) -> WorkbookSheet:
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel_tab if path.suffix.casefold() == ".tsv" else csv.excel
        for raw in csv.reader(handle, dialect):
            row = [normalize_prose(value) for value in raw]
            if any(row):
                rows.append(row)
    title = " ".join(value for value in (rows[0] if rows else []) if value)[:500] or path.stem
    return WorkbookSheet(
        file_name=path.name,
        sheet_name=path.stem,
        state="visible",
        max_row=len(rows),
        max_column=max((len(row) for row in rows), default=0),
        title=title,
        rows=rows,
        nonempty_cells=sum(bool(value) for row in rows for value in row),
    )


def _copy_inputs(paths: Iterable[Path], destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    output: list[Path] = []
    for index, source in enumerate(paths):
        source = Path(source).resolve()
        target = destination / source.name
        if target.exists():
            target = destination / f"{index:02d}-{source.name}"
        shutil.copy2(source, target)
        output.append(target)
    return output


def build_bundle(paths: list[Path], config: DigestConfig, work_dir: Path) -> ParsedBundle:
    files, canonical, unique_paths = inventory(paths, work_dir, config)
    canonical_extraction = extract_pdf(
        canonical,
        enable_ocr=config.enable_ocr,
        ocr_language=config.ocr_language,
    )
    metadata = extract_publication_metadata(canonical_extraction, canonical)
    if config.enable_doi_metadata:
        enrich_from_doi_registry(metadata, config.doi_metadata_timeout_seconds)
    sections = segment_sections(canonical_extraction.blocks, canonical.name)

    supplements_text: dict[str, str] = {}
    workbooks: list[WorkbookSheet] = []
    parser_notes = [canonical_extraction.extractor]
    if "Crossref DOI registry" in metadata.metadata_sources:
        parser_notes.append("crossref-doi-metadata")

    for path in unique_paths:
        if path == canonical:
            continue
        suffix = path.suffix.casefold()
        try:
            if suffix == ".pdf":
                extraction = extract_pdf(
                    path,
                    enable_ocr=config.enable_ocr,
                    ocr_language=config.ocr_language,
                )
                supplements_text[path.name] = extraction.full_text
                parser_notes.append(extraction.extractor)
            elif suffix in {".xlsx", ".xlsm"}:
                workbooks.extend(extract_workbook(path))
            elif suffix == ".docx":
                supplements_text[path.name] = extract_docx(path)
            elif suffix in {".csv", ".tsv"}:
                workbooks.append(_csv_sheet(path))
            elif suffix in {".md", ".txt", ".rst"}:
                supplements_text[path.name] = path.read_text(encoding="utf-8", errors="replace")
            elif suffix in {".json"}:
                obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
                supplements_text[path.name] = json.dumps(obj, ensure_ascii=False, indent=2)
        except Exception as exc:  # Preserve parser failure in QA; do not invent content.
            supplements_text[path.name] = f"[PARSER_ERROR: {type(exc).__name__}: {exc}]"

    return ParsedBundle(
        files=files,
        canonical_pdf=canonical,
        blocks=canonical_extraction.blocks,
        sections=sections,
        full_text=canonical_extraction.full_text,
        page_texts=canonical_extraction.page_texts,
        metadata=metadata,
        workbooks=workbooks,
        supplements_text=supplements_text,
        parser_notes=list(dict.fromkeys(parser_notes)),
        ocr_pages=canonical_extraction.ocr_pages,
        figure_caption_count=canonical_extraction.figure_caption_count,
        table_caption_count=canonical_extraction.table_caption_count,
        grounding_text=canonical_extraction.grounding_text,
        labelled_fields={item.label: item.value for item in canonical_extraction.metadata_fields},
    )


@dataclass(slots=True)
class _Stage1State:
    """What Stage 2 needs to rebuild the digest from an amended selection."""

    profile: UniversalProfile
    profile_scores: list[ProfileScore]
    selection: dict[str, list[Candidate]]
    content: ProfileContent


def _stage2(
    best: CompiledDigest,
    state: _Stage1State,
    bundle: ParsedBundle,
    config: DigestConfig,
) -> CompiledDigest:
    """Repair the best Stage-1 candidate against the gates it actually failed.

    Stage 1 never reads the QA report, so a record that fails structurally is
    unchanged by its four budget passes. The trigger uses the unclamped score:
    the published one is pinned to threshold - 0.01 for every failing record
    and therefore says nothing about how far the record is from the gate.
    """
    if not config.enable_stage2:
        best.qa["stage2"] = {"ran": False, "reason": "disabled"}
        return best
    raw_score = float(best.qa.get("raw_quality_score", best.qa["quality_score"]))
    if raw_score < config.stage2_min_score:
        best.qa["stage2"] = {"ran": False, "reason": "below-stage2-window", "raw_quality_score": raw_score}
        return best
    repaired = repair_digest(
        bundle=bundle,
        config=config,
        profile=state.profile,
        profile_scores=state.profile_scores,
        selection=state.selection,
        content=state.content,
        markdown=best.markdown,
        filename=best.filename,
        qa=best.qa,
    )
    if repaired is None:
        best.qa.setdefault("stage2", {"ran": True, "reason": "no-accepted-operator"})
        return best
    return CompiledDigest(
        status="SOURCE_READY" if repaired.qa["source_ready"] else "NOT_SOURCE_READY",
        markdown=repaired.markdown,
        filename=repaired.filename,
        metadata=bundle.metadata,
        qa=repaired.qa,
        bundle=bundle,
    )


def digest_files(paths: list[Path], config: DigestConfig | None = None) -> CompiledDigest:
    config = config or DigestConfig()
    owned_temp = config.work_dir is None
    temp = Path(tempfile.mkdtemp(prefix="paper-digest-")) if owned_temp else Path(config.work_dir).resolve()
    temp.mkdir(parents=True, exist_ok=True)
    try:
        local_inputs = _copy_inputs(paths, temp / "inputs") if owned_temp else [Path(path).resolve() for path in paths]
        bundle = build_bundle(local_inputs, config, temp)
        best: CompiledDigest | None = None
        best_state: _Stage1State | None = None
        for repair_pass in range(config.repair_passes):
            profile, profile_scores = choose_profile(
                bundle,
                config.profile,
                config=config,
                repair_pass=repair_pass,
            )
            selection = profile.select_all(bundle)
            content = profile.render(bundle, selection)
            markdown, filename = compile_markdown(bundle, content, config)
            qa = evaluate_digest(
                markdown=markdown,
                bundle=bundle,
                profile_name=profile.name,
                profile_scores=profile_scores,
                profile_warnings=content.warnings,
                config=config,
                evidence=content.evidence,
                retrieval_queries=content.retrieval_queries,
                coverage=getattr(profile, "coverage", {}),
                section_capacity=getattr(profile, "section_capacity", {}),
                document_profile=bundle.metadata.document_profile,
                metadata_ledger=metadata_ledger(bundle),
                authored=content.authored,
            )
            qa["repair_pass"] = repair_pass + 1
            qa["repair_passes_allowed"] = config.repair_passes
            status = "SOURCE_READY" if qa["source_ready"] else "NOT_SOURCE_READY"
            candidate = CompiledDigest(
                status=status,
                markdown=markdown,
                filename=filename,
                metadata=bundle.metadata,
                qa=qa,
                bundle=bundle,
            )
            if status == "SOURCE_READY":
                return candidate
            if best is None:
                best = candidate
                best_state = _Stage1State(profile, profile_scores, selection, content)
            else:
                candidate_key = (qa["quality_score"], -len(qa["errors"]), qa["checks"].get("body_words", 0))
                best_qa = best.qa
                best_key = (
                    best_qa["quality_score"],
                    -len(best_qa["errors"]),
                    best_qa["checks"].get("body_words", 0),
                )
                if candidate_key > best_key:
                    best = candidate
                    best_state = _Stage1State(profile, profile_scores, selection, content)
        if best is None or best_state is None:
            raise RuntimeError("The deterministic repair loop produced no candidate digest.")
        return _stage2(best, best_state, bundle, config)
    finally:
        if owned_temp:
            shutil.rmtree(temp, ignore_errors=True)
