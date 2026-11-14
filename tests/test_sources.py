import threading
from dataclasses import asdict
import httpx
import pytest
from melodyvault.sources.engine import SourceSearchEngine
from melodyvault.sources.models import SourceQuery,Candidate
from melodyvault.sources.http import SourceHTTP
from melodyvault.sources.matching import match_candidate
from melodyvault.sources.browser import PublicBrowser
from melodyvault.providers.archive import ArchiveProvider
from melodyvault.providers.commons import CommonsProvider
from melodyvault.providers.jamendo import JamendoProvider
from melodyvault.licensing.source_evidence import check_license,recognized_license
from melodyvault.database.sources import SourceRepository
from melodyvault.catalog.models import CatalogError
from test_review import review_data

LICENSE='https://creativecommons.org/licenses/by/4.0/'


def query():return SourceQuery('a','s','周杰伦','晴天',['周杰伦','周杰倫','Jay Chou'],['晴天'],['studio'],[269000],['r'])


def test_matching_same_name_cover_live_karaoke_and_other_singer_are_not_originals():
    for kind in ('live','cover','karaoke','instrumental','rerecording'):
        c=Candidate('archive','id','晴天','周杰伦','https://archive.org/details/id',version=kind)
        assert match_candidate(query(),c).match_status=='VERSION_MISMATCH'
    foreign=Candidate('archive','id','晴天','另一个歌手','https://archive.org/details/id')
    assert match_candidate(query(),foreign).match_status=='REVIEW_REQUIRED'


def test_license_requires_explicit_valid_file_permission_and_source():
    c=Candidate('jamendo','1','晴天','周杰伦','https://www.jamendo.com/track/1',license_url=LICENSE,audio_url='https://prod-1.storage.jamendo.com/download/track/1/mp32/')
    assert check_license(c,download_allowed=True).license_status=='LICENSE_VERIFIED'
    assert check_license(c,download_allowed=False).license_status=='LICENSE_UNVERIFIED'
    c.provider='archive'
    assert check_license(c,download_allowed=True).license_status=='LICENSE_UNVERIFIED'
    assert '权利' in c.license_reason
    assert not recognized_license('https://creativecommons.org.attacker.invalid/licenses/by/4.0/')
    assert not recognized_license('https://example.com/download-button')


def test_provider_failures_are_isolated_and_attempts_persist_unverified_reason(review_data):
    repo,artist,records,review=review_data;songs=review.load(artist)['result'].songs[:1]
    class Failed:
        name='broken';enabled=True
        def search(self,q,h):raise CatalogError('HTTP 503 actual injected failure')
    class Good:
        name='archive';enabled=True
        def search(self,q,h):return [Candidate('archive','id',q.title,q.artist,'https://archive.org/details/id',license_reason='缺少权利人证据')]
    results=[]
    result=SourceSearchEngine(SourceRepository(repo.path),[Failed(),Good(),JamendoProvider()],progress=results.append).search(artist,songs,{})
    assert result['searched']==result['total']==1 and result['failed']==1
    assert result['no_result']==0 and result['license_unverified']==1 and result['license_verified']==0
    assert result['completed']==0 and result['completed']+result['failed']+result['pending']==result['total']
    assert result['jobs'][0]['unconfigured']==['jamendo']
    saved=SourceRepository(repo.path).latest_jobs(artist.mbid)[songs[0].id]
    assert saved['status']=='partial' and saved['summary']['candidates'][0]['page_url']=='https://archive.org/details/id'
    assert results[0]['searched']==0 and results[-1]['percent']==100


def test_negative_cache_and_changed_recording_fingerprint_prevent_wrong_reuse(review_data):
    repo,artist,records,review=review_data;songs=review.load(artist)['result'].songs[:1]
    class Empty:
        name='empty';enabled=True;calls=0
        def search(self,q,h):self.calls+=1;return []
    provider=Empty();engine=SourceSearchEngine(SourceRepository(repo.path),[provider])
    first=engine.search(artist,songs,{})
    assert first['no_result']==1 and provider.calls==1
    again=engine.search(artist,songs,{})
    assert provider.calls==1 and again['jobs'][0]['cached_providers']==['empty']
    engine.search(artist,songs,{},force=True);assert provider.calls==2
    # Metadata changes invalidate the snapshot without merging same-titled works.
    songs[0].recordings.append(records[-1])
    engine.search(artist,songs,{});assert provider.calls==3


def test_cancel_keeps_successful_provider_attempt_for_resume(review_data):
    repo,artist,records,review=review_data;songs=review.load(artist)['result'].songs[:1];cancel=threading.Event()
    class First:
        name='first';enabled=True;calls=0
        def search(self,q,h):self.calls+=1;return []
    first=First()
    class Second:
        name='second';enabled=True
        def search(self,q,h):cancel.set();return []
    engine=SourceSearchEngine(SourceRepository(repo.path),[first,Second()],cancel)
    result=engine.search(artist,songs,{})
    assert result['status']=='cancelled' and result['searched']==0 and result['pending']==1 and first.calls==1
    cancel.clear();engine.providers=[first]
    again=engine.search(artist,songs,{})
    assert again['searched']==1 and first.calls==1


