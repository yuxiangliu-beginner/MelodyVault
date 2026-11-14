"""Real source searches for five distinct titles per saved artist; never download."""
import argparse,json,sqlite3,threading
from pathlib import Path
from melodyvault.database import initialize_database
from melodyvault.database.catalog import CatalogRepository
from melodyvault.database.sources import SourceRepository
from melodyvault.sources.engine import SourceSearchEngine
from melodyvault.sources.http import SourceHTTP
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.normalize import title_key
from melodyvault.downloads.targets import from_song
from melodyvault.downloads.eligibility import DownloadEligibilityService
from melodyvault.downloads.manager import DownloadManager


def main():
    p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,default=Path('.local/reports/phase3b/artists'));args=p.parse_args();root=args.report_dir;root.mkdir(parents=True,exist_ok=True);path=root/'qa.sqlite3'
    if path.exists():raise SystemExit('Use a new report directory; no overwrites')
    with sqlite3.connect('.local/runtime/database/melodyvault.sqlite3') as src,sqlite3.connect(path) as dst:src.backup(dst)
    initialize_database(path);repo=CatalogRepository(path);reports=[]
    for name,title in [('周杰伦','晴天'),('林俊杰','江南'),('周传雄','黄昏')]:
        artist=repo.resolved_artist(name);songs=repo.songs(artist.mbid)
        preferred=sorted([s for s in songs if title_key(s.title)==title_key(title)],key=lambda s:(s.pending_confirmation,not bool(s.primary_recording_mbid)))
        selected=[];keys=set()
        for song in [*preferred,*sorted(songs,key=lambda s:(s.pending_confirmation,not bool(s.primary_recording_mbid),s.title))]:
            if title_key(song.title) in keys:continue
            selected.append(song);keys.add(title_key(song.title))
            if len(selected)==5:break
        stats=SourceSearchEngine(SourceRepository(path),DownloadManager._default_providers()).search(artist,selected,repo.works(),force=True)
        by_id={s.id:s for s in selected};decisions=[]
        with SourceHTTP() as http,MusicBrainzClient(repo,threading.Event()) as mb:
            service=DownloadEligibilityService(http,mb)
            for job in stats['jobs']:
                target=from_song(artist,by_id[job['song_id']])
                for raw in job['candidates']:
                    try:decisions.append(service.verify(raw,target).to_dict())
                    except Exception as error:decisions.append({'provider':raw['provider'],'external_id':raw['external_id'],'error_type':type(error).__name__,'evidence':{'decision':'VERIFICATION_FAILED'}})
        report={'artist':name,'artist_mbid':artist.mbid,'distinct_titles':len(selected),'source':stats,'eligibility':decisions,
            'candidate_files':sum(len(j['candidates']) for j in stats['jobs']),'songs_with_candidates':stats['found_songs'],
            'source_metadata_license_verified':stats['license_verified'],'download_license_verified':sum(c.get('license_status')=='LICENSE_VERIFIED' for c in decisions),
            'eligible_downloads':sum(c.get('evidence',{}).get('decision')=='READY' for c in decisions),'downloads_executed':0}
        reports.append(report);(root/'artists.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
        print('REAL_ARTIST_SOURCES',name,'songs',len(selected),'candidates',report['candidate_files'],'licenses',report['download_license_verified'],'eligible',report['eligible_downloads'],'no_result',stats['no_result'],'failed',stats['failed'],'requests',stats['api_requests'],flush=True)


if __name__=='__main__':main()
