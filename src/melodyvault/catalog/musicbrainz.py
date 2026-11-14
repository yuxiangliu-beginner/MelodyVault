"""Official JSON API only: descriptive UA, <=1 request/1.1s, bounded retry/cache."""
from email.utils import parsedate_to_datetime
from hashlib import sha256
import json
import threading
import time
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx

from melodyvault import __version__
from melodyvault.catalog.models import CatalogCancelled, CatalogError
from melodyvault.database.catalog import CatalogRepository

BASE_URL = "https://musicbrainz.org/ws/2/"
USER_AGENT = f"MelodyVault/{__version__} (https://github.com/yuxiangliu-beginner/MelodyVault)"
CACHE_MAX_AGE = 7 * 24 * 60 * 60


def check_cancel(event: threading.Event) -> None:
    if event.is_set():
        raise CatalogCancelled("搜索已取消；已保存的 API 页面可在下次搜索时继续使用。")


class RateGate:
    def __init__(self, interval: float = 1.1):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_request = 0.0

    def wait(self, cancel: threading.Event) -> None:
        while not self.lock.acquire(timeout=0.1):
            check_cancel(cancel)
        try:
            check_cancel(cancel)
            delay = max(0.0, self.next_request - time.monotonic())
            if cancel.wait(delay):
                check_cancel(cancel)
            self.next_request = time.monotonic() + self.interval
        finally:
            self.lock.release()


_RATE_GATE = RateGate()


class MusicBrainzClient:
    def __init__(self, repository: CatalogRepository, cancel: threading.Event,
                 force_refresh: bool = False, notice=None, *, transport=None,
                 interval: float = 1.1, max_attempts: int = 5, retry_base: float = 2.0):
        self.repository = repository
        self.cancel = cancel
        self.force_refresh = force_refresh
        self.notice = notice or (lambda text: None)
        self.max_attempts = max_attempts
        self.retry_base = retry_base
        self.gate = _RATE_GATE if interval == 1.1 else RateGate(interval)
        self.http = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                                 timeout=httpx.Timeout(20, connect=10), transport=transport,
                                 follow_redirects=False)
        self.requests = 0
        self.cache_hits = 0
        self.retries = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.http.close()

    @staticmethod
    def _validate(endpoint: str, data: dict, params: dict) -> None:
        if not isinstance(data, dict) or data.get("error"):
            raise CatalogError(f"MusicBrainz {endpoint}: {str(data)[:500]}")
        if endpoint.startswith("artist/"):
            valid = isinstance(data.get("id"), str) and isinstance(data.get("name"), str)
        elif endpoint.startswith(("recording/", "work/")):
            valid = isinstance(data.get("id"), str) and isinstance(data.get("title"), str)
        elif endpoint.startswith('release/'):
            valid = isinstance(data.get('id'),str) and isinstance(data.get('title'),str) and isinstance(data.get('media'),list)
        elif endpoint.startswith('isrc/'):
            valid = isinstance(data.get('recordings'),list)
        else:
            key = {"artist": "artists", "recording": "recordings", "release": "releases",
                   "release-group": "release-groups", "work": "works"}[endpoint]
            count_key = "count" if "query" in params else f"{endpoint}-count"
            valid = (isinstance(data.get(key), list) and isinstance(data.get(count_key), int)
                     and data[count_key] >= 0 and all(isinstance(item, dict) and item.get("id")
                                                     for item in data[key]))
        if not valid:
            raise CatalogError(f"MusicBrainz {endpoint} 返回的数据结构不完整，未标记成功。")

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
            detail = payload.get("error", payload) if isinstance(payload, dict) else payload
        except ValueError:
            detail = response.text or response.reason_phrase
        return " ".join(str(detail).split())[:500]

    def _retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        header = response.headers.get("Retry-After") if response is not None else None
        if header:
            try:
                delay = float(header)
            except ValueError:
                try:
                    delay = parsedate_to_datetime(header).timestamp() - time.time()
                except (ValueError, TypeError, OverflowError):
                    delay = self.retry_base * 2 ** attempt
            if delay > 300:
                raise CatalogError(f"MusicBrainz 要求 Retry-After={header}，请稍后重试（不提前重发请求）。")
            return max(0.0, delay, self.retry_base * 2 ** attempt)
        return min(60.0, self.retry_base * 2 ** attempt)

    def get_json(self, endpoint: str, params: dict | None = None, *, _redirects: int=0) -> dict:
        params = {**(params or {}), "fmt": "json"}
        key = sha256(json.dumps([endpoint, params], sort_keys=True).encode("utf-8")).hexdigest()
        check_cancel(self.cancel)
        if not self.force_refresh:
            cached = self.repository.cached_response(key, CACHE_MAX_AGE)
            if cached is not None:
                try:
                    self._validate(endpoint, cached, params)
                except CatalogError:
                    pass  # A damaged cache entry must not prevent a real retry.
                else:
                    self.cache_hits += 1
                    return cached
        last_error = ""
        for attempt in range(self.max_attempts):
            self.gate.wait(self.cancel)
            response = None
            self.requests += 1
            try:
                response = self.http.get(BASE_URL + endpoint, params=params)
            except httpx.RequestError as error:
                last_error = f"MusicBrainz GET {endpoint}: {type(error).__name__}: {error}"
            else:
                check_cancel(self.cancel)
                if response.status_code in {301,302,307,308} and endpoint.startswith('recording/'):
                    location=urljoin(str(response.url),response.headers.get('Location',''))
                    parsed=urlparse(location)
                    if _redirects>=3 or parsed.scheme!='https' or parsed.netloc!='musicbrainz.org' or not parsed.path.startswith('/ws/2/recording/'):
                        raise CatalogError('MusicBrainz recording 重定向不合法或循环，未跟随')
                    canonical=parsed.path.rstrip('/').rsplit('/',1)[-1]
                    try:UUID(canonical)
                    except ValueError as error:raise CatalogError('MusicBrainz 重定向缺少合法 Recording MBID') from error
                    data=self.get_json(f'recording/{canonical}',params,_redirects=_redirects+1)
                    self.repository.save_recording_redirect(endpoint.split('/')[1],data['id'],location)
                    self.repository.cache_response(key,data)
                    return data
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except ValueError as error:
                        raise CatalogError(f"MusicBrainz GET {endpoint}: HTTP 200 但 JSON 解析失败：{error}") from error
                    self._validate(endpoint, data, params)
                    self.repository.cache_response(key, data)
                    return data
                last_error = (f"MusicBrainz GET {endpoint}: HTTP {response.status_code} "
                              f"{self._error_detail(response)}")
                if response.status_code not in {429, 500, 502, 503, 504}:
                    raise CatalogError(last_error)
            check_cancel(self.cancel)
            if attempt + 1 == self.max_attempts:
                break
            delay = self._retry_delay(response, attempt)
            self.retries += 1
            self.notice(f"{last_error}；{delay:g} 秒后重试（{attempt + 2}/{self.max_attempts}）")
            if self.cancel.wait(delay):
                check_cancel(self.cancel)
        raise CatalogError(f"{last_error}（已尝试 {self.max_attempts} 次；可点击重试复用已保存页面）")
