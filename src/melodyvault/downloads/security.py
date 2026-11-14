"""Fixed origin policy, public IP checks and DNS pinning at TCP connection time."""
import ipaddress,re,socket
from urllib.parse import urlsplit,unquote,urlunsplit,parse_qsl,urlencode
import httpx,httpcore
from melodyvault.downloads.models import DownloadError
from melodyvault.privacy import redact_payload,SECRET_KEYS


def resource_identity(url):
    p=urlsplit(url)
    params=sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k.lower() not in SECRET_KEYS and not k.lower().startswith(('utm_','x-amz-','x-goog-')))
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(params),''))


def strong_etag(value):
    # Bare checksum strings and W/ tags are not strong HTTP entity-tags.
    return bool(re.fullmatch(r'"[\x21\x23-\x7e\x80-\xff]*"',value or ''))


def public_addresses(host,port=443):
    values=list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)))
    if not values:raise DownloadError('UNSAFE_URL','来源域名未解析到有效地址')
    for value in values:
        ip=ipaddress.ip_address(value.split('%')[0]);ip=ip.ipv4_mapped if getattr(ip,'ipv4_mapped',None) else ip
        if not ip.is_global or ip.is_multicast or ip.is_reserved:raise DownloadError('UNSAFE_URL','禁止连接本地、私有或保留网络地址')
    return values


def validate_url(provider,url):
    try:
        p=urlsplit(url);host=p.hostname or ''
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or p.fragment:raise ValueError()
        if any(x in url for x in ('\r','\n','\\')) or any(x in unquote(p.path).split('/') for x in ('.','..')):raise ValueError()
        good=(provider=='commons' and host=='upload.wikimedia.org' and bool(re.fullmatch(r'/wikipedia/commons/[0-9a-f]/[0-9a-f]{2}/[^/]+',p.path)))
        good|=provider=='archive' and (host=='archive.org' or bool(re.fullmatch(r'ia\d+\.(?:us\.)?archive\.org',host))) and p.path.startswith('/download/')
        good|=provider=='jamendo' and bool(re.fullmatch(r'(?:prod-\d+\.)?storage\.jamendo\.com',host)) and p.path.startswith('/download/')
        good|=provider=='ccmixter' and host=='ccmixter.org' and bool(re.fullmatch(r'/content/[A-Za-z0-9_-]+/[^/]+\.(?:mp3|flac|wav|m4a|aac|ogg|opus)',p.path,re.I)) and not p.query
        if not good:raise ValueError()
    except (ValueError,TypeError):raise DownloadError('UNSAFE_URL','下载地址不在该来源允许的HTTPS原始文件范围') from None
    return p


class PublicBackend(httpcore.SyncBackend):
    def connect_tcp(self,host,port,timeout=None,local_address=None,socket_options=None):
        # httpcore still retains the original hostname for certificate checking/SNI.
        # DNS is resolved once, checked, then only the chosen literal IP is dialed.
        values=public_addresses(host,port);last=None
        for ip in values:
            try:return super().connect_tcp(ip,port,timeout,local_address,socket_options)
            except (httpcore.ConnectError,httpcore.ConnectTimeout) as error:last=error
        raise last


def audio_client(timeout=20,transport=None):
    if transport is None:
        transport=httpx.HTTPTransport(retries=0,trust_env=False)
        # Guard the narrow httpx/httpcore integration; fail closed on incompatible versions.
        if not hasattr(transport,'_pool') or not hasattr(transport._pool,'_network_backend'):
            transport.close();raise DownloadError('UNSAFE_TRANSPORT','网络库不支持已验证的DNS固定连接')
        transport._pool._network_backend=PublicBackend()
    return httpx.Client(transport=transport,trust_env=False,follow_redirects=False,
        timeout=httpx.Timeout(timeout,connect=min(10,timeout)),
        headers={'User-Agent':'MelodyVault/0.1 (+https://github.com/yuxiangliu-beginner/MelodyVault)','Accept-Encoding':'identity'})
