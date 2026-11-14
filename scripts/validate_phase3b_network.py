"""Explicit real downloads to an isolated QA library; default refuses execution.

MP3: real MusicBrainz → selected Recording → SourceSearchEngine → official ISRC
verification → paused transfer → new manager/resume → validated original file.
WAV: explicitly identified Commons-native open recording, not a fabricated MBID.
"""
import argparse,json,sqlite3,threading,time
from pathlib import Path
from dataclasses import asdict
from melodyvault.database import initialize_database,connect
from melodyvault.database.catalog import CatalogRepository
from melodyvault.database.sources import SourceRepository
from melodyvault.database.downloads import DownloadRepository
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.search.services import UnifiedSearchEngine
from melodyvault.search.models import SearchRequest
from melodyvault.search.selection import SongSelectionService
from melodyvault.sources.engine import SourceSearchEngine
from melodyvault.sources.http import SourceHTTP
from melodyvault.providers.commons import CommonsProvider
from melodyvault.providers.archive import ArchiveProvider
from melodyvault.providers.jamendo import JamendoProvider
from melodyvault.downloads.targets import from_song
from melodyvault.downloads.models import DownloadSettings
from melodyvault.downloads.manager import DownloadManager

KEVIN='8292bf44-2dd1-4bad-8019-276ec38f28e7'
SILENT='56c6eca2-5953-45d2-a7c2-54d6ab5833ef'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute-downloads',action='store_true');parser.add_argument('--report-dir',type=Path,default=Path('.local/reports/phase3b/network'));args=parser.parse_args()
    if not args.execute_downloads:raise SystemExit('Requires explicit --execute-downloads for authorized open-audio QA. Production settings remain off.')
    root=args.report_dir.resolve();root.mkdir(parents=True,exist_ok=True);path=root/'qa.sqlite3'
    if path.exists():raise SystemExit('Use a new directory; will not overwrite QA library or audio')
    with sqlite3.connect('.local/runtime/database/melodyvault.sqlite3') as src,sqlite3.connect(path) as dst:src.backup(dst)
    initialize_database(path);repo=CatalogRepository(path);downloads=DownloadRepository(path);reports={}
    def save():(root/'network.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    request=SearchRequest('Silent Night','song',artist_hint='Kevin MacLeod',artist_ids=(KEVIN,),force_online=True)
    with MusicBrainzClient(repo,threading.Event(),True,notice=lambda m:print(m,flush=True)) as client:
        result=UnifiedSearchEngine(repo,client).search(request)
        candidate=next(c for c in result.songs if c.recording_mbid==SILENT)
        catalog=SongSelectionService(repo,client).confirm(candidate,request,'Silent Night')
        reports['identity']={'recording_mbid':candidate.recording_mbid,'artist_mbid':candidate.artist.mbid,'api_requests':client.requests,'query_seconds':result.elapsed_seconds}
    target=from_song(catalog.artist,catalog.songs[0],True)
    providers=[ArchiveProvider(),CommonsProvider(),JamendoProvider()]
    stats=SourceSearchEngine(SourceRepository(path),providers).search(catalog.artist,catalog.songs,repo.works(),force=True)
    reports['mp3_source_search']=stats;save()
    raw=next(c for c in stats['jobs'][0]['candidates'] if c['provider']=='commons' and '.mp3' in c.get('audio_url',''))
    settings=DownloadSettings(directory=str(root/'music'),automatic_download=True,max_concurrent=1,speed_limit=128*1024)
    downloads.save_settings(settings);jid=downloads.enqueue(target,settings,candidate=raw)
    manager=DownloadManager(downloads);paused=[False]
    def on_progress():
        row=downloads.get(jid)
        if not paused[0] and row['state']=='DOWNLOADING' and row['bytes_received']>=128*1024:
            paused[0]=True;manager.stop(jid,'PAUSED')
    manager.progress=on_progress;start=time.perf_counter();manager.run()
    row=downloads.get(jid);reports['paused']={k:row[k] for k in ('state','bytes_received','total_bytes','etag','last_modified','part_path')};save()
    assert row['state']=='PAUSED' and Path(row['part_path']).stat().st_size>0,row
    settings.speed_limit=0;downloads.save_settings(settings)
    # New manager object emulates reconstruction after an application restart.
    resumed=DownloadManager(downloads);resumed.recover();resumed.resume(jid);resumed.run()
    row=downloads.get(jid);reports['mp3']={**row,'total_seconds':time.perf_counter()-start,'resume_evidence':[e for e in downloads.evidence_rows(jid) if e['step']=='resume']};save()
    assert row['state']=='COMPLETED',row['reason']
    duplicate=downloads.enqueue(target,settings,candidate=raw);resumed.run();reports['duplicate']=downloads.get(duplicate);save()
    assert reports['duplicate']['state']=='COMPLETED' and reports['duplicate']['result']['reused']
    # A second real, complete, explicitly licensed WAV file. Native Commons ID
    # does not enter catalog_recordings and is never called a MusicBrainz match.
    with SourceHTTP() as http:
        data=http.json('https://commons.wikimedia.org/w/api.php',{'action':'query','format':'json','formatversion':2,'pageids':'145596320','prop':'imageinfo','iiprop':'url|mime|size|sha1|metadata|extmetadata','iiextmetadatalanguage':'en','maxlag':5})
    page=data['query']['pages'][0];info=page['imageinfo'][0];title="Conillet de Vellut, on t'has perdut"
    wav_target={'song_id':'commons:145596320','recording_id':'commons:145596320','namespace':'commons','source_page_url':info['descriptionurl'],
        'artist':{'id':'commons:creator:Jose_Galeote','name':'José Galeote'},'title':title,'version':'unknown','duration':130.04497916666668,'confirmed':True,
        'recording_payload':{'id':'commons:145596320','title':title,'length':130045,'artist-credit':[{'artist':{'id':'commons:creator:Jose_Galeote','name':'José Galeote'}}]},'work_ids':[]}
    from melodyvault.downloads.targets import search_values
    artist,song=search_values(wav_target)
    wav_search=SourceSearchEngine(SourceRepository(path),[CommonsProvider()]).search(artist,[song],{},force=True)
    reports['wav_source_search']=wav_search;save()
    wav_raw=next(c for c in wav_search['jobs'][0]['candidates'] if c['external_id']=='145596320')
    wav=downloads.enqueue(wav_target,settings,candidate=wav_raw);start=time.perf_counter();resumed.run();wav_row=downloads.get(wav)
    reports['wav']={**wav_row,'seconds':time.perf_counter()-start};reports['summary']=downloads.summary();save()
    assert wav_row['state']=='COMPLETED',wav_row['reason']
    print('REAL_DOWNLOAD_OK',reports['mp3']['result'],reports['wav']['result'],flush=True)


if __name__=='__main__':main()
