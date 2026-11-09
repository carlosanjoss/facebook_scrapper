import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
SESSIONS_DIR = DATA_DIR / "sessions"
STATE_DIR = DATA_DIR / "state"
LOG_DIR = DATA_DIR / "logs"
SCREENSHOTS_DIR = LOG_DIR / "screenshots"
ARTIFACTS_DIR = LOG_DIR / "artifacts"
REPORTS_DIR = DATA_DIR / "reports"
EXPORTS_DIR = DATA_DIR / "exports"

LINKS_FILE = INPUT_DIR / "links.txt"
USER_DATA_DIR = SESSIONS_DIR / "facebook_chrome_profile"
LOCK_FILE = STATE_DIR / "collector.lock"

# Browser
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SLOW_MO = int(os.getenv("SLOW_MO", "80"))
BROWSER_EXECUTABLE_PATH = os.getenv("BROWSER_EXECUTABLE_PATH") or None

# Timing (segundos)
PAGE_WAIT_MIN = float(os.getenv("PAGE_WAIT_MIN", "4"))
PAGE_WAIT_MAX = float(os.getenv("PAGE_WAIT_MAX", "7"))
SCROLL_DELAY_SECONDS = float(os.getenv("SCROLL_DELAY_SECONDS", "3"))
CLICK_DELAY_MIN = float(os.getenv("CLICK_DELAY_MIN", "0.8"))
CLICK_DELAY_MAX = float(os.getenv("CLICK_DELAY_MAX", "2.0"))

# Scroll contínuo: para quando a altura não cresce por N rounds consecutivos
MAX_SCROLL_ATTEMPTS = int(os.getenv("MAX_SCROLL_ATTEMPTS", "200"))
STABLE_SCROLL_ROUNDS = int(os.getenv("STABLE_SCROLL_ROUNDS", "3"))

# Limites de coleta
MAX_POSTS_PER_PAGE = int(os.getenv("MAX_POSTS_PER_PAGE", "100"))
MAX_COMMENT_EXPAND_PER_ARTICLE = int(os.getenv("MAX_COMMENT_EXPAND_PER_ARTICLE", "50"))
MAX_REPLY_EXPAND_PER_COMMENT = int(os.getenv("MAX_REPLY_EXPAND_PER_COMMENT", "20"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY_SECONDS = int(os.getenv("RETRY_DELAY_SECONDS", "10"))
SKIP_RECENT_EMPTY_HOURS = int(os.getenv("SKIP_RECENT_EMPTY_HOURS", "24"))
RESTART_BROWSER_EVERY_POSTS = int(os.getenv("RESTART_BROWSER_EVERY_POSTS", "25"))
COLLECT_ALBUM_PHOTOS = os.getenv("COLLECT_ALBUM_PHOTOS", "true").lower() == "true"

# Modo contínuo: volta ao primeiro link após terminar todos
CONTINUOUS_MODE = os.getenv("CONTINUOUS_MODE", "true").lower() == "true"
CONTINUOUS_INTERVAL_MINUTES = int(os.getenv("CONTINUOUS_INTERVAL_MINUTES", "60"))

# Proxy (opcional)
PROXY_SERVER = os.getenv("PROXY_SERVER")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
