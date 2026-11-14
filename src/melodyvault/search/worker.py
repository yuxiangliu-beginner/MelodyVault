import threading,time
from PySide6.QtCore import QThread,Signal
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.catalog.musicbrainz import MusicBrainzClient,check_cancel
from melodyvault.database.catalog import CatalogRepository
from melodyvault.search.services import UnifiedSearchEngine
from melodyvault.search.selection import SongSelectionService


class SearchWorker(QThread):
    ready=Signal(object);partial=Signal(object);progress=Signal(str);failed=Signal(str);cancelled=Signal(str)
    def __init__(self,path,request,parent=None,candidate=None,title_query=''):
        super().__init__(parent);self.path=path;self.request=request;self.candidate=candidate;self.title_query=title_query;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        started=time.perf_counter();client=None
        try:
            repo=CatalogRepository(self.path)
            with MusicBrainzClient(repo,self.cancel_event,self.request.force_online,notice=self.progress.emit) as client:
                if self.candidate:result=SongSelectionService(repo,client).confirm(self.candidate,self.request,self.title_query)
                else:result=UnifiedSearchEngine(repo,client,self.progress.emit,self.partial.emit).search(self.request)
                check_cancel(self.cancel_event)
            self.ready.emit(result)
        except CatalogCancelled as error:self.cancelled.emit(str(error))
        except Exception as error:self.failed.emit(f'{type(error).__name__}: {error}')
        finally:
            self.metrics={'api_requests':client.requests if client else 0,'retries':client.retries if client else 0,'seconds':time.perf_counter()-started,'cancelled':self.cancel_event.is_set()}
