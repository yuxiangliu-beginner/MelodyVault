import threading
import time
from dataclasses import replace
from melodyvault.search.orchestrator import UnifiedCandidate
from melodyvault.downloads.fallback import SourceFallbackManager
from melodyvault.database import connect
from test_downloads import setup,audio,manager,queue,good,opt_in


def test_selected_run_leaves_other_queued_jobs_untouched(setup,audio):
    repo,settings,target,raw,*_=setup
    first=queue(setup)
    other=dict(target,song_id='another')
    second=repo.enqueue(other,settings,candidate=raw)
    manager(setup,lambda req:good(audio,req)).run(job_ids=[first])
    assert repo.get(first)['state']=='READY'
    assert repo.get(second)['state']=='QUEUED'


def test_fallback_ignores_known_wrong_version_and_never_downloads_unauthorized(setup,audio):
    settings=opt_in(setup);repo,_,target,raw,*_=setup
    # Strict mode is the user's opt-in "只下载许可已核验的文件" setting.
    with connect(repo.path) as db:db.execute("INSERT OR REPLACE INTO app_metadata(key,value) VALUES ('ui.require_license','true')")
    calls=[];m=manager(setup,lambda req:(calls.append(req),good(audio,req))[1])
    wrong=dict(raw,external_id='wrong',match_status='VERSION_MISMATCH')
    unknown=dict(raw,provider='archive',external_id='archive/1',match_status='REVIEW_REQUIRED')
    first=UnifiedCandidate('music_archives','https://example.org/wrong','wrong',match_score=99,raw_source=wrong)
    second=UnifiedCandidate('music_archives','https://example.org/unknown','unknown',match_score=95,raw_source=unknown)
    third=UnifiedCandidate('music_archives',raw['page_url'],'valid',match_score=90,raw_source=raw)
    attempts=SourceFallbackManager(repo,m,threading.Event()).run(target,[first,second,third],settings)
    assert [a['reason_code'] for a in attempts[:2]]==['VERSION_MISMATCH','LICENSE_UNVERIFIED']
    assert attempts[-1]['state']=='COMPLETED' and len(calls)==1


def test_one_click_consent_is_task_scoped_and_does_not_change_saved_settings(setup,audio):
    repo,settings,target,raw,*_=setup
    assert not repo.settings().automatic_download
    other=repo.enqueue(dict(target,song_id='other'),settings,candidate=raw)
    calls=[];m=manager(setup,lambda req:(calls.append(req),good(audio,req))[1])
    candidate=UnifiedCandidate('music_archives',raw['page_url'],'valid',raw_source=raw)
    attempts=SourceFallbackManager(repo,m,threading.Event()).run(target,[candidate],replace(settings,automatic_download=True))
    assert attempts[-1]['state']=='COMPLETED' and len(calls)==1
    assert not repo.settings().automatic_download and repo.get(other)['state']=='QUEUED'


def test_failed_eligible_source_falls_back_to_next_eligible_source(setup):
    from contextlib import nullcontext
    from melodyvault.downloads.models import DownloadCandidate
    repo,settings,target,raw,*_=setup
    class Verifier:
        def __init__(self,*args):pass
        def verify(self,source,target):
            c=DownloadCandidate(target['song_id'],target['recording_id'],target['artist']['name'],target['title'],
                target['version'],source['provider'],source['page_url'])
            c.license_status='LICENSE_VERIFIED';c.download_permission=True;c.personal_storage_permission=True
            c.metadata_match_status='RECORDING_VERIFIED';c.full_length_status='FULL_LENGTH';c.evidence={'decision':'READY'}
            return c
    class FakeManager:
        verifier_factory=Verifier
        source_http_factory=staticmethod(lambda cancel:nullcontext(None))
        def __init__(self):self.progress=lambda:None;self.calls=[]
        def run(self,job_ids,settings_override):
            jid=job_ids[0];self.calls.append(jid)
            repo.update(jid,state='FAILED' if len(self.calls)==1 else 'COMPLETED',reason_code='NETWORK_INTERRUPTED' if len(self.calls)==1 else '')
        def stop(self,*args):pass
    m=FakeManager()
    first=UnifiedCandidate('music_archives',raw['page_url'],'first',match_score=100,raw_source=dict(raw,external_id='7'))
    second=UnifiedCandidate('music_archives',raw['page_url'],'second',match_score=90,raw_source=dict(raw,external_id='8'))
    records=[]
    attempts=SourceFallbackManager(repo,m,threading.Event(),record=records.append).run(target,[first,second],replace(settings,automatic_download=True))
    assert [a['state'] for a in attempts]==['FAILED','COMPLETED'] and len(m.calls)==2
    assert records==attempts and attempts[0]['reason_code']=='NETWORK_INTERRUPTED'


