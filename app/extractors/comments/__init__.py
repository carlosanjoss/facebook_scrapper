import re

from app.logger import logger
from app.utils import clean_text, extract_hashtags, extract_mentions
from app.extractors.comments.parsers import _parse_author, _parse_date, _pick_text, _parse_reactions
from app.extractors.comments.post import _JS_EXTRACT_COMMENTS, load_post_comments
from app.extractors.comments.reel import load_reel_comments

_IS_COMMENT = re.compile(r'^(?:Comment by|Coment[aá]rio de) ', re.IGNORECASE)
_IS_REPLY   = re.compile(r'^(?:Reply by|Resposta de) ', re.IGNORECASE)


def collect_comments_from_post_page(page, post_text="", post_url=""):
    """Collect ALL comments from an individual post/photo/reel page."""
    is_reel = '/reel/' in (post_url or '').lower()

    if is_reel:
        load_reel_comments(page)
    else:
        load_post_comments(page)

    # Both reels and photos use [role="article"] with aria-label="Comment by NAME X ago"
    raw = page.evaluate(_JS_EXTRACT_COMMENTS) or []
    logger.debug(f"[{'REEL' if is_reel else 'POST'}] _JS_EXTRACT_COMMENTS → {len(raw)} artigos")

    comments = []
    current_comment = None
    comment_index = 0

    for item in raw:
        aria            = item.get("aria_label", "") or ""
        dir_txt         = item.get("dir_texts", [])
        reactions_label = item.get("reactions_label", "") or ""
        date_label      = item.get("date_label", "") or ""
        attachments     = item.get("attachments", []) or []

        if _IS_COMMENT.match(aria):
            author = _parse_author(aria)
            text   = _pick_text(dir_txt, author, post_text)
            if not text and not attachments:
                continue
            comment_index += 1
            body = clean_text(text)
            current_comment = {
                "comment_index": comment_index,
                "author":     author,
                "created_at": _parse_date(aria, date_label),
                "text":       body,
                "hashtags":   extract_hashtags(body),
                "mentions":   extract_mentions(body),
                "reactions":  _parse_reactions(reactions_label),
                "attachments": attachments,
                "raw": {
                    "aria_label": aria,
                    "date_label": date_label,
                    "dir_texts": dir_txt,
                    "reactions_label": reactions_label,
                },
                "replies": [],
            }
            comments.append(current_comment)

        elif _IS_REPLY.match(aria) and current_comment is not None:
            author = _parse_author(aria)
            text   = _pick_text(dir_txt, author, post_text) or ""
            if not text and not attachments:
                continue
            body = clean_text(text)
            current_comment["replies"].append({
                "reply_index": len(current_comment["replies"]) + 1,
                "author":      author,
                "created_at":  _parse_date(aria, date_label),
                "text":        body,
                "hashtags":    extract_hashtags(body),
                "mentions":    extract_mentions(body),
                "reactions":   _parse_reactions(reactions_label),
                "attachments":  attachments,
                "raw": {
                    "aria_label": aria,
                    "date_label": date_label,
                    "dir_texts": dir_txt,
                    "reactions_label": reactions_label,
                },
            })

        elif not aria:
            # No aria-label: photo page where aria-labels differ.
            if len(dir_txt) >= 2 or attachments:
                author = dir_txt[0] if dir_txt else None
                text   = _pick_text(dir_txt[1:], author, post_text) or ""
                if (text and len(text) > 3) or attachments:
                    comment_index += 1
                    body = clean_text(text)
                    current_comment = {
                        "comment_index": comment_index,
                        "author":     author,
                        "created_at": _parse_date("", date_label),
                        "text":       body,
                        "hashtags":   extract_hashtags(body),
                        "mentions":   extract_mentions(body),
                        "reactions":  _parse_reactions(reactions_label),
                        "attachments": attachments,
                        "raw": {
                            "aria_label": aria,
                            "date_label": date_label,
                            "dir_texts": dir_txt,
                            "reactions_label": reactions_label,
                        },
                        "replies": [],
                    }
                    comments.append(current_comment)

    return comments
