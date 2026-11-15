"""Real A→B→C control, using an explicitly selected MusicBrainz recording.

The permitted English MP3 control is not counted in Chinese coverage. The seed
is the previous isolated QA library; the production library is never edited.
"""
import argparse,json,sqlite3,threading,time
from pathlib import Path
from melodyvault.database import initialize_database
from melodyvault.database.catalog import CatalogRepository
from melodyvault.database.downloads import DownloadRepository
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.downloads.models import DownloadSettings
from melodyvault.providers.commons import CommonsProvider
from melodyvault.search.models import SearchRequest
from melodyvault.search.services import UnifiedSearchEngine
from melodyvault.search.selection import SongSelectionService
from melodyvault.search.pipeline import UnifiedMusicSearchService

RECORDING='56c6eca2-5953-45d2-a7c2-54d6ab5833ef'


def main():
    p=argparse.ArgumentParser();p.add_argument('--execute-downloads',action='store_true');p.add_argument('--report-dir',type=Path,required=True);a=p.parse_args()
    if not a.execute_downloads:raise SystemExit('Explicit --execute-downloads required')
    root=a.report_dir.resolve();root.mkdir(parents=True,exist_ok=True);db=root/'qa.sqlite3'
    if db.exists():raise SystemExit('Use a new directory')
    seed=Path('.local/reports/phase3b1/authorized-control/qa.sqlite3')
    if not seed.exists():raise SystemExit('Prior authorized QA metadata library is unavailable')
    with sqlite3.connect(seed) as src,sqlite3.connect(db) as dst:src.backup(dst)
    initialize_database(db)
    # Remove file references in this disposable copy only, forcing an actual
    # new transfer instead of reusing the previous QA files.
    with sqlite3.connect(db) as c:c.execute('DELETE FROM downloaded_files')
    repository=CatalogRepository(db);downloads=DownloadRepository(db)
    downloads.save_settings(DownloadSettings(directory=str(root/'music'),automatic_download=True,max_concurrent=1))
    request=SearchRequest('Silent Night','song',artist_hint='Kevin MacLeod',local_only=True)
    started=time.perf_counter()
    with MusicBrainzClient(repository,threading.Event()) as client:
        search=UnifiedSearchEngine(repository,client).search(request)
        match=next((v for v in search.songs if v.recording_mbid==RECORDING),None)
        if match is None:raise SystemExit('Selected MusicBrainz recording is absent')
        catalog=SongSelectionService(repository,client).confirm(match,request,'Silent Night')
    result=UnifiedMusicSearchService(db,providers=[CommonsProvider()]).run(catalog.artist,catalog.songs[0],explicit_selection=True)
    report={'input':'Kevin MacLeod Silent Night','identity_search_scope':search.scope,'identity_candidates':len(search.songs),
        'explicitly_selected_mbid':RECORDING,'language':'English','elapsed_seconds':time.perf_counter()-started,'pipeline':result}
    (root/'pipeline.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('MUSICBRAINZ_PIPELINE',result['status'],result['candidate_count'],flush=True)
    if result['status']!='COMPLETED':raise SystemExit('See pipeline.json for actual failure')


if __name__=='__main__':main()
