from app.config import COLLECT_ALBUM_PHOTOS
from app.logger import logger

_COLLECT_URLS_JS = """([pageSlug, collectAlbumPhotos]) => {
    const urls = new Set();
    const albumsSeen = new Set();  // deduplicate album photo sets
    const pageIdsSeen = new Set(); // collect page IDs seen in photo URLs

    document.querySelectorAll('a[href]').forEach(a => {
        const h = a.href || '';
        try {
            const u = new URL(h);
            if (!u.hostname.includes('facebook.com')) return;

            // /slug/posts/...  or /slug/videos/...
            const postMatch = u.pathname.match(/^\\/([^\\/]+)\\/(posts|videos)\\/(.+)/);
            if (postMatch) {
                if (!pageSlug || postMatch[1] === pageSlug) {
                    urls.add(u.origin + u.pathname);
                }
                return;
            }

            // /reel/VIDEO_ID  (Facebook Reels)
            const reelMatch = u.pathname.match(/^\\/reel\\/(\\d+)/);
            if (reelMatch) {
                urls.add(u.origin + '/reel/' + reelMatch[1]);
                return;
            }

            // /watch/?v=VIDEO_ID
            if (u.pathname === '/watch/' && u.searchParams.has('v')) {
                urls.add(u.origin + '/watch/?v=' + u.searchParams.get('v'));
                return;
            }

            // /photo/?fbid=...  — Facebook pages often post photos, not text
            if (u.pathname === '/photo/' && u.searchParams.has('fbid')) {
                const fbid = u.searchParams.get('fbid');
                const set  = u.searchParams.get('set') || '';

                // Photo album (set=a.ALBUMID) — one URL per album is enough
                if (set.startsWith('a.')) {
                    const albumId = set.split('.')[1];
                    if (collectAlbumPhotos || !albumsSeen.has(albumId)) {
                        albumsSeen.add(albumId);
                        urls.add(u.origin + '/photo/?fbid=' + fbid + '&set=' + set);
                    }
                    return;
                }

                // Page timeline photo (set=pb.PAGEID...)
                if (set.startsWith('pb.')) {
                    const pageId = (set.split('.')[1]) || '';
                    pageIdsSeen.add(pageId);
                    urls.add(u.origin + '/photo/?fbid=' + fbid);
                    return;
                }

                // Photo with no set or other format
                urls.add(u.origin + '/photo/?fbid=' + fbid);
                return;
            }

            // story.php?story_fbid=...&id=...
            // Only include if id matches a page we've seen in photo URLs, not a user profile
            if (u.pathname === '/story.php' && u.searchParams.has('story_fbid')) {
                const sfbid  = u.searchParams.get('story_fbid');
                const id     = u.searchParams.get('id') || '';
                // Collect it — we'll filter by page slug later if needed
                if (!pageSlug || pageIdsSeen.has(id)) {
                    urls.add(u.origin + '/story.php?story_fbid=' + sfbid + (id ? '&id=' + id : ''));
                }
            }
        } catch(e) {}
    });
    return Array.from(urls);
}"""


def collect_post_urls_from_feed(page):
    """Return a deduped list of post URLs from the current feed page.

    Uses JavaScript so it works regardless of how Facebook renders the feed.
    Strips tracking params (__cft__, comment_id, __tn__, etc.) that cause redirects.
    If 0 URLs are found, a broader fallback tries /photo/ and /posts/ links without filters.
    """
    try:
        slug = page.url.rstrip("/").split("facebook.com/")[-1].split("/")[0].split("?")[0]
    except Exception:
        slug = ""

    try:
        urls = page.evaluate(_COLLECT_URLS_JS, [slug, COLLECT_ALBUM_PHOTOS])
        urls = urls or []
    except Exception:
        urls = []

    if not urls and slug:
        try:
            urls = page.evaluate(_COLLECT_URLS_JS, ["", COLLECT_ALBUM_PHOTOS]) or []
            if urls:
                logger.warning(f"Fallback sem filtro de slug encontrou {len(urls)} URLs")
        except Exception:
            pass

    return urls
