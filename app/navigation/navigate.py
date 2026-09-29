import re

from playwright.sync_api import Error as PlaywrightError

from app.config import PAGE_WAIT_MIN, PAGE_WAIT_MAX
from app.logger import logger
from app.utils import sleep_random, sleep_seconds

_JS_PAUSE_VIDEO = """() => {
    document.querySelectorAll('video').forEach(v => {
        try { v.pause(); } catch(e) {}
        v.autoplay = false;
        v.loop = false;
    });
}"""


def _wait_for_rendered_content(page, timeout=30000):
    """Wait until Facebook has rendered more than its empty splash shell."""
    try:
        page.wait_for_function(
            """() => {
                const body = document.body;
                if (!body) return false;
                if (document.querySelector('[role="article"]')) return true;
                return (body.innerText || '').trim().length > 0;
            }""",
            timeout=timeout,
        )
        return True
    except PlaywrightError:
        return False


def verify_on_target_page(page, expected_url):
    """Return False if Facebook silently redirected away from the target URL."""
    current = page.url.lower().rstrip("/")

    home_variants = {
        "https://www.facebook.com",
        "https://m.facebook.com",
        "https://web.facebook.com",
        "http://www.facebook.com",
    }
    if current in home_variants:
        return False

    expected_lower = expected_url.lower()

    # For reels, verify the specific reel ID — Facebook auto-advances to unrelated reels
    # so checking only that "/reel/" appears in the expected URL is not enough.
    if '/reel/' in expected_lower:
        m = re.search(r'/reel/(\d+)', expected_lower)
        if m:
            return m.group(1) in current
        return '/reel/' in current

    if any(p in expected_lower for p in ["/posts/", "story_fbid", "/photo/", "/videos/", "/watch/"]):
        return True

    parts = expected_lower.rstrip("/").split("facebook.com/")
    if len(parts) > 1:
        slug = parts[1].split("/")[0].split("?")[0]
        if slug and slug not in current:
            return False

    return True


def _navigate_pfbid(page, url):
    """Navigate to a /posts/pfbid URL by simulating a click from the parent page.

    Facebook pfbid posts redirect to homepage on direct navigation.
    Going to the page first and using window.location.assign() from that context
    (or clicking the actual link) mimics how a real user reaches the post.
    """
    try:
        base = url.split("/posts/")[0]
    except Exception:
        return False

    try:
        page.goto(base, wait_until="domcontentloaded", timeout=30000)
        sleep_seconds(2)
    except Exception:
        return False

    try:
        pfbid = url.split("/posts/")[1].split("?")[0]
        link = page.locator(f'a[href*="{pfbid}"]').first
        if link.count() > 0:
            link.scroll_into_view_if_needed(timeout=5000)
            sleep_seconds(0.5)
            link.click(timeout=5000)
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            return verify_on_target_page(page, url)
    except Exception:
        pass

    try:
        page.evaluate(f"window.location.assign('{url}')")
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        sleep_seconds(2)
        return verify_on_target_page(page, url)
    except Exception:
        pass

    return False


def navigate_to(page, url):
    """Navigate and retry if Facebook redirects away from the target."""
    if "/posts/pfbid" in url:
        if _navigate_pfbid(page, url):
            return True
        logger.error(f"Não foi possível acessar post pfbid: {url}")
        return False

    is_reel = '/reel/' in url.lower()

    for attempt in range(3):
        try:
            # "domcontentloaded" can wait forever when a Facebook subresource
            # stalls. "commit" plus an explicit rendered-content check is both
            # stricter (it rejects the splash shell) and more reliable.
            page.goto(url, wait_until="commit", timeout=60000)
        except PlaywrightError as exc:
            logger.warning(
                f"Falha transitória ao abrir {url} "
                f"({attempt + 1}/3): {str(exc).splitlines()[0]}"
            )

        rendered = _wait_for_rendered_content(page)

        # Pause the reel video immediately after landing — before Facebook can
        # auto-advance to an unrelated reel during the sleep below.
        if is_reel:
            try:
                page.evaluate(_JS_PAUSE_VIDEO)
            except Exception:
                pass

        if rendered:
            sleep_random(PAGE_WAIT_MIN, PAGE_WAIT_MAX)

        if rendered and verify_on_target_page(page, url):
            return True

        if not rendered:
            logger.warning(
                "Facebook não terminou de renderizar a página "
                f"— tentando novamente ({attempt + 1}/3)"
            )
        else:
            logger.warning(
                f"Redirecionado para {page.url} — "
                f"tentando novamente ({attempt + 1}/3)"
            )
        sleep_seconds(2)

    logger.error(f"Não foi possível manter a navegação em: {url}")
    return False
