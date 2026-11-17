from melodyvault.downloads.remote_video import CommonsVideoWorker

def test_remote_video_rejects_unapproved_url_without_network(tmp_path):
    worker=CommonsVideoWorker('https://example.org/video.mp4',tmp_path);errors=[]
    worker.failed.connect(errors.append);worker.run()
    assert errors and '仅支持 Wikimedia Commons' in errors[0]
    assert not list(tmp_path.iterdir())


import hashlib
from pathlib import Path
import httpx,pytest
from melodyvault.downloads import remote_video
from melodyvault.downloads.remote_video import ArchiveVideoWorker
from melodyvault.sources.http import SourceHTTP

VIDEO=b'\x00\x00\x00\x18ftypmp42'+b'\x00'*1000


def metadata(monkeypatch,payload):
    monkeypatch.setattr(remote_video,'SourceHTTP',lambda cancel:SourceHTTP(cancel,transport=httpx.MockTransport(lambda request:httpx.Response(200,json=payload)),interval=0,max_attempts=1))


def run(worker):
    out={'ready':[],'failed':[]};worker.ready.connect(out['ready'].append);worker.failed.connect(out['failed'].append);worker.run();return out


def video_item(**extra):
    return {'metadata':{'title':'Unit MV','creator':'Unit Test'},'files':[
        {'name':'mv.mp4','source':'original','size':str(len(VIDEO)),'md5':hashlib.md5(VIDEO).hexdigest()},
        {'name':'mv.ogv','source':'derivative','original':'mv.mp4','size':'5','md5':'0'*32}],**extra}


def node(body=VIDEO,calls=None):
    def transport(request):
        if calls is not None:calls.append(str(request.url))
        if request.url.host=='archive.org':return httpx.Response(302,headers={'Location':'https://ia800300.us.archive.org/12/items/unit-mv/mv.mp4'})
        return httpx.Response(200,content=body,headers={'Content-Type':'video/mp4'})
    return httpx.MockTransport(transport)


def test_archive_video_follows_storage_redirect_and_verifies_md5(tmp_path,monkeypatch):
    metadata(monkeypatch,video_item());calls=[]
    out=run(ArchiveVideoWorker('https://archive.org/details/unit-mv',tmp_path,require_license=False,transport=node(calls=calls)))
    assert not out['failed'],out
    record=out['ready'][0]
    assert Path(record['path']).read_bytes()==VIDEO and record['provider']=='archive' and record['title']=='Unit MV'
    assert calls==['https://archive.org/download/unit-mv/mv.mp4','https://ia800300.us.archive.org/12/items/unit-mv/mv.mp4']


@pytest.mark.parametrize('case,message',[
    ('strict','只下载许可已核验的文件'),('dark','受访问限制'),('nodownload','受访问限制'),
    ('tampered','校验不一致'),('two_videos','请粘贴具体文件的网址'),('other_site','不是 Internet Archive')])
def test_archive_video_refusals_leave_no_files(tmp_path,monkeypatch,case,message):
    item=video_item(is_dark=case=='dark',nodownload=case=='nodownload')
    if case=='two_videos':item['files'].append({'name':'part2.mp4','source':'original','size':'9','md5':'1'*32})
    metadata(monkeypatch,item)
    url='https://evil.example/details/unit-mv' if case=='other_site' else 'https://archive.org/details/unit-mv'
    body=b'\x01'*len(VIDEO) if case=='tampered' else VIDEO
    out=run(ArchiveVideoWorker(url,tmp_path,require_license=case=='strict',transport=node(body)))
    assert out['failed'] and message in out['failed'][0] and not out['ready']
    assert not list(tmp_path.iterdir())


def test_commons_video_license_requirement_follows_the_setting(tmp_path,monkeypatch):
    info={'url':'https://upload.wikimedia.org/wikipedia/commons/a/ab/Clip.webm','mime':'video/webm','size':len(VIDEO),'sha1':hashlib.sha1(VIDEO).hexdigest(),
          'extmetadata':{'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/4.0/'},'Restrictions':{'value':''},'Categories':{'value':''}}}
    metadata(monkeypatch,{'query':{'pages':[{'imageinfo':[info]}]}})
    monkeypatch.setattr(remote_video,'audio_client',lambda *a,**k:httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=VIDEO))))
    url='https://commons.wikimedia.org/wiki/File:Clip.webm'
    strict=run(CommonsVideoWorker(url,tmp_path/'strict'))
    assert strict['failed'] and 'CC0' in strict['failed'][0]
    relaxed=run(CommonsVideoWorker(url,tmp_path/'relaxed',require_license=False))
    assert not relaxed['failed'],relaxed
    assert Path(relaxed['ready'][0]['path']).read_bytes()==VIDEO
