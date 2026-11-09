from datetime import datetime

from rich.rule import Rule

from app.logger import logger, console
from app.storage import clear_checkpoint, export_page_dataset, finalize_page_result, write_cycle_report
from app.utils import now_iso
from app.collector.page import collect_page_with_retry
from app.collector.options import RuntimeOptions


def _print_cycle_header(cycle: int):
    ts = datetime.now().strftime("%d/%m  %H:%M")
    console.print()
    console.print(Rule(
        f" [bold]ciclo {cycle}[/bold]  [dim]·  {ts}[/dim] ",
        style="cyan",
        characters="━",
    ))
    console.print()


def _print_cycle_summary(cycle: int, stats: dict, links: list):
    n = len(links)
    ok = stats["success"]
    color = "green" if ok == n else ("yellow" if ok > 0 else "red")

    console.print()

    for page in stats.get("pages", []):
        slug = page["url"].rstrip("/").split("facebook.com/")[-1][:38]
        st = page["status"]
        icon = "[green]✓[/]" if st == "ok" else ("[yellow]⚠[/]" if "blocked" in st else "[red]✗[/]")
        dur = f"  [dim]{page['duration_seconds']}s[/dim]" if page.get("duration_seconds") else ""
        console.print(
            f"  {icon}  [dim]{slug}[/dim]"
            f"  {page.get('posts_processed', 0)} posts"
            f"  [cyan]{page.get('new_posts', 0)} novos[/cyan]"
            f"  {page.get('comments_collected', 0)} coment."
            f"{dur}"
        )

    summary_parts = [
        f"[{color}]{ok}/{n}[/{color}]",
        f"[bold cyan]{stats['new_posts']}[/bold cyan] posts",
        f"[bold cyan]{stats['comments_collected']}[/bold cyan] coment.",
    ]
    if stats["blocked"]:
        summary_parts.append(f"[yellow]{stats['blocked']} bloq.[/yellow]")
    if stats["error"]:
        summary_parts.append(f"[red]{stats['error']} erros[/red]")

    console.print()
    console.print(Rule(
        "  [dim]·[/dim]  ".join(summary_parts),
        style="dim",
        characters="─",
    ))
    console.print()


def run_cycle(playwright_ref, links, options: RuntimeOptions, cycle: int):
    _print_cycle_header(cycle)
    cycle_started = now_iso()
    stats = {
        "success": 0,
        "blocked": 0,
        "error": 0,
        "new_posts": 0,
        "new_comments": 0,
        "comments_collected": 0,
        "pages": [],
    }

    for url in links:
        result = collect_page_with_retry(playwright_ref, url, options)
        new_count = result.get("new_posts_count", 0)

        output_path, _ = finalize_page_result(
            url,
            status=result["status"],
            page_metadata=result.get("page_metadata"),
            new_posts_count=new_count,
        )

        if result["status"] == "ok":
            stats["success"] += 1
            stats["new_posts"] += new_count
            new_posts = result["posts"][-new_count:] if new_count else []
            stats["new_comments"] += sum(len(p.get("comments", [])) for p in new_posts)
            stats["comments_collected"] += sum(
                len(p.get("comments", [])) for p in result.get("posts", [])
            )
            logger.info(f"[cyan]{new_count}[/cyan] novos posts — {output_path.name}/")
        elif result["status"] == "blocked_or_checkpoint":
            stats["blocked"] += 1
            logger.warning(f"Checkpoint detectado em {url}")
        else:
            stats["error"] += 1
            logger.error(f"Falha ao coletar {url}")

        exports = {}
        if options.export_after_cycle and result["status"] == "ok":
            try:
                exported = export_page_dataset(url)
                exports = {key: str(value) for key, value in exported.items()}
                logger.info(f"Exports atualizados — {output_path.name}/")
            except Exception as exc:
                logger.warning(f"Falha ao exportar {url}: {exc}")

        stats["pages"].append({
            "url": url,
            "status": result["status"],
            "output_dir": str(output_path),
            "exports": exports,
            "post_urls_found": result.get("post_urls_found"),
            "posts_processed": len(result.get("posts", [])),
            "new_posts": new_count,
            "skipped_posts": result.get("skipped_posts_count", 0),
            "comments_collected": sum(
                len(p.get("comments", [])) for p in result.get("posts", [])
            ),
            "failed_posts": result.get("failed_posts", []),
            "duration_seconds": result.get("duration_seconds"),
        })

    report = {
        "cycle_id": f"{cycle}_{cycle_started}",
        "cycle_number": cycle,
        "started_at": cycle_started,
        "finished_at": now_iso(),
        "options": {
            "continuous_mode": options.continuous_mode,
            "max_pages_per_cycle": options.max_pages_per_cycle,
            "max_posts_per_page": options.max_posts_per_page,
            "collect_comments": options.collect_comments,
            "skip_recent_empty_hours": options.skip_recent_empty_hours,
            "export_after_cycle": options.export_after_cycle,
            "restart_browser_every_posts": options.restart_browser_every_posts,
        },
        "summary": {k: v for k, v in stats.items() if k != "pages"},
        "pages": stats["pages"],
    }
    report_path = write_cycle_report(report)
    stats["report_path"] = str(report_path)
    clear_checkpoint()

    _print_cycle_summary(cycle, stats, links)
    return stats
