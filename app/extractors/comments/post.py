import time

from app.config import CLICK_DELAY_MIN, CLICK_DELAY_MAX, MAX_COMMENT_EXPAND_PER_ARTICLE
from app.logger import logger
from app.utils import sleep_random

_JS_OPEN_SORT_DROPDOWN = """() => {
    const LABELS = ['most relevant', 'mais relevantes', 'mais relevante', 'relevantes',
                    'top comments', 'melhores comentários', 'melhores'];
    let btn = null;
    document.querySelectorAll('[role="button"]').forEach(el => {
        if (btn) return;
        const txt = (el.innerText || el.textContent || '').toLowerCase().trim();
        if (LABELS.some(l => txt === l || txt.startsWith(l))) btn = el;
    });
    if (!btn) return 0;
    btn.click();
    return 1;
}"""

_JS_SELECT_ALL_COMMENTS = """() => {
    const LABELS = ['all comments', 'todos os comentários', 'todos os comentarios',
                    'all', 'todos'];
    let found = 0;
    document.querySelectorAll('[role="menuitem"],[role="option"],[role="listitem"],[tabindex]').forEach(el => {
        if (found) return;
        const txt = (el.innerText || el.textContent || '').toLowerCase().trim();
        if (LABELS.some(l => txt === l || txt.includes(l))) { el.click(); found = 1; }
    });
    return found;
}"""

_JS_EXPAND_SEE_MORE = """() => {
    let c = 0;
    const SM = ['see more', 'ver mais', 'xem thêm', 'xem them'];
    function vis(e) { return e.offsetWidth > 0 || e.offsetHeight > 0; }
    document.querySelectorAll('[role="button"],span[role="button"],a,span').forEach(el => {
        if (!el || !vis(el)) return;
        const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
        if (SM.indexOf(txt) === -1) return;
        let p = el.parentElement, inside = false;
        for (let d = 0; d < 8 && p; d++) {
            if (p.getAttribute && p.getAttribute('role') === 'article') { inside = true; break; }
            p = p.parentElement;
        }
        if (inside) { try { el.click(); c++; } catch(e) {} }
    });
    return c;
}"""

_JS_LOAD_MORE = """() => {
    const LM = [
        'ver mais comentários','ver mais respostas','ver comentários anteriores',
        'ver todas as respostas',
        'view more comments','view more replies','more comments','more replies',
        'see more comments','see more replies','previous comments','previous replies',
        'xem thêm bình luận','xem thêm phản hồi','xem thêm trả lời',
    ];
    // Matches "ver mais 26 comentários", "view more 10 replies", etc.
    const LM_RE = [
        /ver mais \\d+\\s*coment/i,
        /ver mais \\d+\\s*respost/i,
        /view more \\d+\\s*comment/i,
        /view more \\d+\\s*repl/i,
        /see more \\d+\\s*comment/i,
        /see more \\d+\\s*repl/i,
        /mais \\d+\\s*coment/i,
        /mais \\d+\\s*respost/i,
    ];
    const EX = ['ocultar','hide','ẩn','fechar','close'];
    const SK = ['like','reply','share','comment','thích','trả lời','chia sẻ','bình luận'];
    let c = 0;
    const seen = new Set();
    document.querySelectorAll('[role="button"],[role="link"],a').forEach(el => {
        const raw = (el.innerText || el.getAttribute('aria-label') || '').trim();
        const txt = raw.toLowerCase();
        if (!txt || txt.length > 140) return;
        if (SK.indexOf(txt) !== -1) return;
        if (EX.some(e => txt.includes(e))) return;
        const matches = LM.some(k => txt.includes(k)) || LM_RE.some(r => r.test(txt));
        if (!matches) return;
        const key = raw + '|' + el.tagName + '|' + (el.className || '').substring(0, 30);
        if (seen.has(key)) return;
        seen.add(key);
        try {
            el.scrollIntoView({block:'nearest', behavior:'instant'});
            el.click(); c++;
        } catch(e) {}
    });
    return c;
}"""

