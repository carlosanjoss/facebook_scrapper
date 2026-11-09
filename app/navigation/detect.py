import json
from datetime import datetime

from app.config import ARTIFACTS_DIR, SCREENSHOTS_DIR
from app.logger import logger
from app.utils import now_iso, safe_filename


def detect_block_or_checkpoint(page):
    url = page.url.lower()

    if any(t in url for t in ["checkpoint", "captcha", "security", "login", "two_step_verification"]):
        return True

    try:
        body_text = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        body_text = ""

    return any(t in body_text for t in [
        "captcha", "checkpoint",
        "confirme que é você", "confirm it's you",
        "security check", "verificação de segurança",
    ])


def _is_direct_content_url(url: str) -> bool:
    """Return True if the URL points to a single post/reel/video, not a page feed.

    Direct content URLs skip feed scrolling — the URL itself is the post to collect.
    Handles:
      /reel/ID                      → Facebook Reel
      /photo/?fbid=...              → individual photo
      /slug/posts/ID                → post permalink
      /slug/videos/ID               → video permalink
      /watch/?v=ID                  → Watch video
      /story.php?story_fbid=...     → story permalink
    Page feeds (/slug with no content type) return False.
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.lower().rstrip('/')

        if path.startswith('/reel/'):
            return True
        if path.startswith(('/share/r/', '/share/v/', '/share/p/')):
            return True
        if path == '/photo':
            return True
        if path in ('/watch', '/watch/') or path.startswith('/watch/'):
            return bool(parsed.query)
        if path == '/story.php':
            return True
        parts = [p for p in path.split('/') if p]
        if len(parts) >= 2 and parts[1] in ('posts', 'videos'):
            return True
        return False
    except Exception:
        return False


def save_error_screenshot(page, url, attempt):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOTS_DIR / f"{safe_filename(url)}_attempt{attempt}_{ts}.png"
        page.screenshot(path=str(path), full_page=False)
        logger.debug(f"Screenshot de erro salvo: {path.name}")
    except Exception:
        pass


def save_error_artifacts(page, url, stage, error=None):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{safe_filename(url)}_{safe_filename(stage)}_{ts}"
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        screenshot = ARTIFACTS_DIR / f"{base}.png"
        html = ARTIFACTS_DIR / f"{base}.html"
        meta = ARTIFACTS_DIR / f"{base}.json"

        try:
            page.screenshot(path=str(screenshot), full_page=False)
        except Exception:
            screenshot = None
        try:
            html.write_text(page.content(), encoding="utf-8")
        except Exception:
            html = None

        payload = {
            "url": url,
            "stage": stage,
            "page_url": getattr(page, "url", None),
            "error": str(error) if error else None,
            "created_at": now_iso(),
            "screenshot": str(screenshot) if screenshot else None,
            "html": str(html) if html else None,
        }
        meta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug(f"Artefatos de erro salvos: {meta.name}")
    except Exception:
        pass
