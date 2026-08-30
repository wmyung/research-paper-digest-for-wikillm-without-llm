from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import __version__
from .config import DigestConfig
from .pipeline import digest_files
from .webapp import app_html

app = FastAPI(
    title="WikiLLM Paper Digest",
    version=__version__,
    description="Research paper digest for WikiLLM without an LLM.",
)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def web_app() -> HTMLResponse:
    response = HTMLResponse(app_html(__version__))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "version": __version__, "llm": False}


@app.post("/v1/digest")
async def digest(
    files: Annotated[list[UploadFile], File(description="Canonical PDF plus optional supplementary files")],
    options: Annotated[str | None, Form()] = None,
    raw: bool = False,
) -> Response:
    if not files:
        raise HTTPException(400, "At least one uploaded file is required.")
    if len(files) > 20:
        raise HTTPException(400, "At most 20 files are accepted in one evidence bundle.")
    try:
        raw_options = json.loads(options) if options else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"Invalid JSON in options: {exc}") from exc
    if not isinstance(raw_options, dict):
        raise HTTPException(400, "The options field must parse to a JSON object.")
    allowed = {
        "profile",
        "strict",
        "source_collection",
        "pdf_path",
        "extracted_date",
        "fail_on_missing_supplement",
        "source_ready_threshold",
        "enable_doi_metadata",
        "enable_stage2",
        "stage2_min_score",
    }
    unknown = sorted(set(raw_options) - allowed)
    if unknown:
        raise HTTPException(400, "Unsupported options: " + ", ".join(unknown))

    with tempfile.TemporaryDirectory(prefix="paper-digest-api-") as tmp:
        root = Path(tmp)
        paths: list[Path] = []
        total = 0
        for index, upload in enumerate(files):
            data = await upload.read()
            total += len(data)
            if len(data) > 100 * 1024 * 1024:
                raise HTTPException(400, f"File exceeds 100 MB: {upload.filename}")
            if total > 500 * 1024 * 1024:
                raise HTTPException(400, "Evidence bundle exceeds 500 MB.")
            name = Path(upload.filename or f"upload-{index}").name
            if not name or name in {".", ".."}:
                raise HTTPException(400, "Invalid upload filename.")
            path = root / f"{index:02d}-{name}"
            path.write_bytes(data)
            paths.append(path)
        config = DigestConfig(work_dir=root / "work", **raw_options)
        try:
            result = digest_files(paths, config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        status_code = 200 if result.status == "SOURCE_READY" else 422
        if raw and result.status == "SOURCE_READY":
            response: Response = Response(
                content=result.markdown,
                status_code=200,
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
            )
        else:
            response = JSONResponse(result.to_dict(include_markdown=True), status_code=status_code)
        response.headers["X-Paper-Digest-LLM"] = "false"
        response.headers["X-Paper-Digest-Status"] = result.status
        response.headers["Cache-Control"] = "no-store"
        return response
