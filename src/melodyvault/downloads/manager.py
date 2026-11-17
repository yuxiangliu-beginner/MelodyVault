"""Persisted, opt-in, bounded download queue. All I/O runs outside the Qt thread."""
import errno,json,os,re,threading,time,shutil
from pathlib import Path
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from contextlib import contextmanager
from urllib.parse import urljoin
import httpx
from melodyvault.downloads.models import DownloadCandidate,DownloadSettings,DownloadError,Interrupted
from melodyvault.downloads.security import audio_client,validate_url,redact_payload,resource_identity,strong_etag
from melodyvault.downloads.files import contained,verify_file,publish,check_space,hashes,decode_file
from melodyvault.downloads.eligibility import DownloadEligibilityService,license_required
from melodyvault.downloads.targets import search_values
from melodyvault.catalog.models import CatalogCancelled
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.musicbrainz import RateGate
from melodyvault.database.catalog import CatalogRepository,encode
from melodyvault.database.sources import SourceRepository
from melodyvault.sources.engine import SourceSearchEngine
from melodyvault.sources.http import SourceHTTP

_AUDIO_GATES={host:RateGate(1.1) for host in ('commons','archive','jamendo','ccmixter')}


class RunLock:
    def __init__(self,path):self.path=Path(str(path)+'.downloads.lock');self.file=None
    def __enter__(self):
        try:
            self.file=self.path.open('a+b');self.file.seek(0)
            if self.file.read(1)==b'':self.file.write(b'1');self.file.flush()
            self.file.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            if self.file:self.file.close()
            raise DownloadError('QUEUE_BUSY','下载队列锁无法取得，可能有另一进程运行或目录权限不足') from None
        return self
    def __exit__(self,*args):
        self.file.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
        self.file.close()


class Control:
    def __init__(self):self.event=threading.Event();self.action='PAUSED'
    def stop(self,action):self.action=action;self.event.set()
    def check(self):
        if self.event.is_set():raise Interrupted(self.action,'任务已暂停，临时文件和证据保留' if self.action=='PAUSED' else '任务已取消；原歌曲目录保留')


class Bandwidth:
    def __init__(self,limit):self.limit=limit;self.next=0.;self.lock=threading.Lock()
    def consume(self,size,control):
        if not self.limit:return
        with self.lock:
            now=time.monotonic();self.next=max(now,self.next)+size/self.limit;delay=self.next-now
        if control.event.wait(delay):control.check()


