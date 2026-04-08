"""Logging-Setup mit Rich für schöne Terminal-Ausgabe."""

import logging

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
})

console = Console(theme=custom_theme)


def setup_logger(name: str = "scraper", level: str = "INFO") -> logging.Logger:
    """Erstellt einen konfigurierten Logger mit Rich-Handler."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    if not logger.handlers:
        handler = RichHandler(
            console=console,
            show_path=False,
            rich_tracebacks=True,
            markup=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

    return logger


log = setup_logger()
