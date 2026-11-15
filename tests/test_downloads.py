"""Synthetic WAV fixtures and explicit mock transports; never live artist audio."""
import copy,hashlib,io,json,threading,time,wave
from dataclasses import asdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import httpx,pytest
from melodyvault.database import initialize_database,connect
from melodyvault.database.downloads import DownloadRepository
from melodyvault.downloads.models import DownloadSettings,DownloadError
from melodyvault.downloads.manager import DownloadManager,RunLock
from melodyvault.downloads.eligibility import DownloadEligibilityService
from melodyvault.downloads.files import safe_component,contained,verify_file
from melodyvault.downloads.security import validate_url,public_addresses,PublicBackend
from melodyvault.sources.http import SourceHTTP

URL='https://upload.wikimedia.org/wikipedia/commons/a/ab/Test_tone.wav'
PAGE='https://commons.wikimedia.org/wiki/File:Test_tone.wav'


@pytest.fixture
def audio():
    out=io.BytesIO()
    with wave.open(out,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\x00\x01'*8000)
    return out.getvalue()


@pytest.fixture
def setup(tmp_path,audio):
    path=tmp_path/'queue.sqlite3';initialize_database(path);repo=DownloadRepository(path)
    settings=DownloadSettings(directory=str(tmp_path/'music'),max_concurrent=1,max_attempts=1,timeout=1)
    repo.save_settings(settings)
    target={'song_id':'unit-song','recording_id':'commons:7','namespace':'commons','source_page_url':PAGE,'artist':{'id':'commons:unit-creator','name':'Unit Test'},'title':'Test tone','version':'unknown','duration':1.,'confirmed':True,'recording_payload':{'id':'commons:7','title':'Test tone','length':1000},'work_ids':[]}
    raw={'provider':'commons','external_id':'7','title':'Test tone','performer':'Unit Test','page_url':PAGE,'audio_url':URL,'version':'unknown','match_status':'METADATA_MATCH','license_status':'LICENSE_VERIFIED','duration_seconds':1.,'evidence':{}}
    info={'url':URL,'descriptionurl':PAGE,'mime':'audio/wav','size':len(audio),'sha1':hashlib.sha1(audio).hexdigest(),'metadata':[{'name':'playtime_seconds','value':1.}],
          'extmetadata':{k:{'value':v} for k,v in {'ObjectName':'Test tone','Artist':'Unit Test','LicenseUrl':'https://creativecommons.org/publicdomain/zero/1.0/','LicenseShortName':'CC0','Restrictions':'','Categories':'Self-published work'}.items()}}
    response={'query':{'pages':[{'pageid':7,'title':'File:Test_tone.wav','imageinfo':[info]}]}}
    def factory(cancel=None,notice=None):return SourceHTTP(cancel,notice,transport=httpx.MockTransport(lambda request:httpx.Response(200,json=response)),interval=0,max_attempts=1)
    return repo,settings,target,raw,response,factory


def approve(setup):
    repo,settings,target,raw,response,factory=setup
    with factory() as http:return DownloadEligibilityService(http).verify(raw,target)


def manager(setup,transport):
    repo,settings,target,raw,response,factory=setup
    return DownloadManager(repo,transport=httpx.MockTransport(transport),source_http_factory=factory)


def opt_in(setup):
    repo,settings,*_=setup;settings.automatic_download=True;repo.save_settings(settings);return settings


def queue(setup):
    repo,settings,target,raw,*_=setup;return repo.enqueue(target,settings,candidate=raw)


def good(audio,request,status=200,**headers):
    return httpx.Response(status,content=audio,headers={'Content-Type':'audio/wav','Content-Length':str(len(audio)),'ETag':'"original"',**headers})


def test_default_dry_run_never_requests_audio_or_creates_files(setup,audio):
    repo,settings,*_=setup;calls=[];jid=queue(setup)
    m=manager(setup,lambda request:(calls.append(request),good(audio,request))[1]);m.run()
    row=repo.get(jid);assert row['state']=='READY' and row['reason_code']=='DRY_RUN' and not calls
    assert not Path(settings.directory).exists() and repo.summary()['COMPLETED']==0


def test_openverse_index_is_not_download_authorization(setup):
    _,_,target,raw,_,factory=setup
    raw={**raw,'provider':'openverse','license_status':'LICENSE_UNVERIFIED'}
    with factory() as http: result=DownloadEligibilityService(http).verify(raw,target)
    assert not DownloadEligibilityService.allowed(result)
    assert result.evidence['decision']=='LICENSE_UNVERIFIED'
    assert 'Openverse' in result.verification_reason[0]


def test_real_filesystem_atomic_validation_and_exact_source_dedup(setup,audio):
    opt_in(setup);repo,*_=setup;calls=[]
    m=manager(setup,lambda request:(calls.append(request),good(audio,request))[1]);first=queue(setup);m.run()
    row=repo.get(first);assert row['state']=='COMPLETED'
    result=row['result'];path=Path(result['path'])
    assert path.read_bytes()==audio and result['format']=='wav' and result['sha256']==hashlib.sha256(audio).hexdigest()
    record=repo.completed_files()[0]
    assert (record['song_id'],record['recording_id'],record['artist'],record['title'])==('unit-song','commons:7','Unit Test','Test tone')
    assert record['path']==str(path) and path.is_absolute() and record['format']=='wav'
    assert record['size']==len(audio) and record['sha256']==result['sha256'] and record['status']=='COMPLETED'
    assert record['source_url']==PAGE and record['completed_at']
    assert Path(str(path)+'.evidence.json').exists() and not Path(row['part_path']).exists()
    second=queue(setup);assert second!=first;m.run();assert repo.get(second)['result']['reused'] and len(calls)==1
    # A different same-titled recording has a distinct task, not title deduplication.
    changed=copy.deepcopy(setup[2]);changed['recording_id']='commons:999'
    third=repo.enqueue(changed,setup[1],candidate=setup[3]);m.run();assert repo.get(third)['state']=='SKIPPED' and len(calls)==1


@pytest.mark.parametrize('change,decision',[
    ('preview','PREVIEW_ONLY'),('live','VERSION_MISMATCH'),('unknown','LICENSE_UNVERIFIED'),
    ('denied','DOWNLOAD_NOT_PERMITTED'),('unconfirmed','TARGET_UNCONFIRMED'),('short','INCOMPLETE_AUDIO'),('identity','RECORDING_MISMATCH'),('rights_review','LICENSE_UNVERIFIED')])
def test_eligibility_never_upgrades_weak_or_restricted_candidates(setup,change,decision):
    target=setup[2];info=setup[4]['query']['pages'][0]['imageinfo'][0]
    if change=='preview':info['extmetadata']['ObjectName']['value']='Test tone preview'
    if change=='live':setup[3]['match_status']='VERSION_MISMATCH'
    if change=='unknown':info['extmetadata']['LicenseUrl']['value']=''
    if change=='denied':info['extmetadata']['Restrictions']['value']='No downloads'
    if change=='unconfirmed':target['confirmed']=False
    if change=='short':info['metadata'][0]['value']=.2
    if change=='identity':target['recording_id']='commons:8'
    if change=='rights_review':info['extmetadata']['Categories']['value']='License review needed (audio)'
    result=approve(setup);assert result.evidence['decision']==decision and not DownloadEligibilityService.allowed(result)


def test_no_title_artist_duration_only_musicbrainz_identity(setup):
    target=setup[2];target.update(namespace='musicbrainz',recording_id='00000000-0000-4000-8000-000000000001',isrcs=[],urls=[])
    assert approve(setup).evidence['decision']=='RECORDING_MISMATCH'
    target['urls']=[PAGE];assert DownloadEligibilityService.allowed(approve(setup))


def test_archive_license_claim_does_not_approve_recording(setup):
    setup[3]['provider']='archive';assert approve(setup).evidence['decision']=='LICENSE_UNVERIFIED'


@pytest.mark.parametrize('mode,code',[
    ('expired','URL_EXPIRED'),('timeout','DOWNLOAD_TIMEOUT'),('network','NETWORK_INTERRUPTED'),
    ('size','FILE_SIZE_MISMATCH'),('hash','HASH_MISMATCH'),('html','MEDIA_FORMAT_INVALID'),('redirect','UNSAFE_URL')])
def test_transfer_failures_never_publish_or_count_success(setup,audio,mode,code):
    opt_in(setup);repo,*_=setup;jid=queue(setup)
    def transfer(request):
        if mode=='expired':return httpx.Response(403)
        if mode=='timeout':raise httpx.ReadTimeout('fault-injected timeout',request=request)
        if mode=='network':raise httpx.ConnectError('fault-injected disconnect',request=request)
        if mode=='size':return good(audio,request,**{'Content-Length':str(len(audio)+1)})
        if mode=='hash':return good(audio[:-1]+b'X',request)
        if mode=='html':return good(b'<html>'+b'x'*(len(audio)-6),request)
        return httpx.Response(302,headers={'Location':'https://127.0.0.1/private.mp3'})
    manager(setup,transfer).run();row=repo.get(jid)
    assert row['state']=='FAILED' and row['reason_code']==code and repo.summary()['COMPLETED']==0
    assert not list(Path(setup[1].directory).rglob('*.wav'))


def partial(setup,audio,etag='"original"'):
    repo,settings,*_=setup;jid=queue(setup);root=Path(settings.directory);path=root/'.parts'/(jid+'.part');path.parent.mkdir(parents=True);path.write_bytes(audio[:4096])
    repo.update(jid,state='PAUSED',part_path=str(path.resolve()),bytes_received=4096,etag=etag,resource_url=URL)
    return jid,path


@pytest.mark.parametrize('support_range',[True,False])
def test_range_resume_and_safe_server_200_restart(setup,audio,support_range):
    opt_in(setup);repo,*_=setup;jid,path=partial(setup,audio);seen=[]
    def transfer(request):
        seen.append(request.headers.get('Range'))
        assert request.headers.get('If-Range')=='"original"'
        if support_range:return good(audio[4096:],request,206,**{'Content-Range':f'bytes 4096-{len(audio)-1}/{len(audio)}'})
        return good(audio,request)
    m=manager(setup,transfer);m.resume(jid);m.run()
    assert seen==['bytes=4096-'] and repo.get(jid)['state']=='COMPLETED'
    assert Path(repo.get(jid)['result']['path']).read_bytes()==audio
    assert any(e['decision']==('RANGE_ACCEPTED' if support_range else 'RESTART_FROM_ZERO') for e in repo.evidence_rows(jid))


def test_changed_etag_refuses_append_and_weak_validator_restarts(setup,audio):
    opt_in(setup);repo,*_=setup;jid,path=partial(setup,audio)
    m=manager(setup,lambda request:good(audio[4096:],request,206,**{'Content-Range':f'bytes 4096-{len(audio)-1}/{len(audio)}','ETag':'"changed"'}))
    m.resume(jid);m.run();assert repo.get(jid)['reason_code']=='OBJECT_CHANGED' and path.read_bytes()==audio[:4096]
    # A weak ETag is never used in If-Range without a Last-Modified fallback.
    repo.update(jid,state='PAUSED',etag='W/"original"');seen=[]
    m=manager(setup,lambda request:(seen.append(request.headers.get('Range')),good(audio,request))[1]);m.resume(jid);m.run()
    assert seen==[None] and repo.get(jid)['state']=='COMPLETED'


def test_pause_restart_resume_batch_cancel_and_catalog_survives(setup,audio):
    settings=opt_in(setup);settings.speed_limit=4096;setup[0].save_settings(settings)
    repo,*_=setup;jid=queue(setup);m=manager(setup,lambda request:good(audio,request))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(m.run)
        for _ in range(100):
            if repo.get(jid)['state']=='DOWNLOADING':break
            time.sleep(.01)
        m.stop(jid,'PAUSED');future.result(timeout=5)
    assert repo.get(jid)['state']=='PAUSED'
    # A crash while reading is recovered as PAUSED, never COMPLETED/QUEUED auto-run.
    repo.update(jid,state='DOWNLOADING');m2=manager(setup,lambda request:good(audio,request));m2.recover()
    assert repo.get(jid)['state']=='PAUSED' and repo.get(jid)['reason_code']=='RESTART_RECOVERY'
    m2.stop_all('CANCELLED');assert repo.get(jid)['state']=='CANCELLED'
    with connect(repo.path) as db:assert db.execute('SELECT count(*) FROM catalog_recordings').fetchone()[0]==0


def test_disk_space_path_reserved_names_and_existing_different_file(setup,audio,monkeypatch):
    opt_in(setup);repo,*_=setup;jid=queue(setup)
    import melodyvault.downloads.files as files
    monkeypatch.setattr(files.shutil,'disk_usage',lambda p:type('Disk',(),{'free':0})())
    manager(setup,lambda request:good(audio,request)).run();assert repo.get(jid)['reason_code']=='DISK_FULL'
    assert safe_component('CON')=='_CON' and ':' not in safe_component('a:b/../c')
    with pytest.raises(DownloadError):contained(Path(setup[1].directory),'..','escape.wav')


@pytest.mark.parametrize('url',[
    'http://upload.wikimedia.org/wikipedia/commons/a/ab/a.wav','https://127.0.0.1/a.wav',
    'https://upload.wikimedia.org.evil.test/wikipedia/commons/a/ab/a.wav',
    'https://user:pass@upload.wikimedia.org/wikipedia/commons/a/ab/a.wav',
    'https://upload.wikimedia.org/wikipedia/commons/a/ab/../../x.wav',
    'https://upload.wikimedia.org/wikipedia/commons/a/ab/%2e%2e/x.wav',
    'https://upload.wikimedia.org:444/wikipedia/commons/a/ab/a.wav'])
def test_url_security_rejects_unsafe_origins(url):
    with pytest.raises(DownloadError):validate_url('commons',url)


def test_dns_rebinding_connection_checks_all_addresses_before_dial(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('93.184.216.34',443)),(2,1,6,'',('192.168.1.2',443))])
    with pytest.raises(DownloadError):public_addresses('upload.wikimedia.org')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))])
    import httpcore
    seen=[];monkeypatch.setattr(httpcore.SyncBackend,'connect_tcp',lambda self,host,*a,**k:seen.append(host) or 'stream')
    assert PublicBackend().connect_tcp('upload.wikimedia.org',443)=='stream' and seen==['93.184.216.34']


