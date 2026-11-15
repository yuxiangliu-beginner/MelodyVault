"""Music-store metadata first. Preview URLs are deliberately discarded."""
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading, time
import httpx
from melodyvault.catalog.musicbrainz import RateGate, check_cancel
from melodyvault.catalog.normalize import search_names, title_key, name_key
from melodyvault.sources.matching import version_from_text
from melodyvault.database.discovery import DiscoveryRepository

APPLE_GATE=RateGate(3.2)  # official approximate 20 requests/minute

@dataclass
class PlatformSong:
    source:str
    song_id:str
    title:str
    artist:str
    album:str
    duration:float
    source_url:str
    version:str='unknown'
    audio_status:str='metadata_only'
    score:int=0

class AppleMusicSearch:
    name='apple'
    def __init__(self,cancel=None,transport=None):
        self.cancel=cancel or threading.Event(); self.transport=transport; self.requests=0
    def search(self,query):
        term=search_names(query.strip())[0]; last=''
        with httpx.Client(timeout=20,transport=self.transport,follow_redirects=False) as client:
            for attempt in range(3):
                check_cancel(self.cancel); APPLE_GATE.wait(self.cancel); self.requests+=1
                try:
                    r=client.get('https://itunes.apple.com/search',params={'term':term,'country':'tw','media':'music','entity':'song','limit':30})
                    if r.status_code==200:
                        data=r.json()
                        if not isinstance(data.get('results'),list):raise ValueError('平台响应格式不正确')
                        out=[]
                        for x in data['results']:
                            url=x.get('trackViewUrl','')
                            if x.get('kind')!='song' or not url.startswith('https://music.apple.com/'):continue
                            out.append(PlatformSong('apple',str(x['trackId']),x['trackName'],x['artistName'],x.get('collectionName',''),x.get('trackTimeMillis',0)/1000,url,version_from_text(x['trackName'])))
                        return out
                    last=f'HTTP {r.status_code}'
                    if r.status_code not in {429,500,502,503,504}:break
                    try:delay=max(2**(attempt+1),float(r.headers.get('retry-after',0)))
                    except ValueError:delay=2**(attempt+1)
                except httpx.RequestError as error:last=type(error).__name__;delay=2**(attempt+1)
                if attempt<2:
                    if delay>60:break
                    if self.cancel.wait(delay):check_cancel(self.cancel)
        raise RuntimeError('Apple 音乐搜索未完成：'+last)

class PlatformSearchService:
    def __init__(self,path,cancel=None,providers=None):
        self.path=path;self.cancel=cancel or threading.Event();self.providers=providers or [AppleMusicSearch(self.cancel)]
    def search(self,query):
        if not query.strip():raise ValueError('请输入歌曲或歌手')
        repo=DiscoveryRepository(self.path); started=time.perf_counter()
        key='platform-search-v1:tw:'+query.strip();cached=repo.cache(key,ttl=86400)
        if cached is not None:
            check_cancel(self.cancel);return {**cached,'cached':True,'requests':0,'elapsed':time.perf_counter()-started}
        rows=[];statuses={k:{'status':'RESTRICTED','reason':'尚未核实适用于本应用的公开检索授权；未请求'} for k in ['wy','tx','kw','kg','mg','bilibili']}
        statuses['youtube']={'status':'NOT_CONFIGURED','reason':'未配置官方 API 密钥；未请求'}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(p.search,query):p for p in self.providers}
            for f in as_completed(futures):
                check_cancel(self.cancel); p=futures[f]
                try:rows.extend(f.result());statuses[p.name]={'status':'COMPLETED'}
                except Exception as error:statuses[p.name]={'status':'FAILED','reason':str(error)}
        parts=query.split();wanted=title_key(parts[-1]);artist=name_key(' '.join(parts[:-1])) if len(parts)>1 else ''
        for row in rows:
            row.score=(60 if title_key(row.title)==wanted else 0)+(30 if artist and name_key(row.artist)==artist else 0)-(25 if row.version in {'cover','live','remix','instrumental','karaoke'} else 0)
        # Exact platform IDs only. Similar titles/durations do not establish recording identity.
        rows=list({(r.source,r.song_id):r for r in rows}.values());rows.sort(key=lambda r:-r.score)
        result={'rows':[asdict(r) for r in rows],'statuses':statuses,'requests':sum(p.requests for p in self.providers),'cached':False,'elapsed':time.perf_counter()-started}
        if any(s['status']=='COMPLETED' for s in statuses.values()):repo.cache(key,result)
        return result
