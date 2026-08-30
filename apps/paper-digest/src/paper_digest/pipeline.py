from __future__ import annotations

import csv
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .compiler import compile_markdown
from .config import DigestConfig
from .evidence import metadata_ledger
from .inventory import inventory
from .metadata import enrich_from_doi_registry, extract_publication_metadata
from .models import CompiledDigest, ParsedBundle, WorkbookSheet
from .parsers import JATSExtraction, extract_docx, extract_jats, extract_pdf, extract_workbook
from .profiles.base import ProfileContent, ProfileScore
from .profiles.classifier import choose_profile
from .profiles.universal import ORDER, UniversalProfile
from .qa import evaluate_digest
from .repair import repair_digest
from .sections import segment_sections
from .selection import Candidate, score_for
from .text import normalize_prose, word_count

SCIENTIFIC_SECTIONS = {
    "Abstract",
    "Introduction",
    "Objectives",
    "Methods",
    "Results",
    "Discussion",
    "Conclusion",
    "Limitations",
}


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
    pdf_sections = segment_sections(canonical_extraction.blocks, canonical.name)
    sections = pdf_sections
    source_blocks = canonical_extraction.blocks
    source_full_text = canonical_extraction.full_text

    structured_source: dict[str, Any] = {
        "mode": "pdf-layout",
        "selected": False,
        "candidates": [],
    }
    parsed_jats: list[tuple[JATSExtraction, dict[str, Any], dict[str, Any]]] = []
    if config.enable_structured_xml:
        for xml_path in (path for path in unique_paths if path.suffix.casefold() == ".xml"):
            diagnostic: dict[str, Any] = {"file": xml_path.name, "selected": False}
            try:
                extraction = extract_jats(xml_path, canonical_extraction.page_texts, canonical.name)
                jats_sections = segment_sections(extraction.blocks, canonical.name)
                section_count = len(
                    SCIENTIFIC_SECTIONS & {name for name, value in jats_sections.items() if value.paragraphs}
                )
                diagnostic.update(
                    {
                        "aligned_sentences": extraction.aligned_sentences,
                        "total_sentences": extraction.total_sentences,
                        "alignment_ratio": extraction.alignment_ratio,
                        "aligned_words": extraction.aligned_words,
                        "scientific_sections": section_count,
                    }
                )
                parsed_jats.append((extraction, diagnostic, jats_sections))
            except Exception as exc:
                diagnostic["held_reason"] = f"{type(exc).__name__}: {exc}"
            structured_source["candidates"].append(diagnostic)

    if parsed_jats:
        extraction, diagnostic, jats_sections = max(
            parsed_jats,
            key=lambda item: (
                int(item[1]["scientific_sections"]),
                int(item[1]["aligned_words"]),
                float(item[1]["alignment_ratio"]),
                item[0].path.name,
            ),
        )
        pdf_words = word_count(canonical_extraction.full_text)
        pdf_section_count = len(
            SCIENTIFIC_SECTIONS & {name for name, value in pdf_sections.items() if value.paragraphs}
        )
        aligned_enough = (
            extraction.aligned_sentences >= config.jats_min_aligned_sentences
            and extraction.alignment_ratio >= config.jats_min_alignment_ratio
        )
        minimum_words = min(config.min_body_words, max(400, int(pdf_words * 0.65)))
        content_sufficient = extraction.aligned_words >= minimum_words
        source_needs_help = pdf_words < config.min_body_words
        # Never replace a PDF extraction that already clears the source-body
        # floor. Real-data controls showed that richer JATS headings alone are
        # not proof that the aligned subset will compile a better digest. JATS
        # is therefore a recovery fallback for genuinely short PDF prose only.
        selected = (
            aligned_enough and content_sufficient and int(diagnostic["scientific_sections"]) >= 2 and source_needs_help
        )
        diagnostic["selected"] = selected
        diagnostic["pdf_words"] = pdf_words
        diagnostic["pdf_scientific_sections"] = pdf_section_count
        if selected:
            sections = jats_sections
            source_blocks = extraction.blocks
            source_full_text = extraction.full_text
            structured_source.update(
                {
                    "mode": "jats-xml-aligned-to-pdf",
                    "selected": True,
                    "file": extraction.path.name,
                    "alignment_ratio": extraction.alignment_ratio,
                    "aligned_sentences": extraction.aligned_sentences,
                    "aligned_words": extraction.aligned_words,
                }
            )
            if extraction.article_type and metadata.article_type.casefold() in {"", "article", "journal article"}:
                metadata.article_type = extraction.article_type
                metadata.metadata_sources.append("JATS XML")

    supplements_text: dict[str, str] = {}
    workbooks: list[WorkbookSheet] = []
    parser_notes = [canonical_extraction.extractor]
    if structured_source["selected"]:
        parser_notes.append("jats-xml-aligned-to-pdf")
    if "Crossref DOI registry" in metadata.metadata_sources:
        parser_notes.append("crossref-doi-metadata")

    for path in unique_paths:
        if path == canonical:
            continue
        suffix = path.suffix.casefold()
        if suffix == ".xml":
            continue
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
        blocks=source_blocks,
        sections=sections,
        full_text=source_full_text,
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
        structured_source=structured_source,
    )


