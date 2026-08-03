import random
import re
import time
from datetime import datetime, timedelta, timezone
import hashlib

_RE_HASHTAG = re.compile(r'#(\w+)', re.UNICODE)
_RE_MENTION = re.compile(r'@(\w+)', re.UNICODE)

_PT_PARTICLES = frozenset({
    'de', 'da', 'do', 'dos', 'das', 'em', 'no', 'na', 'nos', 'nas',
    'por', 'com', 'que', 'e', 'a', 'o', 'ao', 'aos',
    'um', 'uma', 'para', 'pro', 'pra', 'is', 'the', 'in', 'and',
})
_RE_PROPER_NAME = re.compile(
    r'^[A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][a-záéíóúàâêôãõç]+'
    r'(?:\s+[A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][a-záéíóúàâêôãõç]+){1,3}$'
)


def looks_like_name(text: str) -> bool:
    """Heuristic: is this a personal name rather than real content?"""
    t = text.strip()
    if not (5 <= len(t) <= 45):
        return False
    if any(c in t for c in '!?.,;:()[]{}/@#%0123456789'):
        return False
    words = t.split()
    if not (2 <= len(words) <= 4):
        return False
    if any(w in _PT_PARTICLES for w in words):
        return False
    return bool(_RE_PROPER_NAME.match(t))


def extract_hashtags(text: str) -> list:
    return _RE_HASHTAG.findall(text or '')


def extract_mentions(text: str) -> list:
    return _RE_MENTION.findall(text or '')


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def stable_hash(*parts, length=16):
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:length]


def sleep_seconds(seconds):
    time.sleep(seconds)


def sleep_random(min_seconds, max_seconds):
    time.sleep(random.uniform(min_seconds, max_seconds))


def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_filename(value):
    value = value.lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value)
    value = value.strip("_")
    return value[:120] or "facebook_page"


_PT_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
_PT_MONTHS["mar\u00e7o"] = 3


