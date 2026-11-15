"""Official YouTube metadata only; other unverified interfaces stay disabled."""
import os,re,threading,time
from urllib.parse import quote
import httpx
from melodyvault.catalog.musicbrainz import RateGate,check_cancel
from melodyvault.search.orchestrator import UnifiedCandidate

_YOUTUBE_GATE=RateGate(1.1)


def _duration(value):
    m=re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',value or '')
    return sum(int(part or 0)*factor for part,factor in zip(m.groups(),(3600,60,1))) if m else None


class YouTubeSearchProvider:
    provider_id='youtube';provider_name='YouTube';provider_type='VIDEO_PLATFORM'
    def __init__(self,key=None,cancel=None,transport=None,interval=1.1,*,_display_compliant=False):
        self._key=key if key is not None else os.environ.get('YOUTUBE_API_KEY','')
        self.cancel=cancel or threading.Event();self.transport=transport
        self.gate=_YOUTUBE_GATE if interval==1.1 else RateGate(interval)
        self._display_compliant=_display_compliant
        self.requests=0;self.retries=0;self._cache={}
    def get_status(self):
        if not self._key:return {'status':'NOT_CONFIGURED','reason':'未配置 YOUTUBE_API_KEY；其他来源继续运行。'}
        if not self._display_compliant:return {'status':'RESTRICTED','reason':'YouTube 品牌标识和 API 客户端展示规范尚未完成核验；未发请求。'}
        return {'status':'AVAILABLE'}
    def _get(self,client,endpoint,params):
        for attempt in range(3):
            check_cancel(self.cancel);self.gate.wait(self.cancel);self.requests+=1
            try:
                with client.stream('GET','https://www.googleapis.com/youtube/v3/'+endpoint,params=params,headers={'X-Goog-Api-Key':self._key}) as r:
                    status=r.status_code
                    if status==200:
                        if 'json' not in r.headers.get('content-type','').lower():raise ValueError('YouTube API 未返回 JSON')
                        payload=bytearray()
                        for block in r.iter_bytes():
                            check_cancel(self.cancel);payload.extend(block)
                            if len(payload)>1024*1024:raise ValueError('YouTube API 响应超出上限')
                        import json
                        data=json.loads(payload)
                        if not isinstance(data,dict):raise ValueError('YouTube API 响应格式错误')
                        return data
                    if status not in {429,500,502,503,504} or attempt==2:
                        raise RuntimeError(f'YouTube API HTTP {status}；请检查配额和配置')
                    delay=2**(attempt+1)
                    try:delay=max(delay,float(r.headers.get('retry-after',0)))
                    except ValueError:pass
                    if delay>60:raise RuntimeError('YouTube API 要求过长的重试等待')
            except httpx.RequestError as e:
                # Exception URLs may contain the API key; never expose them.
                if attempt==2:raise RuntimeError(f'YouTube API 网络错误：{type(e).__name__}') from None
                delay=2**(attempt+1)
            self.retries+=1
            if self.cancel.wait(delay):check_cancel(self.cancel)
        raise RuntimeError('YouTube API 请求失败')
    def search(self,query):
        status=self.get_status()
        if status['status']!='AVAILABLE':raise RuntimeError(status['reason'])
        query=str(query).strip()
        if not query:raise ValueError('搜索词不能为空')
        cached=self._cache.get(query)
        if cached and time.monotonic()-cached[0]<3600:return list(cached[1])
        with httpx.Client(transport=self.transport,timeout=httpx.Timeout(20,connect=10),follow_redirects=False,trust_env=False) as client:
            data=self._get(client,'search',{'part':'snippet','type':'video','q':query,'maxResults':5})
            items=data.get('items',[])
            ids=[i.get('id',{}).get('videoId','') for i in items]
            ids=[i for i in ids if re.fullmatch(r'[A-Za-z0-9_-]{11}',i)]
            details=self._get(client,'videos',{'part':'contentDetails,status','id':','.join(ids)}) if ids else {'items':[]}
        metadata={v.get('id'):v for v in details.get('items',[])};out=[]
        for item in items:
            vid=item.get('id',{}).get('videoId','')
            if vid not in ids:continue
            snippet=item.get('snippet',{});detail=metadata.get(vid,{})
            out.append(UnifiedCandidate(self.provider_id,'https://www.youtube.com/watch?v='+quote(vid),
                snippet.get('title',''),snippet.get('channelTitle',''),duration=_duration(detail.get('contentDetails',{}).get('duration')),
                download_permission='METADATA_ONLY',availability_status='METADATA_ONLY',
                permission_evidence={'reason':'YouTube API 元数据不提供本程序下载许可'},
                raw_source={'external_id':vid,'published_at':snippet.get('publishedAt',''),
                            'channel_id':snippet.get('channelId',''),'license':detail.get('status',{}).get('license','')}))
        self._cache[query]=(time.monotonic(),out)
        if len(self._cache)>64:self._cache.pop(next(iter(self._cache)))
        return list(out)


class BilibiliSearchProvider:
    provider_id='bilibili';provider_name='Bilibili';provider_type='VIDEO_PLATFORM'
    def get_status(self):return {'status':'RESTRICTED','reason':'尚未确认适用于通用歌曲搜索的官方接口和使用条件。'}
    def search(self,query):raise RuntimeError(self.get_status()['reason'])


class DouyinSearchProvider:
    provider_id='douyin';provider_name='抖音';provider_type='VIDEO_PLATFORM'
    def get_status(self):return {'status':'RESTRICTED','reason':'官方关键词搜索需要特殊权限、用户授权及相关业务关键词，不能当作通用歌曲搜索。'}
    def search(self,query):raise RuntimeError(self.get_status()['reason'])
