"""License checking is a user setting (off by default); safety and integrity checks are not."""
import hashlib,json,threading
from pathlib import Path
import httpx,pytest
from melodyvault.database import connect
from melodyvault.downloads.eligibility import DownloadEligibilityService,license_required
from melodyvault.downloads.models import DownloadError
from melodyvault.downloads.security import validate_url
from melodyvault.downloads.fallback import SourceFallbackManager
from melodyvault.search.orchestrator import UnifiedCandidate
from melodyvault.sources.http import SourceHTTP
from test_downloads import setup,audio,manager,good,opt_in,approve

DETAILS='https://archive.org/details/unit-item'
NODE='https://dn710003.ca.archive.org/0/items/unit-item/Track-01.wav'


@pytest.fixture
def archive(setup,audio):
    repo,settings,target,raw,response,factory=setup
    target.update(namespace='archive',recording_id='archive:unit-item/Track-01.wav',source_page_url=DETAILS)
    raw.update(provider='archive',external_id='unit-item/Track-01.wav',page_url=DETAILS,license_status='LICENSE_UNVERIFIED')
    item={'metadata':{'identifier':'unit-item','title':'Unit Album','creator':'Unit Test'},
          'files':[{'name':'Track-01.wav','source':'original','title':'Test tone','creator':'Unit Test','length':'1.0',
                    'size':str(len(audio)),'md5':hashlib.md5(audio).hexdigest(),'sha1':hashlib.sha1(audio).hexdigest()}]}
    def metadata(request):
        assert request.url.path=='/metadata/unit-item';return httpx.Response(200,json=item)
    def archive_factory(cancel=None,notice=None):
        return SourceHTTP(cancel,notice,transport=httpx.MockTransport(metadata),interval=0,max_attempts=1)
    return repo,settings,target,raw,item,archive_factory


def verify(archive,require_license=False):
    repo,settings,target,raw,item,factory=archive
    with factory() as http:return DownloadEligibilityService(http,require_license=require_license).verify(raw,target)


def strict(repo,value):
    with connect(repo.path) as db:
        db.execute('INSERT OR REPLACE INTO app_metadata(key,value) VALUES (?,?)',('ui.require_license',json.dumps(value)))


def test_setting_defaults_to_off_and_round_trips(setup):
    repo=setup[0]
    assert license_required(repo.path) is False
    strict(repo,True);assert license_required(repo.path) is True
    strict(repo,False);assert license_required(repo.path) is False


def test_unlicensed_archive_file_is_allowed_but_recorded_as_unverified(archive):
    c=verify(archive)
    assert DownloadEligibilityService.allowed(c) and c.evidence['decision']=='READY'
    assert c.license_status=='LICENSE_UNVERIFIED' and c.evidence['license_check']=='SKIPPED'
    assert c.checksums['md5'] and c.checksums['sha1'] and c.file_format=='wav' and c.duration==1.
    assert c.direct_download_url=='https://archive.org/download/unit-item/Track-01.wav'
    assert any('许可未核验' in r for r in c.restrictions)


def test_strict_setting_restores_rejection(archive):
    c=verify(archive,require_license=True)
    assert c.evidence['decision']=='LICENSE_UNVERIFIED' and not DownloadEligibilityService.allowed(c)


@pytest.mark.parametrize('change',['dark','nodownload','restricted','private'])
def test_archive_access_controls_are_never_bypassed(archive,change):
    item=archive[4]
    if change=='dark':item['is_dark']=True
    if change=='nodownload':item['nodownload']=True
    if change=='restricted':item['metadata']['access-restricted-item']='true'
    if change=='private':item['files'][0]['private']='true'
    c=verify(archive)
    assert c.evidence['decision']=='DOWNLOAD_NOT_PERMITTED' and not DownloadEligibilityService.allowed(c)


@pytest.mark.parametrize('change,decision',[('no_checksum','INCOMPLETE_AUDIO'),('missing','INCOMPLETE_AUDIO'),
    ('preview','PREVIEW_ONLY'),('other_file','RECORDING_MISMATCH'),('format','DOWNLOAD_NOT_PERMITTED')])
def test_integrity_and_identity_checks_still_apply_without_license_check(archive,change,decision):
    repo,settings,target,raw,item,factory=archive;f=item['files'][0]
    if change=='no_checksum':del f['md5'],f['sha1']
    if change=='missing':f['name']='Other.wav'
    if change=='preview':f['title']='Test tone preview'
    if change=='other_file':target['recording_id']='archive:unit-item/Track-02.wav'
    if change=='format':
        f['name']='Track-01.exe';raw['external_id']='unit-item/Track-01.exe';target['recording_id']='archive:unit-item/Track-01.exe'
    c=verify(archive)
    assert c.evidence['decision']==decision and not DownloadEligibilityService.allowed(c)


