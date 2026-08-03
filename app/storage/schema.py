from datetime import datetime


def _is_iso_datetime(value):
    if value in (None, ""):
        return True
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_post_for_database(post: dict) -> list[str]:
    """Return schema/date issues that would make DB import unsafe."""
    issues = []

    for field in ("schema_version", "post_id", "post_url", "post_type"):
        if post.get(field) in (None, ""):
            issues.append(f"post missing {field}")

    for field in ("created_at_absolute", "first_collected_at", "last_collected_at", "collected_at"):
        if not _is_iso_datetime(post.get(field)):
            issues.append(f"post {field} is not ISO datetime")

    comments = post.get("comments", [])
    if not isinstance(comments, list):
        return issues + ["post comments is not a list"]

    seen_comments = set()
    seen_replies = set()
    for idx, comment in enumerate(comments, start=1):
        cid = comment.get("comment_id")
        if not cid:
            issues.append(f"comment {idx} missing comment_id")
        elif cid in seen_comments:
            issues.append(f"duplicate comment_id {cid}")
        else:
            seen_comments.add(cid)

        if comment.get("post_id") != post.get("post_id"):
            issues.append(f"comment {cid or idx} has invalid post_id")
        if comment.get("parent_comment_id") is not None:
            issues.append(f"comment {cid or idx} parent_comment_id should be null")
        if not _is_iso_datetime(comment.get("created_at_absolute")):
            issues.append(f"comment {cid or idx} created_at_absolute is not ISO datetime")

        replies = comment.get("replies", [])
        if not isinstance(replies, list):
            issues.append(f"comment {cid or idx} replies is not a list")
            continue

        for ridx, reply in enumerate(replies, start=1):
            rid = reply.get("reply_id")
            if not rid:
                issues.append(f"reply {idx}.{ridx} missing reply_id")
            elif rid in seen_replies:
                issues.append(f"duplicate reply_id {rid}")
            else:
                seen_replies.add(rid)

            if reply.get("post_id") != post.get("post_id"):
                issues.append(f"reply {rid or f'{idx}.{ridx}'} has invalid post_id")
            if reply.get("parent_comment_id") != cid:
                issues.append(f"reply {rid or f'{idx}.{ridx}'} has invalid parent_comment_id")
            if not _is_iso_datetime(reply.get("created_at_absolute")):
                issues.append(f"reply {rid or f'{idx}.{ridx}'} created_at_absolute is not ISO datetime")

    return issues
