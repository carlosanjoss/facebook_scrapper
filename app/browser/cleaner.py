CLEANER_SCRIPT = """
(() => {
    if (window.__facebook_cleaner_installed) {
        return;
    }

    window.__facebook_cleaner_installed = true;

    setInterval(() => {
        const hrefs = document.getElementsByTagName("a");

        for (let href of hrefs) {
            if (href.href === "https://www.facebook.com/policies/cookies/#other_companies_section") {
                let element = href.parentElement;
                let last = href;

                while (element && (element.tagName === "DIV" || element.tagName === "SPAN")) {
                    last = element;
                    element = element.parentElement;
                }

                if (last) {
                    last.remove();
                }

                break;
            }
        }
    }, 800);

    setInterval(() => {
        const closeButton = document.evaluate(
            "//div[@aria-label='Close' and @role='button']",
            document,
            null,
            XPathResult.FIRST_ORDERED_NODE_TYPE,
            null
        ).singleNodeValue;

        if (closeButton) {
            closeButton.click();
        }
    }, 1200);

    setInterval(() => {
        const allowCookiesButton = document.evaluate(
            "//div[@aria-label='Allow all cookies' and @role='button']",
            document,
            null,
            XPathResult.FIRST_ORDERED_NODE_TYPE,
            null
        ).singleNodeValue;

        if (allowCookiesButton) {
            allowCookiesButton.click();
        }
    }, 1200);

    setInterval(() => {
        document.querySelectorAll('[data-nosnippet]').forEach(el => el.remove());
    }, 1500);
})();
"""


def install_cleaner(page):
    page.add_init_script(CLEANER_SCRIPT)
    page.evaluate(CLEANER_SCRIPT)
