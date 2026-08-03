import hashlib
import csv
import json
import os
import re
from pathlib import Path

from app.config import EXPORTS_DIR, OUTPUT_DIR, REPORTS_DIR, STATE_DIR
from app.storage.quality import enrich_post
from app.utils import safe_filename, now_iso


def _page_dir(page_url: str) -> Path:
    d = OUTPUT_DIR / safe_filename(page_url)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _posts_dir(page_url: str) -> Path:
    d = _page_dir(page_url) / "posts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _export_dir(page_url: str) -> Path:
    d = EXPORTS_DIR / safe_filename(page_url)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _post_slug(post_url: str) -> str:
    url = (post_url or "").rstrip("/")
    m = re.search(r"fbid=(\d+)", url)
    if m:
        return f"photo_{m.group(1)}"
    m_reel = re.search(r"/reel/(\d+)", url)
    if m_reel:
        return f"reel_{m_reel.group(1)}"
    m_watch = re.search(r"[?&]v=(\d+)", url)
    if "/watch/" in url and m_watch:
        return f"watch_{m_watch.group(1)}"
    m_video = re.search(r"/videos/(\d+)", url)
    if m_video:
        return f"video_{m_video.group(1)}"
    if "/posts/pfbid" in url:
        after = url.split("/posts/")[-1]
        uid = after[len("pfbid"):]
        return f"pfbid_{uid[:24]}"
    if "/posts/" in url:
        pid = url.split("/posts/")[-1]
        return f"post_{pid[:28]}"
    m2 = re.search(r"story_fbid=(\d+)", url)
    if m2:
        return f"story_{m2.group(1)}"
    return f"post_{safe_filename(url)[-24:]}"


def _post_id(post: dict) -> str:
    if post.get("post_url"):
        return post["post_url"]
    key = f"{post.get('author', '')}:{post.get('text', '')[:200]}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, payload: dict):
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _load_page_index(page_dir: Path) -> dict:
    path = page_dir / "_page.json"
    if not path.exists():
        return {"first_collected_at": now_iso()}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"first_collected_at": now_iso()}


def _write_page_index(page_dir: Path, page_url: str, page_metadata,
                      status: str, new_posts_count=None) -> Path:
    existing = _load_page_index(page_dir)
    posts_dir = page_dir / "posts"
    slugs = sorted(p.stem for p in posts_dir.glob("*.json")) if posts_dir.exists() else []

    post_files = list(posts_dir.glob("*.json")) if posts_dir.exists() else []
    total_comments = 0
    total_replies = 0
    for post_file in post_files:
        try:
            with open(post_file, "r", encoding="utf-8") as f:
                post = json.load(f)
            total_comments += len(post.get("comments", []))
            total_replies += sum(len(c.get("replies", [])) for c in post.get("comments", []))
        except Exception:
            continue

    payload = {
        "source": "facebook",
        "schema_version": "2.1",
        "page_url": page_url,
        "status": status,
        "page_metadata": page_metadata or existing.get("page_metadata"),
        "first_collected_at": existing.get("first_collected_at", now_iso()),
        "last_collected_at": now_iso(),
        "total_posts": len(slugs),
        "total_comments": total_comments,
        "total_replies": total_replies,
        "post_slugs": slugs,
    }
    if new_posts_count is not None:
        payload["new_posts_count"] = new_posts_count

    path = page_dir / "_page.json"
    _write_json_atomic(path, payload)
    return path