def test_queue_lock_and_append_only_evidence(setup):
    repo,*_=setup;jid=queue(setup)
    with RunLock(repo.path):
        with pytest.raises(DownloadError):
            with RunLock(repo.path):pass
    repo.evidence(jid,'test','SKIPPED',{})
    with connect(repo.path) as db:
        with pytest.raises(Exception):db.execute('DELETE FROM download_evidence')


def test_simultaneous_same_file_tasks_are_serialized_and_deduplicated(setup,audio):
    settings=opt_in(setup);settings.max_concurrent=3;setup[0].save_settings(settings);repo=setup[0];calls=[]
    for i in range(4):
        target={**setup[2],'song_id':f'unit-song-{i}'};repo.enqueue(target,settings,candidate=setup[3])
    m=manager(setup,lambda request:(calls.append(1),good(audio,request))[1]);m.run()
    assert repo.summary()['COMPLETED']==4 and len(calls)==1
    assert sum(repo.get(r['id'])['result']['reused'] for r in repo.rows())==3


def test_new_directory_copies_verified_bytes_without_moving_old_file(setup,audio,tmp_path):
    settings=opt_in(setup);repo=setup[0];calls=[];m=manager(setup,lambda request:(calls.append(1),good(audio,request))[1]);first=queue(setup);m.run()
    old=Path(repo.get(first)['result']['path']);settings.directory=str(tmp_path/'new-music');repo.save_settings(settings)
    second=queue(setup);m.run();new=Path(repo.get(second)['result']['path'])
    assert new!=old and new.is_relative_to(Path(settings.directory)) and new.read_bytes()==old.read_bytes()==audio and len(calls)==1


