import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.config import (
    CONTINUOUS_MODE,
    LINKS_FILE,
    MAX_POSTS_PER_PAGE,
    RESTART_BROWSER_EVERY_POSTS,
    SKIP_RECENT_EMPTY_HOURS,
)

logger = logging.getLogger("facebook_scraper")


@dataclass
class RuntimeOptions:
    continuous_mode: bool
    max_pages_per_cycle: int
    max_posts_per_page: int
    skip_recent_empty_hours: int
    collect_comments: bool
    export_after_cycle: bool
    restart_browser_every_posts: int
    processed_posts_since_restart: int = 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Facebook scraper collector")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one collection cycle and exit, ignoring CONTINUOUS_MODE.",
    )
    parser.add_argument(
        "--limit-posts",
        type=int,
        default=None,
        help="Limit posts processed per page in this run. Use 0 for no limit.",
    )
    parser.add_argument(
        "--limit-pages",
        type=int,
        default=0,
        help="Limit source URLs processed in this run. Use 0 for no limit.",
    )
    parser.add_argument(
        "--skip-recent-empty-hours",
        type=int,
        default=SKIP_RECENT_EMPTY_HOURS,
        help="Skip posts with 0 comments collected less than N hours ago.",
    )
    parser.add_argument(
        "--no-comments",
        action="store_true",
        help="Collect post metadata only. Useful for quick smoke tests.",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Do not refresh JSONL/CSV exports after the cycle.",
    )
    parser.add_argument(
        "--restart-browser-every-posts",
        type=int,
        default=RESTART_BROWSER_EVERY_POSTS,
        help="Restart the browser profile after N processed posts. Use 0 to disable.",
    )

    args = parser.parse_args(argv)

    if args.limit_posts is not None and args.limit_posts < 0:
        parser.error("--limit-posts must be >= 0")
    if args.limit_pages < 0:
        parser.error("--limit-pages must be >= 0")
    if args.skip_recent_empty_hours < 0:
        parser.error("--skip-recent-empty-hours must be >= 0")
    if args.restart_browser_every_posts < 0:
        parser.error("--restart-browser-every-posts must be >= 0")

    return args


def build_runtime_options(args) -> RuntimeOptions:
    return RuntimeOptions(
        continuous_mode=CONTINUOUS_MODE and not args.once,
        max_pages_per_cycle=args.limit_pages,
        max_posts_per_page=(
            args.limit_posts if args.limit_posts is not None else MAX_POSTS_PER_PAGE
        ),
        skip_recent_empty_hours=args.skip_recent_empty_hours,
        collect_comments=not args.no_comments,
        export_after_cycle=not args.no_export,
        restart_browser_every_posts=args.restart_browser_every_posts,
    )


def load_links(path=LINKS_FILE):
    """Load, validate, normalize and deduplicate Facebook URLs."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Arquivo de links não encontrado: {path}. "
            "Crie o arquivo e adicione uma URL do Facebook por linha."
        )

    links = []
    seen = set()
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for line_number, raw_line in enumerate(lines, 1):
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue

        if "://" not in value:
            value = f"https://{value}"

        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        is_facebook = hostname == "facebook.com" or hostname.endswith(".facebook.com")
        if parsed.scheme.lower() not in {"http", "https"} or not is_facebook:
            logger.warning(
                f"Linha {line_number} ignorada em {path}: "
                f"URL do Facebook inválida ({raw_line.strip()})"
            )
            continue

        if value not in seen:
            seen.add(value)
            links.append(value)

    return links
