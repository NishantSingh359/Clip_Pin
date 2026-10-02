import tempfile
import threading
import unittest
from io import BytesIO
from unittest.mock import patch

from config import FAVICON_WORKERS
from core.favicon_service import FaviconService


class SyncExecutor:
    def submit(self, func, *args):
        func(*args)


class TestFaviconService(unittest.TestCase):
    def test_worker_limit_uses_configured_value(self):
        service = FaviconService(tempfile.mkdtemp())
        self.assertEqual(service.executor._max_workers, FAVICON_WORKERS)
        service.executor.shutdown(wait=False)

    def test_cache_hit_calls_callback_without_fetching(self):
        service = FaviconService(tempfile.mkdtemp())
        service.executor.shutdown(wait=False)
        data = b"cached image data"
        service._cache_path("example.com").write_bytes(data)
        received = []

        with patch.object(service, "fetch_favicon_bytes", side_effect=AssertionError("should not fetch")):
            service.request("https://example.com/page", received.append)

        self.assertEqual(received, [data])

    def test_failed_domain_does_not_call_callback(self):
        service = FaviconService(tempfile.mkdtemp())
        service.executor.shutdown(wait=False)
        service.executor = SyncExecutor()
        received = []

        with patch.object(service, "fetch_favicon_bytes", return_value=None):
            service.request("https://missing.example/page", received.append)

        self.assertEqual(received, [])

    def test_download_timeout_returns_none(self):
        service = FaviconService(tempfile.mkdtemp())
        service.executor.shutdown(wait=False)

        with patch("core.favicon_service.urlopen", side_effect=TimeoutError()):
            self.assertIsNone(service.download_favicon("https://example.com/favicon.ico"))

    def test_discover_page_icons_accepts_multi_word_rel(self):
        service = FaviconService(tempfile.mkdtemp())
        service.executor.shutdown(wait=False)

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return b'<link rel="shortcut icon" href="/favicon.png">'

        with patch("core.favicon_service.urlopen", return_value=FakeResponse()):
            icons = service.discover_page_icons("https://example.com")

        self.assertEqual(icons, ["https://example.com/favicon.png"])

    def test_favicon_candidates_prioritize_copied_page_icon(self):
        service = FaviconService(tempfile.mkdtemp())
        service.executor.shutdown(wait=False)
        page_icon = "https://example.com/assets/site-logo.png"

        with patch.object(service, "discover_page_icons", return_value=[page_icon]) as discover:
            candidates = service.favicon_candidates("https://example.com/article/1", "example.com")

        self.assertEqual(candidates[0], page_icon)
        self.assertIn("https://example.com/favicon.ico", candidates)
        self.assertGreater(candidates.index("https://example.com/favicon.ico"), 0)
        discover.assert_called_once_with("https://example.com/article/1")

    def test_favicon_cache_path_uses_v2_namespace(self):
        service = FaviconService(tempfile.mkdtemp())
        service.executor.shutdown(wait=False)

        self.assertTrue(service._cache_path("example.com").parent.exists())
        self.assertNotEqual(
            service._cache_path("example.com").name,
            __import__("hashlib").sha256(b"example.com").hexdigest() + ".ico",
        )

    def test_download_accepts_small_image_favicon(self):
        service = FaviconService(tempfile.mkdtemp())
        service.executor.shutdown(wait=False)

        class FakeResponse(BytesIO):
            headers = {"content-type": "image/png"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()
                return False

        with patch("core.favicon_service.urlopen", return_value=FakeResponse(b"icon")):
            self.assertEqual(
                service.download_favicon("https://example.com/favicon"),
                b"icon",
            )

    def test_inflight_requests_share_one_fetch(self):
        service = FaviconService(tempfile.mkdtemp())
        fetch_started = threading.Event()
        release_fetch = threading.Event()
        received = []

        def fetch(url, domain):
            fetch_started.set()
            release_fetch.wait(2)
            return b"image bytes over 64 characters........................................"

        with patch.object(service, "fetch_favicon_bytes", side_effect=fetch):
            service.request("https://example.com/a", received.append)
            fetch_started.wait(2)
            service.request("https://example.com/b", received.append)
            release_fetch.set()
            service.executor.shutdown(wait=True)

        self.assertEqual(len(received), 2)


if __name__ == "__main__":
    unittest.main()
