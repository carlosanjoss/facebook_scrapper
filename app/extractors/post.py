import re
from urllib.parse import urlparse, urlencode, parse_qs

from app.config import CLICK_DELAY_MIN, CLICK_DELAY_MAX, COLLECT_ALBUM_PHOTOS
from app.utils import (
    clean_text, parse_count, sleep_random, sleep_seconds,
    extract_hashtags, extract_mentions, looks_like_name,
)

_SEE_MORE_SKIP = ("explore", "notification", "curtida", "like", "reaction")


def expand_see_more_on_post_page(page):
    """Click 'Ver mais'/'See more' to expand truncated post text.

    Called while on the individual post page — safe, won't navigate away.
    Scoped to the post article (not comments).
    """
    try:
        post_article = None
        articles = page.locator('[role="article"]')
        for i in range(min(articles.count(), 5)):
            art = articles.nth(i)
            label = art.get_attribute("aria-label") or ""
            if "Comment by" not in label and "Reply by" not in label:
                post_article = art
                break
    except Exception:
        post_article = None

    container = post_article if post_article else page.locator('[role="main"]').first

    for _round in range(5):
        clicked = 0
        for text in ["Ver mais", "See more"]:
            try:
                btns = container.get_by_text(text, exact=True)
                count = btns.count()
                for i in range(min(count, 8)):
                    try:
                        btn = btns.nth(i)
                        label = (btn.get_attribute("aria-label") or "").lower()
                        if any(k in label for k in _SEE_MORE_SKIP):
                            continue
                        btn.click(timeout=800)
                        clicked += 1
                        sleep_random(CLICK_DELAY_MIN, CLICK_DELAY_MAX)
                    except Exception:
                        pass
            except Exception:
                pass
        if not clicked:
            break


def _extract_text_from_article(article):
    try:
        dir_autos = article.locator('[dir="auto"]')
        count = dir_autos.count()
        for i in range(min(count, 15)):
            text = clean_text(dir_autos.nth(i).inner_text(timeout=500))
            if len(text) > 5:
                return text
    except Exception:
        pass
    try:
        return clean_text(article.inner_text(timeout=3000))
    except Exception:
        return ""


def _extract_author_from_article(article):
    for selector in ["h1 a", "h2 a", "h3 a", "h4 a", "h1", "h2", "h3", "h4"]:
        try:
            el = article.locator(selector).first
            text = clean_text(el.inner_text(timeout=800))
            if text and len(text) < 120:
                return text
        except Exception:
            continue
    return None


def _extract_date_from_article(article):
    try:
        abbr = article.locator("abbr[title]").first
        title = abbr.get_attribute("title", timeout=800)
        if title:
            return title
    except Exception:
        pass
    try:
        time_el = article.locator("time[datetime]").first
        dt = time_el.get_attribute("datetime", timeout=500)
        if dt:
            return dt
    except Exception:
        pass
    try:
        links = article.locator("a[aria-label]")
        for i in range(min(links.count(), 6)):
            lbl = links.nth(i).get_attribute("aria-label") or ""
            if 2 <= len(lbl) <= 60 and re.search(r'\d', lbl):
                return lbl
    except Exception:
        pass
    return None


def _get_aria_label(article, selectors):
    for selector in selectors:
        try:
            elements = article.locator(selector)
            count = elements.count()
            for i in range(min(count, 3)):
                label = elements.nth(i).get_attribute("aria-label", timeout=500)
                if label:
                    return label
        except Exception:
            continue
    return None


