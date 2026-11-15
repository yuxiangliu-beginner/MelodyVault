"""Bounded official metadata requests, one shared rate gate per host."""
import threading
from urllib.parse import urlsplit
from email.utils import parsedate_to_datetime
import time
import os
import httpx
from melodyvault.catalog.musicbrainz import RateGate, check_cancel
from melodyvault.catalog.models import CatalogError
from melodyvault import __version__

UA=f'MelodyVault/{__version__} (+https://github.com/yuxiangliu-beginner/MelodyVault; Python desktop metadata client)'+(' '+os.environ['MELODYVAULT_AGENT_ID'] if os.environ.get('MELODYVAULT_AGENT_ID') else '')
HOSTS={'archive.org','commons.wikimedia.org','api.jamendo.com','ccmixter.org','api.openverse.org'}
GATES={host:RateGate(1.1) for host in HOSTS}


class SourceHTTP:
    def __init__(self,cancel=None,notice=None,transport=None,interval=None,max_attempts=3):
        self.cancel=cancel or threading.Event();self.notice=notice or (lambda message:None)
        self.client=httpx.Client(timeout=httpx.Timeout(20,connect=10),headers={'User-Agent':UA},transport=transport,follow_redirects=False)
        self.interval=interval;self.max_attempts=max_attempts;self.requests=0;self.retries=0
    def __enter__(self):return self
    def __exit__(self,*args):self.client.close()
    def get(self,url,params=None):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.hostname not in HOSTS or parsed.username or parsed.port not in (None,443):
            raise CatalogError('不允许访问此来源地址')
        # Deliberately no media endpoints: this client only reads metadata/pages/robots.
        if parsed.path.startswith('/download/') or parsed.path.endswith(('.mp3','.flac','.ogg','.wav','.m4a')):
            raise CatalogError('Phase 2 不请求音频内容')
        last=''
        for attempt in range(self.max_attempts):
            check_cancel(self.cancel)
            (GATES[parsed.hostname] if self.interval is None else RateGate(self.interval)).wait(self.cancel)
            response=None;self.requests+=1
            try:
                response=self.client.get(url,params=params)
            except httpx.RequestError as error:last=f'{type(error).__name__}: {error}'
            else:
                check_cancel(self.cancel)
                if response.status_code==200:return response
                last=f'HTTP {response.status_code}: {response.text[:160]}'
                if response.status_code not in {429,500,502,503,504}:
                    raise CatalogError(f'{parsed.hostname} {last}')
            if attempt+1>=self.max_attempts:break
            delay=2**(attempt+1)
            if response is not None and response.headers.get('Retry-After'):
                value=response.headers['Retry-After']
                try:server_delay=float(value)
                except ValueError:
                    try:server_delay=parsedate_to_datetime(value).timestamp()-time.time()
                    except (ValueError,TypeError,OverflowError):server_delay=delay
                delay=max(delay,server_delay)
            if delay>300:raise CatalogError(f'{parsed.hostname} Retry-After 过长，请稍后重试')
            self.retries+=1;self.notice(f'{parsed.hostname} {last}；{delay:g}秒后重试')
            if self.cancel.wait(delay):check_cancel(self.cancel)
        raise CatalogError(f'{parsed.hostname} {last}；已尝试{self.max_attempts}次')
    def json(self,url,params=None):
        response=self.get(url,params)
        try:data=response.json()
        except ValueError as error:raise CatalogError('来源未返回有效JSON；不改用浏览器绕过访问限制') from error
        if not isinstance(data,dict):raise CatalogError('来源JSON结构不正确')
        return data
