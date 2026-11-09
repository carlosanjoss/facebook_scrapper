import time

from app.config import MAX_SCROLL_ATTEMPTS, SCROLL_DELAY_SECONDS, STABLE_SCROLL_ROUNDS
from app.utils import sleep_seconds

_JS_SMART_SCROLL = """(step) => {
    var best = null, bs = -1;
    var els = document.querySelectorAll('div');
    for (var i = 0; i < els.length; i++) {
        var e = els[i];
        var s = window.getComputedStyle(e);
        var ov = (s.overflow || '') + ' ' + (s.overflowY || '');
        if (!(ov.includes('scroll') || ov.includes('auto'))) continue;
        if (e.scrollHeight <= e.clientHeight + 50) continue;
        var sc = e.querySelectorAll('[role="article"]').length * 10 + e.scrollHeight / 1000;
        if (sc > bs) { bs = sc; best = e; }
    }
    var bef = best ? best.scrollTop : (window.pageYOffset || document.documentElement.scrollTop);
    if (best) best.scrollTop += step; else window.scrollBy(0, step);
    var aft = best ? best.scrollTop : (window.pageYOffset || document.documentElement.scrollTop);
    var arts = document.querySelectorAll('[role="article"]').length;
    var atBot = best
        ? (best.scrollTop + best.clientHeight >= best.scrollHeight - 30)
        : (window.innerHeight + window.scrollY >= document.body.scrollHeight - 30);
    return {
        moved: Math.abs(aft - bef) > 5,
        arts: arts,
        height: best ? best.scrollHeight : document.body.scrollHeight,
        atBottom: atBot,
    };
}"""


def scroll_page(page, step=900, max_articles=0):
    """Scroll until stable or until the requested number of articles is visible."""
    last_height = 0
    stable_count = 0
    at_bottom_count = 0

    for attempt in range(MAX_SCROLL_ATTEMPTS):
        try:
            m = page.evaluate(_JS_SMART_SCROLL, step)
        except Exception:
            m = {}

        moved     = m.get("moved", False)
        articles  = m.get("arts", 0)
        cur_h     = m.get("height", 0)
        at_bottom = m.get("atBottom", False)

        if max_articles and articles >= max_articles:
            break

        deadline = time.time() + SCROLL_DELAY_SECONDS
        while time.time() < deadline:
            sleep_seconds(0.4)
            try:
                new_h = page.evaluate(
                    "(function(){var e=null,bs=-1,els=document.querySelectorAll('div');"
                    "for(var i=0;i<els.length;i++){var el=els[i],s=window.getComputedStyle(el),"
                    "ov=(s.overflow||'')+' '+(s.overflowY||'');"
                    "if(!(ov.includes('scroll')||ov.includes('auto'))||el.scrollHeight<=el.clientHeight+50)continue;"
                    "var sc=el.querySelectorAll('[role=\"article\"]').length*10+el.scrollHeight/1000;"
                    "if(sc>bs){bs=sc;e=el;}}return e?e.scrollHeight:document.body.scrollHeight;})()"
                )
            except Exception:
                new_h = cur_h
            if new_h > cur_h:
                cur_h = new_h
                break

        if at_bottom:
            at_bottom_count += 1
        else:
            at_bottom_count = 0

        if not moved or cur_h <= last_height:
            stable_count += 1
            if stable_count >= STABLE_SCROLL_ROUNDS:
                break
            if at_bottom_count >= 2:
                break
        else:
            stable_count = 0
            last_height = cur_h