def test_failed_job_manual_retry_is_explicit_bounded_and_preserves_history(setup,audio):
    opt_in(setup);repo=setup[0];jid=queue(setup);manager(setup,lambda request:httpx.Response(503)).run()
    assert repo.get(jid)['state']=='FAILED'
    m=manager(setup,lambda request:good(audio,request));m.retry_failed();m.run()
    assert repo.get(jid)['state']=='COMPLETED' and any(r['decision']=='USER_RETRY' for r in repo.evidence_rows(jid))
    with connect(repo.path) as db:assert db.execute('SELECT count(*) FROM download_attempts WHERE status=\'FAILED\'').fetchone()[0]==1


def test_commons_version_word_fallback_preserves_candidate_as_unverified(setup):
    from melodyvault.providers.commons import CommonsProvider
    from melodyvault.sources.models import SourceQuery
    queries=[]
    class API:
        def json(self,url,params):
            queries.append(params['gsrsearch'])
            return {} if len(queries)==1 else setup[4]
    q=SourceQuery('unit','song','Unit Test','Test tone',['Unit Test'],['Test tone'],['instrumental'],[1000],['unit-recording'])
    results=CommonsProvider().search(q,API())
    assert len(results)==1 and '"instrumental"' in queries[0] and '"instrumental"' not in queries[1]
    assert results[0].match_status!='RECORDING_VERIFIED'