_REACTION_MAP_POST = [
    (re.compile(r'(\d[\d,.]*)\s*(?:curtida[s]?|like[s]?)',          re.I), 'like'),
    (re.compile(r'(\d[\d,.]*)\s*(?:am(?:ei|o)|love[s]?)',           re.I), 'love'),
    (re.compile(r'(\d[\d,.]*)\s*(?:haha|risos?)',                   re.I), 'haha'),
    (re.compile(r'(\d[\d,.]*)\s*(?:uau|wow)',                       re.I), 'wow'),
    (re.compile(r'(\d[\d,.]*)\s*(?:triste[s]?|sad)',                re.I), 'sad'),
    (re.compile(r'(\d[\d,.]*)\s*(?:raiva|ang(?:ry|ered?))',         re.I), 'angry'),
    (re.compile(r'(?:like[s]?|curtir|curtida[s]?)\s*:\s*(\d[\d,.]*)',  re.I), 'like'),
    (re.compile(r'(?:love|amor|amei)\s*:\s*(\d[\d,.]*)',               re.I), 'love'),
    (re.compile(r'haha\s*:\s*(\d[\d,.]*)',                             re.I), 'haha'),
    (re.compile(r'(?:wow|uau)\s*:\s*(\d[\d,.]*)',                      re.I), 'wow'),
    (re.compile(r'(?:sad|triste[s]?|tristeza)\s*:\s*(\d[\d,.]*)',      re.I), 'sad'),
    (re.compile(r'(?:angry|raiva|grr)\s*:\s*(\d[\d,.]*)',              re.I), 'angry'),
    (re.compile(r'care\s*:\s*(\d[\d,.]*)',                             re.I), 'care'),
]


def _parse_count_str(s: str) -> int:
    value = parse_count(s)
    if value is None:
        raise ValueError(f"invalid count: {s!r}")
    return value


def _parse_reaction_type_labels(labels: list) -> dict:
    detail = {}
    for label in (labels or []):
        for pattern, key in _REACTION_MAP_POST:
            m = pattern.search(label)
            if m:
                val = _parse_count_str(m.group(1))
                detail[key] = detail.get(key, 0) + val
                break
    if detail:
        detail['total'] = sum(v for k, v in detail.items() if k != 'total')
    return detail


def _parse_reactions_detail(label: str):
    if not label:
        return None
    detail = {}
    for pattern, key in _REACTION_MAP_POST:
        m = pattern.search(label)
        if m:
            detail[key] = _parse_count_str(m.group(1))
    total = parse_count(label)
    if total is not None:
        detail['total'] = total
    elif detail:
        detail['total'] = sum(v for k, v in detail.items() if k != 'total')
    return detail or None


def _extract_reactions(article):
    label = _get_aria_label(article, [
        '[aria-label*="reação"]',   '[aria-label*="reaction"]',
        '[aria-label*="reagiram"]', '[aria-label*="reagiu"]',
        '[aria-label*="reacted"]',  '[aria-label*="pessoas"]',
        '[aria-label*="curtida"]',  '[aria-label*="Curtir"]',
        '[aria-label*="curtidas"]', '[aria-label*="likes"]',
        '[aria-label*="people"]',
    ])
    return parse_count(label), label


def _extract_shares(article):
    label = _get_aria_label(article, [
        '[aria-label*="compartilhamento"]', '[aria-label*="share"]',
    ])
    return parse_count(label)


