"""Conservative name discovery; candidates never authorize audio or merge works."""
from dataclasses import replace
import time
from melodyvault.catalog.models import Artist,Recording,CatalogCancelled
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.catalog.normalize import search_names
from melodyvault.catalog.service import _quote_query
from melodyvault.catalog.grouping import version_kind
from melodyvault.database.search import SearchRepository
from melodyvault.search.models import SearchRequest,SearchResult,SongCandidate,identity_key,song_key


class ArtistSearchService:
    def __init__(self,index,client):self.index=index;self.client=client
    def local(self,text):
        key=identity_key(text)
        return [a for a in self.index.artists() if key in {identity_key(n) for n in (a.name,*a.aliases)}]
    def online(self,text):
        names=list(dict.fromkeys([text,*search_names(text)]))
        query=' OR '.join(f'{field}:{_quote_query(n)}' for field in ('artist','alias') for n in names)
        response=self.client.get_json('artist',{'query':query,'limit':25})
        candidates=[Artist.from_payload(a) for a in response['artists']]
        return sorted(candidates,key=lambda a:(identity_key(text) not in {identity_key(n) for n in (a.name,*a.aliases)},a.mbid))
    def prefixes(self,text,artists):
        keys={}
        for artist in artists:
            for name in (artist.name,*artist.aliases):keys.setdefault(identity_key(name),[]).append(artist)
        for end in range(len(text)-1,0,-1):
            prefix=text[:end].strip();rest=text[end:].lstrip(' -—–:/：')
            # An English alias cannot consume the beginning of a longer word.
            if text[end-1:end].isascii() and text[end:end+1].isascii() and text[end-1:end].isalnum() and text[end:end+1].isalnum():continue
            matches=keys.get(identity_key(prefix),[])
            if rest and matches:return list({a.mbid:a for a in matches}.values()),rest
        return [],text


class SongSearchService:
    def __init__(self,index,client):self.index=index;self.client=client
    def local(self,title,artists=()):
        allowed={a.mbid for a in artists};known={a.mbid:a for a in self.index.artists()};found={}
        for aid,row,kind in self.index.title_rows(title):
            if allowed and aid not in allowed:continue
            artist=known.get(aid)
            if artist is None:continue
            reasons=['原始Recording ID和已保存Song分组保留','名称或已保存官方别名规范化一致']
            if kind==1:reasons.append('来自用户目标选择历史；不是官方别名或作品合并证据')
            if kind==2:reasons.append('仅普通话拼音转写线索，可能同音不同作品；不是官方英文别名，需人工确认')
            if row['reviewed']:reasons.append('已有人工审核分组；本次搜索不会覆盖')
            candidate=SongCandidate(row['recording_mbid'],row['title'],artist,row['performers'],row['song_id'],
                tuple(row['work_ids']),row['version'],row['length_ms'],'sqlite',row['pending'] or kind==2,kind!=2,reasons)
            if candidate.id not in found:found[candidate.id]=candidate
        return sorted(found.values(),key=lambda c:(c.artist.mbid,c.version,c.recording_mbid))
    def online(self,title,artists=(),artist_hint=''):
        names=list(dict.fromkeys([title,*search_names(title)]))
        expression='('+' OR '.join(f'{field}:{_quote_query(n)}' for n in names for field in ('recording','alias'))+')'
        contexts={a.mbid:a for a in artists}
        if contexts:expression+=' AND ('+' OR '.join('arid:'+a for a in sorted(contexts))+')'
        elif artist_hint:expression+=' AND artistname:'+_quote_query(artist_hint)
        response=self.client.get_json('recording',{'query':expression+' AND video:false','limit':50})
        local={(aid,row['recording_mbid']):row for aid,row in self.index.recording_rows([r['id'] for r in response['recordings']])}
        found={}
        for payload in response['recordings']:
            if payload.get('video') is True:continue
            credits=[c['artist'] for c in payload.get('artist-credit',[]) if isinstance(c,dict) and c.get('artist',{}).get('id')]
            if not credits:continue
            matching=[c for c in credits if not contexts or c['id'] in contexts]
            if contexts and not matching:continue
            for performer in matching:
                context=contexts.get(performer['id'])
                artist=context if context and context.name else Artist.from_payload(performer)
                stored=local.get((artist.mbid,payload['id']))
                alias_names=[a.get('name','') for a in payload.get('aliases',[])]
                exact=song_key(title) in {song_key(n) for n in [payload['title'],*alias_names]}
                record=Recording.from_payload(payload);kind=version_kind(record)[0]
                reasons=['MusicBrainz Recording检索命中；API分数不是身份确认',f'演唱署名MBID：{artist.mbid}']
                if stored:reasons.append('Recording ID已存在本地；保留其当前Song/人工分组')
                if not exact:reasons.append('仅检索相关/索引别名线索，歌名仍待确认')
                candidate=SongCandidate(payload['id'],payload['title'],artist,credits,
                    stored['song_id'] if stored else None,tuple(stored['work_ids']) if stored else (),
                    stored['version'] if stored else kind,payload.get('length'),'musicbrainz',
                    not stored or stored['pending'] or not exact,exact,reasons,
                    {k:payload[k] for k in ('id','title','length','video','artist-credit','disambiguation','isrcs','aliases') if k in payload})
                found[candidate.id]=candidate
        return list(found.values()),response['count']>len(response['recordings'])


