import unittest

from app.browser.login import is_logged_in


class _Locator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class _Context:
    def __init__(self, cookies):
        self._cookies = cookies

    def cookies(self, _url):
        return self._cookies


class _Page:
    def __init__(self, url, login_fields=0):
        self.url = url
        self._login_fields = login_fields

    def locator(self, _selector):
        return _Locator(self._login_fields)


class LoginDetectionTests(unittest.TestCase):
    def test_detects_authenticated_session_by_cookie(self):
        context = _Context([{"name": "c_user", "value": "123"}])
        page = _Page("https://www.facebook.com/")
        self.assertTrue(is_logged_in(context, page))

    def test_rejects_login_page_even_with_stale_cookie(self):
        context = _Context([{"name": "c_user", "value": "123"}])
        page = _Page("https://www.facebook.com/login/", login_fields=2)
        self.assertFalse(is_logged_in(context, page))

    def test_rejects_checkpoint_until_user_finishes_it(self):
        context = _Context([{"name": "c_user", "value": "123"}])
        page = _Page("https://www.facebook.com/checkpoint/")
        self.assertFalse(is_logged_in(context, page))

    def test_rejects_session_without_user_cookie(self):
        self.assertFalse(is_logged_in(_Context([]), _Page("https://www.facebook.com/")))


if __name__ == "__main__":
    unittest.main()
