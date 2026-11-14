import threading
import json
import httpx
import pytest
from melodyvault.catalog.service import CatalogService
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.evidence import enrich_artist
from melodyvault.catalog.models import Artist,Recording,CatalogCancelled
from melodyvault.database import initialize_database,connect
from melodyvault.database.catalog import CatalogRepository
from catalog_fixtures import CatalogTransport,ARTIST_ID,recording
from test_review import review_data,find


def test_fast_catalog_publishes_real_pages_and_skips_deep_work(tmp_path):
    repo=CatalogRepository(tmp_path/'fast.sqlite3');initialize_database(repo.path)
    transport=CatalogTransport();partials=[]
    with MusicBrainzClient(repo,threading.Event(),transport=httpx.MockTransport(transport),interval=0) as client:
        result=CatalogService(repo,client,partial=partials.append).search_catalog('周杰伦')
    assert partials and 0<len(partials[0].recordings)<=len(result.recordings)
    assert len(result.recordings)==4
    assert not any('work'==endpoint or 'work-rels' in params.get('inc','') for endpoint,params in transport.calls)
    def forbidden(request):raise AssertionError('Saved catalog must not perform any HTTP request')
    with MusicBrainzClient(repo,threading.Event(),transport=httpx.MockTransport(forbidden)) as client:
        again=CatalogService(repo,client).search_catalog('周杰伦')
        assert client.requests==0 and again.summary['cached_catalog']
    assert {r.mbid for r in again.recordings}=={r.mbid for r in result.recordings}


def test_saved_catalog_preserves_manual_merge_and_audit_without_replay_io(review_data):
    repo,artist,records,review=review_data;snapshot=review.load(artist)
    review.decide(artist,'merge',find(snapshot,records[1].mbid).id,find(snapshot,records[0].mbid).id,'测试本地读取保留手工决定')
    with MusicBrainzClient(repo,threading.Event(),transport=httpx.MockTransport(lambda request:pytest.fail('Unexpected HTTP'))) as client:
        result=CatalogService(repo,client).search_catalog('周杰伦')
    assert any({records[0].mbid,records[1].mbid}<={r.mbid for r in s.recordings} for s in result.songs)
    assert result.summary['manually_reviewed_item_count']==1
    with connect(repo.path) as db:assert db.execute('SELECT count(*) FROM catalog_review_events').fetchone()[0]==1


def test_explicit_catalog_refresh_bypasses_saved_shortcut(tmp_path):
    repo=CatalogRepository(tmp_path/'refresh.sqlite3');initialize_database(repo.path);transport=CatalogTransport()
    with MusicBrainzClient(repo,threading.Event(),transport=httpx.MockTransport(transport),interval=0) as client:
        CatalogService(repo,client).search_catalog('周杰伦')
    transport.calls.clear()
    with MusicBrainzClient(repo,threading.Event(),force_refresh=True,transport=httpx.MockTransport(transport),interval=0) as client:
        result=CatalogService(repo,client).search_catalog('周杰伦')
        assert client.requests>0 and client.cache_hits==0
    assert result.summary['recording_count']==4


def test_negative_work_checks_are_timestamped_and_force_refreshable(tmp_path):
    repo=CatalogRepository(tmp_path/'negative.sqlite3');initialize_database(repo.path)
    artist=Artist.from_payload({'id':ARTIST_ID,'name':'周杰倫'});raw={**recording(1),'relations':[],'releases':[]}
    repo.save_artist('周杰伦',artist);repo.save_recordings(artist,[Recording.from_payload(raw)])
    def transport(request):
        endpoint=request.url.path.removeprefix('/ws/2/')
        if endpoint=='recording':return httpx.Response(200,json={'recordings':[raw],'recording-count':1,'recording-offset':0})
        if endpoint=='work':return httpx.Response(200,json={'works':[],'work-count':0,'work-offset':0})
        return httpx.Response(200,json=raw)
    with MusicBrainzClient(repo,threading.Event(),transport=httpx.MockTransport(transport),interval=0) as client:
        enrich_artist(repo,client,artist,lambda event:None);assert client.requests==3
    with connect(repo.path) as db:
        row=db.execute("SELECT status,checked_at,payload_json FROM catalog_task_cache WHERE kind='recording'").fetchone()
        assert row[0]=='no_work' and row[1]>0 and json.loads(row[2])['work_ids']==[]
    with MusicBrainzClient(repo,threading.Event(),transport=httpx.MockTransport(transport),interval=0) as client:
        assert enrich_artist(repo,client,artist,lambda event:None)['deep_task_reused'] and client.requests==0
    with MusicBrainzClient(repo,threading.Event(),True,transport=httpx.MockTransport(transport),interval=0) as client:
        enrich_artist(repo,client,artist,lambda event:None);assert client.requests==3


def test_cancelled_evidence_keeps_existing_catalog_and_audit(review_data):
    repo,artist,records,review=review_data;review.load(artist)
    before={s.id:{r.mbid for r in s.recordings} for s in repo.songs(artist.mbid)}
    event=threading.Event();event.set()
    with MusicBrainzClient(repo,event) as client:
        with pytest.raises(CatalogCancelled):enrich_artist(repo,client,artist,lambda event:None)
    assert {s.id:{r.mbid for r in s.recordings} for s in repo.songs(artist.mbid)}==before


def test_musicbrainz_retry_after_zero_does_not_remove_exponential_backoff(tmp_path):
    repo=CatalogRepository(tmp_path/'backoff.sqlite3');initialize_database(repo.path)
    with MusicBrainzClient(repo,threading.Event()) as client:
        assert client._retry_delay(httpx.Response(503,headers={'Retry-After':'0'}),1)==4
        assert client._retry_delay(httpx.Response(429,headers={'Retry-After':'9'}),0)==9
        assert client._retry_delay(None,2)==8
