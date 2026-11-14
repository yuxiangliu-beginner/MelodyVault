"""Download identities are separate from a source search score or user song choice."""
from dataclasses import dataclass,field,asdict
from pathlib import Path
import hashlib,json

STATES={'QUEUED','SEARCHING','VERIFYING','READY','DOWNLOADING','PAUSED','COMPLETED','FAILED','CANCELLED','SKIPPED'}
ACTIVE={'QUEUED','SEARCHING','VERIFYING','READY','DOWNLOADING','PAUSED'}


@dataclass
class DownloadCandidate:
    song_id:str
    recording_id:str
    artist_name:str
    title:str
    version:str
    provider:str
    source_page_url:str
    direct_download_url:str=''
    external_id:str=''
    file_format:str=''
    file_size:int=0
    duration:float|None=None
    license_status:str='LICENSE_UNVERIFIED'
    license_name:str=''
    license_url:str=''
    download_permission:bool=False
    personal_storage_permission:bool=False
    metadata_match_status:str='UNVERIFIED'
    full_length_status:str='UNVERIFIED'
    confidence:str='UNVERIFIED'
    verification_reason:list[str]=field(default_factory=list)
    verified_at:str=''
    attribution:str=''
    restrictions:list[str]=field(default_factory=list)
    checksums:dict=field(default_factory=dict)
    evidence:dict=field(default_factory=dict)
    def to_dict(self):return asdict(self)
    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps([self.provider,self.external_id,self.recording_id,self.version,self.checksums],sort_keys=True).encode()).hexdigest()


@dataclass
class DownloadSettings:
    directory:str=str(Path(__file__).resolve().parents[3]/'.local'/'downloads')
    max_concurrent:int=2
    automatic_download:bool=False
    quality:str='original'
    speed_limit:int=0  # shared bytes/sec across this manager, zero = unlimited
    keep_temporary:bool=True
    max_file_bytes:int=512*1024*1024
    max_attempts:int=3
    timeout:float=20
    def validate(self):
        if not Path(self.directory).is_absolute():raise ValueError('下载目录必须为绝对路径')
        if not 1<=self.max_concurrent<=4:raise ValueError('并发数须为1–4')
        if self.quality not in {'original','lossless','small'}:raise ValueError('下载质量选项无效')
        if not 0<=self.speed_limit<=100*1024*1024:raise ValueError('速度限制无效')
        if not 1024<=self.max_file_bytes<=2*1024**3:raise ValueError('最大文件大小无效')
        if not 1<=self.max_attempts<=5 or not 1<=self.timeout<=120:raise ValueError('重试或超时设置无效')
        if type(self.automatic_download) is not bool or type(self.keep_temporary) is not bool:raise ValueError('下载开关必须是布尔值')
        return self


class DownloadError(Exception):
    def __init__(self,code,message):self.code=code;super().__init__(message)


class Interrupted(DownloadError):pass
