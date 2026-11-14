import os,re,threading,time,json
import httpx
from dataclasses import asdict
from urllib.parse import urlsplit
from html import unescape
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.discovery.models import DiscoveryHit,domain_key,query_plan
from melodyvault.discovery.http import DiscoveryHTTP


class WikipediaDiscovery:
    name='wikipedia_external_links'
    def search(self,query,http):
        api='https://zh.wikipedia.org/w/api.php'
        data=http.get(api,{'action':'query','format':'json','formatversion':2,'generator':'search',
            'gsrsearch':query,'gsrlimit':3,'prop':'extlinks|info','inprop':'url','ellimit':20,'maxlag':5}).json()
        if data.get('error'):raise ValueError('Wikipedia API: '+str(data['error']))
        hits=[]
        for page in data.get('query',{}).get('pages',[]):
            for link in page.get('extlinks',[]):
                url=link.get('url') or link.get('*','')
                if not url.startswith('https://'):continue
                hits.append(DiscoveryHit(urlsplit(url).hostname,url,query,self.name,
                    {'api_url':api,'article_url':page.get('fullurl',''),'page_id':page['pageid'],
                     'article_title':page.get('title',''),
                     'scope':'百科相关页面外链；不是全网搜索结果，也未证明具体歌曲/音频/下载权限'}))
        return hits


class BraveDiscovery:
    name='brave_official_api'
    def __init__(self,key):self.key=key
    def search(self,query,http):
        data=http.get('https://api.search.brave.com/res/v1/web/search',{'q':query,'count':5},
                      {'X-Subscription-Token':self.key,'Accept':'application/json'}).json()
        return [DiscoveryHit(urlsplit(v['url']).hostname,v['url'],query,self.name,
                {'result_title':v.get('title',''),'description':v.get('description',''),'scope':'搜索结果不构成授权'})
                for v in data.get('web',{}).get('results',[]) if v.get('url','').startswith('https://')]


