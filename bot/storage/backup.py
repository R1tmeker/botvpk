from __future__ import annotations

from pathlib import Path
from datetime import datetime

from ..utils.files import copy_to_backup


def create_backup(source: Path, backups_dir: Path) -> Path:
    """
    Create timestamped backup for the source file inside backups_dir.
    """
    if not source.exists():
        return source
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    return copy_to_backup(source, backups_dir, suffix_parts=[timestamp])
