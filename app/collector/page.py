import time

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from app.browser import start_browser, close_browser, install_cleaner
from app.config import MAX_RETRIES, RETRY_DELAY_SECONDS
from app.extractors.comments import collect_comments_from_post_page
from app.extractors.page import extract_page_metadata
from app.extractors.feed import collect_post_urls_from_feed
from app.extractors.post import (
    collect_post_data_from_page,
    expand_see_more_on_post_page,
    snapshot_page_metadata,
)
from app.logger import logger, console
from app.navigation import (
    navigate_to,
    verify_on_target_page,
    detect_block_or_checkpoint,
    _is_direct_content_url,
    save_error_artifacts,
    save_error_screenshot,
)
from app.browser import scroll_page
from app.storage import save_checkpoint, save_post_incremental, should_skip_post
from app.utils import now_iso, sleep_random
from app.collector.options import RuntimeOptions


def restart_browser_in_place(playwright_ref):
    playwright, context, _page = playwright_ref
    try:
        close_browser(playwright, context)
    except Exception:
        pass
    playwright, context, page = start_browser()
    playwright_ref[0] = playwright
    playwright_ref[1] = context
    playwright_ref[2] = page
    return page


def _target_was_lost(page, post_url, stage):
    """Log when Facebook moved away from the post being collected."""
    if verify_on_target_page(page, post_url):
        return False
    logger.warning(
        "Facebook saiu do post durante "
        f"{stage}: esperado={post_url} atual={page.url}"
    )
    return True


def collect_page(playwright_ref, url, options: RuntimeOptions):
    page = playwright_ref[2]
    started_at = time.time()
    logger.info(f"Acessando página: {url}")
    install_cleaner(page)

    if not navigate_to(page, url):
        return {"status": "redirect_error", "url": url, "page_metadata": None, "posts": []}

    if detect_block_or_checkpoint(page):
        logger.warning("Coleta interrompida: Facebook pediu verificação ou checkpoint.")
        return {"status": "blocked_or_checkpoint", "url": url, "page_metadata": None, "posts": []}

    page_metadata = extract_page_metadata(page)
    logger.info(f"Página: {page_metadata.get('page_name') or url}")

    # ── Fase 1: determinar URLs dos posts ────────────────────────────────────
    if _is_direct_content_url(url):
        logger.info("Conteúdo direto — coletando como post único...")
        post_urls = [url]
    else:
        logger.info("Scrollando feed para carregar posts...")
        post_urls = []
        for feed_attempt in range(1, MAX_RETRIES + 1):
            if feed_attempt > 1 and not navigate_to(page, url):
                continue
            scroll_page(page)
            if _target_was_lost(page, url, "a rolagem do feed"):
                if feed_attempt < MAX_RETRIES:
                    logger.info(
                        "Voltando à página original para refazer a leitura do feed "
                        f"({feed_attempt + 1}/{MAX_RETRIES})..."
                    )
                continue
            candidate_urls = collect_post_urls_from_feed(page)
            if _target_was_lost(page, url, "a leitura dos links do feed"):
                continue
            post_urls = candidate_urls
            break
        logger.info(f"URLs de posts encontradas: {len(post_urls)}")
        if not post_urls:
            logger.warning(
                "Nenhuma URL de post encontrada no feed; "
                "a página será tentada novamente."
            )
            save_error_artifacts(page, url, "empty_feed")
            return {
                "status": "empty_feed",
                "url": url,
                "page_metadata": page_metadata,
                "posts": [],
            }

    if options.max_posts_per_page and len(post_urls) > options.max_posts_per_page:
        total_found = len(post_urls)
        post_urls = post_urls[:options.max_posts_per_page]
        logger.info(
            f"Limitando coleta a {len(post_urls)} posts "
            f"(de {total_found} encontrados)"
        )

    # ── Fase 2: para cada post, navegar, coletar e salvar imediatamente ───────
    posts = []
    new_posts_count = 0
    skipped = 0
    failed_posts = []

    _bar = Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold]Posts[/bold]"),
        BarColumn(bar_width=28, style="dim", complete_style="cyan"),
        MofNCompleteColumn(),
        TextColumn("[dim]·[/dim]"),
        TimeElapsedColumn(),
        TextColumn("[dim]{task.fields[slug]}[/dim]"),
        console=console,
        transient=True,
    )
    _task = _bar.add_task("posts", total=len(post_urls), slug="—")

    with _bar:
        for i, post_url in enumerate(post_urls):
            _bar.advance(_task)
            _bar.update(_task, slug=post_url.split("facebook.com/")[-1][:40])
            logger.info(f"[{i + 1}/{len(post_urls)}] {post_url}")
            save_checkpoint({
                "page_url": url,
                "post_url": post_url,
                "post_index": i + 1,
                "total_posts_in_page_cycle": len(post_urls),
                "updated_at": now_iso(),
            })

            if should_skip_post(url, post_url, skip_hours=options.skip_recent_empty_hours):
                logger.info("  → sem comentários nas últimas 24h — pulando")
                skipped += 1
                continue

            post_data = None
            comments = []
            failed_stage = "navigate"
            checkpoint_found = False

            # Facebook sometimes auto-advances reels or follows a link while
            # comments are being expanded.  Discard that partial attempt,
            # reopen the exact URL and collect the post again from the start.
            for recovery_attempt in range(1, MAX_RETRIES + 1):
                if not navigate_to(page, post_url):
                    failed_stage = "navigate"
                    continue

                if detect_block_or_checkpoint(page):
                    save_error_artifacts(page, post_url, "checkpoint")
                    logger.warning("Checkpoint detectado — parando coleta.")
                    checkpoint_found = True
                    break

                pre_meta = snapshot_page_metadata(page)
                if _target_was_lost(page, post_url, "a leitura dos metadados"):
                    failed_stage = "metadata_drift"
                    continue

                expand_see_more_on_post_page(page)
                if _target_was_lost(page, post_url, "a expansão do texto"):
                    failed_stage = "text_expansion_drift"
                    continue

                candidate = collect_post_data_from_page(
                    page, post_url, i + 1, pre_meta=pre_meta
                )
                if _target_was_lost(page, post_url, "a coleta do post"):
                    failed_stage = "post_collection_drift"
                    continue

                if '/reel/' not in post_url.lower():
                    scroll_page(page)
                    if _target_was_lost(page, post_url, "a rolagem"):
                        failed_stage = "scroll_drift"
                        continue

                if options.collect_comments:
                    candidate_comments = collect_comments_from_post_page(
                        page, post_text=candidate.get("text", ""), post_url=post_url
                    )
                else:
                    candidate_comments = []

                if _target_was_lost(page, post_url, "a coleta dos comentários"):
                    failed_stage = "comments_drift"
                    if recovery_attempt < MAX_RETRIES:
                        logger.info(
                            "  → Voltando ao post original e reiniciando "
                            f"({recovery_attempt + 1}/{MAX_RETRIES})..."
                        )
                    continue

                post_data = candidate
                comments = candidate_comments
                post_data["comments"] = comments
                break

            if checkpoint_found:
                break

            if post_data is None:
                save_error_artifacts(page, post_url, failed_stage)
                failed_posts.append({"post_url": post_url, "stage": failed_stage})
                logger.warning(
                    "  → Não foi possível manter o post aberto após "
                    f"{MAX_RETRIES} tentativas; pulando."
                )
                continue

            _, is_new = save_post_incremental(url, post_data, page_metadata)
            if is_new:
                new_posts_count += 1

            posts.append(post_data)
            options.processed_posts_since_restart += 1
            logger.info(
                f"  → {len(post_data.get('text', ''))} chars · "
                f"{len(comments)} coment. · "
                f"{'[cyan]novo[/cyan]' if is_new else '[dim]atualizado[/dim]'}"
            )

            if (
                options.restart_browser_every_posts
                and options.processed_posts_since_restart
                >= options.restart_browser_every_posts
                and i + 1 < len(post_urls)
            ):
                logger.info("Reiniciando browser preventivamente...")
                page = restart_browser_in_place(playwright_ref)
                install_cleaner(page)
                options.processed_posts_since_restart = 0

    total_comments = sum(len(p.get("comments", [])) for p in posts)
    logger.info(
        f"Coleta concluída: {len(posts)} posts ({new_posts_count} novos, {skipped} pulados) | "
        f"{total_comments} comentários"
    )

    return {
        "status": "ok",
        "url": url,
        "page_metadata": page_metadata,
        "posts": posts,
        "new_posts_count": new_posts_count,
        "skipped_posts_count": skipped,
        "failed_posts": failed_posts,
        "duration_seconds": round(time.time() - started_at, 2),
        "post_urls_found": len(post_urls),
    }


