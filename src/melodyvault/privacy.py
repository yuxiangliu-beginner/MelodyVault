"""Shared credential redaction for persisted evidence; independent of network/UI."""
import re,html
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode

SECRET_KEYS={'access_token','refresh_token','id_token','token','api_key','client_secret','client_id','authorization','password','signature','sig','key','secret','cookie','set-cookie','credentials'}


def _url(url):
    try:
        p=urlsplit(html.unescape(url));pairs=parse_qsl(p.query,keep_blank_values=True)
        items=[(k,v) for k,v in pairs if k.lower() not in SECRET_KEYS and not k.lower().startswith(('x-amz-','x-goog-'))]
        if len(items)!=len(pairs) or p.username or p.password:
            host=p.hostname or '';host='['+host+']' if ':' in host else host
            return urlunsplit((p.scheme,host+(':'+str(p.port) if p.port else ''),p.path,urlencode(items),''))
    except ValueError:return '[INVALID_URL]'
    return url


def redact_payload(value):
    if isinstance(value,dict):return {k:('[REDACTED]' if k.lower() in SECRET_KEYS else redact_payload(v)) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [redact_payload(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'https?://[^\s<>"\']+',lambda m:_url(m[0]),value)
        return re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+','Bearer [REDACTED]',value)
    return value
