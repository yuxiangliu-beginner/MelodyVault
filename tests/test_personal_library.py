import hashlib,subprocess,threading
from pathlib import Path
import pytest
from melodyvault.database import initialize_database,connect
from melodyvault.library.imports import inspect_audio,import_one

@pytest.fixture
def samples(tmp_path):
    ff=pytest.importorskip('imageio_ffmpeg').get_ffmpeg_exe();paths=[]
    for fmt,codec in [('mp3','libmp3lame'),('flac','flac'),('m4a','aac'),('wav','pcm_s16le')]:
        p=tmp_path/('original.'+fmt)
        subprocess.run([ff,'-v','error','-f','lavfi','-i','sine=frequency=400:duration=1','-c:a',codec,'-metadata','title=Example Song','-metadata','artist=Example Artist',str(p)],check=True,capture_output=True)
        paths.append(p)
    return paths

def test_real_formats_copy_metadata_duplicate_and_conflict(tmp_path,samples):
    db=tmp_path/'db.sqlite3';initialize_database(db);root=tmp_path/'music';cancel=threading.Event();before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in samples}
    results=[]
    for i,p in enumerate(samples):
        item=inspect_audio(p);assert item['title']=='Example Song' and item['artist']=='Example Artist'
        item.update(title='歌曲'+str(i),artist='歌手')
        results.append(import_one(db,root,item,cancel));assert Path(results[-1]['path']).is_file()
    assert all(r['state']=='IMPORTED' for r in results)
    assert all(p.parent.name=='歌手' for p in map(lambda r:Path(r['path']),results))
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==before[p] for p in samples)
    assert import_one(db,root,{**inspect_audio(samples[0]),'title':'另一个标题','artist':'其他'},cancel)['state']=='DUPLICATE'
    p=tmp_path/'different.mp3';ff=pytest.importorskip('imageio_ffmpeg').get_ffmpeg_exe()
    subprocess.run([ff,'-v','error','-f','lavfi','-i','sine=frequency=900:duration=1','-c:a','libmp3lame',str(p)],check=True,capture_output=True)
    with pytest.raises(FileExistsError):import_one(db,root,{**inspect_audio(p),'title':'歌曲0','artist':'歌手'},cancel)
    assert hashlib.sha256(Path(results[0]['path']).read_bytes()).hexdigest()==before[samples[0]]
    with connect(db) as c:assert c.execute('select count(*) from personal_music').fetchone()[0]==4
    cancel.set()
    with pytest.raises(InterruptedError):import_one(db,root,inspect_audio(p),cancel)
    assert not list(root.rglob('*.part'))

def test_recover_does_not_interrupt_live_import(tmp_path):
    from melodyvault.downloads.manager import RunLock
    from melodyvault.downloads.models import DownloadError,DownloadSettings
    from melodyvault.database.downloads import DownloadRepository
    from melodyvault.library.imports import recover_imports
    db=tmp_path/'db.sqlite3';initialize_database(db);repo=DownloadRepository(db)
    target={'song_id':'id','recording_id':'id','namespace':'local_import','title':'test','artist':{'id':'x','name':'test'}}
    jid=repo.enqueue(target,DownloadSettings(directory=str(tmp_path)));repo.update(jid,state='DOWNLOADING')
    repo.recover();assert repo.get(jid)['state']=='DOWNLOADING'
    with RunLock(str(db)+'.imports'):
        with pytest.raises(DownloadError):recover_imports(db)
        assert repo.get(jid)['state']=='DOWNLOADING'
    recover_imports(db);assert repo.get(jid)['state']=='PAUSED'

def test_failed_import_is_saved_as_retryable_task(tmp_path,samples):
    from melodyvault.ui.import_dialog import ImportWorker
    from melodyvault.database.downloads import DownloadRepository
    from melodyvault.downloads.models import DownloadSettings
    db=tmp_path/'db.sqlite3';initialize_database(db);root=tmp_path/'music';repo=DownloadRepository(db)
    repo.save_settings(DownloadSettings(directory=str(root)))
    first={**inspect_audio(samples[0]),'title':'same','artist':'artist'}
    import_one(db,root,first,threading.Event())
    ff=pytest.importorskip('imageio_ffmpeg').get_ffmpeg_exe();other=tmp_path/'other.mp3'
    subprocess.run([ff,'-v','error','-f','lavfi','-i','sine=frequency=901:duration=1','-c:a','libmp3lame',str(other)],check=True,capture_output=True)
    item={**inspect_audio(other),'title':'same','artist':'artist'}
    worker=ImportWorker(db,str(root),[item]);worker.run()
    rows=repo.rows();assert len(rows)==1 and rows[0]['state']=='FAILED'
    assert repo.get(rows[0]['id'])['reason_code']=='IMPORT_FAILED' and other.is_file()

def test_changed_library_file_is_not_mistaken_for_duplicate(tmp_path,samples):
    db=tmp_path/'db.sqlite3';initialize_database(db);source=samples[0];root=tmp_path/'music'
    item={**inspect_audio(source),'artist':'artist','title':'first'}
    first=import_one(db,root,item,threading.Event());Path(first['path']).write_bytes(b'user changed file')
    second=import_one(db,root,{**item,'title':'second'},threading.Event())
    assert second['state']=='IMPORTED' and Path(second['path']).read_bytes()==source.read_bytes()
    assert Path(first['path']).read_bytes()==b'user changed file'

def test_artist_folder_uses_same_simplified_name_as_downloads(tmp_path,samples):
    db=tmp_path/'db.sqlite3';initialize_database(db)
    result=import_one(db,tmp_path/'music',{**inspect_audio(samples[0]),'artist':'周杰倫','title':'测试'},threading.Event())
    assert Path(result['path']).parent.name=='周杰伦'
    with connect(db) as c:assert c.execute('select artist from personal_music').fetchone()[0]=='周杰伦'
