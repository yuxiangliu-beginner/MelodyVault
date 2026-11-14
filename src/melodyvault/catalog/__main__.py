"""Reproducible live integration using the same desktop service."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import signal
import threading
from melodyvault.catalog.models import ArtistChoiceRequired, CatalogCancelled
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.service import CatalogService
from melodyvault.config import load_settings
from melodyvault.database import initialize_database
from melodyvault.database.catalog import CatalogRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch real MusicBrainz metadata; no audio downloads")
    parser.add_argument("--artist", required=True)
    parser.add_argument("--artist-mbid", help="Explicit user-selected identity when ambiguous")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument('--evidence-only',action='store_true',help='Only enrich an already saved artist; never refresh its catalog')
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    settings = load_settings(data_root=args.data_dir)
    settings.prepare()
    initialize_database(settings.database_path)
    cancel = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: cancel.set())
    try:
        repository = CatalogRepository(settings.database_path)
        with MusicBrainzClient(repository, cancel, args.refresh) as client:
            service=CatalogService(repository,client,lambda p:print(p.message,flush=True))
            if args.evidence_only:
                from melodyvault.catalog.evidence import enrich_artist
                from melodyvault.catalog.review import ReviewService
                artist=repository.resolved_artist(args.artist)
                if artist is None:raise ValueError('请先获取并保存歌手目录')
                metrics=enrich_artist(repository,client,artist,lambda p:print(p.message,flush=True))
                result=ReviewService(repository).load(artist)['result']
                result.summary.update(metrics,api_requests=client.requests,cache_hits=client.cache_hits)
            else:result=service.search_catalog(args.artist,args.artist_mbid)
        report = {"summary": result.summary, "artist": result.artist.payload,
                  "songs": [asdict(song) for song in result.songs],
                  "recordings": [asdict(recording) for recording in result.recordings]}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=sorted), encoding="utf-8")
        print(json.dumps(result.summary, ensure_ascii=False, indent=2), flush=True)
        return 0
    except ArtistChoiceRequired as error:
        print(str(error), flush=True)
        for artist in error.candidates:
            print(artist.label, flush=True)
        return 2
    except CatalogCancelled as error:
        print(str(error), flush=True)
        return 130
    except Exception as error:
        print(f"{type(error).__name__}: {error}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