_JS_POST_METADATA = """() => {
    const allArts = new Set(Array.from(document.querySelectorAll('[role="article"]')));
    const commentArts = new Set(Array.from(allArts).filter(a => {
        const l = a.getAttribute('aria-label') || '';
        return l.startsWith('Comment by') || l.startsWith('Reply by') ||
               l.startsWith('Comentário de') || l.startsWith('Resposta de');
    }));

    const inCommentArt = el => {
        let p = el.parentElement;
        while (p) { if (commentArts.has(p)) return true; p = p.parentElement; }
        return false;
    };

    let reactionsLabel = '';
    const rxTotal = ['reagiram','reagiu','reacted','pessoas','people',
                     'curtidas','likes','curtida','curtir','like','reação','reaction'];
    const reactEl = Array.from(document.querySelectorAll('[aria-label]'))
        .filter(el => !inCommentArt(el))
        .find(el => {
            const l = (el.getAttribute('aria-label') || '').toLowerCase();
            return /\\d/.test(l) && rxTotal.some(k => l.includes(k));
        });
    if (reactEl) reactionsLabel = reactEl.getAttribute('aria-label') || '';

    const rxTypeRe = /^(Like|Love|Haha|Wow|Sad|Angry|Care|Curtir|Curtida|Amei|Amor|Haha|Uau|Triste|Tristeza|Raiva|Grr)/i;
    const reactionTypeLabels = Array.from(document.querySelectorAll('[aria-label]'))
        .filter(el => !inCommentArt(el))
        .map(el => el.getAttribute('aria-label') || '')
        .filter(l => rxTypeRe.test(l) && /\\d/.test(l));

    let dateStr = '';
    const relTimeRe = /^(?:(?:a |an |há\\s+)?\\d*\\s*(?:second|minute|hour|day|week|month|year|hora|dia|semana|mês|ano|minuto|segundo)s?(?:\\s+ago)?|\\d+\\s*[smhd])$/i;
    const relEl = Array.from(document.querySelectorAll('[aria-label]'))
        .filter(el => !inCommentArt(el))
        .find(el => relTimeRe.test((el.getAttribute('aria-label') || '').trim()));
    if (relEl) { dateStr = relEl.getAttribute('aria-label').trim(); }

    if (!dateStr) {
        const dateCandidates = [
            ...Array.from(document.querySelectorAll('abbr[title]'))
                .filter(el => !inCommentArt(el))
                .map(el => ({ el, val: el.getAttribute('title') || '' })),
            ...Array.from(document.querySelectorAll('time[datetime]'))
                .filter(el => !inCommentArt(el))
                .map(el => ({ el, val: el.getAttribute('datetime') || el.innerText || '' })),
            ...Array.from(document.querySelectorAll('span[title]'))
                .filter(el => !inCommentArt(el))
                .map(el => ({ el, val: el.getAttribute('title') || '' })),
            ...Array.from(document.querySelectorAll('a[aria-label]'))
                .filter(el => !inCommentArt(el))
                .map(el => ({ el, val: el.getAttribute('aria-label') || '' })),
        ];
        const dateMatch = dateCandidates.find(({ val }) =>
            val.length > 1 && val.length < 100 &&
            (/\\d/.test(val) || /ontem|yesterday|hoje|today/i.test(val))
        );
        if (dateMatch) dateStr = dateMatch.val;
    }

    let sharesLabel = '';
    const shEl = Array.from(document.querySelectorAll('[aria-label]'))
        .filter(el => !inCommentArt(el))
        .find(el => {
            const l = (el.getAttribute('aria-label') || '').toLowerCase();
            return /\\d/.test(l) && (l.includes('compartilhamento') || l.includes('share'));
        });
    if (shEl) sharesLabel = shEl.getAttribute('aria-label') || '';

    return { reactionsLabel, reactionTypeLabels, dateStr, sharesLabel };
}"""


_JS_POST_EVIDENCE = """() => {
    const uniq = (items, keyFn) => {
        const seen = new Set();
        const out = [];
        for (const item of items) {
            const key = keyFn(item);
            if (!key || seen.has(key)) continue;
            seen.add(key);
            out.push(item);
        }
        return out;
    };

    const rawLabels = Array.from(document.querySelectorAll('[aria-label]'))
        .map(el => el.getAttribute('aria-label') || '')
        .filter(Boolean)
        .slice(0, 400);

    const textLabels = Array.from(document.querySelectorAll('[role="button"], [role="link"], a, span, div'))
        .map(el => (el.innerText || el.textContent || '').trim())
        .filter(t => t && t.length < 120 && /\\d/.test(t))
        .slice(0, 400);

    const allLabels = rawLabels.concat(textLabels);
    const commentsLabel = allLabels.find(l => /\\d/.test(l) && /comment|coment/i.test(l)) || '';
    const sharesLabel = allLabels.find(l => /\\d/.test(l) && /share|compartilh/i.test(l)) || '';

    const images = uniq(Array.from(document.querySelectorAll('img')).map(img => ({
        type: 'image',
        src: img.currentSrc || img.src || '',
        alt: img.alt || '',
        width: img.naturalWidth || null,
        height: img.naturalHeight || null,
    })).filter(x =>
        x.src &&
        !x.src.startsWith('data:') &&
        !(x.width > 0 && x.width < 50) &&
        !(x.height > 0 && x.height < 50)
    ), x => x.src).slice(0, 30);

    const videos = uniq(Array.from(document.querySelectorAll('video')).map(video => ({
        type: 'video',
        src: video.currentSrc || video.src || '',
        poster: video.poster || '',
        duration: Number.isFinite(video.duration) ? video.duration : null,
    })).filter(x => x.src || x.poster), x => x.src || x.poster).slice(0, 15);

    const externalLinks = uniq(Array.from(document.querySelectorAll('a[href]')).map(a => {
        let href = a.href || '';
        let host = '';
        try { host = new URL(href).hostname; } catch(e) {}
        return { href, host, text: (a.innerText || '').trim().slice(0, 120) };
    }).filter(x => x.href && x.host && !x.host.includes('facebook.com')), x => x.href).slice(0, 30);

    return {
        observedLabels: allLabels.slice(0, 120),
        commentsLabel,
        sharesLabel,
        media: images.concat(videos),
        externalLinks,
    };
}"""