def test_commons_file_without_license_is_allowed_only_when_check_is_off(setup):
    info=setup[4]['query']['pages'][0]['imageinfo'][0];info['extmetadata']['LicenseUrl']['value']=''
    repo,settings,target,raw,response,factory=setup
    with factory() as http:relaxed=DownloadEligibilityService(http,require_license=False).verify(raw,target)
    assert DownloadEligibilityService.allowed(relaxed) and relaxed.license_status=='LICENSE_UNVERIFIED'
    assert not DownloadEligibilityService.allowed(approve(setup))  # library default stays strict


@pytest.mark.parametrize('url,ok',[
    (NODE,True),('https://ia800300.us.archive.org/12/items/unit-item/a.mp3',True),
    ('https://dn710003.ca.archive.org/etc/passwd',False),('https://dn710003.ca.archive.org.evil.example/0/items/x/y.mp3',False),
    ('http://dn710003.ca.archive.org/0/items/x/y.mp3',False),('https://evil.example/0/items/x/y.mp3',False)])
def test_archive_storage_node_redirects(url,ok):
    if ok:validate_url('archive',url)
    else:
        with pytest.raises(DownloadError):validate_url('archive',url)


def test_leading_padding_before_first_frame_uses_declared_parser(tmp_path):
    import mutagen
    from melodyvault.downloads.files import verify_file
    from melodyvault.downloads.models import DownloadCandidate
    # MPEG-1 Layer III, 128 kbps, 44.1 kHz: 417-byte frames, preceded by zero padding
    # exactly like the real 1931 Archive transfer that sniffing rejected.
    # Verification runs on the extension-less .part file, so sniffing has no name hint.
    data=b'\x00'*16+(b'\xff\xfb\x90\x00'+b'\x00'*413)*200
    path=tmp_path/'job.part';path.write_bytes(data)
    assert mutagen.File(path) is None  # the sniffing path really fails here
    c=DownloadCandidate('s','r','a','t','unknown','archive','',file_format='mp3',file_size=len(data))
    assert verify_file(path,c,10**8)['format']=='mp3'
    junk=tmp_path/'junk.part';junk.write_bytes(b'\x00'*4096)
    with pytest.raises(DownloadError) as error:
        verify_file(junk,DownloadCandidate('s','r','a','t','unknown','archive','',file_format='mp3'),10**8)
    assert error.value.code=='MEDIA_FORMAT_INVALID'


def test_archive_download_follows_storage_redirect_and_verifies_bytes(archive,audio):
    repo,settings,target,raw,item,factory=archive;settings=opt_in((repo,settings))
    calls=[]
    def transport(request):
        calls.append(str(request.url))
        if request.url.host=='archive.org':return httpx.Response(302,headers={'Location':NODE})
        return good(audio,request)
    m=manager((repo,settings,target,raw,None,factory),transport)
    attempts=SourceFallbackManager(repo,m,threading.Event()).run(target,[UnifiedCandidate('archive',DETAILS,'Test tone',match_score=100,raw_source=raw)],settings)
    assert attempts[-1]['state']=='COMPLETED',attempts
    assert calls==['https://archive.org/download/unit-item/Track-01.wav',NODE]
    row=repo.get(attempts[-1]['job_id']);files=repo.files('archive','unit-item/Track-01.wav')
    assert row['state']=='COMPLETED' and len(files)==1 and Path(files[0]['path']).read_bytes()==audio
    sidecar=json.loads(Path(files[0]['path']+'.evidence.json').read_text(encoding='utf-8'))
    assert sidecar['candidate']['evidence']['license_check']=='SKIPPED'
    with connect(repo.path) as db:library=db.execute('SELECT title,album,path FROM personal_music').fetchall()
    assert [tuple(r) for r in library]==[('Test tone','Unit Album',files[0]['path'])]  # in 我的音乐, with album


@pytest.mark.parametrize('raw,expected',[
    ('CPX002832_02_°ÔÍõ±ð¼§ ¶þ','CPX002832_02_霸王别姬 二'),  # GBK tag read as Latin-1
    ('æ\x99´å¤©','晴天'),                                   # UTF-8 tag read as Latin-1
    ('Größe','Größe'),('élève','élève'),('Ærøskøbing','Ærøskøbing'),('晴天','晴天'),('',''),(None,'')])
def test_tag_mojibake_repair_leaves_normal_text_alone(raw,expected):
    from melodyvault.providers.archive import repair_text
    assert repair_text(raw)==expected


