"""Opt-in two-artist official API regression; no offline fixtures in this path."""
import json,os,threading
from pathlib import Path
from hashlib import sha256
import pytest
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.service import CatalogService
from melodyvault.catalog.grouping import identity_work_ids
from melodyvault.database import initialize_database,connect
from melodyvault.database.catalog import CatalogRepository

@pytest.mark.live
@pytest.mark.skipif(os.environ.get('MELODYVAULT_LIVE')!='1',reason='Set MELODYVAULT_LIVE=1 for official API integration')
@pytest.mark.parametrize('name,mbid,minimum',[
    ('周杰伦','a223958d-5c56-4b2c-a30a-87e357bc121b',710),
    ('林俊杰','e5d8c705-8ea4-4820-b11d-fbf580d85ce4',443),
])
def test_real_artist_catalog_and_immutable_data(name,mbid,minimum):
    root=Path(__file__).resolve().parents[1]
    database=root/'.local/runtime/database/melodyvault.sqlite3'
    initialize_database(database);repository=CatalogRepository(database)
    with MusicBrainzClient(repository,threading.Event()) as client:
        result=CatalogService(repository,client).search(name)
    assert result.artist.mbid==mbid and result.artist.matches(name)
    assert len(result.recordings)>=minimum
    original_ids={r.mbid for r in result.recordings}
    assigned=[r.mbid for s in result.songs for r in s.recordings]
    assert len(assigned)==len(set(assigned))==len(result.recordings)
    assert set(assigned)==original_ids
    assert len(repository.recordings(mbid))==len(result.recordings)
    for song in result.songs:
        if not song.pending_confirmation and not song.reviewed:
            assert len(song.work_ids)==1
            assert all(not identity_work_ids(r) or identity_work_ids(r)==set(song.work_ids) for r in song.recordings)
    assert result.summary['independent_song_count']>0
    assert result.summary['version_count']==len(result.recordings)
    baseline=root/'.local/reports/phase1-review/baseline-raw-hashes.json'
    if baseline.exists():
        hashes=json.loads(baseline.read_text(encoding='utf-8'))
        with connect(database) as db:
            actual={row[0]:sha256(row[1].encode()).hexdigest() for row in db.execute('SELECT mbid,payload_json FROM catalog_recordings')}
        assert all(actual.get(key)==value for key,value in hashes.items())
    report=root/'.local/reports/phase1-review'/f'{mbid}-pytest-live.json'
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result.summary,ensure_ascii=False,indent=2),encoding='utf-8')