_JS_POST_DATE_CANDIDATES = """() => {
    const allArts = new Set(Array.from(document.querySelectorAll('[role="article"]')));
    const commentArts = new Set(Array.from(allArts).filter(a => {
        const l = a.getAttribute('aria-label') || '';
        return /^Comment by |^Reply by |^Coment\\u00e1rio de |^Resposta de /i.test(l);
    }));
    const inComment = el => {
        let p = el.parentElement;
        while (p) {
            if (commentArts.has(p)) return true;
            p = p.parentElement;
        }
        return false;
    };
    const out = [];
    const push = val => {
        val = (val || '').trim();
        if (!val || val.length > 120) return;
        if (out.indexOf(val) === -1) out.push(val);
    };
    const rel = /^(\\d+\\s*[smhdwy]|\\d+\\s+(second|minute|hour|day|week|month|year)s?\\s+ago|a\\s+(second|minute|hour|day|week|month|year)\\s+ago|h\\u00e1\\s+\\d+\\s*\\w+|ontem|yesterday|hoje|today)$/i;
    const absPt = /\\d{1,2}\\s+de\\s+\\w+(\\s+de\\s+\\d{4})?(\\s+(as|\\u00e0s)\\s+\\d{1,2}:\\d{2})?/i;

    Array.from(document.querySelectorAll('abbr[title], time[datetime], span[title], a[aria-label], [aria-label]'))
        .filter(el => !inComment(el))
        .forEach(el => {
            const vals = [
                el.getAttribute('title'),
                el.getAttribute('datetime'),
                el.getAttribute('aria-label'),
                el.innerText,
            ];
            vals.forEach(v => {
                v = (v || '').trim();
                if (rel.test(v) || absPt.test(v)) push(v);
            });
        });
    return out;
}"""


_JS_POST_TEXT = """() => {
    const all = Array.from(document.querySelectorAll('[role="article"]'));
    const allSet = new Set(all);

    const outer = all.filter(art => {
        let p = art.parentElement;
        while (p) { if (allSet.has(p)) return false; p = p.parentElement; }
        return true;
    });

    const PRECEDING = 2;

    const results = [];

    if (outer.length === 0) {
        const containers = ['[role="main"]', '[role="dialog"]', '[role="complementary"]'];
        for (const sel of containers) {
            const el = document.querySelector(sel);
            if (!el) continue;
            const texts = Array.from(el.querySelectorAll('[dir="auto"]'))
                .map(e => (e.innerText || '').trim())
                .filter(t => t.length > 5);
            if (texts.length > 0) {
                results.push({ texts: texts.slice(0, 8), author: '', date: '' });
                break;
            }
        }
        return results;
    }

    for (const art of outer) {
        const nested = Array.from(art.querySelectorAll('[role="article"]'));
        const firstNested = nested[0] || null;

        const texts = Array.from(art.querySelectorAll('[dir="auto"]'))
            .filter(el => {
                if (!firstNested) return true;
                if (!(firstNested.compareDocumentPosition(el) & PRECEDING)) return false;
                let p = el.parentElement;
                while (p && p !== art) {
                    if (Array.from(p.children).some(
                        c => c.getAttribute && c.getAttribute('role') === 'article'
                    )) return false;
                    p = p.parentElement;
                }
                return true;
            })
            .map(el => (el.innerText || '').trim())
            .filter(t => t.length > 5);

        let author = '';
        const authorEl = art.querySelector('h1 a, h2 a, h3 a, strong a, b a, h4 a');
        if (authorEl) author = (authorEl.innerText || '').trim();

        let date = '';
        const abbrEl = art.querySelector('abbr[title]');
        if (abbrEl) {
            date = abbrEl.getAttribute('title') || '';
        }
        if (!date) {
            const timeEl = art.querySelector('time[datetime]');
            if (timeEl) date = timeEl.getAttribute('datetime') || (timeEl.innerText || '').trim();
        }
        if (!date) {
            const tsLink = Array.from(art.querySelectorAll('a[aria-label]')).find(el => {
                const l = (el.getAttribute('aria-label') || '').trim();
                return l.length > 1 && l.length < 60 && (/\\d/.test(l) || /ontem|yesterday/i.test(l));
            });
            if (tsLink) date = tsLink.getAttribute('aria-label') || '';
        }

        results.push({ texts: texts.slice(0, 8), author, date });
    }
    return results;
}"""

