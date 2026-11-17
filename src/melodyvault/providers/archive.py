from urllib.parse import quote
import re
from melodyvault.sources.models import Candidate
from melodyvault.licensing.source_evidence import check_license
from melodyvault.providers.commons import clean
from melodyvault.catalog.models import CatalogError
from melodyvault.catalog.normalize import title_key,search_names
from melodyvault.sources.matching import version_from_text


def text(value):return ' / '.join(map(str,value)) if isinstance(value,list) else str(value or '')


_CJK=re.compile(r'[㐀-鿿]')
_MOJIBAKE_RUN=re.compile(r'[\x80-\xff]{4,}')


def repair_text(value):
    """Undo the common GBK/UTF-8-read-as-Latin-1 tag damage in Chinese uploads.

    Only strings with a run of 4+ high Latin-1 characters and no CJK are tried,
    so ordinary European titles ("Größe", "élève") are left alone.
    """
    s=text(value)
    if not s or _CJK.search(s) or not _MOJIBAKE_RUN.search(s):return s
    for codec in ('utf-8','gbk'):
        try:fixed=s.encode('latin-1').decode(codec)
        except (UnicodeEncodeError,UnicodeDecodeError):continue
        if _CJK.search(fixed):return fixed
    return s


def file_stem(file):
    """File name without extension or leading track number ("01 Song.mp3" -> "Song"; "01.mp3" -> "01")."""
    stem=file.get('name','').rsplit('/',1)[-1].rsplit('.',1)[0]
    return re.sub(r'^\d+[ ._-]*','',stem) or stem


def file_title(file):
    """One title rule for search, metadata refresh and download verification."""
    return clean(repair_text(file.get('title'))) or file_stem(file)


def file_creator(file,meta):return clean(repair_text(file.get('creator') or meta.get('creator')))


def file_version(file,meta,identifier):
    """Shared by the search page and download verification, so they never disagree."""
    return version_from_text(file_title(file)+' '+text(meta.get('title'))+' '+identifier)


def restricted_item(item):
    """Archive's own access controls; honoured everywhere, never bypassed."""
    meta=item.get('metadata',{})
    return bool(item.get('is_dark') or item.get('nodownload') or meta.get('access-restricted-item') in ('true',True))


class ArchiveProvider:
    name='archive';enabled=True
    policy_url='https://archive.org/developers/bots.html'
    def __init__(self):self.items={}
    def get_metadata(self,external_id,http):
        identifier,_,filename=external_id.partition('/')
        data=http.json('https://archive.org/metadata/'+quote(identifier,safe=''))
        from melodyvault.sources.models import SourceQuery
        # Same title rule as from_identifiers(), so a selected file always matches itself.
        title=next((file_title(f) for f in data.get('files',[]) if f.get('name')==filename),'')
        self.items[identifier]=data
        q=SourceQuery('',external_id,'',title,[],[title],[],[],[])
        return [c for c in self.from_identifiers(q,[identifier],http) if c.external_id==external_id]
    def search(self,query,http):
        def terms(items):
            # Simplified and traditional spellings; uploads use either.
            values=dict.fromkeys(v for x in items for v in search_names(x) if v.strip())
            return '('+' OR '.join('"'+re.sub(r'["\\]',' ',x)+'"' for x in values)+')'
        artists=terms(query.artist_names);titles=terms(query.titles)
        expression=f'mediatype:audio AND (creator:{artists} OR title:{artists} OR description:{artists}) AND (title:{titles} OR description:{titles})'
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
            restricted=restricted_item(item)
            if restricted:continue
            keys={title_key(t) for t in query.titles}-{''}
            for file in item.get('files',[]):
                filename=file.get('name','')
                if not filename.lower().endswith(('.mp3','.ogg','.flac','.wav','.m4a','.opus')) or file.get('private') in ('true',True):continue
                title=file_title(file)
                # Only tracks whose own title/name (or the item title) contains the song;
                # uploads often prefix the artist ("周杰倫 - 退後"). Identity is decided later.
                blob=title_key(title)+'|'+title_key(file_stem(file))+'|'+title_key(text(meta.get('title')))
                if not any(k in blob for k in keys):continue
                length=file.get('length')
                try:
                    if ':' in str(length):
                        length=sum(float(p)*60**i for i,p in enumerate(reversed(str(length).split(':'))))
                    else:length=float(length)
                except (ValueError,TypeError):length=None
                license_url=text(file.get('licenseurl') or meta.get('licenseurl'))
                c=Candidate(self.name,identifier+'/'+filename,title,file_creator(file,meta),
                    'https://archive.org/details/'+quote(identifier,safe=''),length,
                    version=file_version(file,meta,identifier),license_url=license_url,
                    license_statement=clean(text(file.get('rights') or meta.get('rights'))),
                    audio_url='https://archive.org/download/'+quote(identifier,safe='')+'/'+quote(filename,safe=''),
                    evidence={'identifier':identifier,'file':file,'item_creator':meta.get('creator'),'item_title':meta.get('title'),'license_scope':'file' if file.get('licenseurl') else 'item',
                        'metadata_url':'https://archive.org/metadata/'+quote(identifier,safe=''),'policy_url':self.policy_url})
                result.append(check_license(c,restricted=restricted))
                c.file_format=filename.rsplit('.',1)[-1].lower()
                try:c.file_size=int(file.get('size',0))
                except (TypeError,ValueError):c.file_size=0
        return result
