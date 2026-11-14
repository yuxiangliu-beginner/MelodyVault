"""Opt-in live 30-song benchmark. Never resets production settings or catalog.

Uses a fresh SQLite backup; no English song or generated audio is counted as a
Chinese success. Uncertain rights fail closed. Media is fetched only by the
production DownloadManager after its complete fresh eligibility check.
"""
import argparse,json,sqlite3,threading,time
from pathlib import Path
from dataclasses import asdict
from melodyvault.database import initialize_database
from melodyvault.database.catalog import CatalogRepository
from melodyvault.database.sources import SourceRepository
from melodyvault.database.discovery import DiscoveryRepository
from melodyvault.database.downloads import DownloadRepository
from melodyvault.discovery.service import SourceDiscoveryService
from melodyvault.catalog.models import Artist
from melodyvault.catalog.normalize import search_names
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.search.models import SearchRequest
from melodyvault.search.services import UnifiedSearchEngine
from melodyvault.sources.models import SourceQuery
from melodyvault.sources.engine import SourceSearchEngine
from melodyvault.sources.http import SourceHTTP
from melodyvault.sources.worker import default_providers
from melodyvault.providers.ccmixter import CCMixterProvider
from melodyvault.downloads.eligibility import DownloadEligibilityService
from melodyvault.downloads.manager import DownloadManager
from melodyvault.downloads.models import DownloadSettings


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true')
    parser.add_argument('--execute-authorized-downloads',action='store_true')
    parser.add_argument('--only-native',action='store_true',help='Supplemental native-credit/version regression; not a 30-song run')
    parser.add_argument('--report-dir',type=Path,default=Path('.local/reports/phase3b1/coverage'))
    args=parser.parse_args()
    if not args.live:raise SystemExit('Use --live to explicitly run real public API requests')
    root=args.report_dir.resolve();root.mkdir(parents=True,exist_ok=True);path=root/'qa.sqlite3'
    if path.exists():raise SystemExit('Use a new report directory; existing QA is preserved')
    with sqlite3.connect('.local/runtime/database/melodyvault.sqlite3') as src,sqlite3.connect(path) as dst:src.backup(dst)
    initialize_database(path);repo=CatalogRepository(path);registry=DiscoveryRepository(path);downloads=DownloadRepository(path)
    reports={'songs':[],'started_at':time.time(),'notes':['All downloaded audio must pass the production eligibility service. No general web search key configured.']}
    def save():(root/'coverage.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    service=SourceDiscoveryService(registry)
    reports['compiled_checks']=service.initialize_compiled();save()
    data=json.loads(Path('tests/fixtures/phase3b1_chinese_songs.json').read_text(encoding='utf-8'))
    if args.only_native:data=[g for g in data if g.get('native_upload_id')]
    settings=DownloadSettings(directory=str(root/'music'),automatic_download=args.execute_authorized_downloads,max_concurrent=1)
    downloads.save_settings(settings)
    with MusicBrainzClient(repo,threading.Event(),True,max_attempts=3) as mb:
        engine=UnifiedSearchEngine(repo,mb)
        for group in data:
            for title in group['titles']:
                start=time.perf_counter();before=mb.requests
                entry={'artist':group['artist'],'title':title,'metadata_candidates':[],'eligibility':[],'downloads':[]}
                artist=Artist('benchmark:'+group['artist'],group['artist'],tuple(group['aliases']))
                target=None;selected=None
                try:
                    if not group.get('native_upload_id'):
                        result=engine.search(SearchRequest(title,'song',artist_hint=group['artist'],force_online=True))
                        entry['metadata_candidates']=[c.to_dict() for c in result.songs];entry['metadata_errors']=result.errors
                        exact=[c for c in result.songs if c.title_exact and c.artist.matches(group['artist'])]
                        # This benchmark explicitly selects and records one MBID,
                        # rather than importing or merging candidate identities.
                        if exact:
                            selected=sorted(exact,key=lambda c:(c.version not in {'studio','unknown'},c.recording_mbid))[0]
                            artist=selected.artist
                            target={'song_id':'benchmark:'+artist.mbid+':'+title,'recording_id':selected.recording_mbid,'namespace':'musicbrainz',
                                'artist':artist.payload,'title':title,'recording_title':selected.title,'version':selected.version,
                                'duration':selected.length_ms/1000 if selected.length_ms else None,'isrcs':selected.payload.get('isrcs',[]),
                                'urls':[],'confirmed':True,'recording_payload':selected.payload,'work_ids':list(selected.work_ids)}
                            entry['selected_recording']=selected.recording_mbid
                    query=SourceQuery(artist.mbid,'benchmark:'+group['artist']+':'+title,group['artist'],title,
                        list(dict.fromkeys([artist.name,group['artist'],*group['aliases'],*artist.aliases]))[:10],
                        list(search_names(title)),[selected.version] if selected else [group['version']] if group.get('version') else [],
                        [selected.length_ms] if selected and selected.length_ms else [],[selected.recording_mbid] if selected else [])
                    stats=SourceSearchEngine(SourceRepository(path),default_providers()).search_queries(artist,[query],force=True)
                    entry['sources']=stats
                    if group.get('native_upload_id'):
                        # Refresh authoritative native IDs, preserving BOTH format candidates.
                        with SourceHTTP() as http:
                            native=CCMixterProvider().get_metadata(group['native_upload_id'],http)
                        entry['native_files']=[asdict(c) for c in native]
                        if native:
                            c=native[0];target={'song_id':'ccmixter:'+group['native_upload_id'],'recording_id':'ccmixter:'+group['native_upload_id'],
                                'namespace':'ccmixter','source_page_url':c.page_url,'artist':{'id':'ccmixter:'+c.performer,'name':c.performer},
                                'title':c.title,'version':c.version,'duration':c.duration_seconds,'confirmed':True,'recording_payload':{},'work_ids':[]}
                    candidates=stats['jobs'][0]['candidates'] if stats['jobs'] else []
                    if target:
                        with SourceHTTP() as http:
                            verifier=DownloadEligibilityService(http,mb)
                            for raw in candidates:
                                try:
                                    c=verifier.verify(raw,target);entry['eligibility'].append(c.to_dict())
                                    if args.execute_authorized_downloads and verifier.allowed(c):
                                        jid=downloads.enqueue(target,settings,candidate=raw);DownloadManager(downloads).run()
                                        entry['downloads'].append(downloads.get(jid))
                                except Exception as e:entry['eligibility'].append({'error':str(e),'provider':raw['provider'],'decision':'VERIFICATION_FAILED'})
                    entry['discovery']=service.discover(group['artist'],title,group['aliases'],max_checks=1)
                except Exception as e:entry['error']=f'{type(e).__name__}: {e}'
                entry['musicbrainz_requests']=mb.requests-before;entry['seconds']=time.perf_counter()-start
                reports['songs'].append(entry);save()
                print('LIVE',len(reports['songs']),group['artist'],title,'MB',entry['musicbrainz_requests'],
                    'candidates',entry.get('sources',{}).get('found_songs',0),'error',entry.get('error',''),flush=True)
        reports['musicbrainz_total_requests']=mb.requests
        reports['musicbrainz_retries']=mb.retries
    reports['registry']=registry.rows();reports['finished_at']=time.time();save()
    print('LIVE_BENCHMARK_FINISHED',len(reports['songs']),len(reports['registry']),flush=True)


if __name__=='__main__':main()
