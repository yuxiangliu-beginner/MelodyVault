"""Deterministic fault injection. These tests are not live coverage evidence."""
import json,time,threading
from dataclasses import asdict
import httpx,pytest
from melodyvault.database import initialize_database,connect
from melodyvault.database.discovery import DiscoveryRepository
from melodyvault.discovery.models import DiscoveryHit,domain_key,public_url,query_plan
from melodyvault.discovery.http import DiscoveryHTTP
from melodyvault.discovery.service import SourceDiscoveryService
from melodyvault.providers.ccmixter import CCMixterProvider,sha1
from melodyvault.providers.base import SourceProvider
from melodyvault.providers.commons import CommonsProvider
from melodyvault.providers.archive import ArchiveProvider
from melodyvault.providers.jamendo import JamendoProvider
from melodyvault.downloads.security import validate_url
from melodyvault.downloads.models import DownloadError
from melodyvault.catalog.models import CatalogCancelled


@pytest.fixture
def repo(tmp_path):
    path=tmp_path/'discovery.sqlite3';initialize_database(path);return DiscoveryRepository(path)


def hit(url='https://www.example.org/song'):return DiscoveryHit('Example',url,'周杰伦 晴天','test',{'scope':'investigation only'})


@pytest.mark.parametrize('url',['http://example.org','https://127.0.0.1/a','https://a.local/a','https://user:pw@example.org','https://example.org:444','https://localhost/a'])
def test_url_rejects_unsafe_syntax(url):
    with pytest.raises(ValueError):public_url(url)


def test_domains_idna_www_and_no_incorrect_subdomain_merging():
    assert domain_key('https://WWW.Example.org./song')=='example.org'
    assert domain_key('https://音乐.example.org/')=='xn--fjq180p.example.org'
    assert domain_key('https://other.example.org/')!='example.org'


def test_discovery_is_pending_deduped_with_append_history(repo):
    repo.discover(hit());repo.discover(hit('https://example.org/another'))
    row=repo.rows()[0];assert len(repo.rows())==1 and row['review_status']=='PENDING_REVIEW'
    assert len(repo.history('example.org')['discoveries'])==2
    with pytest.raises(ValueError):repo.approve_compiled('example.org','evil',{})


def test_negative_cache_and_expiry(repo):
    assert repo.cache('missing') is None
    repo.cache('missing',[]);assert repo.cache('missing')==[]
    assert repo.cache('missing',ttl=-1) is None


def test_health_suspend_recheck_and_manual_override(repo):
    repo.discover(hit())
    for _ in range(3):repo.verify('example.org',{'state':'UNAVAILABLE','error':'offline'})
    assert not repo.get('example.org')['enabled']
    repo.verify('example.org',{'state':'ACCESSIBLE'});assert repo.get('example.org')['enabled']
    repo.set_enabled('example.org',False);repo.verify('example.org',{'state':'ACCESSIBLE'})
    assert not repo.get('example.org')['enabled'] and repo.get('example.org')['manual_disabled']


def test_manual_enable_never_approves_or_bypasses_unsafe_expired(repo):
    repo.discover(hit('https://ccmixter.org/'))
    repo.set_enabled('ccmixter.org',True);assert not repo.provider_allowed('ccmixter')
    repo.verify('ccmixter.org',{'state':'SEARCH_SUPPORTED','automation_allowed':True})
    repo.approve_compiled('ccmixter.org','ccmixter',{'policy':'test-only'})
    assert repo.provider_allowed('ccmixter')
    repo.verify('ccmixter.org',{'state':'UNSAFE','automation_allowed':True});repo.set_enabled('ccmixter.org',True)
    assert not repo.provider_allowed('ccmixter')
    repo.verify('ccmixter.org',{'state':'SEARCH_SUPPORTED','automation_allowed':True})
    with connect(repo.path) as db:db.execute('UPDATE discovered_sources SET checked_at=?',(time.time()-8*86400,))
    assert not repo.provider_allowed('ccmixter')


@pytest.mark.parametrize('response',[
    lambda r:httpx.Response(302,headers={'location':'http://127.0.0.1/'}),
    lambda r:httpx.Response(200,headers={'content-type':'audio/mpeg'},content=b'fake'),
    lambda r:httpx.Response(200,headers={'content-type':'text/html'},content=b'x'*1025),
])
def test_metadata_http_rejects_redirect_media_and_size(response):
    with DiscoveryHTTP(transport=httpx.MockTransport(response),interval=0) as http:
        with pytest.raises(ValueError):http.get('https://example.org/',limit=1024)


def test_dns_pinning_uses_existing_public_backend(monkeypatch):
    from melodyvault.downloads import security
    monkeypatch.setattr(security.socket,'getaddrinfo',lambda *a,**kw:[(0,0,0,'',('10.0.0.1',443))])
    with pytest.raises(DownloadError):security.PublicBackend().connect_tcp('example.org',443,timeout=.1)


def test_robots_forbidden_does_not_fetch_page_or_authorize(repo):
    repo.discover(hit());calls=[]
    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200,headers={'content-type':'text/plain'},text='User-agent: *\nDisallow: /')
    with DiscoveryHTTP(transport=httpx.MockTransport(handler),interval=0) as http:
        cap=SourceDiscoveryService(repo).check('example.org',http)
    assert calls==['/robots.txt'] and cap['state']=='RESTRICTED' and not cap['integratable']
    assert cap['download_permission']=='LICENSE_UNVERIFIED'


