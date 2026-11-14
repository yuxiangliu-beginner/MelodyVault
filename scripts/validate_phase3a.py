"""Real metadata validation. Discovery never writes human target selections."""
import argparse,json,threading,time
from pathlib import Path
from melodyvault.database import initialize_database
from melodyvault.database.catalog import CatalogRepository
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.search.services import UnifiedSearchEngine
from melodyvault.search.models import SearchRequest,identity_key

CASES=[('周杰伦','artist'),('林俊杰','artist'),('周传雄','artist'),('晴天','song'),('江南','song'),
       ('周杰伦 晴天','smart'),('林俊杰 江南','smart'),('Jay Chou Qing Tian','smart'),
       ('不存在的歌手','artist'),('不存在的歌曲','song'),('MelodyVaultNoSuchArtist82D57F20261113','artist'),('MelodyVaultNoSuchSong82D57F20261113','song')]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--online',action='store_true');parser.add_argument('--output',type=Path,default=Path('.local/reports/phase3a/search-real.json'));args=parser.parse_args()
    path=Path('.local/runtime/database/melodyvault.sqlite3');initialize_database(path);repo=CatalogRepository(path);reports=[]
    for query,mode in CASES:
        request=SearchRequest(query,mode,local_only=not args.online,force_online=args.online)
        with MusicBrainzClient(repo,threading.Event(),args.online,notice=lambda m:print(m,flush=True)) as client:
            result=UnifiedSearchEngine(repo,client).search(request)
        data=result.to_dict();data['distinct_performers']=len({c.artist.mbid for c in result.songs});data['exact_song_count']=sum(c.title_exact for c in result.songs)
        data['exact_artists']=[a.mbid for a in result.artists if identity_key(query) in {identity_key(n) for n in (a.name,*a.aliases)}]
        if args.online:
            with MusicBrainzClient(repo,threading.Event()) as cached:
                repeat=UnifiedSearchEngine(repo,cached).search(SearchRequest(query,mode))
                data['repeat']={'seconds':repeat.elapsed_seconds,'api_requests':cached.requests,'scope':repeat.scope,'cache_hit':repeat.cache_hit,'songs':len(repeat.songs),'artists':len(repeat.artists)}
                assert cached.requests==0
        reports.append(data);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
        print('REAL_UNIFIED',query,mode,result.scope,len(result.artists),len(result.songs),data['distinct_performers'],result.api_requests,round(result.elapsed_seconds,3),result.errors,flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
