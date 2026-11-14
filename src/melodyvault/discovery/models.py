from dataclasses import dataclass, field, asdict
from urllib.parse import urlsplit, urlunsplit
import ipaddress

STATES = {'DISCOVERED','ACCESSIBLE','SEARCH_SUPPORTED','METADATA_ONLY',
          'FULL_AUDIO_CANDIDATE','DOWNLOAD_PERMISSION_VERIFIED','LICENSE_UNVERIFIED',
          'RESTRICTED','UNSAFE','UNAVAILABLE'}


def public_url(value):
    """Syntax check only; the transport also pins and checks every resolved IP."""
    p = urlsplit(value)
    if p.scheme != 'https' or p.username or p.password or p.port not in (None,443):
        raise ValueError('仅接受无凭据的公共 HTTPS 地址')
    host = (p.hostname or '').rstrip('.').encode('idna').decode().lower()
    if not host or '.' not in host or any(c in value for c in ('\\','\r','\n')):
        raise ValueError('无效的公共域名')
    try:
        if not ipaddress.ip_address(host).is_global: raise ValueError('私网地址')
    except ValueError as e:
        if str(e) == '私网地址': raise
    if host.endswith(('.local','.localhost','.internal')): raise ValueError('本地域名')
    return urlunsplit(('https',host,p.path or '/',p.query,''))


def domain_key(url):
    host = urlsplit(public_url(url)).hostname
    return host.removeprefix('www.')


@dataclass
class DiscoveryHit:
    name: str
    url: str
    query: str
    channel: str
    evidence: dict = field(default_factory=dict)


def query_plan(artist='', title='', aliases=()):
    from melodyvault.catalog.normalize import search_names
    from pypinyin import lazy_pinyin
    base=' '.join(v.strip() for v in (artist,title) if v.strip())
    if not base: raise ValueError('请输入歌手或歌曲')
    names=list(dict.fromkeys([*search_names(base),*aliases,' '.join(' '.join(lazy_pinyin(base)).split())]))
    # A plan is explicit, bounded and auditable. Public encyclopedias use only
    # identity queries; configured general search APIs also use format/intents.
    return list(dict.fromkeys([*names,*[f'{base} {v}' for v in
        ('MP3','FLAC','WAV','M4A','免费下载','完整音频','官方免费发布','Creative Commons 音乐')]]))