class DownloadManager:
    def __init__(self,repository,*,providers_factory=None,verifier_factory=None,transport=None,source_http_factory=None,progress=None):
        self.repository=repository;self.path=repository.path;self.transport=transport;self.progress=progress or (lambda:None)
        self.providers_factory=providers_factory;self.verifier_factory=verifier_factory or (lambda http,mb=None:DownloadEligibilityService(http,mb,require_license=license_required(repository.path)))
        self.source_http_factory=source_http_factory or SourceHTTP;self.controls={};self.lock=threading.RLock();self.file_locks={};self.running=False
    def recover(self):
        with RunLock(self.path):self.repository.recover()
    def stop(self,jid,action):
        if action not in {'PAUSED','CANCELLED'}:raise ValueError(action)
        with self.lock:
            if jid in self.controls:self.controls[jid].stop(action)
            else:
                row=self.repository.get(jid)
                if row['state'] in {'QUEUED','PAUSED','READY'}:self.repository.update(jid,state=action,reason_code=action,reason='用户暂停' if action=='PAUSED' else '用户取消',speed=0,eta=None)
                if action=='CANCELLED':self._discard_part(self.repository.get(jid))
    def stop_all(self,action='PAUSED'):
        from melodyvault.database import connect
        from melodyvault.database.catalog import utc_now
        if action not in {'PAUSED','CANCELLED'}:raise ValueError(action)
        with self.lock:
            for control in self.controls.values():control.stop(action)
            with connect(self.path) as db:db.execute("UPDATE download_jobs SET state=?,reason_code=?,reason=?,speed=0,eta=NULL,updated_at=? WHERE state IN ('QUEUED','PAUSED','READY')",(action,action,'用户批量暂停' if action=='PAUSED' else '用户批量取消',utc_now()))
    def resume_all(self):
        from melodyvault.database import connect
        from melodyvault.database.catalog import utc_now
        with self.lock:
            with connect(self.path) as db:db.execute("UPDATE download_jobs SET state='QUEUED',reason_code='',reason='等待继续',updated_at=? WHERE state='PAUSED'",(utc_now(),))
    def resume(self,jid):
        with self.lock:
            if jid in self.controls:return
            row=self.repository.get(jid)
            if row['state']=='PAUSED' or row['state']=='READY' and not row['dry_run']:
                self.repository.update(jid,state='QUEUED',reason_code='',reason='等待继续',speed=0)
    def retry_failed(self):
        for jid in self.repository.ids({'FAILED'}):
            self.repository.evidence(jid,'retry','USER_RETRY',{'bounded_new_cycle':True})
            self.repository.update(jid,state='QUEUED',reason_code='',reason='用户明确请求新的有界重试周期',attempt_count=0)
    def run(self, job_ids=None, settings_override=None):
        if settings_override is not None and job_ids is None:
            raise ValueError('单次下载设置只能用于明确指定的任务')
        with self.lock:
            if self.running:return
            self.running=True
        try:
            with RunLock(self.path):
                settings=(settings_override.validate() if settings_override is not None else self.repository.settings());bandwidth=Bandwidth(settings.speed_limit)
                with ThreadPoolExecutor(max_workers=settings.max_concurrent,thread_name_prefix='MelodyDownload') as pool:
                    queued=self.repository.ids({'QUEUED'})
                    if job_ids is not None:
                        selected=set(job_ids);queued=[jid for jid in queued if jid in selected]
                    futures=[pool.submit(self._process,jid,settings,bandwidth) for jid in queued]
                    for future in as_completed(futures):future.result();self.progress()
        finally:
            if job_ids is None:self.cleanup()
            else:
                for jid in set(job_ids):
                    row=self.repository.get(jid)
                    if row['state'] in {'FAILED','CANCELLED'}:self._discard_part(row)
            with self.lock:self.running=False
            self.progress()
    def _process(self,jid,current_settings,bandwidth):
        control=Control()
        with self.lock:
            if self.repository.get(jid)['state']!='QUEUED':return
            self.controls[jid]=control
        try:
            row=self.repository.get(jid);settings=DownloadSettings(**row['settings']);target=row['target']
            if not target.get('confirmed'):
                self.repository.update(jid,state='SKIPPED',reason_code='TARGET_UNCONFIRMED',reason='目标Song/Recording未确认，已跳过');return
            budget=max(1,settings.max_attempts-row['attempt_count'])
            for retry in range(budget):
                row=self.repository.get(jid);number=row['attempt_count']+1
                try:
                    control.check();self.repository.update(jid,state='SEARCHING',reason_code='',reason='正在搜索官方来源',speed=0,eta=None)
                    candidates=[]
                    # A selected source is only a hint; verify it afresh below.
                    if target.get('source_hint'):candidates=[target['source_hint']]
                    elif row['candidate'].get('provider') and 'page_url' in row['candidate']:candidates=[row['candidate']]
                    else:
                        artist,song=search_values(target)
                        providers=self.providers_factory() if self.providers_factory else self._default_providers()
                        stats=SourceSearchEngine(SourceRepository(self.path),providers,control.event,
                            progress=lambda event:self._source_progress(jid,event),http_factory=self.source_http_factory).search(artist,[song],CatalogRepository(self.path).works())
                        control.check();candidates=stats['jobs'][0]['candidates'] if stats['jobs'] else []
                        self.repository.evidence(jid,'search',stats['status'],stats)
                        if not candidates and stats['failed']:raise DownloadError('SOURCE_SEARCH_FAILED','来源请求失败；未把错误记为没有音源')
                    if not candidates:
                        self.repository.update(jid,state='SKIPPED',reason_code='NO_SOURCE',reason='本次已配置来源未找到音频候选');return
                    self.repository.update(jid,state='VERIFYING',reason='正在独立核对录音身份和文件级下载许可')
                    verified=[];decisions=[]
                    with self.source_http_factory(control.event) as http,MusicBrainzClient(CatalogRepository(self.path),control.event) as mb:
                        verifier=self.verifier_factory(http,mb)
                        for raw in candidates:
                            control.check()
                            try:
                                from melodyvault.database.discovery import DiscoveryRepository
                                if not DiscoveryRepository(self.path).provider_allowed(raw.get('provider','')):
                                    self.repository.evidence(jid,'eligibility','SOURCE_DISABLED',{'provider':raw.get('provider')})
                                    continue
                                candidate=verifier.verify(raw,target);decisions.append(candidate)
                                self.repository.evidence(jid,'eligibility',candidate.evidence.get('decision','LICENSE_UNVERIFIED'),candidate.to_dict())
                                if DownloadEligibilityService.allowed(candidate):verified.append(candidate)
                            except CatalogCancelled:raise
                            except Exception as error:
                                self.repository.evidence(jid,'eligibility','VERIFICATION_FAILED',{'provider':raw.get('provider'),'external_id':raw.get('external_id'),'error_type':type(error).__name__,'error_code':getattr(error,'code',''),'error_message':str(error)})
                    control.check()
                    if not verified:
                        if not decisions:raise DownloadError('VERIFICATION_FAILED','所有候选的官方核验请求均失败')
                        candidate=decisions[0]
                        self.repository.update(jid,state='SKIPPED',candidate_json=encode(candidate.to_dict()),reason_code=candidate.evidence.get('decision','LICENSE_UNVERIFIED'),reason='；'.join(candidate.verification_reason));return
                    def quality(c):
                        return (0 if settings.quality=='lossless' and c.file_format in {'flac','wav'} else 1,c.file_size or 2**40) if settings.quality=='small' else (0 if settings.quality=='lossless' and c.file_format in {'flac','wav'} else 1,0)
                    candidate=sorted(verified,key=quality)[0]
                    self.repository.update(jid,state='READY',candidate_json=encode(candidate.to_dict()),reason_code='DRY_RUN' if row['dry_run'] else '',reason='资格通过；dry-run不请求音频' if row['dry_run'] else '资格通过')
                    if row['dry_run'] or not current_settings.automatic_download:
                        if not row['dry_run']:self.repository.update(jid,reason_code='OPT_IN_REQUIRED',reason='实际下载开关关闭；等待明确开启')
                        return
                    control.check()
                    self._archive(jid,candidate,settings,control,bandwidth,number);return
                except (CatalogCancelled,Interrupted) as error:
                    action=control.action
                    self.repository.update(jid,state=action,reason_code=action,reason='用户暂停，已保存临时文件及续传信息' if action=='PAUSED' else '用户取消；原歌曲目录保留',speed=0,eta=None)
                    self.repository.attempt(jid,number,action,{});return
                except Exception as error:
                    if isinstance(error,DownloadError):code,message=error.code,str(error)
                    elif isinstance(error,httpx.TimeoutException):code,message='DOWNLOAD_TIMEOUT','下载网络请求超时'
                    elif isinstance(error,httpx.TransportError):code,message='NETWORK_INTERRUPTED','下载网络连接中断'
                    elif isinstance(error,OSError):code,message=('DISK_FULL','磁盘空间不足') if error.errno==errno.ENOSPC else ('FILE_IO_ERROR','文件读写失败：'+type(error).__name__)
                    else:code,message='DOWNLOAD_FAILED','任务失败：'+type(error).__name__
                    if control.event.is_set():
                        self.repository.update(jid,state=control.action,reason_code=control.action,reason='已保存任务中断状态',speed=0,eta=None);return
                    self.repository.update(jid,state='FAILED',reason_code=code,reason=message,attempt_count=number,speed=0,eta=None)
                    self.repository.attempt(jid,number,'FAILED',{'code':code,'message':message})
                    retryable=code in {'NETWORK_INTERRUPTED','DOWNLOAD_TIMEOUT','URL_EXPIRED','HTTP_RETRY','OBJECT_CHANGED','INCOMPLETE_AUDIO','SOURCE_SEARCH_FAILED','VERIFICATION_FAILED'}
                    if not retryable or retry+1>=budget:return
                    if code=='OBJECT_CHANGED':self.repository.update(jid,etag='',last_modified='',resource_url='')
                    if control.event.wait(max(min(2**retry,8),getattr(error,'retry_after',0))):
                        self.repository.update(jid,state=control.action,reason_code=control.action,reason='退避期间中断');return
        finally:
            row=self.repository.get(jid)
            self._discard_part(row)
            with self.lock:self.controls.pop(jid,None)
            self.progress()
    def _discard_part(self,row):
        if row['state'] not in {'CANCELLED','FAILED'} or row['settings']['keep_temporary'] or not row['part_path']:return
        try:
            expected=contained(row['settings']['directory'],'.parts',row['id']+'.part')
            if Path(row['part_path'])==expected and expected.is_file():expected.unlink()
        except (OSError,DownloadError):
            self.repository.evidence(row['id'],'cleanup','NOT_REMOVED',{'reason':'无法安全清理此任务临时文件，未删除其他文件'})
    def cleanup(self):
        for jid in self.repository.ids({'FAILED','CANCELLED'}):self._discard_part(self.repository.get(jid))
    @staticmethod
    def _default_providers():
        # Qt-free provider factory; production search engine is reused.
        from melodyvault.providers.archive import ArchiveProvider
        from melodyvault.providers.commons import CommonsProvider
        from melodyvault.providers.jamendo import JamendoProvider
        from melodyvault.providers.ccmixter import CCMixterProvider
        return [ArchiveProvider(),CommonsProvider(),JamendoProvider(os.environ.get('JAMENDO_CLIENT_ID','')),CCMixterProvider()]
    @contextmanager
    def _file_lock(self,candidate,control):
        with self.lock:lock=self.file_locks.setdefault((candidate.provider,candidate.external_id),threading.Lock())
        while not lock.acquire(timeout=.1):control.check()
        try:control.check();yield
        finally:lock.release()
    def _archive(self,jid,candidate,settings,control,bandwidth,number):
        # Same source file cannot be fetched concurrently under different songs.
        with self._file_lock(candidate,control):
            for existing in self.repository.files(candidate.provider,candidate.external_id):
                if not candidate.checksums or not any(candidate.checksums.get(k)==existing.get(k) for k in ('sha1','sha256')):continue
                path=Path(existing['path'])
                if path.is_file():
                    try:
                        media=verify_file(path,candidate,settings.max_file_bytes)
                        media.update(decode_file(path,control.check))
                    except DownloadError:continue
                    if not path.resolve().is_relative_to(Path(settings.directory).resolve()):
                        part=contained(settings.directory,'.parts',jid+'.part');part.parent.mkdir(parents=True,exist_ok=True)
                        row=self.repository.get(jid)
                        if part.exists() and row['part_path']!=str(part):raise DownloadError('FILE_CONFLICT','新目录的临时文件不属于本任务')
                        check_space(part.parent,media['bytes']);self.repository.update(jid,part_path=str(part),reason='复制已核实原始文件到新归档目录')
                        shutil.copyfile(path,part);media=verify_file(part,candidate,settings.max_file_bytes)
                        media.update(decode_file(part,control.check));control.check()
                        path=publish(part,settings.directory,candidate,media);self._sidecar(path,candidate,media)
                    control.check();self.repository.register_file(jid,candidate,path,media,True);return
            part=self._download(jid,candidate,settings,control,bandwidth)
            control.check();self.repository.update(jid,state='VERIFYING',reason='正在核对SHA-256、官方校验值和实际媒体')
            media=verify_file(part,candidate,settings.max_file_bytes)
            media.update(decode_file(part,control.check));control.check()
            final=publish(part,settings.directory,candidate,media)
            self._sidecar(final,candidate,media)
            self.repository.register_file(jid,candidate,final,media)
            if part.exists() and not settings.keep_temporary:part.unlink()
            self.repository.attempt(jid,number,'COMPLETED',{'bytes':media['bytes'],'sha256':media['sha256']})
    def _source_progress(self,jid,event):
        self.repository.update(jid,reason=f"{event['current_provider']}：{event['current_song']}；已搜索{event['searched']}/{event['total']}")
    def _download(self,jid,candidate,settings,control,bandwidth):
        if not DownloadEligibilityService.allowed(candidate):raise DownloadError('DOWNLOAD_NOT_PERMITTED','下载资格未通过')
        if candidate.file_size>settings.max_file_bytes:raise DownloadError('FILE_TOO_LARGE','来源文件超过设置的大小上限')
        root=Path(settings.directory).resolve();root.mkdir(parents=True,exist_ok=True)
        directory=contained(root,'.parts');directory.mkdir(exist_ok=True)
        part=contained(root,'.parts',jid+'.part');row=self.repository.get(jid)
        if part.exists() and row['part_path']!=str(part):raise DownloadError('FILE_CONFLICT','临时文件已存在且不属于此任务，未覆盖')
        offset=part.stat().st_size if part.exists() else 0
        validator=row['etag'] if strong_etag(row['etag']) else row['last_modified']
        if row['resource_url'] not in {candidate.direct_download_url,resource_identity(candidate.direct_download_url)} or not validator:offset=0
        check_space(directory,max(0,(candidate.file_size or settings.max_file_bytes)-offset))
        headers={}
        if offset:headers={'Range':f'bytes={offset}-','If-Range':validator}
        self.repository.update(jid,state='DOWNLOADING',part_path=str(part),bytes_received=offset,total_bytes=candidate.file_size,reason='正在下载完整原始音频')
        if candidate.file_size and offset==candidate.file_size and candidate.checksums:return part
        with audio_client(settings.timeout,self.transport) as client:
            url=candidate.direct_download_url
            for redirect in range(4):
                control.check();validate_url(candidate.provider,url)
                if self.transport is None:_AUDIO_GATES[candidate.provider].wait(control.event)
                response=client.send(client.build_request('GET',url,headers=headers),stream=True)
                if response.status_code not in {301,302,303,307,308}:break
                destination=urljoin(url,response.headers.get('Location',''));response.close()
                self.repository.evidence(jid,'redirect','CHECKED',{'redirect_number':redirect+1,'provider':candidate.provider})
                validate_url(candidate.provider,destination);url=destination
            else:raise DownloadError('UNSAFE_URL','重定向次数超过上限')
            try:
                status=response.status_code
                if status==401:raise DownloadError('DOWNLOAD_NOT_PERMITTED','来源需要身份认证，不尝试登录或绕过访问控制')
                if status in {403,404,410}:raise DownloadError('URL_EXPIRED',f'原始文件地址不可用：HTTP {status}；仅允许通过官方元数据重新核验')
                if status in {429,500,502,503,504}:
                    from email.utils import parsedate_to_datetime
                    value=response.headers.get('Retry-After','0')
                    try:delay=float(value)
                    except ValueError:
                        try:delay=parsedate_to_datetime(value).timestamp()-time.time()
                        except (ValueError,TypeError,OverflowError):delay=0
                    if delay>300:raise DownloadError('HTTP_DELAY','服务器要求较长等待，请稍后手动重试')
                    error=DownloadError('HTTP_RETRY',f'下载服务器暂时不可用：HTTP {status}');error.retry_after=max(0,delay);raise error
                if status not in {200,206}:raise DownloadError('HTTP_ERROR',f'下载响应HTTP {status}')
                if response.headers.get('Content-Encoding','identity') not in {'identity',''}:raise DownloadError('INCOMPLETE_AUDIO','下载响应有非预期内容编码')
                content_type=response.headers.get('Content-Type','').split(';')[0].lower()
                if not content_type.startswith('audio/') and content_type not in {'application/octet-stream','application/ogg'}:raise DownloadError('MEDIA_FORMAT_INVALID','服务器未返回音频文件')
                length=int(response.headers.get('Content-Length','0'))
                if status==206:
                    match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
                    if not offset or not match or int(match[1])!=offset or int(match[2])<offset or int(match[2])>=int(match[3]):raise DownloadError('OBJECT_CHANGED','续传范围与已有文件不一致')
                    strong=strong_etag(row['etag'])
                    if strong and response.headers.get('ETag')!=row['etag'] or not strong and response.headers.get('Last-Modified')!=row['last_modified']:
                        raise DownloadError('OBJECT_CHANGED','续传对象验证信息已变化，拒绝拼接')
                    total=int(match[3])
                    if length and length!=int(match[2])-offset+1:raise DownloadError('INCOMPLETE_AUDIO','Content-Range与长度不符')
                    self.repository.evidence(jid,'resume','RANGE_ACCEPTED',{'offset':offset,'total':total,'validator':'strong_etag' if strong else 'last_modified'})
                else:
                    if offset:self.repository.evidence(jid,'resume','RESTART_FROM_ZERO',{'previous_bytes':offset,'reason':'服务器返回200；不拼接旧文件'})
                    offset=0;total=length or candidate.file_size
                if not 0<total<=settings.max_file_bytes:raise DownloadError('FILE_TOO_LARGE','总大小未知或超过限制')
                if candidate.file_size and total!=candidate.file_size:raise DownloadError('FILE_SIZE_MISMATCH','HTTP总大小与官方文件大小不符')
                check_space(directory,total-offset)
                # RFC 9110: an old Last-Modified with a Date >=60s later can
                # act as a strong validator. Otherwise restart without Range.
                from email.utils import parsedate_to_datetime
                modified=response.headers.get('Last-Modified','')
                try:
                    if (parsedate_to_datetime(response.headers['Date'])-parsedate_to_datetime(modified)).total_seconds()<60:modified=''
                except (KeyError,ValueError,TypeError,OverflowError):modified=''
                self.repository.update(jid,etag=response.headers.get('ETag',''),last_modified=modified,resource_url=resource_identity(candidate.direct_download_url),total_bytes=total,bytes_received=offset)
                self.repository.evidence(jid,'response',f'HTTP_{status}',{k:response.headers.get(k,'') for k in ('Content-Length','Content-Range','Content-Type','ETag','Last-Modified','Date')})
                received=offset;started=time.monotonic();last=started
                with part.open('ab' if offset else 'wb') as stream:
                    for chunk in response.iter_bytes(64*1024):
                        control.check();bandwidth.consume(len(chunk),control)
                        if received==0 and chunk.lstrip().lower().startswith((b'mz',b'\x7felf',b'pk\x03\x04',b'<!doctype',b'<html',b'#!')):
                            raise DownloadError('MEDIA_FORMAT_INVALID','响应含可执行文件、压缩包或网页标记，未保存为音频')
                        if received+len(chunk)>total:raise DownloadError('FILE_SIZE_MISMATCH','实际响应超过声明大小')
                        check_space(directory,len(chunk));stream.write(chunk);received+=len(chunk)
                        now=time.monotonic();speed=(received-offset)/max(.001,now-started)
                        if now-last>=.25:
                            self.repository.update(jid,bytes_received=received,speed=speed,eta=(total-received)/speed if speed else None);last=now;self.progress()
                    stream.flush();os.fsync(stream.fileno())
                self.repository.update(jid,bytes_received=received,speed=0,eta=None)
                if received!=total:raise DownloadError('INCOMPLETE_AUDIO',f'响应未完整结束：{received}/{total}字节')
                control.check();return part
            finally:response.close()
    @staticmethod
    def _sidecar(final,candidate,media):
        path=Path(str(final)+'.evidence.json')
        if path.exists():
            try:
                if json.loads(path.read_text(encoding='utf-8'))['verification']['sha256']==media['sha256']:return
            except (ValueError,KeyError):pass
            raise DownloadError('FILE_CONFLICT','归档证据文件已存在且不匹配，未覆盖')
        temp=Path(str(path)+'.'+str(threading.get_ident())+'.part')
        with temp.open('x',encoding='utf-8') as f:json.dump(redact_payload({'candidate':candidate.to_dict(),'verification':media,'changes':'none; original bytes preserved'}),f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        if os.name=='nt':os.rename(temp,path)
        else:os.link(temp,path);temp.unlink()