_NOISE_TEXT = {
    "like", "reply", "share", "comment", "curtir", "responder",
    "compartilhar", "comentar", "editar", "edit",
}

_UI_NOISE = frozenset({
    "facebook", "home", "início", "messenger",
    "notificações", "notifications", "marketplace",
    "groups", "grupos", "gaming", "watch", "create", "criar",
    "menu", "search", "pesquisar", "events", "eventos",
    "feeds", "profile", "perfil", "settings", "configurações",
    "log in", "sign up", "reels", "ver mais", "see more",
    "ver menos", "see less", "ocultar", "hide", "denunciar", "report",
    "curtir", "like", "comentar", "comment", "compartilhar", "share",
    "responder", "reply", "salvar", "save",
})


def _filter_observed(labels):
    out = []
    for label in (labels or []):
        ll = label.strip()
        if not ll or len(ll) < 3 or len(ll) > 120:
            continue
        if ll.lower() in _UI_NOISE:
            continue
        out.append(ll)
    return out


def _pick_post_text(texts, author):
    for t in texts:
        tl = t.lower().strip()
        if tl in _NOISE_TEXT:
            continue
        if t == author:
            continue
        if len(tl) < 5:
            continue
        if looks_like_name(t):
            continue
        return t
    return ""


_WAIT_FOR_DATE_JS = """() => {
    const allArts = new Set(Array.from(document.querySelectorAll('[role="article"]')));
    const commentArts = new Set(Array.from(allArts).filter(a => {
        const l = a.getAttribute('aria-label') || '';
        return l.startsWith('Comment by') || l.startsWith('Reply by') ||
               l.startsWith('Coment\\u00e1rio de') || l.startsWith('Resposta de');
    }));
    const inC = el => { let p = el.parentElement; while(p){if(commentArts.has(p))return true;p=p.parentElement;}return false; };
    const re = /^(\\d+\\s*[smhdwy]|\\d+\\s+\\w+\\s+ago|a\\s+\\w+\\s+ago|h[a\\u00e1]\\s+\\d+\\s*\\w*|ontem|yesterday|hoje|today)$/i;
    return Array.from(document.querySelectorAll('[aria-label]'))
        .filter(el => !inC(el))
        .some(el => re.test((el.getAttribute('aria-label')||'').trim()));
}"""


_REL_TS_RE = re.compile(
    r'^(\d+\s*[smhdwy]|\d+\s+\w+\s+ago|a\s+\w+\s+ago|h[aá]\s+\d+\s*\w*'
    r'|ontem|yesterday|hoje|today|\d+\s*(?:hora|dia|semana|mês|mes|ano|min|seg)s?)$',
    re.IGNORECASE,
)


def _hover_for_absolute_date(page) -> str | None:
    """
    Hover over the post's relative timestamp link to trigger Facebook's tooltip,
    which contains the absolute date (e.g. "12 de março de 2026 às 15:30").
    Returns the tooltip text or None.
    """
    try:
        # Find all aria-label links outside comment articles
        links = page.locator(
            ':not([aria-label*="Comment by"]):not([aria-label*="Reply by"]) a[aria-label]'
        )
        count = min(links.count(), 20)
        ts_link = None
        for i in range(count):
            lbl = (links.nth(i).get_attribute("aria-label") or "").strip()
            if _REL_TS_RE.match(lbl):
                ts_link = links.nth(i)
                break

        if ts_link is None:
            return None

        ts_link.hover(timeout=2000)
        # Facebook renders the tooltip in a [role="tooltip"] element
        tooltip = page.locator('[role="tooltip"]')
        tooltip.wait_for(state="visible", timeout=3000)
        text = (tooltip.inner_text(timeout=1000) or "").strip()
        return text if len(text) > 3 else None
    except Exception:
        return None