def test_cancel_and_query_intents():
    cancel=threading.Event();cancel.set()
    with DiscoveryHTTP(cancel,transport=httpx.MockTransport(lambda r:None)) as http:
        with pytest.raises(CatalogCancelled):http.get('https://example.org')
    plan=query_plan('周杰伦','晴天',['Jay Chou Qing Tian'])
    assert '周杰倫 晴天' in plan and 'Jay Chou Qing Tian' in plan
    assert any('FLAC' in q for q in plan) and any('Creative Commons' in q for q in plan)


def upload(uncertain=False):
    return {'upload_id':1,'upload_name':'测试粤语歌曲','user_real_name':'测试作者',
        'file_page_url':'https://ccmixter.org/files/test/1','license_url':'https://creativecommons.org/licenses/by/4.0/',
        'upload_description_plain':'Traditional cover' if uncertain else 'Original Cantonese song by me',
        'upload_tags':',chinese,', 'files':[{'file_id':2,'file_is_remote':0,'file_rawsize':100,
        'download_url':'https://ccmixter.org/content/test/song.flac','file_extra':{'sha1':'A'*32},
        'file_format_info':{'media-type':'audio','default-ext':'flac','ps':'2:24'}}]}


def test_ccmixter_separate_file_ids_formats_and_uncertain_rights():
    provider=CCMixterProvider();row=upload();row['files'].append({**row['files'][0],'file_id':3,'download_url':'https://ccmixter.org/content/test/song.mp3','file_format_info':{'media-type':'audio','default-ext':'mp3','ps':'2:24'}})
    values=provider.parse([row]);assert {v.external_id for v in values}=={'1:2','1:3'}
    assert all(not v.performer for v in values)  # uploader is not the singer
    row['upload_extra']={'featuring':'Explicit singer'}
    assert provider.parse([row])[0].performer=='Explicit singer'
    assert {v.file_format for v in values}=={'flac','mp3'} and all(v.duration_seconds==144 for v in values)
    assert provider.parse([upload(True)])[0].license_status=='LICENSE_UNVERIFIED'
    row=upload();row['files'][0]['file_is_remote']=1
    assert provider.parse([row])[0].license_status=='LICENSE_UNVERIFIED'
    assert sha1('A'*32)=='0'*40


def test_compiled_provider_contract_and_url_scope():
    assert all(isinstance(p,SourceProvider) for p in (CommonsProvider(),ArchiveProvider(),JamendoProvider(),CCMixterProvider()))
    validate_url('ccmixter','https://ccmixter.org/content/test/song.flac')
    for url in ('https://other.org/content/test/song.flac','https://ccmixter.org/content/test/code.exe','https://ccmixter.org/content/test/../secret.mp3'):
        with pytest.raises(DownloadError):validate_url('ccmixter',url)


def test_fixed_coverage_set_is_30_titles_and_8_artists():
    from pathlib import Path
    data=json.loads((Path(__file__).parent/'fixtures/phase3b1_chinese_songs.json').read_text(encoding='utf-8'))
    assert len(data)==8 and sum(len(a['titles']) for a in data)==30
    assert {'周杰伦','林俊杰','周传雄','张惠妹'} <= {a['artist'] for a in data}


def test_retry_429_503_is_bounded_and_counted():
    responses=iter([429,503,200]);delays=[];cancel=threading.Event()
    cancel.wait=lambda seconds:(delays.append(seconds) or False)
    def handler(req):return httpx.Response(next(responses),headers={'content-type':'application/json'},json={'ok':True})
    with DiscoveryHTTP(cancel,transport=httpx.MockTransport(handler),interval=0) as http:
        assert http.get('https://retry.example.org/').json()=={'ok':True}
        assert http.requests==3 and http.retries==2 and 2 in delays and 4 in delays


def test_backend_failure_isolated_and_empty_cache_prevents_repeat(repo):
    calls=[]
    class Empty:
        name='empty'
        def search(self,q,http):calls.append(q);return []
    class Failure:
        name='failure'
        def search(self,q,http):raise ValueError('503 fault injection')
    def factory(cancel):return DiscoveryHTTP(cancel,transport=httpx.MockTransport(lambda r:None),interval=0)
    service=SourceDiscoveryService(repo,http_factory=factory,backends=[Failure(),Empty()])
    first=service.discover('周杰伦','晴天',max_checks=0);count=len(calls)
    second=service.discover('周杰伦','晴天',max_checks=0)
    assert first['errors'] and second['errors'] and first['api_requests']==second['api_requests']==0
    assert count and len(calls)==count and second['cached_queries']==count


def test_fresh_ccmixter_eligibility_rejects_unresolved_composition_and_changed_id():
    from melodyvault.downloads.eligibility import DownloadEligibilityService
    row=upload(True)
    class HTTP:
        def get(self,*args):return httpx.Response(200,json=[row])
    raw=asdict(CCMixterProvider().parse([row])[0])
    target={'song_id':'s','recording_id':'ccmixter:1','namespace':'ccmixter','source_page_url':raw['page_url'],
        'artist':{'name':'测试作者'},'title':raw['title'],'version':'cover','duration':144,'confirmed':True}
    decision=DownloadEligibilityService(HTTP()).verify(raw,target)
    assert decision.evidence['decision']=='LICENSE_UNVERIFIED' and not DownloadEligibilityService.allowed(decision)
    # Metadata-only approval cannot override the refreshed original flags.
    raw['license_status']='LICENSE_VERIFIED';row['files'][0]['file_is_remote']=1
    assert not DownloadEligibilityService.allowed(DownloadEligibilityService(HTTP()).verify(raw,target))
