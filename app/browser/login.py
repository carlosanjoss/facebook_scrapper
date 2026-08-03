from app.browser.driver import close_browser, start_browser


def is_logged_in(page):
    try:
        if "login" in page.url.lower():
            return False

        indicators = [
            '[aria-label="Conta"]',
            '[aria-label="Account"]',
            '[aria-label="Seu perfil"]',
            '[aria-label="Your profile"]',
            '[aria-label="Facebook"]',
        ]
        for selector in indicators:
            if page.locator(selector).count() > 0:
                return True
        return False
    except Exception:
        return False


def main():
    playwright, context, page = start_browser(headless=False)
    try:
        page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=60000)

        print("\nFaca login manualmente no Facebook na janela que abriu.")
        print("Depois que a pagina inicial carregar, volte aqui e pressione ENTER.")
        input("\nPressione ENTER depois do login: ")

        if is_logged_in(page):
            print("\nLogin detectado com sucesso. Sessao salva.")
        else:
            print("\nAviso: login nao detectado.")
            print("Confira se o login terminou antes de rodar o scraper.")
    finally:
        close_browser(playwright, context)


if __name__ == "__main__":
    main()
