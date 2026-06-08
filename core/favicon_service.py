import hashlib
import re
import threading
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

from config import APP_STORAGE_DIR, FAVICON_CACHE_DIR, FAVICON_TIMEOUT_SECONDS, FAVICON_WORKERS
from utils.app_logging import log_exception


class FaviconService:
    def __init__(self, base_dir=APP_STORAGE_DIR):
        self.cache_dir = Path(base_dir) / FAVICON_CACHE_DIR
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.cache_dir = Path(tempfile.gettempdir()) / "Copy Pin" / FAVICON_CACHE_DIR
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=FAVICON_WORKERS, thread_name_prefix="copypin-favicon")
        self._memory_cache = {}
        self._inflight = {}
        self._lock = threading.Lock()

    def request(self, url, callback):
        domain = urlparse(url).netloc.removeprefix("www.").lower()
        if not domain:
            return

        data = self._cached_data(domain)
        if data:
            callback(data)
            return

        with self._lock:
            callbacks = self._inflight.get(domain)
            if callbacks is not None:
                callbacks.append(callback)
                return
            self._inflight[domain] = [callback]

        self.executor.submit(self._fetch_and_dispatch, url, domain)

    def _cached_data(self, domain):
        with self._lock:
            data = self._memory_cache.get(domain)
        if data:
            return data

        cache_path = self._cache_path(domain)
        try:
            if cache_path.exists():
                data = cache_path.read_bytes()
                if data:
                    with self._lock:
                        self._memory_cache[domain] = data
                    return data
        except OSError:
            log_exception("Failed to read favicon cache")
        return None

    def _fetch_and_dispatch(self, url, domain):
        data = None
        try:
            data = self.fetch_favicon_bytes(url, domain)
            if data:
                with self._lock:
                    self._memory_cache[domain] = data
                try:
                    self._cache_path(domain).write_bytes(data)
                except OSError:
                    log_exception("Failed to write favicon cache")
        except Exception:
            log_exception("Failed to fetch favicon")
        finally:
            with self._lock:
                callbacks = self._inflight.pop(domain, [])

        if not data:
            return

        for callback in callbacks:
            try:
                callback(data)
            except Exception:
                log_exception("Failed to deliver favicon")

    def fetch_favicon_bytes(self, url, domain):
        for favicon_url in self.favicon_candidates(url, domain):
            data = self.download_favicon(favicon_url)
            if data:
                return data
        return None

    def favicon_candidates(self, url, domain):
        quoted_url = quote(url, safe="")
        candidates = [
            f"https://www.google.com/s2/favicons?domain_url={quoted_url}&sz=64",
            f"https://www.google.com/s2/favicons?domain={domain}&sz=64",
            f"https://icons.duckduckgo.com/ip3/{domain}.ico",
            f"https://{domain}/favicon.ico",
            f"http://{domain}/favicon.ico",
        ]

        page_icons = self.discover_page_icons(f"https://{domain}")
        if not page_icons:
            page_icons = self.discover_page_icons(f"http://{domain}")

        return page_icons + candidates

    def discover_page_icons(self, page_url):
        try:
            request = Request(
                page_url,
                headers={"User-Agent": "Mozilla/5.0 CopyPin/1.0"},
            )
            with urlopen(request, timeout=FAVICON_TIMEOUT_SECONDS) as response:
                html = response.read(180_000).decode("utf-8", errors="ignore")
        except Exception:
            return []

        icon_urls = []
        for match in re.finditer(r"<link\b[^>]*>", html, flags=re.IGNORECASE):
            tag = match.group(0)
            rel = re.search(r"""rel=["']?([^"'>\s]+)["']?""", tag, flags=re.IGNORECASE)
            href = re.search(r"""href=["']?([^"'>\s]+)["']?""", tag, flags=re.IGNORECASE)
            if not rel or not href:
                continue
            if "icon" not in rel.group(1).lower():
                continue
            icon_urls.append(urljoin(page_url, href.group(1)))

        return icon_urls[:4]

    def download_favicon(self, favicon_url):
        try:
            request = Request(
                favicon_url,
                headers={"User-Agent": "Mozilla/5.0 CopyPin/1.0"},
            )
            with urlopen(request, timeout=FAVICON_TIMEOUT_SECONDS) as response:
                content_type = response.headers.get("content-type", "").lower()
                data = response.read(300_000)
        except Exception:
            return None

        looks_like_image = (
            "image/" in content_type
            or favicon_url.lower().split("?")[0].endswith((".ico", ".png", ".jpg", ".jpeg", ".webp", ".gif"))
        )
        if len(data) > 64 and looks_like_image:
            return data
        return None

    def _cache_path(self, domain):
        digest = hashlib.sha256(domain.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.ico"

    def shutdown(self):
        self.executor.shutdown(wait=False, cancel_futures=True)


_favicon_service = None
_favicon_service_lock = threading.Lock()


def get_favicon_service():
    global _favicon_service
    with _favicon_service_lock:
        if _favicon_service is None:
            _favicon_service = FaviconService()
        return _favicon_service


def shutdown_favicon_service():
    global _favicon_service
    with _favicon_service_lock:
        if _favicon_service is not None:
            _favicon_service.shutdown()
            _favicon_service = None
