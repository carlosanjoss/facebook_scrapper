import time

from app.logger import logger
from app.extractors.comments.post import _set_all_comments_mode

_JS_CLICK_REEL_COMMENTS = """() => {
    const btn = document.querySelector('[aria-label="Comment"]');
    if (btn) { btn.click(); return 'aria-exact:Comment'; }
    const btnPt = document.querySelector('[aria-label="Comentário"]');
    if (btnPt) { btnPt.click(); return 'aria-exact:Comentário'; }
    const BUBBLE = 'M12 .5C18.351.5';
    for (const svg of document.querySelectorAll('svg')) {
        const p = svg.querySelector('path');
        if (!p || !(p.getAttribute('d') || '').startsWith(BUBBLE)) continue;
        let el = svg;
        for (let i = 0; i < 6 && el; i++, el = el.parentElement) {
            try { el.click(); return 'svg-bubble-' + i; } catch(e) {}
        }
    }
    return null;
}"""

_JS_SCROLL_REEL_PANEL = """(step) => {
    const link = document.querySelector('a[href*="comment_id"]');
    if (link) {
        let el = link.parentElement;
        for (let i = 0; i < 50 && el; i++, el = el.parentElement) {
            const s = window.getComputedStyle(el);
            const ov = (s.overflow || '') + ' ' + (s.overflowY || '');
            if ((ov.includes('scroll') || ov.includes('auto')) && el.scrollHeight > el.clientHeight + 50) {
                el.scrollTop += step;
                return { target: 'comment-panel', depth: i, links: document.querySelectorAll('a[href*="comment_id"]').length, h: el.scrollHeight };
            }
        }
    }
    let best = null, bestScore = 0;
    document.querySelectorAll('div').forEach(el => {
        const s = window.getComputedStyle(el);
        const ov = (s.overflow || '') + ' ' + (s.overflowY || '');
        if (!(ov.includes('scroll') || ov.includes('auto'))) return;
        if (el.scrollHeight <= el.clientHeight + 50) return;
        const score = el.querySelectorAll('a[href*="comment_id"]').length * 10 + el.querySelectorAll('[role="article"]').length;
        if (score > bestScore) { bestScore = score; best = el; }
    });
    if (best && bestScore > 0) {
        best.scrollTop += step;
        return { target: 'best-div', score: bestScore, links: document.querySelectorAll('a[href*="comment_id"]').length, h: best.scrollHeight };
    }
    let count = 0;
    document.querySelectorAll('div').forEach(el => {
        const s = window.getComputedStyle(el);
        const ov = (s.overflow || '') + ' ' + (s.overflowY || '');
        if ((ov.includes('scroll') || ov.includes('auto')) && el.scrollHeight > el.clientHeight + 50) {
            el.scrollTop += step;
            count++;
        }
    });
    return { target: 'all', count };
}"""

_JS_LOAD_MORE_REEL = """() => {
    const phrases = [
        'view more comments', 'ver mais comentários', 'ver mais respostas',
        'view more replies', 'carregar mais comentários', 'previous comments',
        'ver comentários anteriores',
    ];
    let clicked = 0;
    document.querySelectorAll('span,div').forEach(el => {
        if (el.children.length > 0) return;
        const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
        if (!phrases.includes(txt)) return;
        let target = el.parentElement || el;
        for (let i = 0; i < 4 && target; i++, target = target.parentElement) {
            try { target.click(); clicked++; break; } catch(e) {}
        }
    });
    return clicked;
}"""

