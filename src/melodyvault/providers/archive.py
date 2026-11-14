from urllib.parse import quote
import re
from melodyvault.sources.models import Candidate
from melodyvault.licensing.source_evidence import check_license
from melodyvault.providers.commons import clean
from melodyvault.catalog.models import CatalogError
from melodyvault.catalog.normalize import title_key
from melodyvault.sources.matching import version_from_text


def text(value):return ' / '.join(map(str,value)) if isinstance(value,list) else str(value or '')


class ArchiveProvider:
    name='archive';enabled=True
    policy_url='https://archive.org/developers/bots.html'
    def __init__(self):self.items={}
    def get_metadata(self,external_id,http):
        identifier,_,filename=external_id.partition('/')
        data=http.json('https://archive.org/metadata/'+quote(identifier,safe=''))
        from melodyvault.sources.models import SourceQuery
        title=next((f.get('title') or f.get('name','').rsplit('.',1)[0] for f in data.get('files',[]) if f.get('name')==filename),'')
        self.items[identifier]=data
        q=SourceQuery('',external_id,'',title,[],[title],[],[],[])
        return [c for c in self.from_identifiers(q,[identifier],http) if c.external_id==external_id]
    def search(self,query,http):
        def terms(items):return '('+' OR '.join('"'+re.sub(r'["\\]',' ',x)+'"' for x in items)+')'
        artists=terms(query.artist_names);titles=terms(query.titles)
        expression=f'mediatype:audio AND creator:{artists} AND (title:{titles} OR description:{titles})'
        if query.version_words:
            versions=terms(query.version_words);expression+=f' AND (title:{versions} OR description:{versions})'
        data=http.json('https://archive.org/advancedsearch.php',{'q':expression,
            'output':'json','rows':10,'page':1,'fl[]':['identifier','title','creator','licenseurl']})
        if not isinstance(data.get('response',{}).get('docs'),list):raise CatalogError('Archive搜索响应不完整')
        return self.from_identifiers(query,[doc['identifier'] for doc in data['response']['docs']],http)

    def from_identifiers(self,query,identifiers,http):
        result=[]
        for identifier in identifiers[:10]:
            if identifier not in self.items:self.items[identifier]=http.json('https://archive.org/metadata/'+quote(identifier,safe=''))
            item=self.items[identifier];meta=item.get('metadata',{})
            restricted=bool(item.get('is_dark') or item.get('nodownload') or meta.get('access-restricted-item')=='true')
            if restricted:continue
            for file in item.get('files',[]):
                filename=file.get('name','')
                if not filename.lower().endswith(('.mp3','.ogg','.flac','.wav','.m4a','.opus')) or file.get('private') in ('true',True):continue
                title=text(file.get('title')) or re.sub(r'^\d+[ ._-]*','',filename.rsplit('.',1)[0])
                # Do not turn every track in an album into this song's candidate.
                keys={title_key(t) for t in query.titles}
                if title_key(title) not in keys and title_key(text(meta.get('title'))) not in keys:continue
                length=file.get('length')
                try:
                    if ':' in str(length):
                        length=sum(float(p)*60**i for i,p in enumerate(reversed(str(length).split(':'))))
                    else:length=float(length)
                except (ValueError,TypeError):length=None
                license_url=text(file.get('licenseurl') or meta.get('licenseurl'))
                c=Candidate(self.name,identifier+'/'+filename,clean(title),clean(text(file.get('creator') or meta.get('creator'))),
                    'https://archive.org/details/'+quote(identifier,safe=''),length,
                    version=version_from_text(title+' '+text(meta.get('title'))+' '+identifier),license_url=license_url,
                    license_statement=clean(text(file.get('rights') or meta.get('rights'))),
                    audio_url='https://archive.org/download/'+quote(identifier,safe='')+'/'+quote(filename,safe=''),
                    evidence={'identifier':identifier,'file':file,'item_creator':meta.get('creator'),'item_title':meta.get('title'),'license_scope':'file' if file.get('licenseurl') else 'item',
                        'metadata_url':'https://archive.org/metadata/'+quote(identifier,safe=''),'policy_url':self.policy_url})
                result.append(check_license(c,restricted=restricted))
                c.file_format=filename.rsplit('.',1)[-1].lower()
                try:c.file_size=int(file.get('size',0))
                except (TypeError,ValueError):c.file_size=0
        return result
