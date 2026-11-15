"""Live open-audio pipeline control in a new, isolated database.

This Spanish-language Commons recording is NOT counted as Chinese coverage.
"""
import argparse,json,sqlite3,time
from pathlib import Path
from melodyvault.database import initialize_database
from melodyvault.database.downloads import DownloadRepository
from melodyvault.downloads.models import DownloadSettings
from melodyvault.downloads.targets import search_values
from melodyvault.providers.commons import CommonsProvider
from melodyvault.search.pipeline import UnifiedMusicSearchService


def main():
    p=argparse.ArgumentParser();p.add_argument('--execute-downloads',action='store_true')
    p.add_argument('--report-dir',type=Path,required=True);args=p.parse_args()
    if not args.execute_downloads:raise SystemExit('Explicit --execute-downloads required')
    root=args.report_dir.resolve();root.mkdir(parents=True,exist_ok=True);db=root/'qa.sqlite3'
    if db.exists():raise SystemExit('Use a fresh directory')
    with sqlite3.connect('.local/runtime/database/melodyvault.sqlite3') as src,sqlite3.connect(db) as dst:src.backup(dst)
    initialize_database(db);repo=DownloadRepository(db)
    settings=DownloadSettings(directory=str(root/'music'),automatic_download=True,max_concurrent=1)
    repo.save_settings(settings)
    target={'song_id':'commons:145596320','recording_id':'commons:145596320','namespace':'commons',
        'source_page_url':'https://commons.wikimedia.org/wiki/File:Conillet_de_Vellut,_on_t%27has_perdut.wav',
        'artist':{'id':'commons:creator:Jose_Galeote','name':'José Galeote'},
        'title':"Conillet de Vellut, on t'has perdut",'version':'unknown','duration':130.04497916666668,
        'confirmed':True,'recording_payload':{'id':'commons:145596320','title':"Conillet de Vellut, on t'has perdut",'length':130045,
        'artist-credit':[{'artist':{'id':'commons:creator:Jose_Galeote','name':'José Galeote'}}]},'work_ids':[]}
    artist,song=search_values(target)
    # The test deliberately selects a provider-native identity. No MBID is fabricated.
    started=time.perf_counter()
    result=UnifiedMusicSearchService(db,providers=[CommonsProvider()]).run(artist,song,explicit_selection=True,native_target=target)
    result['elapsed_seconds']=time.perf_counter()-started;result['control_language']='Spanish'
    (root/'pipeline.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PIPELINE_CONTROL',result['status'],result['candidate_count'],flush=True)
    if result['status']!='COMPLETED':raise SystemExit('Pipeline did not complete; inspect pipeline.json')


if __name__=='__main__':main()