_JS_EXTRACT_COMMENTS = """() => {
    const all = Array.from(document.querySelectorAll('[role="article"]'));
    const allSet = new Set(all);

    const nested = all.filter(art => {
        let p = art.parentElement;
        while (p) {
            if (allSet.has(p)) return true;
            p = p.parentElement;
        }
        return false;
    });

    const source = nested.length > 0 ? nested : all;

    return source.map(art => {
        const aria = art.getAttribute('aria-label') || '';
        const childArts = Array.from(art.querySelectorAll('[role="article"]'));

        const notInChild = el => !childArts.some(c => c !== art && c.contains(el));

        const dirTexts = Array.from(art.querySelectorAll('[dir="auto"]'))
            .filter(notInChild)
            .map(el => (el.innerText || '').trim())
            .filter(t => t.length > 0);

        const reactionEl = Array.from(art.querySelectorAll('[aria-label]'))
            .filter(notInChild)
            .find(el => {
                const l = (el.getAttribute('aria-label') || '').toLowerCase();
                return /\\d/.test(l) && (
                    l.includes('reação') || l.includes('reaction') ||
                    l.includes('curtida') || l.includes('curtir') ||
                    l.includes('amor') || l.includes('love') ||
                    l.includes('raiva') || l.includes('angry') ||
                    l.includes('haha') || l.includes('wow') || l.includes('uau')
                );
            });
        const reactionsLabel = reactionEl ? (reactionEl.getAttribute('aria-label') || '') : '';

        const dateEl = Array.from(art.querySelectorAll('a[aria-label], abbr[title], time[datetime]'))
            .filter(notInChild)
            .find(el => {
                const l = (el.getAttribute('aria-label') || el.getAttribute('title') ||
                           el.getAttribute('datetime') || '').trim();
                return l.length > 1 && l.length < 60 && (
                    /\\d/.test(l) || /ontem|yesterday|hoje|today/i.test(l) ||
                    /há\\s/i.test(l) || /ago/i.test(l)
                );
            });
        const dateLabel = dateEl
            ? (dateEl.getAttribute('aria-label') || dateEl.getAttribute('title') ||
               dateEl.getAttribute('datetime') || '')
            : '';

        const attachments = Array.from(art.querySelectorAll('img, video, a[href]'))
            .filter(notInChild)
            .map(el => ({
                tag: el.tagName.toLowerCase(),
                src: el.currentSrc || el.src || el.href || '',
                alt: el.alt || '',
                text: (el.innerText || '').trim().slice(0, 120),
            }))
            .filter(x => x.src || x.alt || x.text)
            .slice(0, 10);

        return {
            aria_label: aria,
            dir_texts: dirTexts.slice(0, 10),
            inner_text: (art.innerText || '').substring(0, 400),
            reactions_label: reactionsLabel,
            date_label: dateLabel,
            attachments,
        };
    });
}"""


def _set_all_comments_mode(page):
    """Switch to 'All Comments' view (instead of 'Most Relevant')."""
    try:
        opened = page.evaluate(_JS_OPEN_SORT_DROPDOWN) or 0
        if not opened:
            return False
        sleep_random(CLICK_DELAY_MIN, CLICK_DELAY_MAX)
        selected = page.evaluate(_JS_SELECT_ALL_COMMENTS) or 0
        if selected:
            sleep_random(CLICK_DELAY_MIN * 2, CLICK_DELAY_MAX * 2)
        return bool(selected)
    except Exception:
        return False


_JS_COUNT_ARTICLES = "() => document.querySelectorAll('[role=\"article\"]').length"


def _expand_and_load(page, rounds=None):
    """Click all visible 'load more' and 'see more' buttons, waiting for DOM updates."""
    if rounds is None:
        rounds = MAX_COMMENT_EXPAND_PER_ARTICLE
    consecutive_empty = 0
    for _ in range(rounds):
        try:
            prev = page.evaluate(_JS_COUNT_ARTICLES) or 0
        except Exception:
            prev = 0

        expanded = page.evaluate(_JS_EXPAND_SEE_MORE) or 0
        loaded   = page.evaluate(_JS_LOAD_MORE) or 0

        if expanded or loaded:
            consecutive_empty = 0
            # Poll until new articles appear (up to 5 s) instead of fixed sleep
            for _ in range(10):
                time.sleep(0.5)
                try:
                    if (page.evaluate(_JS_COUNT_ARTICLES) or 0) > prev:
                        break
                except Exception:
                    break
        else:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                break
            # One retry after a brief pause — the button may be mid-render
            time.sleep(0.8)


def load_post_comments(page):
    """Scroll and expand until no new articles appear for 3 consecutive rounds."""
    from app.browser import scroll_page
    _set_all_comments_mode(page)
    scroll_page(page)

    stable_rounds = 0
    prev_count = 0

    for _ in range(25):
        try:
            before = page.evaluate(_JS_COUNT_ARTICLES) or 0
        except Exception:
            before = prev_count

        _expand_and_load(page)
        scroll_page(page)

        try:
            after = page.evaluate(_JS_COUNT_ARTICLES) or 0
        except Exception:
            after = before

        if after > prev_count:
            stable_rounds = 0
            prev_count = after
        else:
            stable_rounds += 1
            if stable_rounds >= 3:
                break

        time.sleep(0.5)

    # Final sweep for anything missed
    _expand_and_load(page, rounds=MAX_COMMENT_EXPAND_PER_ARTICLE)