def test_real_engine_bridge_runs_sources_independently_and_persists_combined_job(setup):
    from melodyvault.database import connect
    from melodyvault.database.sources import SourceRepository
    from melodyvault.downloads.targets import search_values
    from melodyvault.search.pipeline import UnifiedMusicSearchService
    from melodyvault.sources.models import Candidate
    repo,settings,target,raw,*_=setup
    artist,song=search_values(target);events=[]
    class Provider:
        enabled=True
        def __init__(self,name,delay=0,fail=False):self.name=name;self.delay=delay;self.fail=fail;self.calls=0
        def search(self,q,http):
            self.calls+=1;time.sleep(self.delay)
            if self.fail:raise RuntimeError('simulated failure')
            return [Candidate(self.name,self.name,q.title,q.artist,'https://example.org/'+self.name)]
    fast=Provider('fast');slow=Provider('slow',delay=.25);failed=Provider('failed',fail=True)
    service=UnifiedMusicSearchService(repo.path,providers=[fast,slow,failed],progress=events.append)
    result=service.run(artist,song,explicit_selection=True,native_target=target,dry_run=True)
    assert result['status']=='SKIPPED' and result['candidate_count']==2
    assert result['source_stats']['status']=='partial'
    progress=[e['stats'] for e in events if e['stage']=='search']
    assert any(len(s['jobs'][0]['candidates'])==1 and not s['searched'] for s in progress)
    assert len(SourceRepository(repo.path).latest_jobs(artist.mbid)[song.id]['summary']['candidates'])==2
    with connect(repo.path) as db:
        assert db.execute('SELECT count(*) FROM pipeline_source_attempts WHERE session_id=?',(result['session_id'],)).fetchone()[0]==2
    service.run(artist,song,explicit_selection=True,native_target=target,dry_run=True)
    assert fast.calls==slow.calls==1 and failed.calls==2


def test_all_unavailable_sources_are_failed_not_no_result(setup):
    from melodyvault.downloads.targets import search_values
    from melodyvault.search.pipeline import UnifiedMusicSearchService
    repo,_,target,*_=setup;artist,song=search_values(target)
    class NotConfigured:
        name='not_configured_test';enabled=False
        def search(self,*args):raise AssertionError('Disabled source must not be called')
    result=UnifiedMusicSearchService(repo.path,providers=[NotConfigured()]).run(
        artist,song,explicit_selection=True,native_target=target,dry_run=True)
    assert result['status']=='FAILED' and '没有成功查询' in result['error']
    from melodyvault.database.sources import SourceRepository
    saved=SourceRepository(repo.path).latest_jobs(artist.mbid)[song.id]
    assert saved['status']=='failed' and '_sources' in saved['summary']['errors']


def test_next_pipeline_marks_abandoned_session_interrupted_without_deleting_it(setup):
    from melodyvault.database import connect
    from melodyvault.downloads.targets import search_values
    from melodyvault.search.pipeline import UnifiedMusicSearchService
    repo,_,target,*_=setup;artist,song=search_values(target)
    with connect(repo.path) as db:
        db.execute("INSERT INTO pipeline_sessions(id,query_json,status,started_at) VALUES ('old','{}','running','earlier')")
    class Disabled:
        name='disabled_test';enabled=False
    UnifiedMusicSearchService(repo.path,providers=[Disabled()]).run(artist,song,explicit_selection=True,native_target=target,dry_run=True)
    with connect(repo.path) as db:
        row=db.execute("SELECT status,finished_at FROM pipeline_sessions WHERE id='old'").fetchone()
    assert row['status']=='INTERRUPTED' and row['finished_at']


def test_unconfigured_jamendo_is_not_mislabeled_as_restricted(setup):
    from melodyvault.database.discovery import DiscoveryRepository
    from melodyvault.database.sources import SourceRepository
    from melodyvault.discovery.models import DiscoveryHit
    from melodyvault.downloads.targets import search_values
    from melodyvault.providers.jamendo import JamendoProvider
    from melodyvault.search.music_adapter import MusicProviderAdapter
    repo,_,target,*_=setup;artist,song=search_values(target)
    DiscoveryRepository(repo.path).discover(DiscoveryHit('Jamendo','https://api.jamendo.com/','test','test'))
    adapter=MusicProviderAdapter(SourceRepository(repo.path),'unused',artist,song,{},JamendoProvider(),threading.Event())
    assert adapter.get_status()['status']=='NOT_CONFIGURED'