def test_archive_search_uses_file_name_when_tags_are_damaged(monkeypatch):
    from melodyvault.search import platforms
    item={'metadata':{'title':'霸王别姬','creator':['梅兰芳','齐如山']},'files':[
        {'name':'梅兰芳《霸王别姬》1931年百代唱片.mp3','source':'original','title':'CPX002832_02_°ÔÍõ±ð¼§ ¶þ','length':'251.12'},
        {'name':'梅兰芳《霸王别姬》1931年百代唱片.ogg','source':'derivative','original':'梅兰芳《霸王别姬》1931年百代唱片.mp3','length':'251.69'},
        {'name':'track02.mp3','source':'original','title':'Ã·À¼·¼¡¶°ÔÍõ±ð¼§¡·','length':'244.18'}]}
    def handler(request):
        if request.url.path=='/advancedsearch.php':return httpx.Response(200,json={'response':{'docs':[{'identifier':'GRPARD'}]}})
        return httpx.Response(200,json=item)
    monkeypatch.setattr(platforms,'SourceHTTP',lambda cancel:SourceHTTP(cancel,transport=httpx.MockTransport(handler),interval=0,max_attempts=1))
    rows=platforms.ArchiveMusicSearch().search('梅兰芳 霸王别姬')
    assert sorted(r.title for r in rows)==['CPX002832_02_霸王别姬 二','梅兰芳《霸王别姬》']
    assert all(r.artist=='梅兰芳 / 齐如山' for r in rows)


def test_archive_search_version_matches_download_side_version(monkeypatch):
    # Real case: "周杰倫 Jay Chou Piano" item; only the identifier says piano-40.
    from melodyvault.search import platforms
    from melodyvault.providers.archive import ArchiveProvider
    item={'metadata':{'title':'周杰倫 Jay Chou Piano','creator':'周杰倫'},'files':[
        {'name':'11.mp3','source':'original','title':'七里香','creator':'周杰倫','length':'290'}]}
    def handler(request):
        if request.url.path=='/advancedsearch.php':return httpx.Response(200,json={'response':{'docs':[{'identifier':'jay-chou-piano-40'}]}})
        return httpx.Response(200,json=item)
    make=lambda cancel=None:SourceHTTP(cancel,transport=httpx.MockTransport(handler),interval=0,max_attempts=1)
    monkeypatch.setattr(platforms,'SourceHTTP',make)
    row,=platforms.ArchiveMusicSearch().search('周杰伦 七里香')
    with make() as http:candidate,=ArchiveProvider().get_metadata(row.song_id,http)
    assert row.version==candidate.version=='instrumental'


def test_archive_search_lists_matching_original_files_and_skips_restricted(monkeypatch):
    from melodyvault.search import platforms
    seen=[]
    items={'unit-item':{'metadata':{'title':'Unit Album','creator':'鄧麗君'},'files':[
              {'name':'Track-01.flac','source':'original','title':'月亮代表我的心','creator':'鄧麗君','length':'205.5'},
              {'name':'Track-01.mp3','source':'derivative','title':'月亮代表我的心','creator':'鄧麗君','length':'03:26'},
              {'name':'Track-02.flac','source':'original','title':'甜蜜蜜','creator':'鄧麗君','length':'210'},
              {'name':'cover.jpg','source':'original'}]},
           'dark-item':{'is_dark':True,'files':[{'name':'a.mp3','title':'月亮代表我的心'}]}}
    def handler(request):
        if request.url.path=='/advancedsearch.php':
            seen.append(request.url.params['q']);return httpx.Response(200,json={'response':{'docs':[{'identifier':'unit-item'},{'identifier':'dark-item'}]}})
        return httpx.Response(200,json=items[request.url.path.rsplit('/',1)[-1]])
    monkeypatch.setattr(platforms,'SourceHTTP',lambda cancel:SourceHTTP(cancel,transport=httpx.MockTransport(handler),interval=0,max_attempts=1))
    rows=platforms.ArchiveMusicSearch().search('邓丽君 月亮代表我的心')
    assert '鄧麗君' in seen[0] and '邓丽君' in seen[0] and 'mediatype:audio' in seen[0]
    assert [(r.song_id,r.artist,r.duration,r.source_url) for r in rows]==[('unit-item/Track-01.flac','鄧麗君',205.5,DETAILS)]


def test_archive_file_without_length_downloads_and_is_measured(archive,audio):
    # Older uploads have no "length"; size + MD5 pin the bytes and the decode measures it.
    repo,settings,target,raw,item,factory=archive;settings=opt_in((repo,settings))
    del item['files'][0]['length'];target['duration']=0
    c=verify(archive)
    assert DownloadEligibilityService.allowed(c) and c.duration is None and c.evidence['duration_unverified']
    def transport(request):
        if request.url.host=='archive.org':return httpx.Response(302,headers={'Location':NODE})
        return good(audio,request)
    m=manager((repo,settings,target,raw,None,factory),transport)
    attempts=SourceFallbackManager(repo,m,threading.Event()).run(target,[UnifiedCandidate('archive',DETAILS,'Test tone',match_score=100,raw_source=raw)],settings)
    assert attempts[-1]['state']=='COMPLETED',attempts
    with connect(repo.path) as db:assert abs(db.execute('SELECT duration FROM personal_music').fetchone()[0]-1.)<.01


def test_other_sources_still_require_an_official_length(setup):
    info=setup[4]['query']['pages'][0]['imageinfo'][0];info['metadata']=[]
    assert approve(setup).evidence['decision']=='INCOMPLETE_AUDIO'
