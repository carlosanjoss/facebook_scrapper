import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.storage import persist
from app.storage.quality import enrich_post
from app.storage.schema import validate_post_for_database
from app.extractors.comments.parsers import _parse_date, _pick_text
from app.extractors.post import _parse_reaction_type_labels, _parse_reactions_detail
from app.utils import parse_count, parse_facebook_datetime
from app.navigation.navigate import navigate_to, verify_on_target_page
from app.collector.page import _browser_needs_restart, collect_page_with_retry


class CountParsingTests(unittest.TestCase):
    def test_parse_count_supports_facebook_formats(self):
        self.assertEqual(parse_count("1,2 mil curtidas"), 1200)
        self.assertEqual(parse_count("2.3K people"), 2300)
        self.assertEqual(parse_count("1.234 pessoas"), 1234)

    def test_post_reaction_detail_accepts_separators(self):
        detail = _parse_reactions_detail("1.234 curtidas")

        self.assertEqual(detail["like"], 1234)
        self.assertEqual(detail["total"], 1234)

    def test_post_reaction_type_labels_sum_total(self):
        detail = _parse_reaction_type_labels(["Like: 1,234 people", "Love: 95 people"])

        self.assertEqual(detail["like"], 1234)
        self.assertEqual(detail["love"], 95)
        self.assertEqual(detail["total"], 1329)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_output_dir = persist.OUTPUT_DIR
        persist.OUTPUT_DIR = Path(self.tmp.name)

    def tearDown(self):
        persist.OUTPUT_DIR = self.old_output_dir
        self.tmp.cleanup()

    def test_incremental_save_preserves_existing_comments_after_sparse_run(self):
        page_url = "https://www.facebook.com/example.page"
        post_url = "https://www.facebook.com/photo/?fbid=123"

        original = {
            "post_url": post_url,
            "text": "original",
            "comments": [
                {"comment_index": 1, "text": "a"},
                {"comment_index": 2, "text": "b"},
                {"comment_index": 3, "text": "c"},
            ],
        }
        persist.save_post_incremental(page_url, original)

        sparse = {"post_url": post_url, "text": "new", "comments": []}
        post_path, is_new = persist.save_post_incremental(page_url, sparse)

        self.assertFalse(is_new)
        saved = persist.json.loads(post_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["comments_count"], 3)
        self.assertEqual([c["text"] for c in saved["comments"]], ["a", "b", "c"])


class CommentParsingTests(unittest.TestCase):
    def test_compact_timestamps_are_not_comment_text(self):
        text = _pick_text(["2y", "34w", "Texto real do comentario"], "Autor Exemplo")

        self.assertEqual(text, "Texto real do comentario")

    def test_month_parser_does_not_match_author_name_prefix(self):
        label = "Comment by Margarene Ibernon Maressa 34 weeks ago"

        self.assertEqual(_parse_date(label, label), "34 weeks ago")

    def test_utf8_portuguese_comment_date_is_parsed(self):
        label = "Coment\u00e1rio de Jo\u00e3o Silva h\u00e1 2 horas"

        self.assertEqual(_parse_date(label, label), "h\u00e1 2 horas")


class DateNormalizationTests(unittest.TestCase):
    def test_parse_absolute_portuguese_date_to_iso(self):
        value = "15 de mar\u00e7o de 2026 \u00e0s 15:30"

        self.assertEqual(
            parse_facebook_datetime(value, "2026-07-14T12:00:00+00:00"),
            "2026-03-15T15:30:00+00:00",
        )

    def test_parse_relative_portuguese_date_to_iso(self):
        value = "h\u00e1 2 horas"

        self.assertEqual(
            parse_facebook_datetime(value, "2026-07-14T12:00:00+00:00"),
            "2026-07-14T10:00:00+00:00",
        )


