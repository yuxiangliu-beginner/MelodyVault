"""Bridge the existing persisted official-source engine to unified results."""
from melodyvault.sources.engine import SourceSearchEngine
from melodyvault.database.sources import SourceRepository
from melodyvault.search.orchestrator import UnifiedCandidate
from melodyvault.database.discovery import DiscoveryRepository


class MusicSourcesAdapter:
    provider_id='music_archives'
    def __init__(self,path,artist,song,works,providers,cancel,progress=None):
        self.path=path;self.artist=artist;self.song=song;self.works=works
        self.providers=providers;self.cancel=cancel;self.progress=progress
        self.last_stats=None
    def get_status(self):return {'status':'AVAILABLE'}
    def search(self,query):
        self.last_stats=SourceSearchEngine(SourceRepository(self.path),self.providers,self.cancel,self.progress).search(
            self.artist,[self.song],self.works)
        output=[]
        for job in self.last_stats['jobs']:
            for c in job['candidates']:
                output.append(UnifiedCandidate(self.provider_id,c['page_url'],c['title'],c.get('performer',''),
                    c['title'],'',c.get('duration_seconds'),c.get('version','unknown'),c.get('match_score',0),
                    c.get('file_format',''),None,'PERMISSION_UNKNOWN',{'reason':c.get('license_reason','')},
                    c.get('match_status','REVIEW_REQUIRED'),c))
        if self.last_stats['jobs'] and all(len(job['unconfigured'])==len(self.providers) for job in self.last_stats['jobs']):
            raise RuntimeError('没有可用的音乐来源；请检查配置及来源审核状态')
        if not output and self.last_stats['failed']:
            raise RuntimeError('来源搜索失败；详见独立来源错误')
        return output


class _SharedRunRepository:
    """Per-provider view of one real source run; coordinator owns final job."""
    def __init__(self,repository,run_id):self.repository=repository;self.path=repository.path;self.run_id=run_id
    def begin(self,artist,queries):return self.run_id
    def job(self,*args):pass
    def finish(self,*args):pass
    def latest_jobs(self,artist):return self.repository.latest_jobs(artist)
    def cached(self,*args,**kwargs):return self.repository.cached(*args,**kwargs)
    def attempt(self,run_id,*args,**kwargs):return self.repository.attempt(self.run_id,*args,**kwargs)


class MusicProviderAdapter:
    def __init__(self,repository,run_id,artist,song,works,provider,cancel,progress=None):
        self.provider_id=provider.name;self.repository=_SharedRunRepository(repository,run_id)
        self.artist=artist;self.song=song;self.works=works;self.provider=provider;self.cancel=cancel;self.progress=progress
        self.last_stats=None
    def get_status(self):
        if not self.provider.enabled:return {'status':'NOT_CONFIGURED','reason':'来源未配置官方凭据'}
        if not DiscoveryRepository(self.repository.path).provider_allowed(self.provider_id):
            return {'status':'RESTRICTED','reason':'来源禁用、待审核或核验过期'}
        return {'status':'AVAILABLE'}
    def search(self,query):
        self.last_stats=SourceSearchEngine(self.repository,[self.provider],self.cancel,self.progress).search(self.artist,[self.song],self.works)
        if self.last_stats['failed']:raise RuntimeError(str(self.last_stats['jobs'][0]['errors']))
        output=[]
        for job in self.last_stats['jobs']:
            for c in job['candidates']:
                output.append(UnifiedCandidate(self.provider_id,c['page_url'],c['title'],c.get('performer',''),
                    c['title'],'',c.get('duration_seconds'),c.get('version','unknown'),c.get('match_score',0),
                    c.get('file_format',''),None,'PERMISSION_UNKNOWN',{'reason':c.get('license_reason','')},
                    c.get('match_status','REVIEW_REQUIRED'),c))
        return output