_BROWSER_RESTART_SIGNALS = (
    "target crashed",
    "page crashed",
    "target page, context or browser has been closed",
    "browser has been closed",
    "target closed",
    "context or browser has been closed",
    "connection closed while reading from the driver",
    "playwright connection closed",
)


def _browser_needs_restart(exc):
    """Return True when the current Playwright page/context cannot be reused."""
    msg = str(exc).lower()
    return any(sig in msg for sig in _BROWSER_RESTART_SIGNALS)


def collect_page_with_retry(playwright_ref, url, options: RuntimeOptions):
    """playwright_ref is a mutable list [playwright, context, page] so we can restart in-place."""
    playwright, context, page = playwright_ref

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = collect_page(playwright_ref, url, options)
            if result["status"] in ("ok", "blocked_or_checkpoint", "redirect_error"):
                return result
            logger.warning(
                f"Tentativa {attempt}/{MAX_RETRIES} terminou com "
                f"status {result['status']} para {url}"
            )
            if attempt < MAX_RETRIES:
                sleep_random(RETRY_DELAY_SECONDS * 0.8, RETRY_DELAY_SECONDS * 1.2)
        except Exception as e:
            playwright, context, page = playwright_ref
            if _browser_needs_restart(e):
                logger.warning(
                    "Aba ou navegador travou — reiniciando para repetir a página "
                    f"(tentativa {attempt}/{MAX_RETRIES})..."
                )
                try:
                    page = restart_browser_in_place(playwright_ref)
                    install_cleaner(page)
                except Exception as restart_err:
                    logger.error(f"Falha ao reiniciar browser: {restart_err}")
                    return {"status": "error", "url": url, "page_metadata": None, "posts": []}
            else:
                logger.warning(f"Tentativa {attempt}/{MAX_RETRIES} falhou para {url}: {e}")
                try:
                    save_error_screenshot(page, url, attempt)
                    save_error_artifacts(page, url, f"attempt_{attempt}", e)
                except Exception:
                    pass
                if attempt < MAX_RETRIES:
                    sleep_random(RETRY_DELAY_SECONDS * 0.8, RETRY_DELAY_SECONDS * 1.2)

    logger.error(f"Todas as tentativas falharam para: {url}")
    return {"status": "error", "url": url, "page_metadata": None, "posts": []}
