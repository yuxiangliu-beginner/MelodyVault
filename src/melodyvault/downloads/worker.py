"""Qt adapter; queue creation and network/disk work stay in worker threads."""
from uuid import uuid4
from PySide6.QtCore import QThread,Signal
from melodyvault.downloads.targets import from_song


class DownloadWorker(QThread):
    completed=Signal(str);failed=Signal(str)
    def __init__(self,manager,action='run',catalog=None,source=None,parent=None):
        super().__init__(parent);self.manager=manager;self.action=action;self.catalog=catalog;self.source=source;self.stop_action=None
    def request_stop(self,action):self.stop_action=action
    def run(self):
        try:
            if self.action=='enqueue':
                settings=self.manager.repository.settings();batch=str(uuid4());count=0
                for song in self.catalog.songs:
                    target=from_song(self.catalog.artist,song,self.catalog.summary.get('selection_scope')=='recording')
                    jid=self.manager.repository.enqueue(target,settings,batch,self.source);count+=1
                    if self.stop_action:self.manager.stop(jid,self.stop_action)
                self.completed.emit(f'已关联{count}首歌曲任务；'+(self.stop_action+'；' if self.stop_action else '')+('仅dry-run，不会下载音频' if not settings.automatic_download else '实际下载已开启；点击开始任务执行'))
            elif self.action=='cleanup':self.manager.cleanup();self.completed.emit('已按设置清理可安全识别的本任务临时文件')
            else:
                if self.action=='retry':self.manager.retry_failed()
                self.manager.run();self.completed.emit('本次队列处理结束；只有COMPLETED表示验证成功归档')
        except Exception as error:self.failed.emit(f'{type(error).__name__}: {error}')
