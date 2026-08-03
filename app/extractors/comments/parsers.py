import re

from app.utils import clean_text, parse_count, looks_like_name

_RE_COMMENT_AUTHOR = re.compile(
    r'^(?:Comment by|Comentário de) (.+?)(?=\s+(?:\d|\ba\s+\w|\ban?\s+\w|há\s))'
)
_RE_REPLY_AUTHOR = re.compile(
    r'^(?:Reply by|Resposta de) (.+?) (?:to |para )'
)
_RE_DATE = re.compile(
    r'(\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago'
    r'|a\s+(?:second|minute|hour|day|week|month|year)s?\s+ago'
    r'|há\s+(?:\d+|um|uma|dois|duas|três|quatro|cinco)\s+\w+'
    r'|\d{1,2}\s+de\s+\w+(?:\s+de\s+\d{4})?(?:\s+[àa]s\s+\d{2}:\d{2})?'
    r'|\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+\d{1,2}(?:,?\s*\d{4})?(?:\s+at\s+\d{1,2}:\d{2}\s*[ap]m)?'
    r'|\d+\s*[smhdwy](?=\s|$)'
    r'|ontem|yesterday|hoje|today'
    r')',
    re.IGNORECASE
)

_REACTION_MAP = [
    (re.compile(r'(\d+)\s*(?:curtida[s]?|like[s]?)', re.I),   'like'),
    (re.compile(r'(\d+)\s*(?:am(?:ei|o)|love[s]?)',  re.I),   'love'),
    (re.compile(r'(\d+)\s*(?:haha|risos?)',           re.I),   'haha'),
    (re.compile(r'(\d+)\s*(?:uau|wow)',               re.I),   'wow'),
    (re.compile(r'(\d+)\s*(?:triste[s]?|sad)',        re.I),   'sad'),
    (re.compile(r'(\d+)\s*(?:raiva|ang(?:ry|ered?))', re.I),   'angry'),
]

_NOISE = {
    "like", "reply", "share", "comment", "curtir", "responder",
    "compartilhar", "comentar", "haha", "love", "wow", "sad", "angry",
}


def _parse_reactions(label: str):
    if not label:
        return None
    detail = {}
    for pattern, key in _REACTION_MAP:
        m = pattern.search(label)
        if m:
            value = parse_count(m.group(1))
            if value is not None:
                detail[key] = value
    total = parse_count(label)
    if total is not None:
        detail['total'] = total
    elif detail:
        detail['total'] = sum(v for k, v in detail.items() if k != 'total')
    return detail or None


def _parse_author(aria_label):
    if not aria_label:
        return None
    m_utf8 = re.match(
        r"^(?:Comment by|Coment\u00e1rio de) (.+?)(?=\s+(?:\d|\ba\s+\w|\ban?\s+\w|h\u00e1\s))",
        aria_label,
    )
    if m_utf8:
        return m_utf8.group(1).strip()
    m = _RE_COMMENT_AUTHOR.match(aria_label) or _RE_REPLY_AUTHOR.match(aria_label)
    return m.group(1).strip() if m else None


def _parse_date(aria_label, date_label=""):
    for src in (date_label, aria_label):
        if not src:
            continue
        m_utf8 = re.search(
            r"(\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago"
            r"|a\s+(?:second|minute|hour|day|week|month|year)s?\s+ago"
            r"|h\u00e1\s+(?:\d+|um|uma|dois|duas|tr\u00eas|tres|quatro|cinco)\s+\w+"
            r"|\d{1,2}\s+de\s+\w+(?:\s+de\s+\d{4})?(?:\s+(?:as|\u00e0s)\s+\d{2}:\d{2})?"
            r"|\d+\s*[smhdwy](?=\s|$)"
            r"|ontem|yesterday|hoje|today)",
            src,
            re.IGNORECASE,
        )
        if m_utf8:
            return m_utf8.group(1)
        m = _RE_DATE.search(src)
        if m:
            return m.group(1)
    return None


def _pick_text(dir_texts, author, post_text=""):
    """Return the best candidate for comment body from dir_texts."""
    post_stripped = (post_text or "").strip()
    for t in dir_texts:
        if not t:
            continue
        if t == author:
            continue
        tl = t.lower().strip()
        if tl in _NOISE:
            continue
        if _RE_DATE.fullmatch(tl.strip()):
            continue
        if looks_like_name(t):
            continue
        if post_stripped and t.strip() == post_stripped:
            continue
        if len(t) >= 2:
            return t
    return ""
