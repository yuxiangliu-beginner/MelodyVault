"""Official ccHost JSON API; original files only, never embedded player streams.

The general robots file excludes /api/ from crawler indexing. Explicit third-
party Query API permission is published at license.ccmixter.org/about. This
adapter's exception is limited to /api/query, not arbitrary restricted pages.
"""
import re,base64
from urllib.parse import urlsplit
from melodyvault.sources.models import Candidate
from melodyvault.sources.matching import version_from_text
from melodyvault.licensing.source_evidence import recognized_license
from melodyvault.downloads.security import validate_url

API='https://ccmixter.org/api/query'
POLICY='https://license.ccmixter.org/about'


def duration(value):
    try:
        parts=[float(p) for p in str(value).split(':')]
        if len(parts)>3:return None
        result=0
        for part in parts:result=result*60+part
        return result if result>0 else None
    except (ValueError,TypeError):return None


def sha1(value):
    if re.fullmatch('[A-Z2-7]{32}',value or ''):return base64.b32decode(value).hex()
    if re.fullmatch('[a-fA-F0-9]{40}',value or ''):return value.lower()
    return ''


class CCMixterProvider:
    name='ccmixter';enabled=True;policy_url=POLICY
    def get_metadata(self,external_id,http):
        upload=external_id.split(':')[0]
        if not upload.isdigit():raise ValueError('Invalid ccMixter upload ID')
        return self.parse(http.get(API,{'f':'json','ids':upload,'limit':1}).json())
    def search(self,query,http):
        found={}
        # Keep artist out of the API term: credits may use account names.
        # Performer, title and version are independently scored afterwards.
        for title in list(dict.fromkeys([query.title,*query.titles]))[:3]:
            data=http.get(API,{'f':'json','search':title,'search_type':'all','limit':10}).json()
            for c in self.parse(data):found[c.external_id]=c
        return list(found.values())
    def parse(self,data):
        if not isinstance(data,list):raise ValueError('ccMixter JSON must be a list')
        output=[]
        for row in data[:100]:
            uid=str(row.get('upload_id',''));title=row.get('upload_name','');page=row.get('file_page_url','')
            tags=set(str(row.get('upload_tags','')).strip(',').split(','))
            description=row.get('upload_description_plain','')
            kind=version_from_text(title+' '+description)
            if kind=='unknown' and 'remix' in tags:kind='remix'
            if kind=='unknown' and 'acappella' in tags:kind='a_cappella'
            for file in row.get('files',[]):
                fmt=file.get('file_format_info',{});ext=fmt.get('default-ext','').lower()
                if fmt.get('media-type')!='audio' or ext not in {'mp3','flac','wav','m4a','aac','ogg','opus'}:continue
                url=file.get('download_url','');valid=True
                try:validate_url('ccmixter',url)
                except Exception:valid=False
                # Creator/uploader is not necessarily the singer. Only explicit
                # featuring credits are exposed as performer evidence.
                performer=str(row.get('upload_extra',{}).get('featuring','') or '').strip()
                c=Candidate(self.name,uid+':'+str(file.get('file_id','')),title,performer,page,
                    duration(fmt.get('ps')),kind,row.get('license_url',''),license_statement=row.get('license_name',''),audio_url=url,
                    file_format=ext,file_size=int(file.get('file_rawsize',0)),
                    evidence={'api_url':API,'policy_url':POLICY,'upload_id':uid,'creator_account':row.get('user_name',''),
                              'creator_name':row.get('user_real_name') or row.get('user_name',''),
                              'performer_evidence':'official featuring credit' if performer else 'not supplied; uploader is not performer',
                              'tags':sorted(tags),'description':description,'file_id':str(file.get('file_id','')),
                              'sha1':sha1(file.get('file_extra',{}).get('sha1','')),'remote':file.get('file_is_remote',1)})
                # A cover/derived work can carry composition rights outside the
                # upload license. Do not silently resolve that uncertainty.
                uncertain=bool(re.search(r'\bcover\b|traditional|old chinese pop|sample',description,re.I)) or bool(tags & {'sample','stems','loops','spoken_word','remix'})
                uncertain |= bool(re.search(r'preview|excerpt|sample|snippet|stem|loop',str(file.get('file_nicname',''))+' '+str(file.get('file_name','')),re.I))
                if valid and not file.get('file_is_remote',1) and recognized_license(c.license_url) and not uncertain:
                    c.license_status='LICENSE_VERIFIED';c.license_reason='官方文件级 CC 许可；仍须完整性和录音身份核验'
                else:c.license_reason='改编/翻唱/采样权利链或完整歌曲范围未核实' if uncertain else '官方原始文件身份/许可不足'
                c.evidence['rights_chain_uncertain']=uncertain
                output.append(c)
        return output
