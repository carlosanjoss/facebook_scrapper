import time

from app.browser import BrowserStartupError, start_browser, close_browser
from app.collector.cycle import run_cycle
from app.collector.options import parse_args, build_runtime_options, load_links
from app.config import CONTINUOUS_INTERVAL_MINUTES
from app.logger import logger
from app.runtime import CollectorAlreadyRunning, CollectorLock
from app.storage import migrate_flat_to_hierarchy


def main(argv=None):
    args = parse_args(argv)
    options = build_runtime_options(args)

    try:
        links = load_links()
    except (OSError, UnicodeError) as exc:
        logger.error(str(exc))
        return 2

    if options.max_pages_per_cycle:
        links = links[:options.max_pages_per_cycle]

    if not links:
        logger.warning("Nenhum link encontrado em data/input/links.txt")
        return

    logger.info(f"Links carregados: {len(links)}")

    for link in links:
        n = migrate_flat_to_hierarchy(link)
        if n:
            logger.info(f"Migração: {n} posts movidos para estrutura hierárquica ({link})")

    if options.continuous_mode:
        logger.info(f"Modo contínuo ativo — intervalo entre ciclos: {CONTINUOUS_INTERVAL_MINUTES} min")
    else:
        logger.info("Modo único — coleta uma vez e encerra.")

    lock = CollectorLock()
    try:
        lock.acquire()
    except CollectorAlreadyRunning as exc:
        logger.error(f"Outra coleta ja esta em execucao. Lock: {exc}")
        return 2

    playwright_ref = [None, None, None]
    cycle = 0

    try:
        try:
            playwright, context, page = start_browser()
        except BrowserStartupError as exc:
            logger.error(str(exc))
            return 2
        playwright_ref = [playwright, context, page]

        while True:
            cycle += 1
            logger.info(f"\n{'='*45}\n  CICLO {cycle}\n{'='*45}")

            stats = run_cycle(playwright_ref, links, options, cycle)
            playwright, context, page = playwright_ref  # may have been restarted

            logger.info(
                f"Ciclo {cycle} concluído — "
                f"sucesso: {stats['success']}/{len(links)} | "
                f"novos posts: {stats['new_posts']} | "
                f"novos comentários: {stats['new_comments']} | "
                f"bloqueados: {stats['blocked']} | "
                f"erros: {stats['error']}"
            )
            logger.info(
                f"Comentarios coletados no ciclo: {stats['comments_collected']} | "
                f"Relatorio: {stats.get('report_path')}"
            )

            if not options.continuous_mode:
                break

            logger.info(f"Aguardando {CONTINUOUS_INTERVAL_MINUTES} min para o próximo ciclo...")
            time.sleep(CONTINUOUS_INTERVAL_MINUTES * 60)

    finally:
        playwright, context, page = playwright_ref
        if playwright and context:
            try:
                close_browser(playwright, context)
            except Exception as exc:
                logger.warning(f"Falha ao fechar o navegador: {exc}")
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
