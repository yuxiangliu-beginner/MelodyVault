"""QObject receivers keep all generation checks and widget updates on Qt's UI thread."""
from PySide6.QtCore import QObject,Slot


class RequestRelay(QObject):
    def __init__(self,owner,worker,generation,callbacks,catalog=False):
        super().__init__(owner);self.owner=owner;self.worker=worker;self.generation=generation;self.callbacks=callbacks;self.catalog=catalog
    def deliver(self,key,data):
        callback=self.callbacks.get(key)
        if callback:self.owner._deliver(self.generation,callback,data)
    @Slot(object)
    def ready(self,data):self.deliver('ready',data)
    @Slot(object)
    def progress(self,data):self.deliver('progress',data)
    @Slot(str)
    def text_progress(self,data):self.deliver('progress',data)
    @Slot(object)
    def partial(self,data):self.deliver('partial',data)
    @Slot(object)
    def choices(self,data):self.deliver('choices',data)
    @Slot(str)
    def failed(self,data):self.deliver('failed',data)
    @Slot(str)
    def cancelled(self,data):self.deliver('cancelled',data)
    @Slot()
    def finished(self):
        if self.catalog:self.owner._catalog_finished(self.worker,self.generation)
        else:self.owner._unified_finished(self.worker,self.generation)
        self.deleteLater()
