import html,re
from melodyvault.sources.models import Candidate
from melodyvault.licensing.source_evidence import check_license
from melodyvault.catalog.models import CatalogError

API='https://commons.wikimedia.org/w/api.php'


def clean(value):return html.unescape(re.sub('<[^>]+>','',str(value or ''))).strip()


class CommonsProvider:
    name='commons';enabled=True
    policy_url='https://www.mediawiki.org/wiki/API:Etiquette'
    def get_metadata(self,external_id,http):
        if not str(external_id).isdigit():raise CatalogError('Invalid Commons file ID')
        return self.parse(http.json(API,{'action':'query','format':'json','formatversion':2,'pageids':external_id,
            'prop':'imageinfo','iiprop':'url|mime|mediatype|size|extmetadata|metadata','iiextmetadatalanguage':'en','maxlag':5}))
    def search(self,query,http):
        candidates={}
        for artist,title in query.keyword_pairs:
            # CirrusSearch does not interpret Solr-style parenthesized groups.
            keywords='"'+artist.replace('"',' ')+'" "'+title.replace('"',' ')+'"'
            searches=[keywords+' "'+query.version_words[0]+'"'] if query.version_words else []
            searches.append(keywords)
            for expression in searches:
                response=http.json(API,{'action':'query','format':'json','formatversion':2,'generator':'search',
                    'gsrsearch':expression+' filetype:audio','gsrnamespace':6,'gsrlimit':5,
                    'prop':'imageinfo','iiprop':'url|mime|mediatype|extmetadata|metadata','iiextmetadatalanguage':'en','maxlag':5})
                if response.get('error'):raise CatalogError('Wikimedia API: '+str(response['error']))
                if response.get('query',{}).get('pages'):break
            for candidate in self.parse(response):candidates[candidate.external_id]=candidate
        return list(candidates.values())

    def parse(self,response):
        candidates=[]
        for page in response.get('query',{}).get('pages',[]):
            for info in page.get('imageinfo',[]):
                if not info.get('mime','').startswith('audio/') and info.get('mediatype')!='AUDIO':continue
                ext=info.get('extmetadata',{})
                def value(key):return clean(ext.get(key,{}).get('value',''))
                title=value('ObjectName') or page['title'].removeprefix('File:').rsplit('.',1)[0]
                performer=value('Performer')  # Author/photographer/uploader is NOT a performer.
                duration=next((x.get('value') for x in info.get('metadata',[]) if x.get('name')=='length'),None)
                try:duration=float(duration)
                except (ValueError,TypeError):duration=None
                c=Candidate(self.name,str(page['pageid']),title,performer,info.get('descriptionurl',''),duration,
                    license_url=value('LicenseUrl'),license_statement=value('LicenseShortName'),audio_url=info.get('url',''),
                    evidence={'api_url':API,'page_id':page['pageid'],'extmetadata':ext,'policy_url':self.policy_url,
                              'author_is_not_performer':value('Artist')})
                c.file_size=int(info.get('size',0));c.file_format=info.get('url','').rsplit('.',1)[-1].lower()
                candidates.append(check_license(c,download_allowed=bool(c.audio_url),restricted=bool(value('Restrictions')) or value('Copyrighted')=='True' and not c.license_url))
        return candidates
