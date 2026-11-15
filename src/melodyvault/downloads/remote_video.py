"""Download a Commons CC0 original only after checking official file metadata."""
import hashlib,threading,tempfile,re
from pathlib import Path
from urllib.parse import urlsplit,unquote
from PySide6.QtCore import QThread,Signal
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.providers.commons import clean
from melodyvault.sources.http import SourceHTTP
from melodyvault.downloads.security import audio_client,validate_url,resource_identity

class CommonsVideoWorker(QThread):
    ready=Signal(object);failed=Signal(str);progress=Signal(str)
    def __init__(self,url,directory,parent=None):
        super().__init__(parent);self.url=url;self.directory=Path(directory);self.cancel_event=threading.Event();self.part=None
    def cancel(self):self.cancel_event.set()
    def run(self):
        try:
            p=urlsplit(self.url)
            direct=p.hostname=='upload.wikimedia.org'
            if direct:
                validate_url('commons',self.url);title='File:'+unquote(p.path.rsplit('/',1)[-1]).replace('_',' ')
            elif p.scheme=='https' and p.hostname=='commons.wikimedia.org' and not p.username and not p.query and not p.fragment and p.port in (None,443) and p.path.startswith('/wiki/File:'):
                title=unquote(p.path[len('/wiki/'):]).replace('_',' ')
            else:raise ValueError('目前仅支持 Wikimedia Commons 文件页或原始文件网址')
            if '/' in title or not title.lower().endswith(('.webm','.ogv','.mp4','.mov')):raise ValueError('网址不是受支持的视频文件页')
            with SourceHTTP(self.cancel_event) as http:
                data=http.json('https://commons.wikimedia.org/w/api.php',{'action':'query','format':'json','formatversion':2,'titles':title,'prop':'imageinfo','iiprop':'url|mime|size|sha1|extmetadata','iiextmetadatalanguage':'en','maxlag':5})
            pages=data.get('query',{}).get('pages',[]);info=next(iter(pages[0].get('imageinfo',[])),{}) if pages else {};ext=info.get('extmetadata',{})
            value=lambda k:clean(ext.get(k,{}).get('value',''))
            if info.get('mime') not in {'video/webm','video/ogg','video/mp4','video/quicktime'}:raise ValueError('来源未提供受支持的完整视频文件')
            license_url=value('LicenseUrl').rstrip('/').replace('http://','https://')
            if not re.fullmatch(r'https://creativecommons\.org/publicdomain/zero/1\.0(?:/deed(?:\.[a-z-]+)?)?',license_url) or value('Restrictions') or re.search(r'copyvio|copyright violation|disputed|license review needed|no permission',value('Categories'),re.I):
                raise ValueError('该视频尚无可核验的 CC0 文件授权')
            size=int(info.get('size') or 0);digest=info.get('sha1','');original=info.get('url','')
            if direct and resource_identity(self.url)!=resource_identity(original):raise ValueError('网址与官方原始视频不一致')
            if not 0<size<=256*1024*1024 or not digest:raise ValueError('视频大小或官方校验值缺失')
            validate_url('commons',original)
            expected=digest.lower() if len(digest)==40 else f'{int(digest,36):040x}'
            self.directory.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.directory,prefix='mv-video-',suffix=Path(title).suffix,delete=False) as file:
                self.part=Path(file.name);h=hashlib.sha1();received=0
                with audio_client() as client,client.stream('GET',original) as response:
                    if response.status_code!=200:raise ValueError(f'来源返回 HTTP {response.status_code}')
                    for block in response.iter_bytes(65536):
                        check_cancel(self.cancel_event);received+=len(block)
                        if received>size:raise ValueError('下载大小超过官方文件大小')
                        file.write(block);h.update(block);self.progress.emit(f'正在下载视频：{received}/{size} 字节')
            if received!=size or h.hexdigest()!=expected:raise ValueError('视频大小或 SHA-1 校验不一致')
            check_cancel(self.cancel_event);self.ready.emit({'path':str(self.part),'source_url':self.url,'license_url':license_url,'title':title[5:].rsplit('.',1)[0]});self.part=None
        except Exception as error:self.failed.emit('网址处理未完成：'+str(error))
        finally:
            if self.part:self.part.unlink(missing_ok=True)