def _coerce_base_datetime(base=None):
    if base is None:
        return datetime.now(timezone.utc)
    if isinstance(base, datetime):
        return base if base.tzinfo else base.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(base).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def parse_facebook_datetime(value, collected_at=None):
    """Best-effort conversion of Facebook relative/absolute labels to ISO UTC.

    The original label should still be stored; relative labels are approximate
    because Facebook does not expose the exact timestamp in every layout.
    """
    if not value:
        return None

    raw = clean_text(str(value))
    if not raw:
        return None

    base = _coerce_base_datetime(collected_at)
    lower = raw.lower()

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass

    compact = re.fullmatch(r"(\d+)\s*([smhdwy])", lower)
    if compact:
        amount = int(compact.group(1))
        unit = compact.group(2)
        seconds = {
            "s": amount,
            "m": amount * 60,
            "h": amount * 3600,
            "d": amount * 86400,
            "w": amount * 7 * 86400,
            "y": amount * 365 * 86400,
        }[unit]
        return (base - timedelta(seconds=seconds)).isoformat()

    if lower in ("hoje", "today"):
        return base.isoformat()
    if lower in ("ontem", "yesterday"):
        return (base - timedelta(days=1)).isoformat()

    # Proper UTF-8 Portuguese labels. Kept before the legacy fallback below,
    # which still handles previously mojibake-collected labels.
    pt_rel = re.search(
        r"(?:ha|h\u00e1)?\s*"
        r"(\d+|um|uma|dois|duas|tres|tr\u00eas|quatro|cinco)\s+"
        r"(segundo|minuto|hora|dia|semana|mes|m\u00eas|ano)s?",
        lower,
    )
    if pt_rel:
        amount_raw, unit = pt_rel.groups()
        pt_numbers = {
            "um": 1, "uma": 1, "dois": 2, "duas": 2,
            "tres": 3, "tr\u00eas": 3, "quatro": 4, "cinco": 5,
        }
        amount = pt_numbers.get(amount_raw, int(amount_raw) if amount_raw.isdigit() else 1)
        unit_days = {
            "segundo": 1 / 86400,
            "minuto": 1 / 1440,
            "hora": 1 / 24,
            "dia": 1,
            "semana": 7,
            "mes": 30,
            "m\u00eas": 30,
            "ano": 365,
        }[unit]
        return (base - timedelta(days=amount * unit_days)).isoformat()

    pt_abs_utf8 = re.search(
        r"(\d{1,2})\s+de\s+([a-z\u00e7]+)"
        r"(?:\s+de\s+(\d{4}))?"
        r"(?:\s+(?:as|\u00e0s)\s+(\d{1,2}):(\d{2}))?",
        lower,
    )
    if pt_abs_utf8:
        day, month_name, year, hour, minute = pt_abs_utf8.groups()
        month = _PT_MONTHS.get(month_name)
        if month:
            dt = datetime(
                int(year or base.year),
                month,
                int(day),
                int(hour or 0),
                int(minute or 0),
                tzinfo=timezone.utc,
            )
            return dt.isoformat()

    number_words = {
        "a": 1,
        "an": 1,
        "um": 1,
        "uma": 1,
        "dois": 2,
        "duas": 2,
        "tres": 3,
        "três": 3,
        "quatro": 4,
        "cinco": 5,
    }
    rel = re.search(
        r"(?:ha|há)?\s*(\d+|a|an|um|uma|dois|duas|tres|três|quatro|cinco)\s+"
        r"(second|minute|hour|day|week|month|year|segundo|minuto|hora|dia|semana|mes|mês|ano)s?"
        r"(?:\s+ago)?",
        lower,
    )
    if rel:
        amount_raw, unit = rel.groups()
        amount = number_words.get(amount_raw, None)
        if amount is None:
            amount = int(amount_raw)
        unit_days = {
            "second": 1 / 86400,
            "segundo": 1 / 86400,
            "minute": 1 / 1440,
            "minuto": 1 / 1440,
            "hour": 1 / 24,
            "hora": 1 / 24,
            "day": 1,
            "dia": 1,
            "week": 7,
            "semana": 7,
            "month": 30,
            "mes": 30,
            "mês": 30,
            "year": 365,
            "ano": 365,
        }[unit]
        return (base - timedelta(days=amount * unit_days)).isoformat()

    pt_abs = re.search(
        r"(\d{1,2})\s+de\s+([a-zç]+)(?:\s+de\s+(\d{4}))?(?:\s+(?:as|às)\s+(\d{1,2}):(\d{2}))?",
        lower,
    )
    if pt_abs:
        day, month_name, year, hour, minute = pt_abs.groups()
        month = _PT_MONTHS.get(month_name)
        if month:
            dt = datetime(
                int(year or base.year),
                month,
                int(day),
                int(hour or 0),
                int(minute or 0),
                tzinfo=timezone.utc,
            )
            return dt.isoformat()

    en_formats = [
        "%b %d, %Y at %I:%M %p",
        "%B %d, %Y at %I:%M %p",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d",
        "%B %d",
    ]
    for fmt in en_formats:
        try:
            dt = datetime.strptime(raw, fmt)
            if "%Y" not in fmt:
                dt = dt.replace(year=base.year)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    return None


def parse_count(text):
    """Parse a human-readable count string into an integer.

    Handles: '45 pessoas', '1,2 mil curtidas', '5 mil', '2.3K', '1.234'
    Returns None if no number is found.
    """
    if not text:
        return None

    t = text.strip().lower()

    # "1,2 mil" or "1.2 mil"
    m = re.search(r"([\d]+[,.][\d]+)\s*mil", t)
    if m:
        try:
            return int(float(m.group(1).replace(",", ".")) * 1000)
        except (ValueError, OverflowError):
            pass

    # "5 mil"
    m = re.search(r"(\d+)\s*mil\b", t)
    if m:
        try:
            return int(m.group(1)) * 1000
        except ValueError:
            pass

    # "2,3K" or "2.3K"
    m = re.search(r"([\d]+[,.][\d]+)\s*k\b", t)
    if m:
        try:
            return int(float(m.group(1).replace(",", ".")) * 1000)
        except (ValueError, OverflowError):
            pass

    # "5K"
    m = re.search(r"(\d+)\s*k\b", t)
    if m:
        try:
            return int(m.group(1)) * 1000
        except ValueError:
            pass

    # Plain number, stripping dot/comma separators ("1.234" or "1,234" → 1234)
    digits_only = re.sub(r"[.,]", "", text)
    m = re.search(r"\d+", digits_only)
    if m:
        try:
            return int(m.group())
        except ValueError:
            pass

    return None
