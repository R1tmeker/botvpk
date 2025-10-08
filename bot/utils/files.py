from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Iterable


def ensure_directory(directory: Path) -> None:
    """Create directory (and parents) if it does not exist."""
    directory.mkdir(parents=True, exist_ok=True)


def atomic_write(
    target_path: Path,
    data: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = "\n",
) -> None:
    """
    Write text to a file atomically:
    - create temp file in same directory
    - replace the target file
    """
    ensure_directory(target_path.parent)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, encoding=encoding, newline=newline, dir=target_path.parent
    ) as tmp_file:
        tmp_file.write(data)
        tmp_name = Path(tmp_file.name)

    tmp_name.replace(target_path)


def copy_to_backup(source: Path, backup_dir: Path, suffix_parts: Iterable[str] | None = None) -> Path:
    """
    Copy file to backup directory with timestamp-based name.
    suffix_parts allows injecting additional tokens before extension.
    """
    ensure_directory(backup_dir)
    stem = source.stem
    extension = source.suffix
    suffix = ""
    if suffix_parts:
        suffix = "_" + "_".join(part for part in suffix_parts if part)
    backup_name = f"{stem}{suffix}{extension}"
    destination = backup_dir / backup_name
    counter = 1
    while destination.exists():
        destination = backup_dir / f"{stem}{suffix}_{counter}{extension}"
        counter += 1

    shutil.copy2(source, destination)
    return destination