class UnifiedSearchEngine:
    def __init__(self,repository,client,progress=None,partial=None):
        self.repository=repository;self.index=SearchRepository(repository);self.client=client
        self.progress=progress or (lambda message:None)
        self.partial=partial
        self.artists=ArtistSearchService(self.index,client);self.songs=SongSearchService(self.index,client)
    def search(self,request):
        started=time.perf_counter();self.progress('读取本地歌手/歌曲索引')
        self.index.ensure_index(self.client.cancel);check_cancel(self.client.cancel)
        local_artists=self.artists.local(request.query)
        all_artists=self.index.artists();contexts=[];title=request.query
        if request.artist_ids:
            known={a.mbid:a for a in all_artists}
            contexts=[known.get(aid) or Artist(aid,'') for aid in request.artist_ids]
        elif request.artist_hint:contexts=self.artists.local(request.artist_hint)
        elif request.mode!='artist':contexts,title=self.artists.prefixes(request.query,all_artists)
        local_songs=self.songs.local(title,contexts) if request.mode!='artist' else []
        # Explicit unresolved singer text must not accidentally search all local singers.
        if request.artist_hint and not contexts:local_songs=[]
        listed_artists=list({a.mbid:a for a in [*local_artists,*contexts] if a.name}.values()) if request.mode!='song' else []
        result=SearchResult(request,listed_artists,local_songs,title_query=title)
        result.catalog_revision=self.index.revision()
        reliable=bool(any(s.title_exact for s in local_songs) and (contexts or request.artist_ids)) or bool(local_artists and title==request.query and request.mode!='song')
        effective=replace(request,artist_ids=tuple(a.mbid for a in contexts) or request.artist_ids)
        if request.local_only:
            result.elapsed_seconds=time.perf_counter()-started;return result
        if not request.force_online:
            cached=self.index.cached(effective)
            if cached:
                cached.elapsed_seconds=time.perf_counter()-started;return cached
        if reliable and not request.force_online:
            result.elapsed_seconds=time.perf_counter()-started;return result
        if self.partial and (result.artists or result.songs):
            result.elapsed_seconds=time.perf_counter()-started
            self.partial(replace(result,artists=list(result.artists),songs=list(result.songs),errors=dict(result.errors)))
        result.request=effective;result.scope='musicbrainz'
        self.progress('本地无可靠匹配或已明确要求联网；查询MusicBrainz')
        if request.mode!='song':
            try:
                online=self.artists.online(request.query)
                result.artists=list({a.mbid:a for a in [*result.artists,*online]}.values())
            except CatalogCancelled:raise
            except Exception as error:result.errors['artist']=str(error)
        if request.mode!='artist':
            preliminary=None;preliminary_truncated=False
            if request.artist_hint and not contexts:
                try:
                    options=self.artists.online(request.artist_hint)
                    contexts=[a for a in options if identity_key(request.artist_hint) in {identity_key(n) for n in (a.name,*a.aliases)}]
                except CatalogCancelled:raise
                except Exception as error:result.errors['artist_filter']=str(error)
            if not contexts and not request.artist_hint and not local_songs:
                # Prefixes are validated artist identities, never a keyword-length guess.
                # First respect a whole multiword song title (e.g. All Of Me).
                try:preliminary,preliminary_truncated=self.songs.online(title)
                except CatalogCancelled:raise
                except Exception as error:result.errors['song']=str(error)
                pieces=request.query.split()
                splits=[] if preliminary is None or any(c.title_exact for c in preliminary) else range(len(pieces)-1,max(0,len(pieces)-4),-1)
                for count in splits:
                    prefix=' '.join(pieces[:count]);rest=' '.join(pieces[count:])
                    try:
                        options=self.artists.online(prefix)
                        exact=[a for a in options if identity_key(prefix) in {identity_key(n) for n in (a.name,*a.aliases)}]
                    except CatalogCancelled:raise
                    except Exception as error:result.errors['prefix']=str(error);break
                    if exact:
                        contexts=exact;title=rest
                        if request.mode=='smart':result.artists=list({a.mbid:a for a in [*result.artists,*exact]}.values())
                        break
            try:
                if preliminary is not None and not contexts and not request.artist_hint:online,truncated=preliminary,preliminary_truncated
                elif 'song' in result.errors and preliminary is None and not contexts and not local_songs:online,truncated=[],False
                else:online,truncated=self.songs.online(title,contexts,request.artist_hint)
                result.songs=list({c.id:c for c in [*local_songs,*online]}.values());result.truncated=truncated
                result.title_query=title
            except CatalogCancelled:raise
            except Exception as error:result.errors['song']=str(error)
        check_cancel(self.client.cancel)
        result.request=replace(request,artist_ids=tuple(a.mbid for a in contexts) or request.artist_ids)
        result.elapsed_seconds=time.perf_counter()-started;result.api_requests=self.client.requests;result.retries=self.client.retries
        self.index.save_cache(result)
        # Persist the typed original request too, so a previously unknown prefix reuses it.
        if result.request.cache_key()!=effective.cache_key():
            self.index.save_cache(result,lookup_request=effective)
        return result