_JS_EXTRACT_REEL_COMMENTS = """() => {
    const results = [];
    const seen = new Set();

    const links = Array.from(document.querySelectorAll('a[href*="comment_id"]'));
    for (const link of links) {
        const href = link.getAttribute('href') || '';
        const m = href.match(/comment_id=([^&\\s]+)/);
        if (!m) continue;
        const cid = decodeURIComponent(m[1]);
        if (seen.has(cid)) continue;
        seen.add(cid);

        const author = (link.innerText || '').trim();

        let container = link.parentElement;
        for (let i = 0; i < 12 && container; i++) {
            const inner = (container.innerText || '').trim();
            const hasLink = container.querySelector('a[href*="comment_id"]');
            const textEls = container.querySelectorAll('[dir="auto"]');
            if (hasLink && textEls.length >= 1 && inner.length > 3 && inner.length < 1500) break;
            container = container.parentElement;
        }

        const dirEls = Array.from((container || link.parentElement).querySelectorAll('[dir="auto"]'));
        const texts = dirEls
            .filter(el => !el.querySelector('a[href*="comment_id"]'))
            .map(el => (el.innerText || '').trim())
            .filter(t => t.length > 0);

        const dateEl = (container || link.parentElement).querySelector('a[aria-label]');
        const dateLabel = dateEl ? (dateEl.getAttribute('aria-label') || '').trim() : '';

        const rxEl = (container || link.parentElement).querySelector(
            '[aria-label*="reação"],[aria-label*="curtida"],[aria-label*="reaction"],[aria-label*="like"]'
        );
        const rxLabel = rxEl ? (rxEl.getAttribute('aria-label') || '') : '';

        if (author || texts.length > 0) {
            results.push({
                aria_label: '',
                author,
                dir_texts: texts.slice(0, 10),
                inner_text: ((container || link.parentElement).innerText || '').substring(0, 400),
                reactions_label: rxLabel,
                date_label: dateLabel,
                _comment_id: cid,
            });
        }
    }
    return results;
}"""

_JS_REEL_DOM_PROBE = """() => {
    const arts = Array.from(document.querySelectorAll('[role="article"]'));
    return {
        articles: arts.length,
        article_labels: arts.map(a => a.getAttribute('aria-label') || '').slice(0, 30),
        listitems: document.querySelectorAll('[role="listitem"]').length,
        feed_items: document.querySelectorAll('[role="feed"] > *').length,
        has_complementary: !!document.querySelector('[role="complementary"]'),
        has_dialog: !!document.querySelector('[role="dialog"]'),
        complementary_arts: document.querySelector('[role="complementary"]')
            ? document.querySelector('[role="complementary"]').querySelectorAll('[role="article"]').length
            : 0,
        comment_aria_labels: Array.from(document.querySelectorAll('[aria-label]'))
            .map(el => el.getAttribute('aria-label') || '')
            .filter(l => /comment|comentario|comentário/i.test(l))
            .slice(0, 20),
        scrollable_containers: Array.from(document.querySelectorAll('div'))
            .filter(el => {
                const s = window.getComputedStyle(el);
                const ov = (s.overflow||'') + ' ' + (s.overflowY||'');
                return (ov.includes('scroll')||ov.includes('auto')) && el.scrollHeight > el.clientHeight + 50;
            })
            .map(el => ({
                role: el.getAttribute('role') || '',
                arts: el.querySelectorAll('[role="article"]').length,
                listitems: el.querySelectorAll('[role="listitem"]').length,
                h: el.scrollHeight,
            }))
            .sort((a, b) => (b.arts + b.listitems) - (a.arts + a.listitems))
            .slice(0, 8),
    };
}"""