def test_truncated_declared_media_and_file_extension_do_not_pass(setup,audio,tmp_path):
    candidate=approve(setup);path=tmp_path/'misnamed.mp3';path.write_bytes(audio)
    assert verify_file(path,candidate,100000)['format']=='wav'
    candidate.checksums={};path.write_bytes(audio[:-200]);candidate.file_size=path.stat().st_size
    with pytest.raises(DownloadError):verify_file(path,candidate,100000)


def test_bare_etag_uses_valid_last_modified_for_if_range(setup,audio):
    opt_in(setup);repo=setup[0];jid,path=partial(setup,audio,etag='bare-checksum')
    stamp='Mon, 11 Dec 2017 22:11:08 GMT';repo.update(jid,last_modified=stamp);seen=[]
    def transfer(request):
        seen.append(request.headers.get('If-Range'))
        return good(audio[4096:],request,206,**{'Content-Range':f'bytes 4096-{len(audio)-1}/{len(audio)}','ETag':'bare-checksum','Last-Modified':stamp,'Date':'Sat, 14 Nov 2026 04:00:00 GMT'})
    m=manager(setup,transfer);m.resume(jid);m.run();assert seen==[stamp] and repo.get(jid)['state']=='COMPLETED'


def test_official_url_expiry_refreshes_before_bounded_retry(setup,audio):
    settings=opt_in(setup);settings.max_attempts=2;setup[0].save_settings(settings)
    repo=setup[0];jid=queue(setup);calls=[]
    def transfer(request):
        calls.append(str(request.url))
        if len(calls)==1:
            setup[4]['query']['pages'][0]['imageinfo'][0]['url']=URL.replace('Test_tone','Fresh_object')
            return httpx.Response(403)
        return good(audio,request)
    manager(setup,transfer).run()
    assert repo.get(jid)['state']=='COMPLETED' and len(calls)==2 and calls[0]!=calls[1]


