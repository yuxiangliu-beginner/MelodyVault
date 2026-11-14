"""Opt-in real Phase 2 measurements. Never downloads audio or fabricates outcomes."""
import argparse,json,threading,time
from pathlib import Path
from melodyvault.database import initialize_database,connect
from melodyvault.database.catalog import CatalogRepository
from melodyvault.database.sources import SourceRepository
from melodyvault.catalog.service import CatalogService
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.evidence import enrich_artist
from melodyvault.catalog.normalize import title_key
from melodyvault.sources.engine import SourceSearchEngine
from melodyvault.sources.worker import default_providers

ARTISTS=[('周杰伦','晴天'),('林俊杰','江南'),('周传雄','黄昏')]


def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['catalog','sources','evidence'],required=True)
    parser.add_argument('--report-root',type=Path,default=Path('.local/reports/phase2'))
    args=parser.parse_args();root=args.report_root;root.mkdir(parents=True,exist_ok=True)
    database=Path('.local/runtime/database/melodyvault.sqlite3');initialize_database(database);repo=CatalogRepository(database)
    reports=[]
    if args.stage=='catalog':
        fresh=root/'online-runtime/database/melodyvault.sqlite3';new=not fresh.exists();initialize_database(fresh)
        for name,_ in ARTISTS:
            with MusicBrainzClient(repo,threading.Event()) as client:
                started=time.perf_counter();stored=CatalogService(repo,client).search_catalog(name);elapsed=time.perf_counter()-started
                assert stored.summary['cached_catalog'] and client.requests==0
            partials=[];last=['']
            def progress(event):
                if event.stage!=last[0] or 'HTTP' in event.message:print(name,event.message,flush=True)
                last[0]=event.stage
            def partial(result):partials.append({'elapsed_seconds':time.perf_counter()-began,'songs':len(result.songs),'recordings':len(result.recordings)})
            online_repo=CatalogRepository(fresh)
            with MusicBrainzClient(online_repo,threading.Event(),force_refresh=True) as live:
                began=time.perf_counter();result=CatalogService(online_repo,live,progress,partial).search_catalog(name,stored.artist.mbid)
            assert partials and result.recordings
            online_seconds=time.perf_counter()-began
            with MusicBrainzClient(online_repo,threading.Event()) as cached:
                began=time.perf_counter();again=CatalogService(online_repo,cached).search_catalog(name);cached_seconds=time.perf_counter()-began
                assert cached.requests==0 and len(again.recordings)==len(result.recordings)
            reports.append({'artist':name,'artist_mbid':result.artist.mbid,'original_local_songs':len(stored.songs),'local_seconds':elapsed,
                'local_api_requests':0,'fresh_database_at_start':new,'online_seconds':online_seconds,'api_requests':live.requests,
                'retries':live.retries,'cache_hits':live.cache_hits,'raw_recordings':len(result.recordings),'fast_catalog_songs':len(result.songs),
                'partial_batches':partials,'second_load_seconds':cached_seconds,'second_load_api_requests':cached.requests,
                'deep_work_not_requested':True})
            write(root/'catalog-online.json',reports);print('REAL_CATALOG_OK',name,json.dumps(reports[-1],ensure_ascii=False),flush=True)
    elif args.stage=='evidence':
        for name,_ in ARTISTS:
            artist=repo.resolved_artist(name);before=repo.songs(artist.mbid);before_records={r.mbid for s in before for r in s.recordings}
            last=['']
            def progress(event):
                if last[0]!=event.stage:print(name,event.message,flush=True)
                last[0]=event.stage
            started=time.perf_counter()
            with MusicBrainzClient(repo,threading.Event()) as client:stats=enrich_artist(repo,client,artist,progress)
            elapsed=time.perf_counter()-started
            with MusicBrainzClient(repo,threading.Event()) as again:
                began=time.perf_counter();reuse=enrich_artist(repo,again,artist,progress);second=time.perf_counter()-began
                assert again.requests==0 and reuse['deep_task_reused']
            with connect(database) as db:
                negative=db.execute("SELECT count(*) FROM catalog_task_cache c JOIN catalog_artist_recordings a ON a.recording_mbid=c.entity_id WHERE a.artist_mbid=? AND c.kind='recording' AND c.status='no_work'",(artist.mbid,)).fetchone()[0]
            assert {r.mbid for s in repo.songs(artist.mbid) for r in s.recordings}==before_records
            reports.append({'artist':name,'seconds':elapsed,'api_requests':client.requests,'cache_hits':client.cache_hits,'retries':client.retries,
                'second_seconds':second,'second_api_requests':again.requests,'negative_work_cache_records':negative,'stats':stats})
            write(root/'evidence.json',reports);print('REAL_EVIDENCE_OK',name,json.dumps(reports[-1],ensure_ascii=False),flush=True)
    else:
        for name,title in ARTISTS:
            with MusicBrainzClient(repo,threading.Event()) as client:catalog=CatalogService(repo,client).search_catalog(name)
            song=next(s for s in catalog.songs if title_key(s.title)==title_key(title))
            selected=[song];selected_titles={title_key(song.title)}
            for candidate in catalog.songs:
                if title_key(candidate.title) not in selected_titles:
                    selected.append(candidate);selected_titles.add(title_key(candidate.title))
                if len(selected)==5:break
            previous=[-1]
            def progress(stats):
                if stats['searched']!=previous[0]:print(name,'SOURCE',stats['searched'],stats['total'],stats['current_song'],stats['current_provider'],flush=True)
                previous[0]=stats['searched']
            engine=SourceSearchEngine(SourceRepository(database),default_providers(),progress=progress)
            single=engine.search(catalog.artist,[song],repo.works())
            batch=engine.search(catalog.artist,selected,repo.works())
            cached=engine.search(catalog.artist,selected,repo.works())
            assert cached['api_requests']==0
            reports.append({'artist':name,'single':single,'batch_five':batch,'repeat':cached})
            write(root/'source-search.json',reports);print('REAL_SOURCES_OK',name,{k:batch[k] for k in ('searched','found_songs','license_verified','license_unverified','no_result','failed','api_requests')},flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
