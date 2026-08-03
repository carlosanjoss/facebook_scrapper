import re
from urllib.parse import parse_qs, urlparse

from app.utils import clean_text, parse_facebook_datetime, stable_hash


def _extract_post_id_from_url(url: str):
    """Return the raw ID embedded in the URL, or None if not found."""
    parsed = urlparse(url or "")
    path = parsed.path.rstrip("/")
    qs = parse_qs(parsed.query)

    fbid = (qs.get("fbid") or qs.get("photo_id") or [""])[0]
    if fbid.isdigit():
        return fbid

    m = re.search(r"/(?:reel|videos)/(\d+)", path, re.I)
    if m:
        return m.group(1)

    m = re.search(r"/posts/(\w+)", path, re.I)
    if m:
        return m.group(1)

    v = (qs.get("v") or [""])[0]
    if v.isdigit():
        return v

    sfbid = (qs.get("story_fbid") or [""])[0]
    if sfbid.isdigit():
        return sfbid

    return None


def infer_post_type(url):
    parsed = urlparse(url or "")
    path = parsed.path.lower()
    if "/reel/" in path:
        return "reel"
    if "/watch/" in path:
        return "watch_video"
    if "/videos/" in path:
        return "video"
    if "/photo/" in path:
        return "photo"
    if "/story.php" in path:
        return "story"
    if "/posts/" in path:
        return "post"
    return "unknown"


def infer_album_id(url):
    query = parse_qs(urlparse(url or "").query)
    set_value = (query.get("set") or [""])[0]
    if set_value.startswith("a."):
        return set_value.split(".", 1)[1]
    return None


def classify_content(text):
    body = clean_text(text or "")
    if not body:
        return "empty_or_media"
    words = body.split()
    if len(words) == 1 and (body.startswith("http://") or body.startswith("https://") or "." in body):
        return "link_only"
    if body.startswith("http://") or body.startswith("https://"):
        return "link_with_text"
    if not any(ch.isalnum() for ch in body):
        return "emoji_or_symbol_only"
    return "text"


def _missing_fields(payload, required):
    return [field for field in required if payload.get(field) in (None, "", [])]


def _comment_identity(post_url, item, fallback_index, prefix):
    identity_parts = [
        item.get("author"),
        item.get("created_at"),
        clean_text(item.get("text", ""))[:300],
    ]
    if any(identity_parts):
        return stable_hash(prefix, post_url, *identity_parts)
    return stable_hash(
        prefix,
        post_url,
        fallback_index,
    )


def enrich_comments(comments, post_url, collected_at, post_id=None):
    enriched = []
    seen = set()
    duplicate_count = 0

    for idx, comment in enumerate(comments or [], start=1):
        c = dict(comment)
        c.setdefault("comment_index", idx)
        c["comment_id"] = c.get("comment_id") or _comment_identity(post_url, c, idx, "comment")
        c["post_id"] = post_id
        c["parent_comment_id"] = None
        c["created_at_absolute"] = parse_facebook_datetime(c.get("created_at"), collected_at)
        c["content_type"] = classify_content(c.get("text"))
        c["data_quality"] = {
            "missing_fields": _missing_fields(c, ["author", "created_at", "text"]),
        }

        replies = []
        reply_seen = set()
        for ridx, reply in enumerate(c.get("replies", []) or [], start=1):
            r = dict(reply)
            r.setdefault("reply_index", ridx)
            r["reply_id"] = r.get("reply_id") or _comment_identity(post_url, r, ridx, "reply")
            r["post_id"] = post_id
            r["parent_comment_id"] = c["comment_id"]
            r["created_at_absolute"] = parse_facebook_datetime(r.get("created_at"), collected_at)
            r["content_type"] = classify_content(r.get("text"))
            r["data_quality"] = {
                "missing_fields": _missing_fields(r, ["author", "created_at", "text"]),
            }
            if r["reply_id"] in reply_seen:
                duplicate_count += 1
                continue
            reply_seen.add(r["reply_id"])
            replies.append(r)
        c["replies"] = replies

        if c["comment_id"] in seen:
            duplicate_count += 1
            continue
        seen.add(c["comment_id"])
        enriched.append(c)

    return enriched, duplicate_count


def enrich_post(post, collected_at):
    p = dict(post)
    post_url = p.get("post_url", "")
    p["schema_version"] = "2.1"
    p["post_id"] = _extract_post_id_from_url(post_url) or p.get("post_id") or stable_hash("post", post_url or p.get("text", ""))
    p["post_type"] = p.get("post_type") or infer_post_type(post_url)
    p["album_id"] = p.get("album_id") or infer_album_id(post_url)
    p["created_at_absolute"] = parse_facebook_datetime(p.get("created_at"), collected_at)
    p["content_type"] = classify_content(p.get("text"))

    comments, duplicate_count = enrich_comments(
        p.get("comments", []),
        post_url,
        collected_at,
        post_id=p["post_id"],
    )
    p["comments"] = comments
    p["comments_count"] = len(comments)
    p["replies_count"] = sum(len(c.get("replies", [])) for c in comments)

    observed = p.get("observed_counts") or {}
    observed_comments = observed.get("comments")
    gap = None
    if isinstance(observed_comments, int):
        gap = max(observed_comments - p["comments_count"], 0)

    missing = _missing_fields(p, ["author", "created_at", "text"])
    if p.get("created_at_absolute"):
        date_status = "parsed"
    elif p.get("created_at"):
        date_status = "unparsed"
    else:
        date_status = "missing"
    p["data_quality"] = {
        "missing_fields": missing,
        "created_at_status": date_status,
        "duplicate_items_removed": duplicate_count,
        "observed_comments_count": observed_comments,
        "extracted_comments_count": p["comments_count"],
        "comments_gap": gap,
        "possible_incomplete_comments": bool(gap and gap > 0),
        "has_media": bool(p.get("media")),
    }
    return p