def test_sha256_mismatch_and_existing_different_file_are_rejected(setup,audio,tmp_path):
    from melodyvault.downloads.files import publish
    c=approve(setup);part=tmp_path/'owned.part';part.write_bytes(audio)
    c.checksums['sha256']='0'*64
    with pytest.raises(DownloadError,match='SHA256'):verify_file(part,c,100000)
    c.checksums.pop('sha256');verified=verify_file(part,c,100000);final=publish(part,setup[1].directory,c,verified)
    final.write_bytes(b'pre-existing different user content');part.write_bytes(audio)
    with pytest.raises(DownloadError) as error:publish(part,setup[1].directory,c,verified)
    assert error.value.code=='FILE_CONFLICT' and final.read_bytes()==b'pre-existing different user content'


def test_automatic_opt_in_revoked_before_run_prevents_transfer(setup,audio):
    settings=opt_in(setup);jid=queue(setup);settings.automatic_download=False;setup[0].save_settings(settings);calls=[]
    manager(setup,lambda request:(calls.append(1),good(audio,request))[1]).run()
    assert not calls and setup[0].get(jid)['state']=='READY' and setup[0].get(jid)['reason_code']=='OPT_IN_REQUIRED'


def test_maximum_concurrency_is_actual_stream_concurrency(setup,audio):
    settings=opt_in(setup);settings.max_concurrent=2;setup[0].save_settings(settings);repo=setup[0]
    def factory(cancel=None,notice=None):
        def metadata(request):
            pid=request.url.params['pageids'];response=copy.deepcopy(setup[4]);page=response['query']['pages'][0];page['pageid']=int(pid)
            page['imageinfo'][0].update(url=URL.replace('Test_tone','tone_'+pid),descriptionurl=PAGE.replace('Test_tone','tone_'+pid))
            return httpx.Response(200,json=response)
        return SourceHTTP(cancel,notice,transport=httpx.MockTransport(metadata),interval=0,max_attempts=1)
    for i in range(8,12):
        target={**setup[2],'song_id':f'song-{i}','recording_id':f'commons:{i}','source_page_url':PAGE.replace('Test_tone','tone_'+str(i))}
        raw={**setup[3],'external_id':str(i)};repo.enqueue(target,settings,candidate=raw)
    count=[0,0];lock=threading.Lock();barrier=threading.Barrier(2,timeout=10)
    class Slow(httpx.SyncByteStream):
        def __iter__(self):
            with lock:count[0]+=1;count[1]=max(count[1],count[0])
            try:barrier.wait();yield audio
            finally:
                with lock:count[0]-=1
    m=DownloadManager(repo,source_http_factory=factory,transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=Slow(),headers={'Content-Type':'audio/wav','Content-Length':str(len(audio)),'ETag':'"v1"'})))
    m.run();assert repo.summary()['COMPLETED']==4 and count[1]==2


