"""Two-artist production regression; records facts, never creates human decisions."""
import argparse,json,threading,time
from pathlib import Path
from hashlib import sha256
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.service import CatalogService
from melodyvault.catalog.grouping import group_recordings,grouping_statistics,identity_work_ids
from melodyvault.database import initialize_database,connect
from melodyvault.database.catalog import CatalogRepository


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,default=Path('.local/runtime'));parser.add_argument('--report-dir',type=Path,default=Path('.local/reports/phase1-review'))
    args=parser.parse_args();args.report_dir.mkdir(parents=True,exist_ok=True)
    repository=CatalogRepository(args.data_dir/'database/melodyvault.sqlite3');initialize_database(repository.path)
    baseline=json.loads((args.report_dir/'baseline.json').read_text(encoding='utf-8'))
    old_by_id={item['artist']['id']:item['stats'] for item in baseline}
    reports=[]
    for name in ('林俊杰','周杰伦'):
        last=[''];started=time.monotonic()
        def progress(event):
            if event.stage!=last[0] or event.processed%50==0 or event.processed==event.total or 'HTTP ' in event.message:
                print(name,event.message,flush=True)
            last[0]=event.stage
        with MusicBrainzClient(repository,threading.Event()) as client:
            result=CatalogService(repository,client,progress).search(name)
        records=repository.recordings(result.artist.mbid)
        automatic=group_recordings(result.artist,records,repository.works())
        stats=grouping_statistics(records,automatic)
        assigned=[r.mbid for song in result.songs for r in song.recordings]
        assert len(assigned)==len(set(assigned))==len(records)
        before=old_by_id[result.artist.mbid]
        pending_records=[r for song in automatic if song.pending_confirmation for r in song.recordings]
        report={'artist':name,'artist_mbid':result.artist.mbid,'before':before,'automatic_after':stats,
            'effective_after':result.summary,'pending_change':stats['pending_song_count']-before['pending_song_count'],
            'pending_without_work_evidence':sum(not identity_work_ids(r) for r in pending_records),
            'pending_multiple_work_or_conflict':sum(len(identity_work_ids(r))>1 for r in pending_records),
            'elapsed_seconds':time.monotonic()-started}
        (args.report_dir/(result.artist.mbid+'-regression.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        reports.append(report)
        print('ARTIST_REGRESSION_OK',name,'verified',stats['independent_song_count'],'pending',stats['pending_song_count'],'change',report['pending_change'],flush=True)
    hashes=json.loads((args.report_dir/'baseline-raw-hashes.json').read_text(encoding='utf-8'))
    with connect(repository.path) as db:
        actual={row[0]:sha256(row[1].encode()).hexdigest() for row in db.execute('SELECT mbid,payload_json FROM catalog_recordings')}
        assert all(actual.get(key)==value for key,value in hashes.items())
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        audit_count=db.execute('SELECT count(*) FROM catalog_review_events').fetchone()[0]
        history={row[0]:row[1] for row in db.execute('SELECT version,checksum FROM schema_migrations WHERE version<=3')}
    import sqlite3
    with sqlite3.connect(args.report_dir/'before-review.sqlite3') as db:
        assert history=={row[0]:row[1] for row in db.execute('SELECT version,checksum FROM schema_migrations')}
    summary={'success':True,'original_recording_hashes_preserved':len(hashes),'total_recordings':len(actual),
        'schema_1_to_3_checksums_preserved':True,'integrity_check':'ok','foreign_key_check':'ok',
        'production_review_events':audit_count,'artists':reports}
    (args.report_dir/'regression-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('TWO_ARTIST_REGRESSION_OK',len(hashes),'original payloads preserved',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
