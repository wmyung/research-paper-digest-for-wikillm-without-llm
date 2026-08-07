from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path

from ..config import DigestConfig


def _safe_member_name(name: str) -> Path:
    candidate = Path(name.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Unsafe archive path: {name}")
    if not candidate.name and len(candidate.parts) == 0:
        raise ValueError("Empty archive path.")
    return candidate


def expand_zip(path: Path, destination: Path, config: DigestConfig) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > config.max_archive_members:
            raise ValueError(f"Archive has {len(infos)} members; limit is {config.max_archive_members}.")
        for info in infos:
            relative = _safe_member_name(info.filename)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"Archive symlink is not allowed: {info.filename}")
            if info.is_dir():
                continue
            if info.file_size > config.max_archive_member_bytes:
                raise ValueError(f"Archive member exceeds size limit: {info.filename}")
            total += info.file_size
            if total > config.max_archive_total_bytes:
                raise ValueError("Archive expanded size exceeds total limit.")
            compressed = max(info.compress_size, 1)
            if info.file_size / compressed > config.max_archive_ratio:
                raise ValueError(f"Archive compression ratio exceeds limit: {info.filename}")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
            extracted.append(target)
    return extracted


def expand_archives(paths: list[Path], destination: Path, config: DigestConfig) -> list[Path]:
    output: list[Path] = []
    queue = list(paths)
    archive_index = 0
    while queue:
        path = queue.pop(0)
        if path.suffix.casefold() != ".zip":
            output.append(path)
            continue
        archive_index += 1
        children = expand_zip(path, destination / f"archive-{archive_index:03d}", config)
        queue[:0] = children
    return output