def test_credentials_never_persist_in_evidence_hints_or_signed_urls(setup):
    from melodyvault.privacy import redact_payload
    repo,settings,target,raw,*_=setup
    raw={**raw,'audio_url':URL+'?token=PRIVATE_VALUE&foo=public','evidence':{'api_key':'PRIVATE_KEY','note':'Bearer PRIVATE_BEARER','html':'<a href="https://user:password@host.test/a?signature=PRIVATE_SIG">x</a>'}}
    jid=repo.enqueue(target,settings,candidate=raw);repo.evidence(jid,'privacy','TEST',raw)
    with connect(repo.path) as db:serialized=''.join(str(tuple(r)) for table in ('download_jobs','download_evidence') for r in db.execute('SELECT * FROM '+table))
    assert 'PRIVATE_' not in serialized and 'user:password' not in serialized and 'foo=public' in serialized


@pytest.mark.parametrize('action',['PAUSED','CANCELLED'])
def test_pause_or_cancel_during_batch_creation_applies_to_remaining_songs(setup,action):
    from melodyvault.catalog.models import Artist,Recording,Song,CatalogResult
    from melodyvault.downloads.worker import DownloadWorker
    repo,settings,*_=setup
    artist=Artist.from_payload({'id':'00000000-0000-4000-8000-000000000001','name':'Synthetic test artist'})
    songs=[]
    for i in range(3):
        r=Recording.from_payload({'id':f'00000000-0000-4000-8000-00000000000{i+2}','title':f'Synthetic tone {i}'})
        songs.append(Song(f'unit-{i}',r.title,[r],(),True,[]))
    w=DownloadWorker(DownloadManager(repo),'enqueue',CatalogResult(artist,songs,{}));w.request_stop(action);w.run()
    assert repo.summary()['total']==3 and repo.summary()[action]==3 and not Path(settings.directory).exists()


