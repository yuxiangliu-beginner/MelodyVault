"""Public, allowlisted Chrome pages only. No shared profile, stealth or media reads."""
from urllib.parse import urlsplit,quote,unquote
from urllib.robotparser import RobotFileParser
import re
from melodyvault.catalog.models import CatalogError
from melodyvault.catalog.musicbrainz import check_cancel
from melodyvault.sources.http import UA
from melodyvault.providers.archive import ArchiveProvider


class PublicBrowser:
    def __init__(self,http,headless=True):
        self.http=http;self.headless=headless;self.browser=None;self.context=None;self.runtime=None
        self.policy_cache={};self.version='';self.navigation_count=0
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.runtime=sync_playwright().start()
        try:
            self.browser=self.runtime.chromium.launch(channel='chrome',headless=self.headless)
            self.version=self.browser.version
            self.context=self.browser.new_context(user_agent=UA,accept_downloads=False,service_workers='block')
            self.context.route('**/*',self._route)
            return self
        except BaseException:
            self.__exit__();raise
    def __exit__(self,*args):
        if self.context:self.context.close()
        if self.browser:self.browser.close()
        if self.runtime:self.runtime.stop()
    @staticmethod
    def allowed_url(url):
        p=urlsplit(url)
        return p.scheme=='https' and p.hostname in {'archive.org','commons.wikimedia.org'} and not p.username and p.port in (None,443) and (
            p.hostname=='archive.org' and p.path.startswith(('/search','/details/')) or
            p.hostname=='commons.wikimedia.org' and p.path.startswith('/wiki/File:'))
    def policy(self,url):
        if not self.allowed_url(url):raise CatalogError('浏览器网址不在已核实公开页面白名单')
        p=urlsplit(url)
        if p.hostname not in self.policy_cache:
            robots=self.http.get('https://'+p.hostname+'/robots.txt').text
            parser=RobotFileParser();parser.parse(robots.splitlines());self.policy_cache[p.hostname]=parser
        if not self.policy_cache[p.hostname].can_fetch('MelodyVault',url):raise CatalogError('robots.txt不允许此公开页面的自动访问')
    def _route(self,route):
        request=route.request;p=urlsplit(request.url)
        media_suffix=p.path.lower().endswith(('.mp3','.mp4','.ogg','.flac','.wav','.m4a','.opus')) and not request.is_navigation_request()
        if self.http.cancel.is_set() or request.resource_type in {'media','image','font'} or p.hostname not in {'archive.org','commons.wikimedia.org'} or p.path.startswith(('/download/','/serve/','/stream/')) or media_suffix:
            route.abort();return
        if request.is_navigation_request():
            try:self.policy(request.url)
            except Exception:route.abort();return
        route.continue_()
    def read(self,url):
        check_cancel(self.http.cancel);self.policy(url)
        page=self.context.new_page()
        try:
            self.navigation_count+=1
            response=page.goto(url,wait_until='domcontentloaded',timeout=20000)
            if response is None or response.status!=200:raise CatalogError(f'Chrome HTTP {response.status if response else "无响应"}；停止，不绕过限制')
            result_links=[]
            if urlsplit(url).path.startswith('/search'):
                # Wait for actual public search output, never for an arbitrary timer.
                page.get_by_role('heading',name=re.compile(r'\bResults?\b|No results',re.I)).first.wait_for(state='visible',timeout=15000)
                heading=page.get_by_role('heading',name=re.compile(r'\bResults?\b|No results',re.I)).first.inner_text()
                if not re.search(r'\b0\s+Results?\b|No results',heading,re.I):
                    feed=page.get_by_role('feed',name='Search results')
                    feed.locator('a[href*="/details/"]').first.wait_for(timeout=10000)
                    result_links=feed.locator('a[href*="/details/"]').evaluate_all('(nodes)=>nodes.map(a=>({text:a.innerText,url:a.href}))')
            body=page.locator('body').inner_text(timeout=10000)
            if urlsplit(url).path.startswith('/search'):body=page.locator('body').aria_snapshot()
            lowered=body.casefold()
            if any(term in lowered for term in ('verify you are human','checking your browser','access denied','captcha challenge','just a moment...')):
                raise CatalogError('Chrome遇到验证码/访问控制，已停止该来源')
            check_cancel(self.http.cancel)
            links=page.locator('a[href]').evaluate_all('(nodes)=>nodes.map(a=>({text:a.innerText,url:a.href}))')
            return {'url':page.url,'title':page.title(),'text':body[:40000],'links':links[:500],'search_results':result_links,
                    'chrome_version':self.version,'robots_checked':True,'policy_url':'https://archive.org/developers/bots.html' if 'archive.org' in url else 'https://www.mediawiki.org/wiki/API:Etiquette'}
        finally:page.close()
    def search(self,query):
        # Archive explicitly documents automated API/page access; search limits remain bounded.
        artists='('+ ' OR '.join('"'+name.replace('"',' ')+'"' for name in query.artist_names)+')'
        titles='('+' OR '.join('"'+name.replace('"',' ')+'"' for name in query.titles)+')'
        keywords=f'creator:{artists} AND (title:{titles} OR description:{titles}) AND mediatype:audio'
        if query.version_words:
            words='('+' OR '.join('"'+word+'"' for word in query.version_words)+')'
            keywords+=f' AND (title:{words} OR description:{words})'
        evidence=self.read('https://archive.org/search?query='+quote(keywords))
        identifiers=[]
        for link in evidence['search_results']:
            p=urlsplit(link['url'])
            if p.hostname=='archive.org' and p.path.startswith('/details/'):
                identifier=unquote(p.path.split('/')[2])
                if identifier not in identifiers:identifiers.append(identifier)
        candidates=ArchiveProvider().from_identifiers(query,identifiers,self.http)
        if not identifiers and not re.search(r'\b0\s+results?\b|no (?:results|items|matches)',evidence['text'],re.I):
            raise CatalogError('Chrome公开搜索页未呈现可读结果或明确无结果标记；未假定无结果')
        for candidate in candidates:
            candidate.evidence['browser_search']={'url':evidence['url'],'chrome_version':self.version,'robots_checked':True}
        return candidates,evidence


class BrowserArchiveProvider:
    name='archive_chrome';enabled=True
    def search(self,query,http):
        with PublicBrowser(http) as browser:
            candidates,evidence=browser.search(query)
        self.last_evidence=evidence
        # These candidates still carry provider='archive' and conservative license decisions.
        return candidates
