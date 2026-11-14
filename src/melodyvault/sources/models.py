from dataclasses import dataclass, field, asdict
import hashlib
import json
import re
from melodyvault.catalog.normalize import display_name, title_key
from melodyvault.catalog.grouping import version_kind


def unique(values):
    return list(dict.fromkeys(v for v in values if v and str(v).strip()))


@dataclass
class SourceQuery:
    artist_mbid:str
    song_id:str
    artist:str
    title:str
    artist_names:list[str]
    titles:list[str]
    versions:list[str]
    lengths_ms:list[int]
    recording_ids:list[str]
    fingerprint:str=''

    def __post_init__(self):
        if not self.fingerprint:
            payload=asdict(self);payload.pop('fingerprint')
            profile='source-query-v3' if self.version_words else 'source-query-v2'
            self.fingerprint=hashlib.sha256(json.dumps([profile,payload],sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    @property
    def version_words(self):
        if len(self.versions)!=1:return []
        return {'live':['live','现场','現場'],'remix':['remix','混音'],'karaoke':['karaoke','伴奏'],
            'instrumental':['instrumental','演奏'],'rerecording':['re-recording','重录','重錄']}.get(self.versions[0],[])

    @property
    def keyword_pairs(self):
        from melodyvault.catalog.normalize import search_names
        simple, *traditional=search_names(self.artist)
        title_simple, *title_traditional=search_names(self.title)
        pairs=[(simple,title_simple),(traditional[0] if traditional else simple,title_traditional[0] if title_traditional else title_simple)]
        english_artist=next((a for a in self.artist_names if a.isascii() and any(c.isalpha() for c in a)),None)
        english_title=next((t for t in self.titles if t.isascii() and any(c.isalpha() for c in t)),self.title)
        if english_artist:pairs.append((english_artist,english_title))
        return list(dict.fromkeys(pairs))

    @classmethod
    def from_song(cls,artist,song,works):
        names=[artist.name,display_name(artist.name)]
        names += [a['name'] for a in artist.payload.get('aliases',[]) if a.get('primary') and (a.get('locale','') or '').startswith(('en','zh'))]
        # Always include a real English alias if supplied; never invent translations.
        if not any(re.search('[a-zA-Z]',name) for name in names):
            names += [a for a in artist.aliases if re.search('[a-zA-Z]',a) and len(a.split())>=2][:1]
        titles=[song.title,display_name(song.title)]
        for wid in song.work_ids:
            titles += [a.get('name') for a in works.get(wid,{}).get('aliases',[])]
        titles += [e['title'] for e in song.evidence if e.get('rule')=='user_selected_search_alias' and e.get('title')]
        titles += [r.original_title for r in song.recordings if title_key(r.title)==title_key(song.title)][:2]
        main=next((r for r in song.recordings if r.mbid==song.primary_recording_mbid),None)
        versions=[version_kind(main)[0]] if main else unique(version_kind(r)[0] for r in song.recordings)
        return cls(artist.mbid,song.id,artist.name,song.title,unique(names),unique(titles)[:10],versions,
                   unique(r.length_ms for r in ([main] if main else song.recordings) if r.length_ms),sorted(r.mbid for r in song.recordings))


@dataclass
class Candidate:
    provider:str
    external_id:str
    title:str
    performer:str
    page_url:str
    duration_seconds:float|None=None
    version:str='unknown'
    license_url:str=''
    license_status:str='LICENSE_UNVERIFIED'
    license_reason:str='缺少明确授权证据'
    license_statement:str=''
    audio_url:str=''
    match_status:str='REVIEW_REQUIRED'
    match_score:int=0
    match_reasons:list[str]=field(default_factory=list)
    evidence:dict=field(default_factory=dict)
    file_format:str=''
    file_size:int=0
