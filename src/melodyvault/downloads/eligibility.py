"""Fail-closed file-level permission and recording identity verification."""
import re
from urllib.parse import unquote,urlsplit
from melodyvault.downloads.models import DownloadCandidate,DownloadError
from melodyvault.downloads.security import validate_url,resource_identity
from melodyvault.providers.commons import clean
from melodyvault.licensing.source_evidence import recognized_license
from melodyvault.sources.matching import version_from_text
from melodyvault.catalog.normalize import title_key,normalized_isrc,name_key
from melodyvault.database.catalog import utc_now


def comparable(text):
    return title_key(re.sub(r'\s*[([]?ISRC\s*[: ]*\w{12}[)\]]?','',text,flags=re.I))


LICENSE_SETTING='ui.require_license'


def license_required(path):
    """User setting; default off. Security, integrity and identity checks stay on."""
    from melodyvault.database import connect
    try:
        with connect(path) as db:row=db.execute('SELECT value FROM app_metadata WHERE key=?',(LICENSE_SETTING,)).fetchone()
    except Exception:return False
    return bool(row) and row[0]=='true'


class DownloadEligibilityService:
    def __init__(self,http,mb_client=None,require_license=True):self.http=http;self.mb_client=mb_client;self.require_license=require_license
    def verify(self,raw,target):
        c=DownloadCandidate(target['song_id'],target['recording_id'],target['artist']['name'],target['title'],target['version'],raw['provider'],raw.get('page_url',''),external_id=raw['external_id'])
        c.evidence={'source_candidate':raw,'target':target,'source_type':'download'};c.verified_at=utc_now()
        def reject(code,reason):
            c.verification_reason.append(reason);c.evidence['decision']=code
            if code=='VERSION_MISMATCH':c.metadata_match_status=code
            if code in {'PREVIEW_ONLY','INCOMPLETE_AUDIO'}:c.full_length_status=code
            if code=='DOWNLOAD_NOT_PERMITTED':c.download_permission=False
            return c
        def license_gap(reason):
            # Returns a rejection only when the user requires verified licenses;
            # otherwise records the gap and lets the remaining checks decide.
            if self.require_license:return reject('LICENSE_UNVERIFIED',reason)
            c.evidence.setdefault('license_gaps',[]).append(reason);c.evidence['license_check']='SKIPPED'
            return None
        if not target.get('confirmed'):return reject('TARGET_UNCONFIRMED','目标录音尚未确认；不能自动下载')
        if raw.get('match_status')=='VERSION_MISMATCH':return reject('VERSION_MISMATCH','已知候选版本与目标不同')
        if c.provider=='commons':
            if not c.external_id.isdigit():return reject('LICENSE_UNVERIFIED','Commons文件身份不正确')
            data=self.http.json('https://commons.wikimedia.org/w/api.php',{'action':'query','format':'json','formatversion':2,'pageids':c.external_id,'prop':'imageinfo','iiprop':'url|mime|mediatype|size|sha1|metadata|extmetadata','iiextmetadatalanguage':'en','maxlag':5})
            if data.get('error'):raise DownloadError('VERIFICATION_FAILED','Commons官方API错误：'+str(data['error'].get('code','unknown')))
            pages=data.get('query',{}).get('pages',[])
            page=next((p for p in pages if str(p.get('pageid'))==c.external_id),{})
            info=next(iter(page.get('imageinfo',[])),{})
            c.evidence['official_file']=info;c.evidence['official_title']=page.get('title','')
            ext=info.get('extmetadata',{});get=lambda k:clean(ext.get(k,{}).get('value',''))
            if not info.get('mime','').startswith('audio/') and not (info.get('mime')=='application/ogg' and info.get('mediatype')=='AUDIO'):return reject('DOWNLOAD_NOT_PERMITTED','不是官方音频原始文件')
            c.source_page_url=info.get('descriptionurl','');c.direct_download_url=info.get('url','')
            c.file_size=int(info.get('size',0));c.file_format={'audio/mpeg':'mp3','audio/wav':'wav','audio/x-wav':'wav','audio/flac':'flac','audio/x-flac':'flac','audio/ogg':'ogg','application/ogg':'ogg','audio/opus':'opus','audio/mp4':'m4a','audio/aac':'aac'}.get(info.get('mime'),'')
            if not c.file_format:return reject('DOWNLOAD_NOT_PERMITTED','不支持该媒体类型的安全归档')
            c.license_url=get('LicenseUrl');c.license_name=get('LicenseShortName');c.attribution=get('Attribution') or get('Artist')
            duration=next((m.get('value') for m in info.get('metadata',[]) if m.get('name') in {'length','playtime_seconds'}),None)
            try:c.duration=float(duration)
            except (ValueError,TypeError):c.duration=None
            digest=info.get('sha1','')
            if digest:
                try:c.checksums={'sha1':digest.lower() if re.fullmatch('[0-9a-fA-F]{40}',digest) else f'{int(digest,36):040x}'}
                except ValueError:return reject('INCOMPLETE_AUDIO','官方校验值无效')
            source_title=get('ObjectName') or page.get('title','').removeprefix('File:').rsplit('.',1)[0]
            source_text=source_title+' '+get('ImageDescription')+' '+get('Credit')
            flags=get('Categories')+' '+get('Restrictions')
            if re.search('no downloads?|download (?:prohibited|not permitted)|automated access prohibited|禁止下载',flags+' '+get('Permission'),re.I):return reject('DOWNLOAD_NOT_PERMITTED','来源明确禁止下载或自动访问')
            if get('Restrictions') or re.search('copyvio|copyright violation|disputed|license review needed|no permission',flags,re.I):
                if (r:=license_gap('文件含权利冲突、限制或待审核标记')):return r
            if not recognized_license(c.license_url):
                if (r:=license_gap('缺少明确且可识别的文件级许可')):return r
            if not c.attribution:
                if (r:=license_gap('无法满足许可所需署名')):return r
            c.download_permission=c.personal_storage_permission=True
            c.license_status='LICENSE_UNVERIFIED' if c.evidence.get('license_gaps') else 'LICENSE_VERIFIED'
            c.evidence['platform_policy']='https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia'
            c.evidence['license_scope']='file'
            if not c.file_size or not c.checksums:return reject('INCOMPLETE_AUDIO','缺少官方原始文件大小或校验值')
        elif c.provider=='ccmixter':
            from melodyvault.providers.ccmixter import CCMixterProvider
            refreshed=next((v for v in CCMixterProvider().get_metadata(c.external_id,self.http) if v.external_id==c.external_id),None)
            if refreshed is None:return reject('LICENSE_UNVERIFIED','官方文件 ID 不再存在')
            c.evidence['official_file']=refreshed.evidence
            c.license_url=refreshed.license_url;c.license_name=refreshed.license_statement;c.attribution=refreshed.evidence.get('creator_name','')
            if refreshed.license_status!='LICENSE_VERIFIED':
                if (r:=license_gap(refreshed.license_reason)):return r
            if raw.get('performer')!=refreshed.performer:return reject('RECORDING_MISMATCH','官方创作者署名已变化')
            c.source_page_url=refreshed.page_url;c.direct_download_url=refreshed.audio_url
            c.file_format=refreshed.file_format;c.file_size=refreshed.file_size;c.duration=refreshed.duration_seconds
            c.checksums={'sha1':refreshed.evidence['sha1']} if refreshed.evidence.get('sha1') else {}
            if not c.file_size or not c.checksums:return reject('INCOMPLETE_AUDIO','缺少官方文件大小或校验值')
            c.license_status='LICENSE_UNVERIFIED' if c.evidence.get('license_gaps') else 'LICENSE_VERIFIED';c.download_permission=c.personal_storage_permission=True
            source_title=refreshed.title;source_text=source_title+' '+refreshed.evidence.get('description','')
            c.evidence['platform_policy']=CCMixterProvider.policy_url
        elif c.provider=='jamendo':
            # Refresh only through the official API; no key means no download.
            import os
            key=os.environ.get('JAMENDO_CLIENT_ID','')
            if not key:return reject('DOWNLOAD_NOT_PERMITTED','Jamendo未配置官方client_id')
            data=self.http.json('https://api.jamendo.com/v3.0/tracks/',{'client_id':key,'format':'json','id':c.external_id,'include':'licenses'})
            if data.get('headers',{}).get('status')!='success':raise DownloadError('VERIFICATION_FAILED','Jamendo官方API返回错误状态')
            item=next((i for i in data.get('results',[]) if str(i['id'])==c.external_id),{})
            c.evidence['official_file']={k:v for k,v in item.items() if k!='client_id'}
            if item.get('audiodownload_allowed') is not True:return reject('DOWNLOAD_NOT_PERMITTED','官方API未允许下载该录音')
            c.license_url=item.get('license_ccurl','');c.license_name=c.license_url;c.attribution=item.get('artist_name','')
            if not recognized_license(c.license_url):
                if (r:=license_gap('缺少明确文件许可')):return r
            c.direct_download_url=item.get('audiodownload','');c.source_page_url=item.get('shareurl','');c.duration=item.get('duration');c.file_format='mp3'
            c.download_permission=c.personal_storage_permission=True;c.license_status='LICENSE_UNVERIFIED' if c.evidence.get('license_gaps') else 'LICENSE_VERIFIED';source_title=item.get('name','');source_text=source_title
        elif c.provider=='archive' and not self.require_license:
            from urllib.parse import quote
            identifier,_,filename=c.external_id.partition('/')
            if not identifier or not filename:return reject('RECORDING_MISMATCH','Archive文件身份不正确')
            from melodyvault.providers.archive import restricted_item
            item=self.http.json('https://archive.org/metadata/'+quote(identifier,safe=''))
            meta=item.get('metadata',{})
            # Access controls set by Archive itself are honoured, never bypassed.
            if restricted_item(item):return reject('DOWNLOAD_NOT_PERMITTED','Archive条目受访问限制，不尝试绕过')
            file=next((f for f in item.get('files',[]) if f.get('name')==filename),None)
            if file is None:return reject('INCOMPLETE_AUDIO','Archive条目中已不存在该文件')
            if file.get('private') in ('true',True):return reject('DOWNLOAD_NOT_PERMITTED','Archive文件为私有，不尝试绕过')
            c.evidence['official_file']=file;c.evidence['official_title']=meta.get('title','')
            ext=filename.rsplit('.',1)[-1].lower() if '.' in filename else ''
            c.file_format={'mp3':'mp3','flac':'flac','wav':'wav','ogg':'ogg','opus':'opus','m4a':'m4a'}.get(ext,'')
            if not c.file_format:return reject('DOWNLOAD_NOT_PERMITTED','不支持该媒体类型的安全归档')
            try:c.file_size=int(file.get('size',0))
            except (TypeError,ValueError):c.file_size=0
            length=file.get('length')
            try:c.duration=sum(float(p)*60**i for i,p in enumerate(reversed(str(length).split(':')))) if ':' in str(length) else float(length)
            except (TypeError,ValueError):c.duration=None
            c.checksums={k:str(file[k]).lower() for k in ('sha1','md5') if re.fullmatch('[0-9a-fA-F]+',str(file.get(k,'')))}
            if not c.file_size or not c.checksums:return reject('INCOMPLETE_AUDIO','缺少Archive文件大小或校验值')
            c.source_page_url='https://archive.org/details/'+quote(identifier,safe='')
            c.direct_download_url='https://archive.org/download/'+quote(identifier,safe='')+'/'+quote(filename,safe='')
            from melodyvault.providers.archive import text,file_title,file_creator,repair_text
            c.evidence['album']=clean(repair_text(meta.get('title')))  # the Archive item is the album
            c.license_url=text(file.get('licenseurl') or meta.get('licenseurl'));c.license_name=clean(text(file.get('rights') or meta.get('rights')))
            c.attribution=file_creator(file,meta)
            if not recognized_license(c.license_url):license_gap('Archive上传者未提供可识别的录音许可')
            else:license_gap('Archive许可由上传者声明，未核实其权利')
            c.license_status='LICENSE_UNVERIFIED';c.download_permission=c.personal_storage_permission=True
            source_title=file_title(file)
            source_text=source_title+' '+clean(repair_text(meta.get('description')))
            c.evidence['platform_policy']='https://archive.org/developers/bots.html'
        else:
            if c.provider=='openverse':
                return reject('LICENSE_UNVERIFIED','Openverse 仅提供索引线索，未核验原始来源的完整录音与下载权利')
            return reject('LICENSE_UNVERIFIED','该来源尚无可核实的具体录音权利链；Archive上传者声明或Chrome页面不批准下载')
        if re.search(r'\b(preview|excerpt|sample|snippet)\b|试听|試聽|片段',source_title,re.I):return reject('PREVIEW_ONLY','候选标明试听或片段')
        kind=version_from_text(source_title+' '+str(raw.get('version','')))
        if kind!='unknown' and kind!=target['version']:return reject('VERSION_MISMATCH','明确的现场/翻奏/混音等版本不一致')
        if not c.duration or c.duration<=0:
            # Older Archive uploads carry no length. Their official size and checksum still
            # pin the exact bytes, and the length is then measured from the file during the
            # full decode; other sources keep requiring an official length.
            if not (c.provider=='archive' and c.file_size and c.checksums):return reject('INCOMPLETE_AUDIO','没有可靠完整文件时长')
            c.duration=None;c.evidence['duration_unverified']=True
        if target.get('duration') and c.duration and abs(c.duration-target['duration'])>max(.05,min(2,target['duration']*.02)):return reject('INCOMPLETE_AUDIO','来源时长与目标录音不一致，可能是片段或其他版本')
        identity=False
        if target.get('namespace')=='musicbrainz':
            artist=target['artist'];aliases=[a.get('name','') for a in artist.get('aliases',[])]
            if raw.get('performer') and name_key(raw['performer']) not in {name_key(n) for n in (artist['name'],*aliases)}:
                return reject('RECORDING_MISMATCH','来源明确演唱署名与目标歌手/别名不一致')
            isrcs={normalized_isrc(v) for v in target.get('isrcs',[])}-{None};urls=target.get('urls',[])
            if self.mb_client and (not isrcs or not urls):
                detail=self.mb_client.get_json('recording/'+target['recording_id'],{'inc':'isrcs+url-rels+artist-credits'})
                credits=[v['artist']['id'] for v in detail.get('artist-credit',[]) if isinstance(v,dict) and v.get('artist')]
                if detail['id']!=target['recording_id'] or target['artist']['id'] not in credits:return reject('RECORDING_MISMATCH','官方Recording身份或歌手署名已变化')
                isrcs|={normalized_isrc(v) for v in detail.get('isrcs',[])}-{None}
                urls += [v['url']['resource'] for v in detail.get('relations',[]) if v.get('url',{}).get('resource')]
                c.evidence['official_recording']=detail
            observed=set(re.findall(r'\b[A-Z]{2}[A-Z0-9]{3}\d{7}\b',unquote(source_text).upper()))
            def page_key(url):
                p=urlsplit(resource_identity(url));return p.hostname,unquote(p.path).replace(' ','_').rstrip('/'),p.query
            explicit_url=any(page_key(url) in {page_key(c.source_page_url),page_key(c.direct_download_url)} for url in urls)
            identity=explicit_url or bool(isrcs&observed and comparable(source_title) in {comparable(target['title']),comparable(target.get('recording_title',''))})
            if identity:c.verification_reason.append('官方Recording文件URL关系' if explicit_url else '官方Recording ISRC与文件明确ISRC一致，标题/版本/时长无冲突')
        elif target.get('namespace')==c.provider:
            # A separately identified provider-native recording is never inserted
            # as a fabricated MusicBrainz UUID. Used by explicit open-file controls.
            native_id=c.external_id.split(':')[0] if c.provider=='ccmixter' else c.external_id
            identity=target['recording_id']==c.provider+':'+native_id and target.get('source_page_url')==c.source_page_url
            if identity:c.verification_reason.append('明确选择的来源原生文件ID；不冒充MusicBrainz录音或商业原唱')
        if not identity and target.get('namespace') in {'commons','archive'} and target.get('equivalent_sources'):
            # Automatic source switching, opted into per task by the search page when
            # "自动换源" is on: another upload counts as the same recording only when
            # song name and artist agree and the length already matched within the
            # tolerance checked above (target duration required). Version conflicts
            # were rejected earlier. Without the flag identity stays exact.
            identity=self._same_recording(target,source_title,raw.get('performer') or c.attribution,c)
            if identity:
                c.evidence['identity_basis']='title_artist_duration'
                c.verification_reason.append('自动换源：歌名、歌手一致且时长相差不超过2秒，判定为同一录音（启发式）')
        if not identity:return reject('RECORDING_MISMATCH','只有标题/歌手/时长线索，缺少可靠录音ID、ISRC或精确官方文件关联')
        try:validate_url(c.provider,c.direct_download_url)
        except DownloadError as error:return reject(error.code,str(error))
        source_host=urlsplit(c.source_page_url).hostname
        if source_host!={'commons':'commons.wikimedia.org','jamendo':'www.jamendo.com','ccmixter':'ccmixter.org','archive':'archive.org'}.get(c.provider):return reject('UNSAFE_URL','官方来源页面与下载服务身份不一致')
        c.restrictions=['保留署名及许可链接；原始字节不改动']
        if c.evidence.get('license_check')=='SKIPPED':
            c.restrictions.insert(0,'许可未核验（用户已关闭许可检查）；仅供个人使用，不要再分发')
        if '/by-nc' in c.license_url:c.restrictions.append('仅非商业用途')
        if '-nd/' in c.license_url:c.restrictions.append('禁止再分发改编版本')
        if '-sa/' in c.license_url:c.restrictions.append('再分发改编作品须遵守相同许可')
        c.metadata_match_status='RECORDING_VERIFIED';c.full_length_status='FULL_LENGTH';c.confidence='HIGH'
        c.evidence['decision']='READY'
        c.verification_reason.append('许可检查已关闭：'+'；'.join(c.evidence['license_gaps']) if c.evidence.get('license_check')=='SKIPPED' else '已核对文件级许可、私人复制及自动下载来源；保存署名与限制')
        return c

    @staticmethod
    def _same_recording(target,source_title,performer,candidate):
        from melodyvault.sources.matching import core_title
        def names(value):return {name_key(n) for n in re.split(r'\s*/\s*',value or '') if n.strip()}-{'','未知歌手'}
        artist=target['artist'].get('name','');wanted,found=names(artist),names(performer)
        if not target.get('duration') or not candidate.duration or not wanted or not found:return False
        # A labelled live/cover/remix pick is never replaced by an unlabelled upload (or vice versa).
        have_version,want_version=version_from_text(source_title),target.get('version') or 'unknown'
        if have_version!=want_version and not {have_version,want_version}<={'unknown','studio'}:return False
        # "周杰倫" matches "周杰倫 Jay Chou"; joint credits ("梅兰芳 / 齐如山") need one shared name.
        if not any(a in b or b in a for a in wanted for b in found):return False
        want=title_key(core_title(target['title'],artist));have=title_key(core_title(source_title,performer))
        return bool(want) and want==have

    @staticmethod
    def allowed(candidate):
        license_ok=candidate.license_status=='LICENSE_VERIFIED' or candidate.evidence.get('license_check')=='SKIPPED'
        return candidate.evidence.get('decision')=='READY' and license_ok and candidate.download_permission and candidate.personal_storage_permission and candidate.metadata_match_status=='RECORDING_VERIFIED' and candidate.full_length_status=='FULL_LENGTH'
