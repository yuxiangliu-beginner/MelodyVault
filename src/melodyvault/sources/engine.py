"""Sequential bounded providers; isolated failures and persistent real progress."""
import threading,time
from dataclasses import asdict
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.sources.models import SourceQuery
from melodyvault.sources.matching import match_candidate
from melodyvault.sources.http import SourceHTTP
from melodyvault.database.sources import SourceRepository


class SourceSearchEngine:
    def __init__(self,repository,providers,cancel=None,progress=None,http_factory=None):
        self.repository=repository;self.providers=providers;self.cancel=cancel or threading.Event()
        self.progress=progress or (lambda event:None);self.http_factory=http_factory or SourceHTTP

    def search(self,artist,songs,works,force=False,mode='all'):
        queries=[SourceQuery.from_song(artist,song,works) for song in songs]
        return self.search_queries(artist,queries,force,mode)

    def search_queries(self,artist,queries,force=False,mode='all'):
        from melodyvault.database.discovery import DiscoveryRepository
        registry=DiscoveryRepository(self.repository.path)
        previous=self.repository.latest_jobs(artist.mbid)
        def current(q):
            p=previous.get(q.song_id)
            return p if p and p['query'].get('fingerprint')==q.fingerprint else None
        if mode=='missing':queries=[q for q in queries if not current(q) or not current(q)['summary'].get('verified_sources')]
        elif mode=='failed':queries=[q for q in queries if current(q) and current(q)['status'] in {'failed','partial','cancelled'}]
        elif mode!='all':raise ValueError('Unknown source search mode')
        run_id=self.repository.begin(artist.mbid,queries);started=time.perf_counter()
        jobs=[];active=None;current_provider='';current_title=''
        def snapshot(message='',status='running'):
            stats={'run_id':run_id,'artist':artist.name,'artist_mbid':artist.mbid,'status':status,'total':len(queries),'searched':len(jobs),'current_song':current_title,
                'current_provider':current_provider,'found_songs':sum(bool(j['candidates']) for j in jobs),
                'verified_sources':sum(j['verified_sources'] for j in jobs),
                'license_verified':sum(c['license_status']=='LICENSE_VERIFIED' for j in jobs for c in j['candidates']),
                'license_unverified':sum(c['license_status']=='LICENSE_UNVERIFIED' for j in jobs for c in j['candidates']),
                'unverified_songs':sum(any(c['license_status']=='LICENSE_UNVERIFIED' for c in j['candidates']) for j in jobs),
                'no_result':sum(not j['candidates'] and not j['errors'] for j in jobs),
                'completed':sum(not j['errors'] for j in jobs),
                'failed':sum(bool(j['errors']) for j in jobs),'pending':len(queries)-len(jobs),
                'percent':round(100*len(jobs)/len(queries),2) if queries else 100,
                'message':message,'jobs':list(jobs),'elapsed_seconds':time.perf_counter()-started}
            self.progress(stats);return stats
        with self.http_factory(self.cancel,lambda msg:snapshot(msg)) as http:
            try:
                snapshot('已建立真实歌曲任务队列')
                for query in queries:
                    check_cancel(self.cancel);active=query;current_title=query.title
                    self.repository.job(run_id,query,'running',{})
                    found={};errors={};skipped=[];cached_providers=[]
                    for provider in self.providers:
                        check_cancel(self.cancel);current_provider=provider.name
                        snapshot('正在查询官方来源')
                        if not registry.provider_allowed(provider.name):
                            skipped.append(provider.name)
                            self.repository.attempt(run_id,query,provider.name,'disabled',[],'来源禁用、待审核或核验已过期；可在音源发现中重新检查')
                            continue
                        if provider.name=='archive_chrome' and 'archive' in errors:
                            errors[provider.name]='Archive API已失败，本次不改用Chrome重试或绕过限制'
                            self.repository.attempt(run_id,query,provider.name,'blocked',[],errors[provider.name]);continue
                        if not provider.enabled:
                            skipped.append(provider.name)
                            self.repository.attempt(run_id,query,provider.name,'unconfigured',[], '未配置官方client_id；未发请求')
                            snapshot('未配置官方client_id，已跳过该来源')
                            continue
                        items=None if force else self.repository.cached(provider.name,query.fingerprint)
                        if items is not None:
                            cached_providers.append(provider.name)
                        else:
                            try:
                                items=[asdict(match_candidate(query,c)) for c in provider.search(query,http)]
                                check_cancel(self.cancel)
                                self.repository.attempt(run_id,query,provider.name,'ok',items)
                                registry.attempt(provider.name,True,bool(items))
                                registry.observe_candidates(provider.name,items)
                            except CatalogCancelled:raise
                            except Exception as error:
                                errors[provider.name]=f'{type(error).__name__}: {error}'
                                registry.attempt(provider.name,False,error=errors[provider.name])
                                self.repository.attempt(run_id,query,provider.name,'failed',[],errors[provider.name])
                                snapshot(errors[provider.name]);continue
                        for c in items:found[(c['provider'],c['external_id'])]=c
                    job={'song_id':query.song_id,'title':query.title,'fingerprint':query.fingerprint,
                         'candidates':list(found.values()),'errors':errors,'unconfigured':skipped,'cached_providers':cached_providers,
                         'verified_sources':sum(c['license_status']=='LICENSE_VERIFIED' and c['match_status']=='METADATA_MATCH' for c in found.values())}
                    state='partial' if errors and found else 'failed' if errors else 'ok'
                    self.repository.job(run_id,query,state,job);jobs.append(job);active=None
                    current_provider=''
                    snapshot('该歌曲全部已配置来源搜索结束')
                current_title='';current_provider=''
                result=snapshot('来源搜索完成；此任务只查询元数据','partial' if any(j['errors'] for j in jobs) else 'completed')
            except CatalogCancelled:
                if active:self.repository.job(run_id,active,'cancelled',{})
                result=snapshot('已取消；已完成来源仍可复用','cancelled')
            except BaseException:
                result=snapshot('任务异常结束','failed');self.repository.finish(run_id,'failed',result);raise
            result.update(api_requests=http.requests,retries=http.retries)
        self.repository.finish(run_id,result['status'],result)
        return result
