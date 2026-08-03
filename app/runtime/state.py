from app.config import STATE_DIR

_STATE_FILE = STATE_DIR / "collected_urls.txt"


def load_collected_urls():
    if not _STATE_FILE.exists():
        return set()
    with open(_STATE_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def mark_url_collected(url):
    with open(_STATE_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")
