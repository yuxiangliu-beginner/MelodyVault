import os,threading
from PySide6.QtCore import QThread,Signal
from melodyvault.database.sources import SourceRepository
from melodyvault.sources.engine import SourceSearchEngine
from melodyvault.providers.archive import ArchiveProvider
from melodyvault.providers.commons import CommonsProvider
from melodyvault.providers.jamendo import JamendoProvider


def default_providers():
    from melodyvault.providers.ccmixter import CCMixterProvider
    from melodyvault.providers.openverse import OpenverseProvider
    return [ArchiveProvider(),CommonsProvider(),JamendoProvider(os.environ.get('JAMENDO_CLIENT_ID','')),CCMixterProvider(),OpenverseProvider()]


class SourceWorker(QThread):
    progress=Signal(object);completed=Signal(object);failed=Signal(str)
    def __init__(self,path,artist,songs,works,force=False,mode='all',parent=None,browser=False):
        super().__init__(parent);self.path=path;self.artist=artist;self.songs=songs;self.works=works;self.force=force;self.mode=mode;self.browser=browser;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        try:
            providers=default_providers()
            if self.browser:
                from melodyvault.sources.browser import BrowserArchiveProvider
                providers.append(BrowserArchiveProvider())
            if self.works is None:
                from melodyvault.database.catalog import CatalogRepository
                self.works=CatalogRepository(self.path).works()
            result=SourceSearchEngine(SourceRepository(self.path),providers,self.cancel_event,self.progress.emit).search(
                self.artist,self.songs,self.works,self.force,self.mode)
            self.completed.emit(result)
        except Exception as error:self.failed.emit(f'{type(error).__name__}: {error}')
