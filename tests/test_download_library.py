"""Download-to-library integration, with explicit synthetic WAV fixtures."""
from dataclasses import replace
from pathlib import Path
import pytest
from melodyvault.database import connect
from melodyvault.downloads.files import decode_file
from melodyvault.downloads.models import DownloadError
from test_downloads import setup, audio, manager, good


def test_verified_download_indexes_once_preserves_user_edits(setup,audio):
    repo,settings,target,raw,*_=setup
    settings=replace(settings,automatic_download=True)
    engine=manager(setup,lambda req:good(audio,req))
    first=repo.enqueue(target,settings,candidate=raw);engine.run(job_ids=[first],settings_override=settings)
    row=repo.get(first)
    assert row['state']=='COMPLETED' and row['result']['full_decode']
    with connect(repo.path) as db:
        assert db.execute('select count(*) from personal_music').fetchone()[0]==1
        db.execute("update personal_music set title='用户修改' where id=?",(row['result']['library_id'],))
    second=repo.enqueue(target,settings,candidate=raw);engine.run(job_ids=[second],settings_override=settings)
    again=repo.get(second)
    assert again['state']=='COMPLETED' and again['result']['reused']
    assert again['result']['library_id']==row['result']['library_id']
    with connect(repo.path) as db:
        assert [tuple(r) for r in db.execute('select title,path from personal_music')]==[('用户修改',row['result']['path'])]


def test_failed_download_never_enters_library(setup,audio):
    import httpx
    repo,settings,target,raw,*_=setup
    settings=replace(settings,automatic_download=True,max_attempts=1)
    engine=manager(setup,lambda req:httpx.Response(200,headers={'Content-Type':'text/html'},content=b'<html>login</html>',request=req))
    jid=repo.enqueue(target,settings,candidate=raw);engine.run(job_ids=[jid],settings_override=settings)
    assert repo.get(jid)['state']=='FAILED'
    with connect(repo.path) as db:assert db.execute('select count(*) from personal_music').fetchone()[0]==0


def test_decoder_rejects_fake_audio_and_obeys_cancel(tmp_path):
    path=tmp_path/'bad.ogg';path.write_bytes(b'OggS'+b'\x00'*100)
    with pytest.raises(DownloadError,match='无法完整解码'):decode_file(path)
    def cancel():raise InterruptedError('cancelled')
    with pytest.raises(InterruptedError):decode_file(path,check=cancel)
