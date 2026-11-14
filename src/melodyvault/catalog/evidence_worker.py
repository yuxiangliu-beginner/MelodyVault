import threading
import time
from PySide6.QtCore import QThread, Signal
from melodyvault.catalog.evidence import enrich_artist
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.catalog.review import ReviewService
from melodyvault.database.catalog import CatalogRepository


class EvidenceWorker(QThread):
    progress=Signal(str)
    completed=Signal(object)
    failed=Signal(str)
    cancelled=Signal(str)

    def __init__(self,path,artist,force=False,parent=None):
        super().__init__(parent);self.path=path;self.artist=artist;self.force=force;self.cancel_event=threading.Event()

    def cancel(self):self.cancel_event.set()

    def run(self):
        client=None;started=time.perf_counter()
        try:
            started=time.perf_counter();repo=CatalogRepository(self.path)
            with MusicBrainzClient(repo,self.cancel_event,self.force,notice=self.progress.emit) as client:
                stats=enrich_artist(repo,client,self.artist,lambda p:self.progress.emit(p.message))
            result=ReviewService(repo).load(self.artist)['result']
            result.summary.update(stats,api_requests=client.requests,cache_hits=client.cache_hits,evidence_seconds=time.perf_counter()-started)
            self.completed.emit(result)
        except CatalogCancelled as error:self.cancelled.emit(str(error))
        except Exception as error:self.failed.emit(f'{type(error).__name__}: {error}')
        finally:
            self.metrics={'api_requests':client.requests if client else 0,'cache_hits':client.cache_hits if client else 0,
                          'retries':client.retries if client else 0,'seconds':time.perf_counter()-started}
