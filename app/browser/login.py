import time

from app.browser.driver import close_browser, start_browser


def is_logged_in(context, page):
    try:
        cookies = context.cookies("https://www.facebook.com")
        has_user_cookie = any(
            cookie.get("name") == "c_user" and cookie.get("value")
            for cookie in cookies
        )
        current_url = page.url.lower()
        blocked_routes = ("login", "checkpoint", "two_step_verification")
        if not has_user_cookie or any(route in current_url for route in blocked_routes):
            return False
        return page.locator('input[name="email"], input[name="pass"]').count() == 0
    except Exception:
        return False


def main():
    playwright, context, page = start_browser(headless=False)
    try:
        page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=60000)

        if is_logged_in(context, page):
            print("\nA sessao do Facebook ja esta autenticada.")
            return

        print("\nFaca login manualmente no Facebook na janela que abriu.")
        print("Nao feche a janela: ela sera fechada automaticamente quando o login for confirmado.")
        print("Se o Facebook pedir codigo, confirmacao ou CAPTCHA, conclua na propria janela.")
        print("Aguardando o login por ate 15 minutos...")

        deadline = time.monotonic() + (15 * 60)
        last_status = None
        while time.monotonic() < deadline:
            if page.is_closed():
                print("\nA janela foi fechada antes da confirmacao do login.")
                return

            current_url = page.url.lower()
            status = None
            if "checkpoint" in current_url or "two_step_verification" in current_url:
                status = "Aguardando a confirmacao de seguranca do Facebook..."
            elif "login" in current_url or page.locator('input[name="email"]').count():
                status = "Aguardando email, senha e envio do formulario..."

            if status and status != last_status:
                print(status)
                last_status = status

            if is_logged_in(context, page):
                page.wait_for_timeout(2000)
                print("\nLogin detectado com sucesso. Sessao salva.")
                return
            time.sleep(1)

        print("\nTempo limite atingido sem confirmar o login.")
        print("Deixe todas as confirmacoes do Facebook concluidas e execute novamente.")
    finally:
        close_browser(playwright, context)


if __name__ == "__main__":
    main()
