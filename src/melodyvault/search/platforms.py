"""Search only sources whose individual files can be downloaded (Commons, Archive).

Catalog-only stores (the former iTunes search) were removed: their rows could
never be downloaded and only produced "不可下载" results.
"""
from dataclasses import dataclass, asdict
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading, time
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.catalog.normalize import search_names, title_key, name_key
from melodyvault.sources.matching import version_from_text
from melodyvault.database.discovery import DiscoveryRepository
from melodyvault.providers.commons import CommonsProvider
from melodyvault.sources.http import SourceHTTP
from melodyvault.providers.commons import clean
from urllib.parse import urlsplit

# Search results are cached for 24 h under this version. Bump it whenever the
# search sources, matching or filtering change, or users keep seeing old results.
# 6: Archive title/creator-first search, item-credit matching, Commons noise filter.
SEARCH_VERSION=6

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

class CommonsMusicSearch:
    """Discovery of individual official files; a selected file is its own identity."""
    name='commons'
    def __init__(self,cancel=None):self.cancel=cancel or threading.Event();self.requests=0
    def search(self,query):
        # The file search uses the official MediaWiki API, with the same rate gate.
        with SourceHTTP(self.cancel) as http:
            data=http.json('https://commons.wikimedia.org/w/api.php',{'action':'query','format':'json','formatversion':2,'generator':'search','gsrsearch':query+' filetype:audio','gsrnamespace':6,'gsrlimit':20,'prop':'imageinfo','iiprop':'url|mime|mediatype|size|extmetadata|metadata','iiextmetadatalanguage':'en','maxlag':5})
            self.requests=http.requests
        if data.get('error'):raise RuntimeError('Commons 搜索失败：'+str(data['error'].get('code','unknown')))
        keys=[k for k in (title_key(t) for t in query.split()) if k]
        out=[]
        for c in CommonsProvider().parse(data):
            if not urlsplit(c.audio_url).path.lower().endswith(('.mp3','.flac','.wav','.ogg','.opus','.m4a','.aac')):continue
            ext=c.evidence.get('extmetadata',{})
            desc=clean(ext.get('ImageDescription',{}).get('value',''));categories=clean(ext.get('Categories',{}).get('value',''))
            # Spoken-Wikipedia readings are speech, not music ("En-Jay Chou-article").
            if re.search(r'spoken\b[^|]*wikipedia|audio versions of wikipedia articles',categories,re.I) or re.search(r'spoken word version of the wikipedia article',desc,re.I):continue
            # Full-text search also returns files that never mention the query
            # (e.g. a 1971 White House tape); every word must appear in the file's own text.
            if not all(k in title_key(' '.join([c.title,desc,c.performer or '',categories])) for k in keys):continue
            version=version_from_text(c.title+' '+desc)
            # Explicit creator credits may be displayed with their role, but an
            # uploader/photographer is never silently promoted to performer.
            creator=re.search(r'创作\s*[:：]\s*([^\s，。；;<>]+)',desc)
            credit=c.performer or (creator.group(1)+'（创作）' if creator else '未知歌手')
            out.append(PlatformSong('commons',c.external_id,c.title,credit,'',c.duration_seconds or 0,c.page_url,version))
        return out