@pytest.mark.parametrize('failure',['disconnect','timeout'])
def test_midstream_interruption_preserves_bytes_and_manual_retry_resumes(setup,failure):
    out=io.BytesIO()
    with wave.open(out,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\x00\x01'*(8000*8))
    data=out.getvalue();opt_in(setup);repo=setup[0];setup[2]['duration']=8
    info=setup[4]['query']['pages'][0]['imageinfo'][0];info.update(size=len(data),sha1=hashlib.sha1(data).hexdigest());info['metadata'][0]['value']=8
    jid=queue(setup);calls=[]
    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            yield data[:65536]
            if failure=='timeout':raise httpx.ReadTimeout('fault-injected after actual prefix')
            raise httpx.ReadError('fault-injected after actual prefix')
    def transport(request):
        calls.append(request.headers.get('Range'))
        if len(calls)==1:return httpx.Response(200,stream=Broken(),headers={'Content-Type':'audio/wav','Content-Length':str(len(data)),'ETag':'"original"'})
        return good(data[65536:],request,206,**{'Content-Range':f'bytes 65536-{len(data)-1}/{len(data)}'})
    m=manager(setup,transport);m.run();row=repo.get(jid)
    assert row['state']=='FAILED' and Path(row['part_path']).stat().st_size==65536
    assert row['reason_code']==('DOWNLOAD_TIMEOUT' if failure=='timeout' else 'NETWORK_INTERRUPTED')
    m.retry_failed();m.run();assert calls==[None,'bytes=65536-'] and repo.get(jid)['state']=='COMPLETED'


def test_recording_proof_does_not_collapse_meaningful_url_queries(setup):
    target=setup[2];target.update(namespace='musicbrainz',isrcs=[],urls=[PAGE+'?oldid=1'])
    setup[4]['query']['pages'][0]['imageinfo'][0]['descriptionurl']=PAGE+'?oldid=2'
    assert approve(setup).evidence['decision']=='RECORDING_MISMATCH'
    target['urls']=[URL+'?utm_source=reference'];assert DownloadEligibilityService.allowed(approve(setup))


def test_resume_resource_identity_retains_file_ids_and_format_parameters():
    from melodyvault.downloads.security import resource_identity
    assert resource_identity(URL+'?id=1&format=wav')!=resource_identity(URL+'?id=2&format=wav')
    assert resource_identity(URL+'?id=1&token=SECRET&utm_source=app')==URL+'?id=1'


@pytest.mark.parametrize('provider',['commons','jamendo'])
def test_official_api_json_errors_are_failures_not_denied_permission(setup,provider,monkeypatch):
    repo=setup[0];setup[3]['provider']=provider;setup[4].clear()
    setup[4].update({'error':{'code':'maxlag'}} if provider=='commons' else {'headers':{'status':'failed'}})
    if provider=='jamendo':monkeypatch.setenv('JAMENDO_CLIENT_ID','unit-fake-id')
    jid=queue(setup);manager(setup,lambda request:pytest.fail('API failure cannot request audio')).run()
    assert repo.get(jid)['state']=='FAILED' and repo.get(jid)['reason_code']=='VERIFICATION_FAILED'


def test_selected_query_alias_and_exact_version_survive_download_snapshot():
    from melodyvault.catalog.models import Artist,Recording,Song
    from melodyvault.downloads.targets import from_song,search_values
    from melodyvault.sources.models import SourceQuery
    artist=Artist.from_payload({'id':'00000000-0000-4000-8000-000000000001','name':'Unit Test'})
    record=Recording.from_payload({'id':'00000000-0000-4000-8000-000000000002','title':'晴天（现场）','length':1000,'disambiguation':'live'})
    song=Song('unit-song','晴天',[record],(),True,[{'rule':'user_selected_search_alias','title':'Qing Tian','not_identity_proof':True}])
    before=SourceQuery.from_song(artist,song,{})
    target=from_song(artist,song,True);after_artist,after_song=search_values(target);after=SourceQuery.from_song(after_artist,after_song,{})
    assert 'Qing Tian' in after.titles and after.versions==['live'] and before.fingerprint==after.fingerprint
