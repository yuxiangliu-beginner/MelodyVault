"""Bounded independent search tasks. Providers must enforce network timeouts.

Callbacks are delivered on the caller's thread; GUI callers must invoke this
from a worker and relay callbacks through Qt signals.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, field
from typing import Protocol
import threading

from melodyvault.catalog.musicbrainz import check_cancel


@dataclass(frozen=True)
class UnifiedCandidate:
    provider_id: str
    source_url: str
    source_title: str
    artist_name: str = ''
    song_title: str = ''
    recording_id: str = ''
    duration: float | None = None
    version_type: str = 'UNKNOWN'
    match_score: int = 0
    media_format: str = ''
    is_full_audio: bool | None = None
    download_permission: str = 'PERMISSION_UNKNOWN'
    permission_evidence: dict = field(default_factory=dict)
    availability_status: str = 'UNKNOWN'
    raw_source: dict = field(default_factory=dict)


class SearchProvider(Protocol):
    provider_id: str
    def get_status(self) -> dict: ...
    def search(self, query): ...


class SearchOrchestrator:
    def __init__(self, providers, max_workers=3, cancel=None, on_result=None):
        if not 1 <= max_workers <= 4:
            raise ValueError('并发数须为 1–4')
        self.providers = tuple(providers)
        if len({p.provider_id for p in self.providers}) != len(self.providers):
            raise ValueError('来源 ID 不得重复')
        self.max_workers = max_workers
        self.cancel = cancel or threading.Event()
        self.on_result = on_result or (lambda event: None)

    def search(self, query):
        check_cancel(self.cancel)
        executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix='mv-search')
        pending = {}
        results = {}
        try:
            for provider in self.providers:
                check_cancel(self.cancel)
                try:
                    status = provider.get_status()
                    if status.get('status') != 'AVAILABLE':
                        event = {'provider_id':provider.provider_id, **status, 'candidates':[]}
                        results[provider.provider_id] = event
                        self.on_result(event)
                        continue
                    pending[executor.submit(provider.search, query)] = provider.provider_id
                except Exception as error:
                    event = {'provider_id':provider.provider_id, 'status':'FAILED', 'error':str(error), 'candidates':[]}
                    results[provider.provider_id] = event
                    self.on_result(event)
            while pending:
                check_cancel(self.cancel)
                done, _ = wait(pending, timeout=.1, return_when=FIRST_COMPLETED)
                check_cancel(self.cancel)
                for future in done:
                    provider_id = pending.pop(future)
                    try:
                        candidates = future.result()
                        if not all(isinstance(c, UnifiedCandidate) and c.provider_id == provider_id for c in candidates):
                            raise ValueError('来源返回无效的统一候选')
                        # Deduplicate only the same source URL and version. Different
                        # performances/versions never collapse on title alone.
                        unique = {(c.provider_id, c.raw_source.get('external_id',''), c.source_url, c.recording_id, c.version_type):c for c in candidates}
                        event = {'provider_id':provider_id, 'status':'COMPLETED', 'candidates':list(unique.values())}
                    except Exception as error:
                        event = {'provider_id':provider_id, 'status':'FAILED', 'error':str(error), 'candidates':[]}
                    results[provider_id] = event
                    self.on_result(event)
            return results
        finally:
            for future in pending: future.cancel()
            # Do not let a provider outlive its owning QThread/SQLite session.
            # Network providers are required to use bounded I/O timeouts.
            executor.shutdown(wait=True, cancel_futures=True)
