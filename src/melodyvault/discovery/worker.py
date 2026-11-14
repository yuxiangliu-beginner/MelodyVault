import threading
from PySide6.QtCore import QThread,Signal
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.database.discovery import DiscoveryRepository
from melodyvault.discovery.service import SourceDiscoveryService


class DiscoveryWorker(QThread):
    progress=Signal(object);completed=Signal(object);failed=Signal(str)
    def __init__(self,path,artist='',title='',domain=None,force=False,parent=None):
        super().__init__(parent);self.path=path;self.artist=artist;self.title=title
        self.domain=domain;self.force=force;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        try:
            service=SourceDiscoveryService(DiscoveryRepository(self.path),self.cancel_event,self.progress.emit)
            result=service.initialize_compiled() if self.domain=='__compiled__' else service.check(self.domain) if self.domain else service.discover(self.artist,self.title,force=self.force)
            self.completed.emit(result)
        except CatalogCancelled:self.completed.emit({'cancelled':True,'message':'已取消，已保存的来源保留'})
        except Exception as e:self.failed.emit(f'{type(e).__name__}: {e}')
