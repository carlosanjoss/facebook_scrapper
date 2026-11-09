import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.config import (
    BROWSER_EXECUTABLE_PATH,
    HEADLESS,
    PROXY_PASSWORD,
    PROXY_SERVER,
    PROXY_USERNAME,
    SLOW_MO,
    USER_DATA_DIR,
)


def resolve_browser_executable(configured_path=None):
    if configured_path:
        path = Path(configured_path).expanduser()
        if not path.is_file():
            raise RuntimeError(f"BROWSER_EXECUTABLE_PATH nao existe: {path}")
        return str(path)

    candidates = [
        Path(os.environ.get("PROGRAMFILES", ""))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", ""))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", ""))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", ""))
        / "Microsoft/Edge/Application/msedge.exe",
    ]
    return next((str(path) for path in candidates if path.is_file()), None)


def start_browser(headless=None):
    playwright = sync_playwright().start()
    executable_path = resolve_browser_executable(BROWSER_EXECUTABLE_PATH)

    proxy = None
    if PROXY_SERVER:
        proxy = {"server": PROXY_SERVER}
        if PROXY_USERNAME:
            proxy["username"] = PROXY_USERNAME
        if PROXY_PASSWORD:
            proxy["password"] = PROXY_PASSWORD

    launch_options = dict(
        user_data_dir=str(USER_DATA_DIR),
        headless=HEADLESS if headless is None else headless,
        slow_mo=SLOW_MO,
        viewport={"width": 1366, "height": 768},
        locale="pt-BR",
        proxy=proxy,
        args=[
            # Facebook occasionally negotiates HTTP/3/QUIC and then leaves the
            # page stuck on its splash screen (or fails with
            # ERR_CONNECTION_RESET). Force the stable TCP/TLS path.
            "--disable-quic",
            "--disable-notifications",
            "--start-maximized",
            "--disable-dev-shm-usage",  # evita crash no Docker (/dev/shm limitado a 64MB)
        ],
    )
    if executable_path:
        launch_options["executable_path"] = executable_path

    context = playwright.chromium.launch_persistent_context(**launch_options)

    page = context.pages[0] if context.pages else context.new_page()
    return playwright, context, page


def close_browser(playwright, context):
    context.close()
    playwright.stop()