@dataclass(slots=True)
class _Stage1State:
    """What Stage 2 needs to rebuild the digest from an amended selection."""

    profile: UniversalProfile
    profile_scores: list[ProfileScore]
    selection: dict[str, list[Candidate]]
    content: ProfileContent


def _annotate_triage(qa: dict[str, Any], profile: UniversalProfile, bundle: ParsedBundle) -> None:
    """Attach compact, machine-readable diagnostics for cheap failure triage."""
    counts = {
        target: {
            "strict": sum(1 for item in profile.candidates if score_for(item, target) > 0.0),
            "relaxed": sum(1 for item in profile.candidates if score_for(item, target, relaxed=True) > 0.0),
        }
        for target in ORDER
    }
    raw = float(qa.get("raw_quality_score", qa.get("quality_score", 0.0)))
    errors = list(qa.get("errors", []))
    near_ready = bool(errors) and raw >= 0.90 and len(errors) <= 2
    qa["triage"] = {
        "near_ready": near_ready,
        "priority": "certified" if not errors else ("fast-lane" if near_ready else "structural"),
        "raw_quality_score": raw,
        "hard_error_count": len(errors),
        "candidate_counts": counts,
        "selection": dict(profile.selection_diagnostics),
        "document_profile_ranking": [list(item) for item in profile.profile_ranking],
        "structured_source": dict(bundle.structured_source),
    }


def _stage1_candidate_rank(qa: dict[str, Any]) -> tuple[int, float, int, int]:
    """Rank failing Stage-1 candidates without the published-score clamp."""
    return (
        -len(qa.get("errors", [])),
        float(qa.get("raw_quality_score", qa.get("quality_score", 0.0))),
        -len(qa.get("warnings", [])),
        int(qa.get("checks", {}).get("body_words", 0)),
    )


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
        _annotate_triage(best.qa, state.profile, bundle)
        return best
    raw_score = float(best.qa.get("raw_quality_score", best.qa["quality_score"]))
    if raw_score < config.stage2_min_score and config.external_repair_plan is None:
        best.qa["stage2"] = {"ran": False, "reason": "below-stage2-window", "raw_quality_score": raw_score}
        _annotate_triage(best.qa, state.profile, bundle)
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
        _annotate_triage(best.qa, state.profile, bundle)
        return best
    _annotate_triage(repaired.qa, state.profile, bundle)
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
            _annotate_triage(qa, profile, bundle)
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
                if _stage1_candidate_rank(qa) > _stage1_candidate_rank(best.qa):
                    best = candidate
                    best_state = _Stage1State(profile, profile_scores, selection, content)
        if best is None or best_state is None:
            raise RuntimeError("The deterministic repair loop produced no candidate digest.")
        return _stage2(best, best_state, bundle, config)
    finally:
        if owned_temp:
            shutil.rmtree(temp, ignore_errors=True)
