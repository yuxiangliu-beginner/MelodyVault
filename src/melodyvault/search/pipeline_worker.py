import threading
from PySide6.QtCore import QThread,Signal
from melodyvault.search.pipeline import UnifiedMusicSearchService


class PipelineWorker(QThread):
    progress=Signal(object);completed=Signal(object);failed=Signal(str)
    def __init__(self,path,artist,song,parent=None,dry_run=False):
        super().__init__(parent);self.path=path;self.artist=artist;self.song=song;self.dry_run=dry_run;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        try:
            result=UnifiedMusicSearchService(self.path,self.cancel_event,self.progress.emit).run(self.artist,self.song,explicit_selection=True,dry_run=self.dry_run)
            self.completed.emit(result)
        except Exception as e:self.failed.emit(f'{type(e).__name__}: {e}')


class BatchPipelineWorker(QThread):
    progress=Signal(object);completed=Signal(object);failed=Signal(str)
    def __init__(self,path,artist,selections,parent=None,dry_run=False):
        super().__init__(parent);self.path=path;self.artist=artist;self.selections=selections
        self.dry_run=dry_run;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        results=[]
        try:
            for song,explicit in self.selections:
                if self.cancel_event.is_set():break
                self.progress.emit({'stage':'batch','title':song.title,'completed':len(results),'total':len(self.selections)})
                result=UnifiedMusicSearchService(self.path,self.cancel_event,self.progress.emit).run(
                    self.artist,song,explicit_selection=explicit,dry_run=self.dry_run)
                results.append(result)
                if result['status']=='CANCELLED':break
            self.completed.emit({'status':'CANCELLED' if self.cancel_event.is_set() else 'BATCH_COMPLETED',
                                 'results':results,'total':len(self.selections),'attempts':[]})
        except Exception as error:self.failed.emit(f'{type(error).__name__}: {error}')