_JS_EXTRACT_REEL_FALLBACK = """() => {
    const extractEl = (el) => {
        const childArts = Array.from(el.querySelectorAll('[role="article"]'));
        const notInChild = x => !childArts.some(c => c !== el && c.contains(x));

        const dirTexts = Array.from(el.querySelectorAll('[dir="auto"]'))
            .filter(notInChild)
            .map(e => (e.innerText || '').trim())
            .filter(t => t.length > 0);

        const reactionEl = Array.from(el.querySelectorAll('[aria-label]'))
            .filter(notInChild)
            .find(e => {
                const l = (e.getAttribute('aria-label') || '').toLowerCase();
                return /\\d/.test(l) && (l.includes('curtida') || l.includes('like') ||
                    l.includes('reação') || l.includes('reaction') || l.includes('amor') || l.includes('love'));
            });

        const dateEl = Array.from(el.querySelectorAll('a[aria-label],abbr[title],time[datetime]'))
            .filter(notInChild)
            .find(e => {
                const l = (e.getAttribute('aria-label') || e.getAttribute('title') ||
                           e.getAttribute('datetime') || '').trim();
                return l.length > 1 && l.length < 60 &&
                    (/\\d/.test(l) || /ontem|yesterday|hoje|today/i.test(l) || /ago/i.test(l) || /h[aá]\\s/i.test(l));
            });

        return {
            aria_label: el.getAttribute('aria-label') || '',
            dir_texts: dirTexts.slice(0, 10),
            inner_text: (el.innerText || '').substring(0, 400),
            reactions_label: reactionEl ? (reactionEl.getAttribute('aria-label') || '') : '',
            date_label: dateEl
                ? (dateEl.getAttribute('aria-label') || dateEl.getAttribute('title') ||
                   dateEl.getAttribute('datetime') || '')
                : '',
            attachments: [],
        };
    };

    const comp = document.querySelector('[role="complementary"]');
    if (comp) {
        const compArts = Array.from(comp.querySelectorAll('[role="article"]'));
        if (compArts.length > 0) return compArts.map(extractEl);
    }

    const allArts = Array.from(document.querySelectorAll('[role="article"]'));
    const looseComment = allArts.filter(a => {
        const l = (a.getAttribute('aria-label') || '').toLowerCase();
        return l.includes('comment') || l.includes('comentar') || l.includes('resposta') || l.includes('reply');
    });
    if (looseComment.length > 0) return looseComment.map(extractEl);

    const listItems = Array.from(document.querySelectorAll('[role="listitem"]'))
        .filter(el => {
            const texts = Array.from(el.querySelectorAll('[dir="auto"]'))
                .map(e => (e.innerText || '').trim()).filter(t => t.length > 2);
            return texts.length >= 1;
        });
    if (listItems.length > 0) return listItems.map(extractEl);

    const contentArts = allArts.filter(a => {
        const texts = Array.from(a.querySelectorAll('[dir="auto"]'))
            .map(e => (e.innerText || '').trim()).filter(t => t.length > 3);
        const hasDate = Array.from(a.querySelectorAll('a[aria-label],abbr[title],time[datetime]'))
            .some(e => {
                const l = (e.getAttribute('aria-label') || e.getAttribute('title') || '').trim();
                return l.length > 1 && l.length < 60 && /\\d/.test(l);
            });
        return texts.length >= 1 && hasDate;
    });
    return contentArts.map(extractEl);
}"""


def _reel_pause_video(page):
    """Pause all videos and remove autoplay to prevent reel from advancing."""
    try:
        page.evaluate("""() => {
            document.querySelectorAll('video').forEach(v => {
                try { v.pause(); } catch(e) {}
                v.autoplay = false;
                v.loop = false;
            });
        }""")
    except Exception:
        pass


def _reel_click_comments(page):
    """Open the comments panel on a reel page using JS .click()."""
    try:
        result = page.evaluate(_JS_CLICK_REEL_COMMENTS)
        if result:
            logger.debug(f"[REEL] ícone clicado: {result}")
            return True
    except Exception:
        pass
    logger.debug("[REEL] ícone de comentários não encontrado")
    return False


def load_reel_comments(page):
    """Reel flow — pause video, open comments panel, scroll until all comments loaded."""
    # Step 1: pause video immediately to prevent auto-advance
    _reel_pause_video(page)
    time.sleep(1.0)

    # Step 2: click the comment icon
    for attempt in range(4):
        if _reel_click_comments(page):
            break
        time.sleep(1.5)
        _reel_pause_video(page)

    # Step 3: wait for comments panel to open
    time.sleep(3.0)
    _reel_pause_video(page)

    # Step 4: switch to All Comments sort
    _set_all_comments_mode(page)
    time.sleep(1.0)

    # Step 5: scroll comment panel until all comments loaded.
    # Stop only when BOTH conditions hold for 6 consecutive rounds:
    #   (a) comment_id link count unchanged, AND (b) no "View more" button clicked.
    prev_count = 0
    stable_rounds = 0

    for round_ in range(300):
        _reel_pause_video(page)

        try:
            page.evaluate(_JS_SCROLL_REEL_PANEL, 800)
        except Exception:
            pass
        time.sleep(0.8)

        clicked_more = 0
        try:
            clicked_more = page.evaluate(_JS_LOAD_MORE_REEL) or 0
        except Exception:
            pass

        time.sleep(1.5 if clicked_more else 0.5)

        try:
            cur_count = page.evaluate(
                "() => document.querySelectorAll('a[href*=\"comment_id\"]').length"
            ) or 0
        except Exception:
            cur_count = prev_count

        if cur_count > prev_count or clicked_more:
            stable_rounds = 0
            prev_count = cur_count
        else:
            stable_rounds += 1

        logger.debug(
            f"[REEL] round {round_}: links={cur_count} "
            f"stable={stable_rounds} clicked_more={clicked_more}"
        )

        if round_ >= 10 and stable_rounds >= 6:
            break

    logger.info(
        f"[REEL] scroll concluído após {round_ + 1} rounds "
        f"| {prev_count} links comment_id"
    )
