"""Download one remote video original (Commons or Internet Archive) for audio extraction.

Official file metadata, size and checksum are always verified. The file-level
license requirement follows the user's "只下载许可已核验的文件" setting.
"""
import hashlib,threading,tempfile,re
from pathlib import Path
from urllib.parse import urlsplit,unquote,quote,urljoin
from PySide6.QtCore import QThread,Signal
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.providers.commons import clean
from melodyvault.sources.http import SourceHTTP
from melodyvault.downloads.security import audio_client,validate_url,resource_identity

VIDEO=('.mp4','.m4v','.mkv','.webm','.ogv','.mov','.avi','.mpeg','.mpg')


class ArchiveVideoWorker(QThread):
    """A public Internet Archive video; Archive's own access controls are never bypassed."""
    ready=Signal(object);failed=Signal(str);progress=Signal(str)
    MAX_BYTES=2*1024**3
    def __init__(self,url,directory,parent=None,require_license=True,transport=None):
        super().__init__(parent);self.url=url;self.directory=Path(directory);self.require_license=require_license
        self.transport=transport;self.cancel_event=threading.Event();self.part=None
    def cancel(self):self.cancel_event.set()
    @staticmethod
    def parse(url):
        p=urlsplit(url.strip())
        if p.scheme!='https' or (p.hostname or '').lower() not in {'archive.org','www.archive.org'} or p.username or p.port not in (None,443):
            raise ValueError('不是 Internet Archive 的 https 网址')
        parts=[unquote(x) for x in p.path.split('/') if x]
        if len(parts)<2 or parts[0] not in {'details','download'}:raise ValueError('请使用 archive.org/details/… 或 archive.org/download/… 网址')
        return parts[1],'/'.join(parts[2:])
    def run(self):
        from melodyvault.providers.archive import restricted_item,file_title,text,repair_text
        try:
            if self.require_license:raise ValueError('已开启“只下载许可已核验的文件”；Archive 上传者声明的许可无法核验')
            identifier,filename=self.parse(self.url)
            with SourceHTTP(self.cancel_event) as http:item=http.json('https://archive.org/metadata/'+quote(identifier,safe=''))
            if not item.get('files'):raise ValueError('Archive 条目不存在或没有文件')
            if restricted_item(item):raise ValueError('Archive 条目受访问限制，不尝试绕过')
            videos=[f for f in item['files'] if f.get('name','').lower().endswith(VIDEO) and f.get('private') not in ('true',True)]
            if filename:
                file=next((f for f in videos if f['name']==filename),None)
                if file is None:raise ValueError('该文件不是条目中可用的视频')
            else:
                originals=[f for f in videos if f.get('source')=='original'] or videos
                if not originals:raise ValueError('条目中没有可用的视频文件')
                if len(originals)>1:raise ValueError(f'条目中有 {len(originals)} 个视频，请粘贴具体文件的网址：archive.org/download/{identifier}/文件名')
                file=originals[0]
            size=int(file.get('size') or 0);md5=str(file.get('md5','')).lower()
            if not 0<size<=self.MAX_BYTES or not re.fullmatch(r'[0-9a-f]{32}',md5):raise ValueError('视频大小或官方校验值缺失，或超过 2 GB')
            meta=item.get('metadata',{})
            title=file_title(file) if file.get('title') else clean(repair_text(meta.get('title'))) or Path(file['name']).stem
            url='https://archive.org/download/'+quote(identifier,safe='')+'/'+quote(file['name'],safe='')
            self.directory.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.directory,prefix='mv-video-',suffix=Path(file['name']).suffix,delete=False) as out:
                self.part=Path(out.name);digest=hashlib.md5();received=0
                with audio_client(transport=self.transport) as client:
                    for _ in range(4):  # /download/ redirects to the storage node; every hop is re-checked
                        check_cancel(self.cancel_event);validate_url('archive',url)
                        response=client.send(client.build_request('GET',url),stream=True)
                        if response.status_code not in {301,302,303,307,308}:break
                        url=urljoin(url,response.headers.get('Location',''));response.close()
                    else:raise ValueError('重定向次数过多')
                    try:
                        if response.status_code!=200:raise ValueError(f'来源返回 HTTP {response.status_code}')
                        for block in response.iter_bytes(65536):
                            check_cancel(self.cancel_event);received+=len(block)
                            if received>size:raise ValueError('下载大小超过官方文件大小')
                            out.write(block);digest.update(block);self.progress.emit(f'正在下载视频：{received}/{size} 字节')
                    finally:response.close()
            if received!=size or digest.hexdigest()!=md5:raise ValueError('视频大小或 MD5 校验不一致')
            check_cancel(self.cancel_event)
            self.ready.emit({'path':str(self.part),'source_url':self.url,'license_url':text(file.get('licenseurl') or meta.get('licenseurl')),
                             'title':title,'provider':'archive'});self.part=None
        except Exception as error:self.failed.emit('网址处理未完成：'+str(error))
        finally:
            if self.part:self.part.unlink(missing_ok=True)


class CommonsVideoWorker(QThread):
    ready=Signal(object);failed=Signal(str);progress=Signal(str)
    def __init__(self,url,directory,parent=None,require_license=True):
        super().__init__(parent);self.url=url;self.directory=Path(directory);self.require_license=require_license;self.cancel_event=threading.Event();self.part=None
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
            if self.require_license and (not re.fullmatch(r'https://creativecommons\.org/publicdomain/zero/1\.0(?:/deed(?:\.[a-z-]+)?)?',license_url) or value('Restrictions') or re.search(r'copyvio|copyright violation|disputed|license review needed|no permission',value('Categories'),re.I)):
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
