"""Bounded metadata only, pinned public DNS, no cross-origin redirect following."""
import threading,time
from urllib.parse import urlsplit,urljoin
from urllib.robotparser import RobotFileParser
import httpx
from melodyvault.catalog.musicbrainz import RateGate,check_cancel
from melodyvault.downloads.security import audio_client
from melodyvault.downloads.models import DownloadError
from melodyvault.discovery.models import public_url,domain_key

GATES={};LOCK=threading.Lock()


class DiscoveryHTTP:
    def __init__(self,cancel=None,transport=None,interval=1.1):
        self.cancel=cancel or threading.Event();self.client=audio_client(15,transport)
        self.requests=0;self.retries=0;self.interval=interval
    def __enter__(self):return self
    def __exit__(self,*args):self.client.close()
    def get(self,url,params=None,headers=None,limit=512*1024):
        url=public_url(url);host=urlsplit(url).hostname
        with LOCK:gate=GATES.setdefault(host,RateGate(self.interval))
        for attempt in range(3):
            check_cancel(self.cancel);gate.wait(self.cancel);self.requests+=1
            with self.client.stream('GET',url,params=params,headers=headers) as r:
                if r.status_code in {429,503,502,504} and attempt<2:
                    try:delay=max(2**(attempt+1),float(r.headers.get('Retry-After',0)))
                    except ValueError:delay=2**(attempt+1)
                    if delay>60:raise ValueError('Retry-After 过长，请稍后重试')
                    self.retries+=1
                    if self.cancel.wait(delay):check_cancel(self.cancel)
                    continue
                if r.is_redirect:
                    raise ValueError('重定向未自动跟随：'+r.headers.get('location','')[:180])
                r.raise_for_status()
                kind=r.headers.get('content-type','').split(';')[0]
                if not any(v in kind for v in ('text/','json','xml')):raise ValueError('仅调查文本/JSON；拒绝媒体和可执行文件')
                if int(r.headers.get('content-length','0') or 0)>limit:raise ValueError('调查响应超出大小上限')
                data=bytearray()
                for block in r.iter_bytes():
                    check_cancel(self.cancel);data.extend(block)
                    if len(data)>limit:raise ValueError('调查响应超出大小上限')
                return httpx.Response(r.status_code,headers=r.headers,content=bytes(data),request=r.request)
        raise ValueError('调查重试结束')
    def robots(self,url):
        p=urlsplit(public_url(url));base=f'https://{p.hostname}/robots.txt'
        try:r=self.get(base,limit=128*1024)
        except httpx.HTTPStatusError as e:
            if e.response.status_code==404:return True,'robots.txt HTTP 404；仅允许有限公开元数据检查，未证明下载权限'
            return None,str(e)
        except DownloadError:raise
        except Exception as e:return None,str(e)
        parser=RobotFileParser();parser.parse(r.text.splitlines())
        return parser.can_fetch('MelodyVault',url),base
