"""A selected recording -> existing music search -> verified source fallback."""
from uuid import uuid4
import threading,time
from dataclasses import asdict,replace
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.database import connect
from melodyvault.database.catalog import encode,utc_now,CatalogRepository
from melodyvault.database.downloads import DownloadRepository
from melodyvault.downloads.manager import DownloadManager,RunLock
from melodyvault.downloads.targets import from_song
from melodyvault.downloads.fallback import SourceFallbackManager
from melodyvault.search.music_adapter import MusicProviderAdapter
from melodyvault.search.orchestrator import SearchOrchestrator
from melodyvault.sources.worker import default_providers
from melodyvault.sources.models import SourceQuery
from melodyvault.database.sources import SourceRepository
from melodyvault.privacy import redact_payload


class UnifiedMusicSearchService:
    def __init__(self,path,cancel=None,progress=None,manager=None,providers=None):
        self.path=path;self.cancel=cancel or threading.Event();self.progress=progress or (lambda event:None)
        self.repository=DownloadRepository(path);self.manager=manager or DownloadManager(self.repository)
        self.providers=providers if providers is not None else default_providers()
    def run(self,artist,song,*,explicit_selection=False,native_target=None,dry_run=None):
        # A separate cross-process lock means a restarted application can mark
        # abandoned sessions without touching a live pipeline in another window.
        with RunLock(str(self.path)+'.pipeline'):
            with connect(self.path) as db:
                db.execute("UPDATE pipeline_sessions SET status='INTERRUPTED',finished_at=? WHERE status='running'",(utc_now(),))
            return self._run_locked(artist,song,explicit_selection=explicit_selection,native_target=native_target,dry_run=dry_run)

    def _run_locked(self,artist,song,*,explicit_selection=False,native_target=None,dry_run=None):
        if native_target is not None:
            if not explicit_selection or native_target.get('namespace') not in {'commons','ccmixter'}:
                raise ValueError('来源原生录音需要明确选择')
            if native_target.get('song_id')!=song.id or native_target.get('recording_id') not in {r.mbid for r in song.recordings}:
                raise ValueError('来源原生录音与所选歌曲不一致')
            target=dict(native_target)
        else:target=from_song(artist,song,explicit_selection)
        if not target['confirmed']:raise ValueError('目标录音未确认，不能开始自动任务')
        sid=str(uuid4());started=utc_now()
        with connect(self.path) as db:
            db.execute('INSERT INTO pipeline_sessions(id,query_json,status,started_at) VALUES (?,?,?,?)',
                (sid,encode(redact_payload(target)),'running',started))
        result={'session_id':sid,'status':'failed','attempts':[]}
        try:
            self.progress({'stage':'identify','artist':artist.name,'title':song.title,'recording_id':target['recording_id']})
            check_cancel(self.cancel)
            works=CatalogRepository(self.path).works();query=SourceQuery.from_song(artist,song,works)
            source_repo=SourceRepository(self.path);run_id=source_repo.begin(artist.mbid,[query]);start=time.perf_counter()
            adapters=[MusicProviderAdapter(source_repo,run_id,artist,song,works,p,self.cancel) for p in self.providers]
            from melodyvault.providers.netease import NeteaseMusicSearchProvider
            from melodyvault.providers.video_search import YouTubeSearchProvider,BilibiliSearchProvider,DouyinSearchProvider
            music_ids={a.provider_id for a in adapters};partial={};source_finished=False
            def summary(final=False):
                candidates=[c.raw_source for e in partial.values() for c in e.get('candidates',[])]
                errors={k:v.get('error','来源失败') for k,v in partial.items() if v['status']=='FAILED'}
                if final and not any(v['status']=='COMPLETED' for v in partial.values()):
                    errors.setdefault('_sources','没有成功查询的音乐来源')
                skipped=[k for k,v in partial.items() if v['status'] in {'RESTRICTED','NOT_CONFIGURED'}]
                cached=[a.provider_id for a in adapters if a.last_stats and a.last_stats['jobs'] and a.provider_id in a.last_stats['jobs'][0]['cached_providers']]
                verified=sum(c.get('license_status')=='LICENSE_VERIFIED' and c.get('match_status')=='METADATA_MATCH' for c in candidates)
                job={'song_id':song.id,'title':song.title,'fingerprint':query.fingerprint,'candidates':candidates,
                     'errors':errors,'unconfigured':skipped,'cached_providers':cached,'verified_sources':verified}
                return {'run_id':run_id,'artist':artist.name,'artist_mbid':artist.mbid,'status':('partial' if candidates else 'failed') if errors else 'completed' if final else 'running',
                    'total':1,'searched':int(final),'current_song':'' if final else song.title,'current_provider':'',
                    'found_songs':int(bool(candidates)),'verified_sources':verified,
                    'license_verified':sum(c.get('license_status')=='LICENSE_VERIFIED' for c in candidates),
                    'license_unverified':sum(c.get('license_status')=='LICENSE_UNVERIFIED' for c in candidates),
                    'no_result':int(final and not candidates and not errors),'completed':int(final and not errors),
                    'failed':int(bool(errors)),'pending':int(not final),'percent':100 if final else 0,
                    'message':'来源搜索完成' if final else f'已返回 {len(partial)}/{len(adapters)} 个音乐来源',
                    'jobs':[job],'api_requests':sum(a.last_stats['api_requests'] for a in adapters if a.last_stats),
                    'retries':sum(a.last_stats['retries'] for a in adapters if a.last_stats),'elapsed_seconds':time.perf_counter()-start}
            def source_result(event):
                self.progress({'stage':'source_result','event':event})
                if event['provider_id'] in music_ids:
                    partial[event['provider_id']]=event;self.progress({'stage':'search','stats':summary()})
            try:
                events=SearchOrchestrator([*adapters,NeteaseMusicSearchProvider(),YouTubeSearchProvider(cancel=self.cancel),BilibiliSearchProvider(),DouyinSearchProvider()],
                    cancel=self.cancel,on_result=source_result).search(f'{artist.name} {song.title}')
                check_cancel(self.cancel);stats=summary(True)
                job=stats['jobs'][0];state='partial' if job['errors'] and job['candidates'] else 'failed' if job['errors'] else 'ok'
                source_repo.job(run_id,query,state,job);source_repo.finish(run_id,stats['status'],stats);source_finished=True
                self.progress({'stage':'search','stats':stats})
            finally:
                if not source_finished:
                    stats=summary();source_repo.job(run_id,query,'cancelled',stats['jobs'][0]);source_repo.finish(run_id,'cancelled',stats)
            music_events=[events[a.provider_id] for a in adapters]
            candidates=[c for e in music_events for c in e.get('candidates',[])]
            result.update(source_stats=stats, candidate_count=len(candidates), recording_id=target['recording_id'],
                          provider_statuses={k:{key:value for key,value in v.items() if key!='candidates'} for k,v in events.items()})
            if not any(e['status']=='COMPLETED' for e in music_events):raise RuntimeError('没有成功查询的音乐来源；请检查配置及错误')
            check_cancel(self.cancel)
            settings=self.repository.settings()
            if dry_run is not None:settings=replace(settings,automatic_download=not dry_run).validate()
            def record_attempt(attempt):
                with connect(self.path) as db:
                    db.execute('INSERT INTO pipeline_source_attempts VALUES (?,?,?,?)',
                        (str(uuid4()),sid,encode(redact_payload(attempt)),utc_now()))
            if not candidates and any(e['status']=='FAILED' for e in music_events):
                details='；'.join(f"{e['provider_id']}: {e.get('error','来源请求失败')}" for e in music_events if e['status']=='FAILED')
                raise RuntimeError('部分音乐来源查询失败；不能将失败记为无结果。'+details)
            attempts=SourceFallbackManager(self.repository,self.manager,self.cancel,self.progress,record_attempt).run(target,candidates,settings)
            state=attempts[-1]['state'] if attempts else 'NO_SOURCE'
            result.update(status=state,attempts=attempts,source_stats=stats,
                          candidate_count=len(candidates),recording_id=target['recording_id'],
                          provider_statuses={k:{key:value for key,value in v.items() if key!='candidates'} for k,v in events.items()})
            return result
        except CatalogCancelled:
            result.update(status='CANCELLED');return result
        except Exception as error:
            result.update(status='FAILED',error=f'{type(error).__name__}: {error}');return result
        finally:
            with connect(self.path) as db:
                db.execute('UPDATE pipeline_sessions SET status=?,result_json=?,finished_at=? WHERE id=?',
                    (result['status'],encode(redact_payload(result)),utc_now(),sid))