class ImmediateEvent(threading.Event):
    def __init__(self):super().__init__();self.delays=[]
    def wait(self,timeout=None):self.delays.append(timeout);return self.is_set()


@pytest.mark.parametrize('failure',[503,429,'timeout'])
def test_http_retry_backoff_uses_real_response_codes_without_waiting_in_unit_test(failure):
    attempts=[];event=ImmediateEvent()
    def transport(request):
        attempts.append(request)
        if len(attempts)==1:
            if failure=='timeout':raise httpx.ReadTimeout('injected read timeout',request=request)
            return httpx.Response(failure,headers={'Retry-After':'3'},text='service unavailable')
        return httpx.Response(200,json={'ok':True})
    with SourceHTTP(event,transport=httpx.MockTransport(transport),interval=0) as http:
        assert http.json('https://archive.org/metadata/test')['ok']
        assert http.requests==2 and http.retries==1
        assert max(event.delays)>=2


def test_chrome_allowlist_does_not_allow_media_login_or_foreign_urls():
    assert PublicBrowser.allowed_url('https://archive.org/details/item')
    assert PublicBrowser.allowed_url('https://commons.wikimedia.org/wiki/File:Audio.ogg')
    for url in ('https://archive.org/download/item/file.mp3','https://archive.org/account/login','https://example.com/details/x','https://archive.org@evil.invalid/details/x'):
        assert not PublicBrowser.allowed_url(url)
    with SourceHTTP() as http:
        with pytest.raises(CatalogError,match='音频'):http.get('https://archive.org/download/item/file.mp3')


def test_commons_file_page_ending_in_audio_extension_is_html_navigation():
    from types import SimpleNamespace
    browser=PublicBrowser(SimpleNamespace(cancel=threading.Event()))
    browser.policy=lambda url:None
    decisions=[]
    request=SimpleNamespace(url='https://commons.wikimedia.org/wiki/File:Audio.ogg',resource_type='document',is_navigation_request=lambda:True)
    route=SimpleNamespace(request=request,abort=lambda:decisions.append('abort'),continue_=lambda:decisions.append('continue'))
    browser._route(route)
    assert decisions==['continue']
    request.url='https://archive.org/download/item/audio.ogg'
    browser._route(route)
    assert decisions[-1]=='abort'


def test_realistic_archive_piano_collection_does_not_become_original_by_misleading_tags():
    def transport(request):
        if request.url.path.endswith('advancedsearch.php'):
            return httpx.Response(200,json={'response':{'docs':[{'identifier':'jay-chou-piano-40'}]}})
        return httpx.Response(200,json={'metadata':{'title':'周杰倫 Jay Chou Piano','creator':'Jay Chou'},'files':[
            {'name':'08.mp3','title':'晴天','creator':'周杰伦','length':'4:28','source':'derivative'}]})
    with SourceHTTP(transport=httpx.MockTransport(transport),interval=0) as http:
        items=ArchiveProvider().search(query(),http)
    assert len(items)==1 and match_candidate(query(),items[0]).match_status=='VERSION_MISMATCH'
    assert items[0].license_status=='LICENSE_UNVERIFIED' and items[0].page_url


def test_commons_file_license_keeps_author_separate_from_performer():
    data={'query':{'pages':[{'pageid':1,'title':'File:晴天.ogg','imageinfo':[{'mime':'audio/ogg',
        'url':'https://upload.wikimedia.org/wikipedia/commons/a/ab/audio.ogg','descriptionurl':'https://commons.wikimedia.org/wiki/File:晴天.ogg',
        'extmetadata':{'LicenseUrl':{'value':LICENSE},'Artist':{'value':'Photographer, not a singer'}}}]}]}}
    def transport(request):
        assert '(' not in request.url.params['gsrsearch']
        return httpx.Response(200,json=data)
    with SourceHTTP(transport=httpx.MockTransport(transport),interval=0) as http:
        item=CommonsProvider().search(query(),http)[0]
    assert item.license_status=='LICENSE_VERIFIED' and item.performer==''
    assert match_candidate(query(),item).match_status=='REVIEW_REQUIRED'


def test_failed_only_retry_does_not_repeat_successful_provider(review_data):
    repo,artist,records,review=review_data;songs=review.load(artist)['result'].songs[:1]
    class Provider:
        name='flaky';enabled=True;fail=True;calls=0
        def search(self,q,h):
            self.calls+=1
            if self.fail:raise CatalogError('HTTP 429 fault injection')
            return []
    provider=Provider();engine=SourceSearchEngine(SourceRepository(repo.path),[provider])
    assert engine.search(artist,songs,{})['failed']==1
    provider.fail=False
    assert engine.search(artist,songs,{},mode='failed')['no_result']==1
    assert engine.search(artist,songs,{},mode='failed')['total']==0
    assert provider.calls==2
