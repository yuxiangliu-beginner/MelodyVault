"""Artist resolution and complete paged traversal, independent of Qt."""
from collections import Counter
import re
import time
import json

from melodyvault.catalog.models import (
    Artist, ArtistChoiceRequired, CatalogCancelled, CatalogError, CatalogResult, Progress, Recording, credit_ids,
)
from melodyvault.catalog.musicbrainz import MusicBrainzClient, check_cancel
from melodyvault.catalog.normalize import name_key, search_names
from melodyvault.catalog.enrichment import enrich_recordings
from melodyvault.catalog.grouping import RULE_VERSION, group_recordings, grouping_statistics
from melodyvault.catalog.supplement import supplement_pending
from melodyvault.catalog.review import ReviewService
from melodyvault.database.catalog import CatalogRepository, utc_now


def _quote_query(text: str) -> str:
    return '"' + re.sub(r'([+\-!(){}\[\]^"~*?:\\/&|])', r'\\\1', text) + '"'


class CatalogService:
    def __init__(self, repository: CatalogRepository, client: MusicBrainzClient, progress=None, partial=None):
        self.repository = repository
        self.client = client
        self.on_progress = progress or (lambda event: None)
        self.run_id = ""
        self.current = Progress("artist", 0, None, "准备搜索歌手")
        self.client.notice = self._notice
        self.pages = Counter()
        self.recordings: dict[str, Recording] = {}
        self.excluded_video_ids: set[str] = set()
        self.recording_ids: set[str] = set()
        self.group_ids: set[str] = set()
        self.release_ids: set[str] = set()
        self.track_ids: set[str] = set()
        self.occurrences = 0
        self.collaboration_tracks = 0
        self.on_partial = partial
        self._last_persist = (None, 0.0)
        self.catalog_only = False

    def _emit(self, event: Progress) -> None:
        self.current = event
        stage, stamp = self._last_persist
        if event.stage != stage or time.monotonic()-stamp >= 0.5 or event.processed == event.total:
            self.repository.update_run(self.run_id, event)
            self._last_persist = (event.stage, time.monotonic())
        self.on_progress(event)

    def _publish(self, artist):
        if self.catalog_only and self.on_partial:
            snapshot = ReviewService(self.repository).load(artist)
            snapshot['result'].summary.update(api_requests=self.client.requests, cache_hits=self.client.cache_hits, partial=True)
            self.on_partial(snapshot['result'])

    def saved(self, query, selected_mbid=None):
        artist = self.repository.resolved_artist(query)
        if artist is None or (selected_mbid and artist.mbid != selected_mbid):
            return None
        songs = self.repository.songs(artist.mbid)
        if not songs:
            return None
        records = [r for song in songs for r in song.recordings]
        summary = {**grouping_statistics(records, songs), 'api_requests':0, 'cache_hits':0,
                   'cached_catalog':True, 'partial':False, 'artist_mbid':artist.mbid}
        from melodyvault.database.reviews import ReviewRepository
        from melodyvault.database import connect
        events = ReviewRepository(self.repository).events(artist.mbid)
        with connect(self.repository.path) as db:
            row=db.execute("SELECT payload_json FROM catalog_task_cache WHERE kind='review_summary' AND entity_id=? AND profile='v1'",(artist.mbid,)).fetchone()
        saved_review=json.loads(row[0]) if row else None
        if saved_review and saved_review['head']==(events[-1]['id'] if events else None):
            audit_stats=saved_review['summary']
        elif events:audit_stats=ReviewService(self.repository)._build(artist,recordings=records)['result'].summary
        else:audit_stats={}
        for key in ('manually_reviewed_item_count','manually_reviewed_recording_count','stale_review_count'):
            summary[key]=audit_stats.get(key,0)
        return CatalogResult(artist, songs, summary, records)

    def search_catalog(self, query, selected_mbid=None):
        """Local first; refreshing the catalog never starts deep evidence I/O."""
        if not self.client.force_refresh:
            stored = self.saved(query, selected_mbid)
            if stored is not None:
                return stored
        self.catalog_only = True
        return self.search(query, selected_mbid)

    def _notice(self, text: str) -> None:
        self.on_progress(Progress(self.current.stage, self.current.processed, self.current.total,
                                  text, self.current.artist))

    def _resolve_artist(self, query: str, selected_mbid: str | None) -> Artist:
        previous = self.repository.resolved_artist(query)
        mbid = selected_mbid or (previous.mbid if previous else None)
        if mbid is None:
            names = search_names(query)
            expression = " OR ".join(f'{field}:{_quote_query(name)}' for name in names
                                     for field in ("artist", "alias"))
            data = self.client.get_json("artist", {"query": expression, "limit": 100})
            candidates = [Artist.from_payload(item) for item in data["artists"]]
            if not candidates:
                raise CatalogError(f"MusicBrainz 未找到歌手：{query}")
            exact = [artist for artist in candidates if artist.matches(query)]
            if len(exact) != 1:
                raise ArtistChoiceRequired(exact or candidates)
            mbid = exact[0].mbid
        verified = Artist.from_payload(self.client.get_json(f"artist/{mbid}", {"inc": "aliases"}))
        if verified.mbid != mbid:
            raise CatalogError(f"Artist lookup MBID 不一致：请求 {mbid}，收到 {verified.mbid}")
        # Non-exact names are only permitted after the user explicitly selected this identity.
        if selected_mbid is None and previous is None and not verified.matches(query):
            raise ArtistChoiceRequired([verified])
        self.repository.save_artist(query, verified)
        self._emit(Progress("artist", 1, 1, f"已核对 MusicBrainz Artist MBID：{verified.mbid}", verified))
        return verified

    def _pages(self, endpoint: str, params: dict, stage: str, label: str, artist: Artist):
        offset = 0
        seen_pages = set()
        self._emit(Progress(stage, 0, None, f"正在读取{label}第一页", artist))
        while True:
            check_cancel(self.client.cancel)
            data = self.client.get_json(endpoint, {**params, "limit": 100, "offset": offset})
            key = {"recording": "recordings", "release-group": "release-groups", "release": "releases"}[endpoint]
            items = data[key]
            total = data[f"{endpoint}-count"]
            returned_offset = data.get(f"{endpoint}-offset", offset)
            if returned_offset != offset:
                raise CatalogError(f"MusicBrainz {endpoint} 分页 offset 不符：请求 {offset}，收到 {returned_offset}")
            signature = tuple(item["id"] for item in items)
            if (not items and offset < total) or (items and signature in seen_pages):
                raise CatalogError(f"MusicBrainz {endpoint} 分页提前结束或重复（offset={offset}, total={total}），未标记完成。")
            seen_pages.add(signature)
            self.pages[stage] += 1
            yield items
            # Release pages may contain fewer than limit because of the 500-track ceiling.
            offset += len(items)
            self._emit(Progress(stage, offset, total,
                                f"{label}：{offset}/{total}；已收集 {len(self.recordings)} 个音频录音版本", artist))
            if offset >= total:
                break
            if self.pages[stage] >= 10000:
                raise CatalogError(f"MusicBrainz {endpoint} 分页超过安全上限，未标记完成。")

    def _collect(self, recording: dict, official: bool, origin: str) -> Recording | None:
        if not recording.get("id") or not recording.get("title"):
            raise CatalogError("MusicBrainz 曲目缺少 Recording MBID 或标题，未标记完成。")
        self.recording_ids.add(recording["id"])
        if recording.get("video") is True:
            self.excluded_video_ids.add(recording["id"])
            return None
        self.occurrences += 1
        incoming = Recording.from_payload(recording, official, origin)
        if incoming.mbid in self.recordings:
            self.recordings[incoming.mbid].merge(incoming)
        else:
            self.recordings[incoming.mbid] = incoming
        return self.recordings[incoming.mbid]

    def _read_releases(self, artist: Artist, field: str, stage: str, label: str) -> None:
        params = {field: artist.mbid, "status": "official", "inc": "recordings+artist-credits+release-groups"}
        for releases in self._pages("release", params, stage, label, artist):
            changed = {}
            for release in releases:
                if (release.get("status") or "").casefold() != "official":
                    raise CatalogError(f"MusicBrainz 返回非正式发行 {release['id']}，与请求筛选不符。")
                self.release_ids.add(release["id"])
                if release.get("release-group"):
                    self.group_ids.add(release["release-group"]["id"])
                for medium in release.get("media", []):
                    tracks = medium.get("tracks", [])
                    if medium.get("track-count", len(tracks)) > len(tracks):
                        raise CatalogError(f"MusicBrainz 正式发行 {release['id']} 音轨列表不完整，未标记完成。")
                    for track in tracks:
                        recording = dict(track.get("recording") or {})
                        # Explicit recording OR track performer credit supports collaborations.
                        credits = track.get("artist-credit") or recording.get("artist-credit") or release.get("artist-credit") or []
                        if artist.mbid not in credit_ids(credits) | credit_ids(recording.get("artist-credit") or []):
                            continue
                        recording.setdefault("title", track.get("title"))
                        if not recording.get("artist-credit"):
                            recording["artist-credit"] = credits
                        if recording.get("length") is None:
                            recording["length"] = track.get("length")
                        song = self._collect(recording, True, stage)
                        if song:
                            changed[song.mbid] = song
                            self.track_ids.add(track.get("id") or f'{release["id"]}:{medium.get("position")}:{track.get("position")}')
                            if len(credit_ids(credits) | credit_ids(song.credits)) > 1:
                                self.collaboration_tracks += 1
            self.repository.save_recordings(artist, list(changed.values()))
            self.repository.save_releases(artist, releases)
            self._publish(artist)

    def search(self, query: str, selected_mbid: str | None = None) -> CatalogResult:
        query = query.strip()
        if not query:
            raise CatalogError("请输入歌手名字。")
        self.run_id = self.repository.begin_run(query)
        try:
            self._emit(Progress("artist", 0, None, "通过 MusicBrainz 搜索歌手并核对别名和 MBID"))
            artist = self._resolve_artist(query, selected_mbid)
            for recordings in self._pages("recording", {"artist": artist.mbid, "inc": "artist-credits+isrcs"},
                                          "recordings", "歌手录音", artist):
                changed = {}
                for recording in recordings:
                    song = self._collect(recording, False, "recordings")
                    if song:
                        changed[song.mbid] = song
                self.repository.save_recordings(artist, list(changed.values()))
                self._publish(artist)
            for groups in self._pages("release-group", {"artist": artist.mbid, "inc": "artist-credits"},
                                      "release_groups", "后台发行组元数据", artist):
                self.group_ids.update(group["id"] for group in groups)
                self.repository.save_groups(artist, groups)
            self._read_releases(artist, "artist", "official_releases", "正式发行曲目")
            self._read_releases(artist, "track_artist", "collaboration_releases", "合作/合辑中的相关曲目")
            check_cancel(self.client.cancel)
            self.repository.finalize_membership(artist, set(self.recordings))
            supplement_stats = {}
            if not self.catalog_only:
                from melodyvault.catalog.evidence import enrich_artist
                supplement_stats = enrich_artist(self.repository, self.client, artist, self._emit)
            check_cancel(self.client.cancel)
            self._emit(Progress('grouping', 0, None, '按 Work / ISRC / 发行曲目证据建立歌曲与录音分层；不按同名强制合并', artist))
            recordings = self.repository.recordings(artist.mbid)
            automatic = group_recordings(artist, recordings, self.repository.works())
            check_cancel(self.client.cancel)
            reviewed=ReviewService(self.repository).load(artist,recordings,automatic)
            songs=reviewed['result'].songs
            summary = {
                "artist_mbid": artist.mbid, "artist_name": artist.name, "recording_count": len(recordings),
                "distinct_title_count": len({name_key(recording.title) for recording in recordings}),
                "official_recording_count": sum(recording.official for recording in recordings),
                "collaboration_recording_count": sum(len(credit_ids(recording.credits)) > 1 for recording in recordings),
                "all_recording_ids_seen": len(self.recording_ids), "excluded_video_recordings": len(self.excluded_video_ids),
                "release_group_count": len(self.group_ids), "official_release_count": len(self.release_ids),
                "related_track_count": len(self.track_ids), "duplicate_occurrences_removed": self.occurrences - len(self.recordings),
                "pages": dict(self.pages), "api_requests": self.client.requests,
                "cache_hits": self.client.cache_hits, "retries": self.client.retries,
                "run_id": self.run_id, "completed_at": utc_now(),
                "coverage": "保留全部原始录音；有证据的作品归为 Song，无法确定身份的记录独立保留待确认。同名不等于同一作品，社区目录不保证完整。",
                **grouping_statistics(recordings, songs),
                **supplement_stats,
                'manually_reviewed_item_count':reviewed['result'].summary['manually_reviewed_item_count'],
                'manually_reviewed_recording_count':reviewed['result'].summary['manually_reviewed_recording_count'],
                'stale_review_count':reviewed['result'].summary['stale_review_count'],
            }
            self.repository.finish_run(self.run_id, "completed", summary=summary)
            self._emit(Progress("complete", len(recordings), len(recordings),
                                f"目录处理完成：原始录音 {len(recordings)}；已核实独立歌曲 {summary['independent_song_count']}；待确认条目 {summary['pending_song_count']}；已保存到 SQLite。", artist))
            return CatalogResult(artist, songs, summary, recordings)
        except ArtistChoiceRequired as error:
            self.repository.finish_run(self.run_id, "needs_selection", str(error))
            raise
        except CatalogCancelled as error:
            self.repository.finish_run(self.run_id, "cancelled", str(error))
            raise
        except Exception as error:
            self.repository.finish_run(self.run_id, "failed", str(error))
            raise
