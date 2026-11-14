from dataclasses import dataclass,field,asdict
import unicodedata,hashlib,json
import re
from functools import lru_cache
from uuid import UUID
from melodyvault.catalog.models import Artist
from melodyvault.catalog.normalize import display_name,base_title


def identity_key(text):
    text=unicodedata.normalize('NFKD',display_name(text).casefold())
    return ''.join(c for c in text if not unicodedata.category(c).startswith(('P','Z','M')) and not c.isspace())


def song_key(text):return identity_key(base_title(text))


@lru_cache(maxsize=4096)
def pinyin_key(text):
    text=base_title(text)
    if not re.search('[\u3400-\u9fff]',text):return ''
    from pypinyin import lazy_pinyin
    return 'pinyin:'+identity_key(''.join(lazy_pinyin(text)))


@dataclass
class SearchRequest:
    query:str
    mode:str='smart'
    artist_hint:str=''
    artist_ids:tuple[str,...]=()
    local_only:bool=False
    force_online:bool=False
    def __post_init__(self):
        self.query=self.query.strip();self.artist_hint=self.artist_hint.strip()
        try:self.artist_ids=tuple(sorted({str(UUID(x)) for x in self.artist_ids}))
        except (ValueError,TypeError,AttributeError) as error:raise ValueError('歌手MBID格式不正确') from error
        if not self.query or len(self.query)>300:raise ValueError('请输入1–300个字符的歌手或歌曲名称')
        if self.mode not in {'smart','artist','song'}:raise ValueError('不支持的搜索模式')
    def cache_key(self):
        # Keep token boundaries: "AB C" and "A BC" can resolve different
        # artist/song splits even though their punctuation-free keys coincide.
        return hashlib.sha256(json.dumps(['unified-v3',self.mode,display_name(self.query).casefold(),identity_key(self.artist_hint),self.artist_ids],ensure_ascii=False).encode()).hexdigest()


@dataclass
class SongCandidate:
    recording_mbid:str
    title:str
    artist:Artist
    performers:list[dict]=field(default_factory=list)
    song_id:str|None=None
    work_ids:tuple[str,...]=()
    version:str='unknown'
    length_ms:int|None=None
    origin:str='sqlite'
    pending_confirmation:bool=True
    title_exact:bool=False
    reasons:list[str]=field(default_factory=list)
    payload:dict=field(default_factory=dict)
    @property
    def id(self):return self.artist.mbid+':'+self.recording_mbid
    def to_dict(self):return asdict(self)
    @classmethod
    def from_dict(cls,data):
        data=dict(data);data['artist']=Artist(**data['artist']);data['work_ids']=tuple(data.get('work_ids',[]))
        return cls(**data)


@dataclass
class SearchResult:
    request:SearchRequest
    artists:list[Artist]=field(default_factory=list)
    songs:list[SongCandidate]=field(default_factory=list)
    errors:dict=field(default_factory=dict)
    title_query:str=''
    scope:str='sqlite'
    cache_hit:bool=False
    elapsed_seconds:float=0
    api_requests:int=0
    retries:int=0
    truncated:bool=False
    catalog_revision:int=0
    def to_dict(self):
        return {**asdict(self),'songs':[s.to_dict() for s in self.songs]}
    @classmethod
    def from_dict(cls,data):
        data=dict(data);data['request']=SearchRequest(**data['request']);data['artists']=[Artist(**a) for a in data['artists']]
        data['songs']=[SongCandidate.from_dict(s) for s in data['songs']]
        return cls(**data)
