import json
from melodyvault.catalog.models import Artist, Recording
from melodyvault.catalog.grouping import group_recordings, RULE_VERSION
from melodyvault.database import initialize_database, connect, migrations
from melodyvault.database.catalog import CatalogRepository
from catalog_fixtures import ARTIST_ID, recording


def test_v2_upgrade_preserves_original_payload_cache_and_recording_ids(tmp_path,monkeypatch):
    path=tmp_path/'v2.sqlite3'
    original=migrations.MIGRATIONS
    monkeypatch.setattr(migrations,'MIGRATIONS',original[:2])
    assert initialize_database(path)==2
    data=recording(1,'龍拳'); raw=json.dumps(data,ensure_ascii=False)
    artist_data={'id':ARTIST_ID,'name':'周杰倫'}
    with connect(path) as db:
        db.execute('INSERT INTO catalog_artists VALUES (?,?,?,?)',(ARTIST_ID,'周杰倫',json.dumps(artist_data),'2026-01-01'))
        db.execute('INSERT INTO catalog_recordings VALUES (?,?,?,?,?)',(data['id'],'龍拳','龙拳',raw,'2026-01-01'))
        db.execute('INSERT INTO catalog_artist_recordings VALUES (?,?,?,?)',(ARTIST_ID,data['id'],1,'[]'))
        db.execute('INSERT INTO catalog_http_cache VALUES (?,?,?)',('old-page','{"original":true}',1))
    monkeypatch.setattr(migrations,'MIGRATIONS',original)
    assert initialize_database(path)==len(original)
    repository=CatalogRepository(path)
    repository.save_recordings(Artist.from_payload(artist_data),[Recording.from_payload({**data,'title':'新查询标题'})])
    repository.cache_response('old-page',{'new':True})
    repository.finalize_membership(Artist.from_payload(artist_data),set())
    with connect(path) as db:
        assert db.execute('SELECT payload_json FROM catalog_recordings').fetchone()[0]==raw
        assert db.execute('SELECT count(*) FROM catalog_artist_recordings').fetchone()[0]==1
        assert raw in {row[0] for row in db.execute('SELECT payload_json FROM catalog_recording_snapshots')}
        assert '{"original":true}' in {row[0] for row in db.execute('SELECT payload_json FROM catalog_response_history')}
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_rebuilding_only_derived_song_mappings_preserves_recordings(tmp_path):
    path=tmp_path/'songs.sqlite3'; initialize_database(path); repository=CatalogRepository(path)
    artist=Artist.from_payload({'id':ARTIST_ID,'name':'周杰倫'})
    repository.save_artist('周杰伦',artist)
    records=[Recording.from_payload(recording(1)),Recording.from_payload(recording(2))]
    repository.save_recordings(artist,records)
    songs=group_recordings(artist,records,{})
    repository.save_grouping(artist,songs,RULE_VERSION)
    repository.save_grouping(artist,songs,RULE_VERSION)
    assert len(repository.songs(ARTIST_ID))==2
    assert len(repository.recordings(ARTIST_ID))==2
    with connect(path) as db:
        assert db.execute('SELECT count(*) FROM catalog_song_recordings').fetchone()[0]==2