def save_post_incremental(page_url: str, post: dict, page_metadata=None):
    """Write a single post to its own JSON file immediately."""
    posts_dir = _posts_dir(page_url)
    slug = _post_slug(post.get("post_url", ""))
    post_path = posts_dir / f"{slug}.json"

    is_new = not post_path.exists()
    post = dict(post)
    collected_at = now_iso()

    if not is_new:
        try:
            with open(post_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            old_count = len(existing.get("comments", []))
            new_count = len(post.get("comments", []))
            if old_count > 0 and new_count < old_count * 0.5:
                post["comments"] = existing["comments"]
            post["first_collected_at"] = existing.get("first_collected_at", now_iso())
        except Exception:
            is_new = True

    post = enrich_post(post, collected_at)

    if "first_collected_at" not in post:
        post["first_collected_at"] = collected_at
    post["collected_at"] = collected_at
    post["last_collected_at"] = collected_at
    post["comments_count"] = len(post.get("comments", []))

    _write_json_atomic(post_path, post)
    _write_page_index(_page_dir(page_url), page_url, page_metadata, status="collecting")
    return post_path, is_new


def should_skip_post(page_url: str, post_url: str, skip_hours: int = 24) -> bool:
    from datetime import datetime, timezone, timedelta
    posts_dir = _posts_dir(page_url)
    slug = _post_slug(post_url)
    post_path = posts_dir / f"{slug}.json"
    if not post_path.exists():
        return False
    try:
        with open(post_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if (existing.get("comments_count") or 0) > 0:
            return False
        observed_comments = (existing.get("observed_counts") or {}).get("comments")
        if isinstance(observed_comments, int) and observed_comments > 0:
            return False
        last = existing.get("last_collected_at")
        if not last:
            return False
        last_dt = datetime.fromisoformat(last)
        age = datetime.now(timezone.utc) - last_dt
        return age < timedelta(hours=skip_hours)
    except Exception:
        return False


def finalize_page_result(page_url: str, status: str, page_metadata=None, new_posts_count: int = 0):
    page_dir = _page_dir(page_url)
    _write_page_index(page_dir, page_url, page_metadata, status, new_posts_count)
    return page_dir, new_posts_count


def write_cycle_report(report: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cycle_id = report.get("cycle_id") or now_iso().replace(":", "").replace(".", "")
    path = REPORTS_DIR / f"cycle_{safe_filename(cycle_id)}.json"
    _write_json_atomic(path, report)
    return path


def save_checkpoint(payload: dict):
    path = STATE_DIR / "cycle_checkpoint.json"
    _write_json_atomic(path, payload)
    return path


def clear_checkpoint():
    path = STATE_DIR / "cycle_checkpoint.json"
    try:
        path.unlink()
    except OSError:
        pass


def export_page_dataset(page_url: str):
    page_dir = _page_dir(page_url)
    posts_dir = page_dir / "posts"
    export_dir = _export_dir(page_url)
    posts_jsonl = export_dir / "posts.jsonl"
    comments_csv = export_dir / "comments.csv"

    post_files = sorted(posts_dir.glob("*.json")) if posts_dir.exists() else []
    with open(posts_jsonl, "w", encoding="utf-8") as out:
        for post_file in post_files:
            try:
                with open(post_file, "r", encoding="utf-8") as f:
                    out.write(json.dumps(json.load(f), ensure_ascii=False) + "\n")
            except Exception:
                continue

    fields = [
        "post_id", "post_url", "item_type", "item_id", "parent_comment_id",
        "author", "created_at", "created_at_absolute", "text", "content_type",
        "reactions_total", "hashtags", "mentions",
    ]
    with open(comments_csv, "w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for post_file in post_files:
            try:
                with open(post_file, "r", encoding="utf-8") as f:
                    post = json.load(f)
            except Exception:
                continue
            for comment in post.get("comments", []):
                writer.writerow(_comment_row(post, comment, "comment"))
                for reply in comment.get("replies", []):
                    writer.writerow(_comment_row(post, reply, "reply", comment.get("comment_id")))

    return {"posts_jsonl": posts_jsonl, "comments_csv": comments_csv}


def normalize_existing_outputs(page_url: str | None = None) -> dict:
    """Re-enrich saved post JSON files so existing data matches current schema."""
    if page_url:
        page_dirs = [_page_dir(page_url)]
    else:
        page_dirs = [p for p in OUTPUT_DIR.iterdir() if p.is_dir()]

    normalized_posts = 0
    pages = []
    for page_dir in page_dirs:
        index_path = page_dir / "_page.json"
        try:
            page_index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            page_index = {}
        current_page_url = page_index.get("page_url") or page_url

        posts_dir = page_dir / "posts"
        if not posts_dir.exists():
            continue

        for post_file in sorted(posts_dir.glob("*.json")):
            try:
                post = json.loads(post_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            collected_at = (
                post.get("collected_at")
                or post.get("last_collected_at")
                or post.get("first_collected_at")
                or now_iso()
            )
            enriched = enrich_post(post, collected_at)
            enriched["first_collected_at"] = post.get("first_collected_at") or collected_at
            enriched["last_collected_at"] = post.get("last_collected_at") or collected_at
            enriched["collected_at"] = post.get("collected_at") or collected_at
            enriched["comments_count"] = len(enriched.get("comments", []))
            _write_json_atomic(post_file, enriched)
            normalized_posts += 1

        if current_page_url:
            finalize_page_result(
                current_page_url,
                status=page_index.get("status", "normalized"),
                page_metadata=page_index.get("page_metadata"),
                new_posts_count=page_index.get("new_posts_count", 0),
            )
        pages.append(str(page_dir))

    return {"pages": pages, "normalized_posts": normalized_posts}


def _comment_row(post, item, item_type, parent_comment_id=None):
    reactions = item.get("reactions") or {}
    return {
        "post_id": post.get("post_id"),
        "post_url": post.get("post_url"),
        "item_type": item_type,
        "item_id": item.get("comment_id") or item.get("reply_id"),
        "parent_comment_id": parent_comment_id,
        "author": item.get("author"),
        "created_at": item.get("created_at"),
        "created_at_absolute": item.get("created_at_absolute"),
        "text": item.get("text"),
        "content_type": item.get("content_type"),
        "reactions_total": reactions.get("total"),
        "hashtags": ";".join(item.get("hashtags", [])),
        "mentions": ";".join(item.get("mentions", [])),
    }


def migrate_flat_to_hierarchy(page_url: str) -> int:
    old_path = OUTPUT_DIR / (safe_filename(page_url) + ".json")
    if not old_path.exists():
        return 0

    try:
        with open(old_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0

    posts = data.get("data", {}).get("posts", [])
    page_metadata = data.get("data", {}).get("page_metadata")
    first_at = data.get("first_collected_at", now_iso())
    last_at = data.get("last_collected_at", now_iso())

    posts_dir = _posts_dir(page_url)
    migrated = 0
    for post in posts:
        slug = _post_slug(post.get("post_url", ""))
        post_path = posts_dir / f"{slug}.json"
        if not post_path.exists():
            p = dict(post)
            p.setdefault("first_collected_at", first_at)
            p.setdefault("last_collected_at", last_at)
            p["comments_count"] = len(p.get("comments", []))
            _write_json_atomic(post_path, p)
            migrated += 1

    _write_page_index(
        _page_dir(page_url), page_url, page_metadata,
        status=data.get("data", {}).get("status", "ok"),
    )

    old_path.rename(old_path.with_suffix(".json.bak"))
    return migrated
