"""
src/utils/logger.py
-------------------
Configuracao de logging centralizada com Rich.
Uso: from src.utils.logger import get_logger
     log = get_logger(__name__)
"""
import logging
import sys
from pathlib import Path

from rich.logging import RichHandler


def get_logger(name: str, level: str | None = None, log_file: Path | None = None) -> logging.Logger:
    """Retorna logger configurado com Rich (console) + arquivo."""
    from config.settings import LOG_LEVEL, LOG_FILE

    _level = getattr(logging, (level or LOG_LEVEL).upper(), logging.INFO)
    _file = log_file or LOG_FILE

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(_level)

    # Console handler (Rich)
    console = RichHandler(
        rich_tracebacks=True,
        show_path=False,
        markup=True,
    )
    console.setLevel(_level)
    fmt_console = logging.Formatter("%(message)s", datefmt="[%X]")
    console.setFormatter(fmt_console)
    logger.addHandler(console)

    # File handler
    _file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(_file, encoding="utf-8")
    fh.setLevel(_level)
    fmt_file = logging.Formatter(
        "%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fmt_file)
    logger.addHandler(fh)

    return logger
