from __future__ import annotations

import logging
from datetime import datetime
from logging import Logger
from pathlib import Path

from .files import ensure_directory


def setup_logging(logs_dir: Path) -> Logger:
    """
    Configure application logging:
    - INFO level console handler
    - DEBUG level file handler (daily rolling by file name)
    """
    ensure_directory(logs_dir)
    logger = logging.getLogger("vpk_bot")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s][%(levelname)s][%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file = logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
