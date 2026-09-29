from playwright.sync_api import sync_playwright

from app.config import (
    HEADLESS,
    PROXY_PASSWORD,
    PROXY_SERVER,
    PROXY_USERNAME,
    SLOW_MO,
    USER_DATA_DIR,
)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def start_browser(headless=None):
    playwright = sync_playwright().start()

    proxy = None
    if PROXY_SERVER:
        proxy = {"server": PROXY_SERVER}
        if PROXY_USERNAME:
            proxy["username"] = PROXY_USERNAME
        if PROXY_PASSWORD:
            proxy["password"] = PROXY_PASSWORD

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=HEADLESS if headless is None else headless,
        slow_mo=SLOW_MO,
        viewport={"width": 1366, "height": 768},
        locale="pt-BR",
        user_agent=_USER_AGENT,
        proxy=proxy,
        args=[
            # Facebook occasionally negotiates HTTP/3/QUIC and then leaves the
            # page stuck on its splash screen (or fails with
            # ERR_CONNECTION_RESET). Force the stable TCP/TLS path.
            "--disable-quic",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-notifications",
            "--start-maximized",
            "--disable-dev-shm-usage",  # evita crash no Docker (/dev/shm limitado a 64MB)
        ],
    )

    page = context.pages[0] if context.pages else context.new_page()
    return playwright, context, page


def close_browser(playwright, context):
    context.close()
    playwright.stop()