def snapshot_page_metadata(page) -> dict:
    """Evaluate _JS_POST_METADATA and return the raw dict.

    Call this BEFORE expand_see_more so that date/reaction-type elements,
    which Facebook removes from the DOM after 'See more' is clicked,
    are captured in their original state.
    """
    try:
        page.wait_for_function(_WAIT_FOR_DATE_JS, timeout=12000)
    except Exception:
        pass
    try:
        return page.evaluate(_JS_POST_METADATA) or {}
    except Exception:
        return {}


def collect_post_data_from_page(page, post_url, index, pre_meta=None):
    """Collect post metadata from an individual post page.

    pre_meta: result of snapshot_page_metadata() called BEFORE expand_see_more.
    If not supplied, _JS_POST_METADATA is evaluated now (may miss date/reactions
    if DOM was already mutated by expand_see_more).
    """
    text = author = date = None
    reactions = shares = None
    reactions_label = None
    reactions_detail_override = None
    evidence = {}

    meta = pre_meta if pre_meta is not None else snapshot_page_metadata(page)
    try:
        date = meta.get("dateStr") or None
        r_label = meta.get("reactionsLabel") or ""
        reactions = parse_count(r_label)
        reactions_label = r_label or None
        shares = parse_count(meta.get("sharesLabel") or "") or None
        type_labels = meta.get("reactionTypeLabels") or []
        if type_labels:
            detail_from_types = _parse_reaction_type_labels(type_labels)
            if detail_from_types:
                reactions_detail_override = detail_from_types
                if not reactions:
                    reactions = detail_from_types.get('total')
    except Exception:
        pass

    try:
        evidence = page.evaluate(_JS_POST_EVIDENCE) or {}
        if not shares:
            shares = parse_count(evidence.get("sharesLabel") or "") or None
    except Exception:
        evidence = {}

    try:
        results = page.evaluate(_JS_POST_TEXT) or []
        for r in results:
            author = r.get("author") or None
            date   = date or r.get("date") or None
            text   = _pick_post_text(r.get("texts", []), author)
            if text:
                break
    except Exception:
        pass

    try:
        articles = page.locator('[role="article"]')
        count = articles.count()
        for i in range(min(count, 8)):
            article = articles.nth(i)
            label = article.get_attribute("aria-label") or ""
            if "Comment by" in label or "Reply by" in label:
                continue
            if not text:
                text   = _extract_text_from_article(article)
                author = author or _extract_author_from_article(article)
                date   = date   or _extract_date_from_article(article)
            loc_reactions, loc_label = _extract_reactions(article)
            if loc_reactions and not reactions_detail_override:
                reactions = loc_reactions
                reactions_label = loc_label
            if not shares:
                shares = _extract_shares(article)
            break
    except Exception:
        pass

    if not date:
        try:
            late_meta = page.evaluate(_JS_POST_METADATA) or {}
            date = late_meta.get("dateStr") or None
        except Exception:
            pass

    if not date:
        try:
            candidates = page.evaluate(_JS_POST_DATE_CANDIDATES) or []
            if candidates:
                date = candidates[0]
        except Exception:
            pass

    # Last resort: hover over the timestamp link to trigger the absolute-date tooltip
    if not date:
        date = _hover_for_absolute_date(page)

    body = text or ""
    observed_comments = parse_count(evidence.get("commentsLabel") or "")
    return {
        "post_index": index,
        "post_url": post_url,
        "author": author,
        "created_at": date,
        "text": body,
        "hashtags": extract_hashtags(body),
        "mentions": extract_mentions(body),
        "reactions_count": reactions,
        "reactions_detail": reactions_detail_override or _parse_reactions_detail(reactions_label),
        "shares_count": shares,
        "observed_counts": {
            "comments": observed_comments,
            "reactions": reactions,
            "shares": shares,
        },
        "raw_labels": {
            "reactions": reactions_label,
            "comments": evidence.get("commentsLabel") or None,
            "shares": evidence.get("sharesLabel") or meta.get("sharesLabel") or None,
            "observed": _filter_observed(evidence.get("observedLabels", [])),
        },
        "media": evidence.get("media", []),
        "external_links": evidence.get("externalLinks", []),
        "comments_count": None,
        "comments": [],
    }