class DatabaseSchemaTests(unittest.TestCase):
    def test_enriched_post_has_database_safe_hierarchy(self):
        post = enrich_post(
            {
                "post_url": "https://www.facebook.com/photo/?fbid=123",
                "created_at": "15 de mar\u00e7o de 2026 \u00e0s 15:30",
                "text": "post",
                "comments": [
                    {
                        "author": "Ana",
                        "created_at": "h\u00e1 2 horas",
                        "text": "comentario",
                        "replies": [
                            {
                                "author": "Bia",
                                "created_at": "1h",
                                "text": "resposta",
                            }
                        ],
                    }
                ],
            },
            "2026-07-14T12:00:00+00:00",
        )
        post["first_collected_at"] = "2026-07-14T12:00:00+00:00"
        post["last_collected_at"] = "2026-07-14T12:00:00+00:00"
        post["collected_at"] = "2026-07-14T12:00:00+00:00"

        issues = validate_post_for_database(post)

        self.assertEqual(issues, [])
        self.assertEqual(post["comments"][0]["post_id"], post["post_id"])
        self.assertIsNone(post["comments"][0]["parent_comment_id"])
        self.assertEqual(
            post["comments"][0]["replies"][0]["parent_comment_id"],
            post["comments"][0]["comment_id"],
        )


class NavigationTests(unittest.TestCase):
    def test_different_post_is_not_accepted_as_target(self):
        page = Mock()
        page.url = "https://www.facebook.com/example/posts/pfbidOUTRO"

        self.assertFalse(
            verify_on_target_page(
                page,
                "https://www.facebook.com/example/posts/pfbidESPERADO",
            )
        )

    def test_same_post_with_tracking_query_is_accepted(self):
        page = Mock()
        page.url = "https://www.facebook.com/example/posts/12345?__cft__=tracking"

        self.assertTrue(
            verify_on_target_page(page, "https://www.facebook.com/example/posts/12345")
        )

    def test_different_photo_is_not_accepted_as_target(self):
        page = Mock()
        page.url = "https://www.facebook.com/photo/?fbid=999"

        self.assertFalse(
            verify_on_target_page(page, "https://www.facebook.com/photo/?fbid=123")
        )

    def test_reel_auto_advance_is_not_accepted_as_target(self):
        page = Mock()
        page.url = "https://www.facebook.com/reel/222"

        self.assertFalse(
            verify_on_target_page(page, "https://www.facebook.com/reel/111")
        )

    def test_video_canonicalization_keeps_same_content(self):
        page = Mock()
        page.url = "https://www.facebook.com/watch/?v=123"

        self.assertTrue(
            verify_on_target_page(page, "https://www.facebook.com/example/videos/123")
        )

    def test_login_redirect_is_not_accepted_as_target(self):
        page = Mock()
        page.url = "https://www.facebook.com/login/?next=%2Fexample"

        self.assertFalse(
            verify_on_target_page(page, "https://www.facebook.com/example")
        )

    @patch("app.navigation.navigate.sleep_seconds")
    @patch("app.navigation.navigate.sleep_random")
    @patch("app.navigation.navigate._wait_for_rendered_content")
    def test_empty_facebook_shell_is_retried(self, wait_rendered, _sleep_random, _sleep):
        wait_rendered.side_effect = [False, True]
        page = Mock()
        page.url = "https://www.facebook.com/example"

        result = navigate_to(page, "https://www.facebook.com/example")

        self.assertTrue(result)
        self.assertEqual(page.goto.call_count, 2)
        page.goto.assert_called_with(
            "https://www.facebook.com/example",
            wait_until="commit",
            timeout=60000,
        )


class BrowserCrashRecoveryTests(unittest.TestCase):
    def test_target_crashed_requires_browser_restart(self):
        error = RuntimeError("Page.add_init_script: Target crashed")

        self.assertTrue(_browser_needs_restart(error))

    def test_regular_collection_error_does_not_require_browser_restart(self):
        self.assertFalse(_browser_needs_restart(RuntimeError("selector not found")))

    @patch("app.collector.page.install_cleaner")
    @patch("app.collector.page.restart_browser_in_place")
    @patch("app.collector.page.collect_page")
    def test_crashed_page_is_restarted_and_same_url_is_retried(
        self, collect_page, restart_browser, install_cleaner
    ):
        recovered_page = Mock()
        restart_browser.return_value = recovered_page
        collect_page.side_effect = [
            RuntimeError("Page.add_init_script: Target crashed"),
            {"status": "ok", "url": "https://www.facebook.com/example", "posts": []},
        ]
        playwright_ref = [Mock(), Mock(), Mock()]
        options = Mock()

        result = collect_page_with_retry(
            playwright_ref, "https://www.facebook.com/example", options
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(collect_page.call_count, 2)
        restart_browser.assert_called_once_with(playwright_ref)
        install_cleaner.assert_called_once_with(recovered_page)


if __name__ == "__main__":
    unittest.main()