class SourceDiscoveryService:
    def __init__(self,repository,cancel=None,progress=None,http_factory=None,backends=None):
        self.repository=repository;self.cancel=cancel or threading.Event();self.progress=progress or (lambda x:None)
        self.http_factory=http_factory or DiscoveryHTTP
        self.backends=backends if backends is not None else [WikipediaDiscovery()]
        if backends is None and os.environ.get('BRAVE_SEARCH_API_KEY'):self.backends.append(BraveDiscovery(os.environ['BRAVE_SEARCH_API_KEY']))
    def discover(self,artist='',title='',aliases=(),force=False,max_checks=5):
        started=time.perf_counter();plan=query_plan(artist,title,aliases);found=set();errors=[];cached=0
        with self.http_factory(self.cancel) as http:
            for backend in self.backends:
                queries=plan if backend.name!='wikipedia_external_links' else plan[:2]
                for i,q in enumerate(queries):
                    check_cancel(self.cancel);key=json.dumps([backend.name,q],ensure_ascii=False)
                    values=None if force else self.repository.cache(key)
                    try:
                        self.progress({'message':f'{backend.name} · {q}','processed':i,'total':len(queries)})
                        if values is None:
                            values=[asdict(v) for v in backend.search(q,http)][:60];self.repository.cache(key,values)
                        else:cached+=1
                        for value in values:
                            try:found.add(self.repository.discover(DiscoveryHit(**value)))
                            except ValueError:continue
                    except CatalogCancelled:raise
                    except Exception as e:errors.append({'channel':backend.name,'query':q,'error':str(e)})
            checked=0
            for domain in sorted(found):
                check_cancel(self.cancel);row=self.repository.get(domain)
                if checked>=max_checks:break
                if not row['enabled'] or not force and time.time()-row['checked_at']<86400:continue
                self.progress({'message':'检查 '+domain,'processed':checked,'total':min(max_checks,len(found))})
                self.check(domain,http);checked+=1
            return {'domains':sorted(found),'discovered':len(found),'checked':checked,'cached_queries':cached,
                    'errors':errors,'api_requests':http.requests,'retries':http.retries,
                    'elapsed_seconds':time.perf_counter()-started,'query_plan':plan,
                    'general_search':'已配置' if any(b.name=='brave_official_api' for b in self.backends) else '未配置；本次仅公开目录外链发现'}
    def check(self,domain,http=None):
        if http is None:
            with self.http_factory(self.cancel) as client:return self.check(domain,client)
        row=self.repository.get(domain)
        if row is None:raise ValueError('Unknown source')
        cap={'state':'DISCOVERED','accessible':None,'search_supported':None,'chinese_search':None,
             'metadata':None,'full_audio':None,'formats':[],'login_required':None,'payment_required':None,
             'automation_allowed':None,'download_permission':'LICENSE_UNVERIFIED','integratable':False,
             'risk':'UNKNOWN','url':row['first_url']}
        try:
            from melodyvault.database.discovery import BUILTINS
            if domain in BUILTINS:
                return self._check_api(domain,http,cap)
            allowed,policy=http.robots(row['first_url']);cap.update(automation_allowed=allowed,automation_evidence=policy)
            if allowed is not True:
                cap.update(state='RESTRICTED',reason='自动访问禁止或无法确认；未读取歌曲页')
            else:
                response=http.get(row['first_url'],limit=256*1024);text=response.text
                cap.update(accessible=True,state='ACCESSIBLE',risk='REVIEW_REQUIRED',http_status=response.status_code,
                    search_supported=bool(re.search(r'<form[^>]+(?:search|搜索)|[?&](?:q|search)=',text,re.I)),
                    login_required=True if re.search(r'login required|请先登录|需要登入',text,re.I) else None,
                    payment_required=True if re.search(r'payment required|付费后|購買後',text,re.I) else None,
                    formats=sorted(set(m.lower() for m in re.findall(r'\b(MP3|FLAC|WAV|M4A|AAC|OGG|Opus)\b',text,re.I))),
                    reason='网页提及的格式、搜索表单仅为调查线索；未核验特定歌曲、完整性或授权')
                if cap['search_supported']:cap['state']='SEARCH_SUPPORTED'
                cap['page_title']=unescape(re.sub('<[^>]*>','',next(iter(re.findall(r'<title[^>]*>(.*?)</title>',text,re.I|re.S)),'')))[:240]
        except CatalogCancelled:raise
        except Exception as e:
            unsafe='重定向' in str(e) or '私有' in str(e) or '公共' in str(e)
            restricted=isinstance(e,httpx.HTTPStatusError) and e.response.status_code in {401,403,429}
            cap.update(state='UNSAFE' if unsafe else 'RESTRICTED' if restricted else 'UNAVAILABLE',risk='HIGH' if unsafe else 'UNKNOWN',error=str(e))
        self.repository.verify(domain,cap);return cap

    def _check_api(self,domain,http,cap):
        from melodyvault.database.discovery import BUILTINS
        endpoints={
            'commons.wikimedia.org':('https://commons.wikimedia.org/w/api.php',{'action':'query','format':'json','meta':'siteinfo'},'https://www.mediawiki.org/wiki/API:Etiquette'),
            'archive.org':('https://archive.org/advancedsearch.php',{'q':'title:晴天','output':'json','rows':1},'https://archive.org/developers/'),
            'ccmixter.org':('https://ccmixter.org/api/query',{'f':'json','search':'晴天','search_type':'all','limit':1},'https://license.ccmixter.org/about'),
        }
        if domain not in endpoints:
            cap.update(state='METADATA_ONLY',reason='Jamendo client_id 未配置；未请求 API',automation_allowed=None)
            self.repository.verify(domain,cap);return cap
        url,params,policy=endpoints[domain]
        data=http.get(url,params).json()
        if not isinstance(data,(dict,list)) or isinstance(data,dict) and data.get('error'):raise ValueError('官方 API 返回错误')
        cap.update(state='SEARCH_SUPPORTED',accessible=True,search_supported=True,metadata=True,
            chinese_search=True,automation_allowed=True,automation_evidence=policy,api_url=url,
            risk='FILE_REVIEW_REQUIRED',reason='官方 API 接受中文查询；命中/完整性/授权逐文件核验',
            integratable=True,download_permission='LICENSE_UNVERIFIED')
        self.repository.verify(domain,cap)
        self.repository.approve_compiled(domain,BUILTINS[domain][1],{'policy_url':policy,'scope':'compiled official metadata adapter; never blanket download permission'})
        return cap

    def initialize_compiled(self):
        from melodyvault.database.discovery import BUILTINS
        results={}
        with self.http_factory(self.cancel) as http:
            for domain,(name,provider) in BUILTINS.items():
                check_cancel(self.cancel)
                self.repository.discover(DiscoveryHit(name,'https://'+domain+'/',provider,'compiled_adapter',{'scope':'预置适配器，不计为自动发现的新网站'}))
                self.progress({'message':'核验官方 API '+domain})
                results[domain]=self.check(domain,http)
            return {'sources':results,'api_requests':http.requests,'retries':http.retries}
