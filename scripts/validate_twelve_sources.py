"""Bounded public-page research, no audio parsing or production database writes.

Raw results stay under .local. This is not a production source adapter.
"""
import concurrent.futures
import datetime
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

ROOT = Path('.local/reports/twelve-sources-validation')
SITES = {
    'myfreemp3': 'https://tool.liumingye.cn/music/',
    'xiageba': 'https://xiageba.com/',
    'wusunk': 'https://wusunk.com/',
    '23ape': 'http://www.23ape.net/',
    'fma': 'https://freemusicarchive.org/',
    'cctrax': 'https://cctrax.com/',
    'cdbao': 'https://www.cdbao.net/',
    'hifi15': 'https://hifi15.com/',
    'netease': 'https://music.163.com/',
    'kuwo': 'https://www.kuwo.cn/',
    'migu': 'https://music.migu.cn/',
    'tonzhon': 'https://tonzhon.com/',
}


def probe(name, url):
    ROOT.mkdir(parents=True, exist_ok=True)
    result = {'source': name, 'requested_url': url,
              'time': datetime.datetime.now().astimezone().isoformat(),
              'purpose': 'public page only, not song search', 'requests': []}
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=httpx.Timeout(12), trust_env=False,
                          headers={'User-Agent': 'MelodyVaultResearch/0.1 (public-page evaluation)'},
                          follow_redirects=False) as client:
            current = url
            for _ in range(4):
                with client.stream('GET', current) as r:
                    entry = {'url': str(r.url), 'http_status': r.status_code,
                             'content_type': r.headers.get('content-type', '')}
                    result['requests'].append(entry)
                    if r.is_redirect:
                        location = urljoin(current, r.headers.get('location', ''))
                        entry['location'] = location
                        old, new = urlsplit(current), urlsplit(location)
                        if (new.scheme not in {'http','https'} or
                            new.hostname.removeprefix('www.') != old.hostname.removeprefix('www.') or
                            (old.scheme == 'https' and new.scheme != 'https')):
                            result['status'] = 'REDIRECT_NOT_FOLLOWED'; break
                        current = location
                        continue
                    body = bytearray()
                    for chunk in r.iter_bytes():
                        body.extend(chunk)
                        if len(body) >= 1_000_000: break
                    data = bytes(body[:1_000_000])
                    (ROOT / (name + '.html')).write_bytes(data)
                    result['body_sha256'] = hashlib.sha256(data).hexdigest()
                    result['bytes_saved'] = len(data)
                    result['encoding'] = r.encoding
                    result['status'] = ('PAGE_RECEIVED' if r.status_code == 200 else
                                        'RATE_LIMITED' if r.status_code == 429 else
                                        'ACCESS_RESTRICTED' if r.status_code in {401,403} else 'HTTP_ERROR')
                    break
            else: result['status'] = 'REDIRECT_LIMIT'
    except httpx.RequestError as e:
        result.update(status='NETWORK_ERROR', error=type(e).__name__+': '+str(e))
    result['elapsed_seconds'] = round(time.perf_counter()-start, 3)
    (ROOT/(name+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda item: probe(*item), SITES.items()))
    (ROOT/'phase-b.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in results: print(r['source'],r['status'],r['elapsed_seconds'],r.get('error',''))
