"""Automatic source switching and source-approval renewal."""
import hashlib,threading,time
import httpx,pytest
from melodyvault.database import connect,initialize_database
from melodyvault.downloads.eligibility import DownloadEligibilityService
from melodyvault.downloads.fallback import SourceFallbackManager
from melodyvault.search.orchestrator import UnifiedCandidate
from melodyvault.sources.http import SourceHTTP
from test_downloads import setup,audio,manager,good,opt_in
from test_license_optional import archive,verify


def pick_other_file(target,**changes):
    """The task's selected file is a different upload than the candidate being checked."""
    target.update({'recording_id':'archive:other-item/Track-09.wav','source_page_url':'https://archive.org/details/other-item',
                   'title':'Unit Test - Test tone [HQ]',**changes})


def test_other_upload_replaces_the_pick_only_when_the_task_opts_in(archive):
    target=archive[2];pick_other_file(target)
    assert verify(archive).evidence['decision']=='RECORDING_MISMATCH'  # exact identity by default
    target['equivalent_sources']=True
    c=verify(archive)
    assert DownloadEligibilityService.allowed(c) and c.evidence['identity_basis']=='title_artist_duration'
    assert any('自动换源' in r for r in c.verification_reason)


@pytest.mark.parametrize('change,decision',[
    ({'artist':{'id':'x','name':'Someone Else'}},'RECORDING_MISMATCH'),
    ({'title':'Another song'},'RECORDING_MISMATCH'),
    ({'duration':0},'RECORDING_MISMATCH'),            # no length to compare
    ({'duration':6.},'INCOMPLETE_AUDIO'),             # 5 s apart
    ({'version':'live'},'RECORDING_MISMATCH')])       # labelled live pick vs unlabelled upload
def test_switching_needs_same_song_artist_length_and_version(archive,change,decision):
    target=archive[2];pick_other_file(target,equivalent_sources=True,**change)
    c=verify(archive)
    assert c.evidence['decision']==decision and not DownloadEligibilityService.allowed(c)


def test_failed_pick_switches_to_another_upload_and_downloads_it(archive,audio):
    repo,settings,target,raw,item,_=archive;settings=opt_in((repo,settings))
    target.update(recording_id='archive:dead-item/song.wav',source_page_url='https://archive.org/details/dead-item',
                  title='Unit Test - Test tone',equivalent_sources=True)
    items={'dead-item':{'metadata':{'title':'Gone'},'files':[]},  # the picked file was removed
           'alt-item':{'metadata':{'title':'Alt Album','creator':'Unit Test'},'files':[{'name':'Track-01.wav','source':'original','title':'Test tone',
               'creator':'Unit Test','length':'1.0','size':str(len(audio)),'md5':hashlib.md5(audio).hexdigest()}]}}
    def metadata(request):return httpx.Response(200,json=items[request.url.path.rsplit('/',1)[-1]])
    def factory(cancel=None,notice=None):return SourceHTTP(cancel,notice,transport=httpx.MockTransport(metadata),interval=0,max_attempts=1)
    def transport(request):
        if request.url.host=='archive.org':return httpx.Response(302,headers={'Location':'https://dn710003.ca.archive.org/0/items/alt-item/Track-01.wav'})
        return good(audio,request)
    m=manager((repo,settings,target,raw,None,factory),transport)
    def candidate(identifier,name,score):
        return UnifiedCandidate('archive','https://archive.org/details/'+identifier,'Test tone',match_score=score,raw_source={'provider':'archive',
            'external_id':identifier+'/'+name,'page_url':'https://archive.org/details/'+identifier,'title':'Test tone','performer':'Unit Test',
            'match_status':'METADATA_MATCH','version':'unknown'})
    attempts=SourceFallbackManager(repo,m,threading.Event()).run(target,[candidate('dead-item','song.wav',100),candidate('alt-item','Track-01.wav',90)],settings)
    assert [(a['source'][1],a['state'],a['reason_code']) for a in attempts]==[
        ('dead-item/song.wav','SKIPPED','INCOMPLETE_AUDIO'),('alt-item/Track-01.wav','COMPLETED','')]
    with connect(repo.path) as db:assert db.execute('SELECT title,album FROM personal_music').fetchall()[0][1]=='Alt Album'


class FakeDiscoveryHTTP:
    requests=0;retries=0
    def __init__(self,cancel=None):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def get(self,url,params=None,**kwargs):
        FakeDiscoveryHTTP.requests+=1
        return type('Response',(),{'json':lambda self:{'response':{'docs':[]}}})()


def test_lapsed_source_approval_is_renewed_but_user_disabled_sources_are_not(tmp_path):
    from melodyvault.database.discovery import DiscoveryRepository
    from melodyvault.discovery.models import DiscoveryHit
    from melodyvault.discovery.service import SourceDiscoveryService,refresh_stale_builtins
    path=tmp_path/'d.sqlite3';initialize_database(path);repo=DiscoveryRepository(path)
    for domain,provider in [('archive.org','archive'),('commons.wikimedia.org','commons')]:
        repo.discover(DiscoveryHit(domain,'https://'+domain+'/',provider,'compiled_adapter',{}))
        SourceDiscoveryService(repo,http_factory=FakeDiscoveryHTTP).check(domain)
    assert repo.provider_allowed('archive') and repo.provider_allowed('commons')
    with connect(path) as db:
        db.execute('UPDATE discovered_sources SET checked_at=?',(time.time()-8*86400,))
        db.execute("UPDATE discovered_sources SET manual_disabled=1,enabled=0 WHERE domain='commons.wikimedia.org'")
    assert not repo.provider_allowed('archive')  # lapsed: would silently skip every Archive download
    FakeDiscoveryHTTP.requests=0
    assert refresh_stale_builtins(path,{'commons','archive'},http_factory=FakeDiscoveryHTTP)==['archive.org']
    assert repo.provider_allowed('archive') and not repo.provider_allowed('commons') and FakeDiscoveryHTTP.requests==1
    assert refresh_stale_builtins(path,{'commons','archive'},http_factory=FakeDiscoveryHTTP)==[]  # fresh: no request
