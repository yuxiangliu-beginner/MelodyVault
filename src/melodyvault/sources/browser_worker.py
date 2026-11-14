import threading
from dataclasses import asdict
from PySide6.QtCore import QThread,Signal
from melodyvault.sources.http import SourceHTTP
from melodyvault.sources.browser import PublicBrowser
from melodyvault.database.sources import SourceRepository


class BrowserCheckWorker(QThread):
    completed=Signal(object);failed=Signal(str)
    def __init__(self,path,url,parent=None):
        super().__init__(parent);self.path=path;self.url=url;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        repo=SourceRepository(self.path)
        try:
            with SourceHTTP(self.cancel_event) as http,PublicBrowser(http) as browser:
                result=browser.read(self.url)
            # Public text alone cannot elevate an existing license decision.
            result['license_status']='LICENSE_UNVERIFIED';result['reason']='已读取公开授权说明；网页文本不能独立证明上传者权利或原唱身份'
            result['license_excerpt']='\n'.join(line for line in result['text'].splitlines() if any(term in line.casefold() for term in ('license','copyright','creative commons','rights','版权','許可','许可','授权')))[:4000]
            repo.browser_check(self.url,'read',result);self.completed.emit(result)
        except Exception as error:
            message=f'{type(error).__name__}: {error}'
            repo.browser_check(self.url,'failed',{'error':message});self.failed.emit(message)
