import logging
from logging.handlers import RotatingFileHandler

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

from app.config import LOG_DIR

_theme = Theme({
    "log.time":              "dim",
    "logging.level.info":    "default",
    "logging.level.warning": "yellow",
    "logging.level.error":   "bold red",
})

console = Console(highlight=False, theme=_theme)

_ICONS = {
    logging.WARNING:  "▲ ",
    logging.ERROR:    "✗ ",
    logging.CRITICAL: "‼ ",
}


class _IconFormatter(logging.Formatter):
    def format(self, record):
        icon = _ICONS.get(record.levelno, "")
        if icon:
            record = logging.makeLogRecord(record.__dict__)
            record.msg = icon + str(record.msg)
            record.args = ()
        return super().format(record)


def _setup() -> logging.Logger:
    log = logging.getLogger("facebook_scraper")
    if log.handlers:
        return log

    log.setLevel(logging.DEBUG)

    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=False,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
        omit_repeated_times=False,
        log_time_format="[%H:%M:%S]",
        level=logging.INFO,
    )
    rich_handler.setFormatter(_IconFormatter())
    log.addHandler(rich_handler)

    file_handler = RotatingFileHandler(
        LOG_DIR / "scraper.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    log.addHandler(file_handler)

    return log


logger = _setup()