class ArchiveMusicSearch:
    """Individual Internet Archive audio files; a selected file is its own identity."""
    name='archive'
    AUDIO=('.mp3','.flac','.ogg','.opus','.m4a','.wav')
    # Same song in several formats: originals first, then FLAC, MP3, ...
    FORMAT_RANK={'flac':0,'mp3':1,'m4a':2,'ogg':3,'opus':3,'wav':4}
    def __init__(self,cancel=None,max_items=10,max_rows=40,per_item=25):
        self.cancel=cancel or threading.Event();self.requests=0
        self.max_items=max_items;self.max_rows=max_rows;self.per_item=per_item
    @staticmethod
    def _length(value):
        try:return sum(float(p)*60**i for i,p in enumerate(reversed(str(value).split(':')))) if ':' in str(value) else float(value)
        except (TypeError,ValueError):return 0
    def _identifiers(self,http,tokens):
        """Items naming the words in title/creator first; full-text matches only fill the rest.

        Full-text relevance alone ranks podcasts and audiobooks that merely
        mention an artist above actual uploads of the music.
        """
        def group(token,field=''):
            values='('+' OR '.join('"'+re.sub(r'["\\]',' ',v)+'"' for v in search_names(token))+')'
            return field+':'+values if field else values
        fielded='mediatype:audio AND '+' AND '.join('('+group(t,'title')+' OR '+group(t,'creator')+')' for t in tokens)
        full='mediatype:audio AND '+' AND '.join(group(t) for t in tokens)
        found=[]
        for expression in (fielded,full):
            if len(found)>=self.max_items:break
            check_cancel(self.cancel)
            data=http.json('https://archive.org/advancedsearch.php',{'q':expression,'fl[]':['identifier'],'rows':self.max_items,'page':1,'output':'json'})
            docs=data.get('response',{}).get('docs')
            if not isinstance(docs,list):raise RuntimeError('Archive 搜索响应不完整')
            found+=[d['identifier'] for d in docs if d.get('identifier') and d['identifier'] not in found]
        return found[:self.max_items]
    def search(self,query):
        from urllib.parse import quote
        from melodyvault.providers.archive import file_title,file_stem,file_creator,file_version,repair_text,restricted_item
        tokens=[t for t in query.split() if t.strip()]
        keys=[k for k in (title_key(t) for t in tokens) if k]
        if not keys:return []
        ranked=[]
        with SourceHTTP(self.cancel) as http:
            for order,identifier in enumerate(self._identifiers(http,tokens)):
                check_cancel(self.cancel)
                item=http.json('https://archive.org/metadata/'+quote(identifier,safe=''))
                meta=item.get('metadata',{})
                if restricted_item(item):continue
                files=[f for f in item.get('files',[]) if f.get('name','').lower().endswith(self.AUDIO) and f.get('private') not in ('true',True)]
                # Archive-generated transcodes point at their source via "original".
                originals={f['name'] for f in files if f.get('source')=='original'}
                files=[f for f in files if not (f.get('source')=='derivative' and f.get('original') in originals)]
                album=clean(repair_text(meta.get('title')))
                # The item's credited artist vouches for all its tracks; its title only for a
                # single-track upload. Compilations titled "Best songs of X" are often grab-bags.
                item_key=title_key(clean(repair_text(meta.get('creator'))))+'|'+(title_key(album) if len(files)==1 else '')
                best={}
                for f in files:
                    title=file_title(f);stem=file_stem(f);creator=file_creator(f,meta)
                    file_key=title_key(' '.join([title,stem,creator]))
                    # Every word must appear in the track's own tags/name or the item's credit:
                    # "周杰伦" lists that artist's album tracks, "周杰伦 七里香" only that song,
                    # and "Jay Chou" works without guessing which word is the song.
                    if not all(k in file_key or k in item_key for k in keys):continue
                    # Damaged or generic tags ("Track 01") fall back to the file name.
                    shown=title if any(k in title_key(title) for k in keys) or not any(k in title_key(stem) for k in keys) else stem
                    # Generic names ("01", "Track 1") of a single-track upload that matched only
                    # through the item title: the item title says more.
                    if not title_key(shown) or shown.isdigit() or (len(files)==1 and not all(k in file_key for k in keys)):shown=album or shown
                    if not creator:
                        # Uncredited "Jay_Chou_-_Rainbow.mp3": the part before " - " is the artist
                        # when it is what the user searched for.
                        parts=re.match(r'^\s*(.+?)\s*[-–—]\s*(.+)$',shown.replace('_',' '))
                        # ...and little else: "周杰倫好聽的20首歌 Best Songs Of Jay Chou - ..." is a title, not an artist.
                        if parts and any(k in title_key(parts[1]) for k in keys) and len(title_key(parts[1]))<=sum(map(len,keys))+6:
                            creator,shown=parts[1].strip(),parts[2].strip()
                    rank=(0 if f.get('source')=='original' else 1,self.FORMAT_RANK.get(f['name'].rsplit('.',1)[-1].lower(),9))
                    if title_key(shown) not in best or rank<best[title_key(shown)][0]:
                        best[title_key(shown)]=(rank,f,shown,creator,sum(k in file_key for k in keys))
                for rank,f,shown,creator,hits in list(best.values())[:self.per_item]:
                    ranked.append(((-hits,order),PlatformSong('archive',identifier+'/'+f['name'],shown,creator or '未知歌手',album,
                        self._length(f.get('length')),'https://archive.org/details/'+quote(identifier,safe=''),file_version(f,meta,identifier))))
            self.requests=http.requests
        # Tracks naming all the words themselves first, then Archive's item order.
        ranked.sort(key=lambda r:r[0])
        return [song for _,song in ranked][:self.max_rows]

class PlatformSearchService:
    def __init__(self,path,cancel=None,providers=None):
        self.path=path;self.cancel=cancel or threading.Event();self.providers=providers or [CommonsMusicSearch(self.cancel),ArchiveMusicSearch(self.cancel)]
    def search(self,query):
        if not query.strip():raise ValueError('请输入歌曲或歌手')
        repo=DiscoveryRepository(self.path); started=time.perf_counter()
        key=f'platform-search-v{SEARCH_VERSION}:'+query.strip();cached=repo.cache(key,ttl=86400)
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
        if all(statuses[p.name]['status']=='COMPLETED' for p in self.providers):repo.cache(key,result)
        return result
