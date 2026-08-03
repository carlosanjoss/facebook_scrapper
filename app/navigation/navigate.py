import re

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
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Pause the reel video immediately after landing — before Facebook can
        # auto-advance to an unrelated reel during the sleep below.
        if is_reel:
            try:
                page.evaluate(_JS_PAUSE_VIDEO)
            except Exception:
                pass

        sleep_random(PAGE_WAIT_MIN, PAGE_WAIT_MAX)

        if verify_on_target_page(page, url):
            return True

        logger.warning(
            f"Redirecionado para {page.url} — "
            f"tentando novamente ({attempt + 1}/3)"
        )
        sleep_seconds(2)

    logger.error(f"Não foi possível manter a navegação em: {url}")
    return False
