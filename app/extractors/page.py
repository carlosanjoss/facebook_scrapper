from app.utils import clean_text, parse_count


def extract_page_name(page):
    try:
        h1 = page.locator("h1").first
        text = clean_text(h1.inner_text(timeout=2000))
        if text:
            return text
    except Exception:
        pass
    return None


def extract_page_followers(page):
    for selector in [
        'a:has-text("seguidores")',
        'a:has-text("followers")',
        '[href*="followers"]',
    ]:
        try:
            el = page.locator(selector).first
            text = clean_text(el.inner_text(timeout=1000))
            if text:
                return {"label": text, "count": parse_count(text)}
        except Exception:
            continue
    return None


def extract_page_likes(page):
    for selector in [
        'a:has-text("curtidas")',
        'a:has-text("likes")',
        'a:has-text("pessoas curtem")',
        'a:has-text("people like")',
    ]:
        try:
            el = page.locator(selector).first
            text = clean_text(el.inner_text(timeout=1000))
            if text:
                return {"label": text, "count": parse_count(text)}
        except Exception:
            continue
    return None


def extract_page_metadata(page):
    return {
        "page_name": extract_page_name(page),
        "followers": extract_page_followers(page),
        "likes": extract_page_likes(page),
    }
