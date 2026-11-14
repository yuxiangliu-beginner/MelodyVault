"""Catalog persistence. Each page is committed; incomplete runs stay incomplete."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from hashlib import sha256
from pathlib import Path
import time
from uuid import uuid4

from melodyvault.catalog.models import Artist, Progress, Recording, Song
from melodyvault.catalog.normalize import name_key
from melodyvault.database import connect


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class CatalogRepository:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def transaction(self):
        with connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def cached_response(self, key: str, max_age: float) -> dict | None:
        with connect(self.path) as db:
            row = db.execute("SELECT payload_json, fetched_at FROM catalog_http_cache WHERE cache_key=?",
                             (key,)).fetchone()
        if row is None or time.time() - row["fetched_at"] > max_age:
            return None
        try:
            data = json.loads(row["payload_json"])
            return data if isinstance(data, dict) else None
        except ValueError:
            return None

    def cache_response(self, key: str, payload: dict) -> None:
        raw = encode(payload)
        with self.transaction() as db:
            db.execute("INSERT OR IGNORE INTO catalog_response_history VALUES (?,?,?,?)",
                       (key, sha256(raw.encode()).hexdigest(), raw, time.time()))
            db.execute("INSERT INTO catalog_http_cache VALUES (?, ?, ?) ON CONFLICT(cache_key) "
                       "DO UPDATE SET payload_json=excluded.payload_json, fetched_at=excluded.fetched_at",
                       (key, raw, time.time()))

    def save_artist(self, query: str, artist: Artist) -> None:
        with self.transaction() as db:
            db.execute("INSERT INTO catalog_artists VALUES (?, ?, ?, ?) ON CONFLICT(mbid) DO UPDATE "
                       "SET name=excluded.name, payload_json=excluded.payload_json, verified_at=excluded.verified_at",
                       (artist.mbid, artist.name, encode(artist.payload), utc_now()))
            db.execute("INSERT INTO catalog_queries VALUES (?, ?) ON CONFLICT(query_key) "
                       "DO UPDATE SET artist_mbid=excluded.artist_mbid", (name_key(query), artist.mbid))

    def resolved_artist(self, query: str) -> Artist | None:
        with connect(self.path) as db:
            row = db.execute("SELECT a.payload_json FROM catalog_queries q JOIN catalog_artists a "
                             "ON q.artist_mbid=a.mbid WHERE q.query_key=?", (name_key(query),)).fetchone()
        return Artist.from_payload(json.loads(row[0])) if row else None

    def begin_run(self, query: str) -> str:
        run_id = str(uuid4())
        with connect(self.path) as db:
            db.execute("INSERT INTO catalog_runs (id,query,status,phase,started_at) VALUES (?,?,'running','artist',?)",
                       (run_id, query, utc_now()))
        return run_id

    def update_run(self, run_id: str, progress: Progress) -> None:
        with connect(self.path) as db:
            db.execute("UPDATE catalog_runs SET phase=?,processed=?,total=?,artist_mbid=COALESCE(?,artist_mbid) WHERE id=?",
                       (progress.stage, progress.processed, progress.total,
                        progress.artist.mbid if progress.artist else None, run_id))

    def finish_run(self, run_id: str, status: str, error: str | None = None, summary: dict | None = None) -> None:
        with connect(self.path) as db:
            db.execute("UPDATE catalog_runs SET status=?,error=?,summary_json=?,finished_at=? WHERE id=?",
                       (status, error, encode(summary) if summary is not None else None, utc_now(), run_id))

    def save_recordings(self, artist: Artist, recordings: list[Recording]) -> None:
        with self.transaction() as db:
            for song in recordings:
                raw = encode(song.payload)
                # Original first-observed payloads are immutable; refreshes are snapshots.
                db.execute("INSERT OR IGNORE INTO catalog_recordings VALUES (?,?,?,?,?)",
                           (song.mbid, song.original_title, name_key(song.title), raw, utc_now()))
                db.execute("INSERT OR IGNORE INTO catalog_recording_snapshots VALUES (?,?,?,?)",
                           (song.mbid, sha256(raw.encode()).hexdigest(), raw, utc_now()))
                db.execute("INSERT INTO catalog_artist_recordings VALUES (?,?,?,?) "
                           "ON CONFLICT(artist_mbid,recording_mbid) DO UPDATE SET official=MAX(official,excluded.official),origins_json=excluded.origins_json",
                           (artist.mbid, song.mbid, int(song.official), encode(sorted(song.origins))))

    @staticmethod
    def _save_group(db, artist: Artist, group: dict) -> None:
        db.execute("INSERT INTO catalog_release_groups VALUES (?,?,?,?) ON CONFLICT(mbid) DO UPDATE SET "
                   "title=excluded.title,primary_type=excluded.primary_type,payload_json=excluded.payload_json",
                   (group["id"], group.get("title", ""), group.get("primary-type"), encode(group)))
        db.execute("INSERT OR IGNORE INTO catalog_artist_groups VALUES (?,?)", (artist.mbid, group["id"]))

    def save_groups(self, artist: Artist, groups: list[dict]) -> None:
        with self.transaction() as db:
            for group in groups:
                self._save_group(db, artist, group)

    def save_releases(self, artist: Artist, releases: list[dict]) -> None:
        with self.transaction() as db:
            for release in releases:
                group = release.get("release-group")
                if group:
                    self._save_group(db, artist, group)
                db.execute("INSERT INTO catalog_releases VALUES (?,?,?,?) ON CONFLICT(mbid) DO UPDATE SET "
                           "group_mbid=excluded.group_mbid,status=excluded.status,payload_json=excluded.payload_json",
                           (release["id"], group["id"] if group else None, release.get("status"), encode(release)))
                for medium in release.get("media", []):
                    for track in medium.get("tracks", []):
                        key = track.get("id") or f'{release["id"]}:{medium.get("position")}:{track.get("position")}'
                        db.execute("INSERT INTO catalog_tracks VALUES (?,?,?,?,?,?,?) ON CONFLICT(mbid) DO UPDATE SET "
                                   "recording_mbid=excluded.recording_mbid,title=excluded.title,payload_json=excluded.payload_json",
                                   (key, release["id"], (track.get("recording") or {}).get("id"),
                                    track.get("title") or (track.get("recording") or {}).get("title", ""),
                                    medium.get("position"), track.get("position"), encode(track)))

    def finalize_membership(self, artist: Artist, recording_ids: set[str]) -> None:
        # Preserve historical observations, including IDs absent from later API pages.
        # Only derived Song mappings may be rebuilt; never delete original recordings.
        return

    def recordings(self, artist_mbid: str) -> list[Recording]:
        with connect(self.path) as db:
            rows = db.execute("SELECT r.mbid,r.payload_json,a.official,a.origins_json,d.payload_json AS details FROM catalog_recordings r "
                              "JOIN catalog_artist_recordings a ON a.recording_mbid=r.mbid "
                              "LEFT JOIN catalog_recording_details d ON d.mbid=r.mbid WHERE a.artist_mbid=? "
                              "ORDER BY r.normalized_title,r.mbid", (artist_mbid,)).fetchall()
            tracks = db.execute("SELECT t.recording_mbid,t.payload_json AS track,r.mbid AS release_mbid,r.status,"
                                "r.payload_json AS release,g.mbid AS group_mbid,g.payload_json AS release_group,t.medium_position,t.position "
                                "FROM catalog_tracks t JOIN catalog_releases r ON r.mbid=t.release_mbid "
                                "LEFT JOIN catalog_release_groups g ON g.mbid=r.group_mbid "
                                "JOIN catalog_artist_recordings a ON a.recording_mbid=t.recording_mbid WHERE a.artist_mbid=?",
                                (artist_mbid,)).fetchall()
            identity = {}
            for row in db.execute('SELECT recording_mbid,payload_json FROM catalog_identity_evidence WHERE artist_mbid=?',(artist_mbid,)):
                identity.setdefault(row[0],[]).append(json.loads(row[1]))
        contexts = {}
        decoded_releases = {}
        decoded_groups = {}
        for row in tracks:
            if row['release_mbid'] not in decoded_releases:
                decoded_releases[row['release_mbid']] = json.loads(row['release'])
            release = decoded_releases[row['release_mbid']]
            track = json.loads(row['track'])
            if row['group_mbid'] not in decoded_groups:
                decoded_groups[row['group_mbid']] = json.loads(row['release_group']) if row['release_group'] else {}
            group = decoded_groups[row['group_mbid']]
            medium = next((m for m in release.get('media',[]) if m.get('position') == row['medium_position']), {})
            contexts.setdefault(row['recording_mbid'], []).append({
                'release_mbid': row['release_mbid'], 'release_group_mbid': row['group_mbid'],
                'medium_position': row['medium_position'], 'position': row['position'],
                'status': row['status'], 'primary_type': group.get('primary-type'),
                'secondary_types': group.get('secondary-types', []), 'release_title': release.get('title',''),
                'date': release.get('date',''), 'track_title': track.get('title',''),
                'credits': track.get('artist-credit') or release.get('artist-credit') or [],
                'track_mbid': track.get('id'),
                'medium_track_count': medium.get('track-count',len(medium.get('tracks',[]))),
            })
        result = []
        for row in rows:
            song = Recording.from_payload(json.loads(row['payload_json']), bool(row['official']))
            song.origins = set(json.loads(row['origins_json']))
            song.details = json.loads(row['details']) if row['details'] else {}
            song.contexts = contexts.get(row['mbid'], [])
            song.identity_links = identity.get(row['mbid'], [])
            result.append(song)
        return result

    def save_details(self, recordings: list[dict]) -> None:
        with self.transaction() as db:
            for data in recordings:
                if db.execute("SELECT 1 FROM catalog_recordings WHERE mbid=?", (data['id'],)).fetchone():
                    raw = encode(data)
                    db.execute("INSERT OR IGNORE INTO catalog_recording_snapshots VALUES (?,?,?,?)",
                               (data['id'], sha256(raw.encode()).hexdigest(), raw, utc_now()))
                    db.execute("INSERT INTO catalog_recording_details VALUES (?,?,?) ON CONFLICT(mbid) DO UPDATE "
                               "SET payload_json=excluded.payload_json,verified_at=excluded.verified_at",
                               (data['id'], raw, utc_now()))

    def save_works(self, works: list[dict]) -> None:
        with self.transaction() as db:
            for work in works:
                db.execute("INSERT INTO catalog_works VALUES (?,?,?,?) ON CONFLICT(mbid) DO UPDATE "
                           "SET title=excluded.title,payload_json=excluded.payload_json,verified_at=excluded.verified_at",
                           (work['id'], work['title'], encode(work), utc_now()))

    def source_aliases(self,work_ids):
        """Small projection for source-query fingerprints; no full Work decoding in UI."""
        ids=list(set(work_ids));result={}
        with connect(self.path) as db:
            for offset in range(0,len(ids),500):
                batch=ids[offset:offset+500]
                rows=db.execute("SELECT mbid,json_extract(payload_json,'$.aliases') FROM catalog_works WHERE mbid IN ("+','.join('?' for _ in batch)+')',batch).fetchall()
                result.update({row[0]:{'aliases':json.loads(row[1]) if row[1] else []} for row in rows})
        return result

    def works(self) -> dict[str, dict]:
        with connect(self.path) as db:
            return {row[0]: json.loads(row[1]) for row in db.execute('SELECT mbid,payload_json FROM catalog_works')}

    def save_grouping(self, artist: Artist, songs: list[Song], rule_version: str) -> None:
        with self.transaction() as db:
            self.write_grouping(db,artist,songs,rule_version)

    @staticmethod
    def write_grouping(db, artist: Artist, songs: list[Song], rule_version: str) -> None:
        db.execute('DELETE FROM catalog_songs WHERE artist_mbid=?', (artist.mbid,))
        for song in songs:
            db.execute('INSERT INTO catalog_songs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (song.id, artist.mbid, song.title, int(song.pending_confirmation), encode(song.work_ids),
                        song.primary_recording_mbid, song.primary_reason, encode(song.evidence), rule_version, utc_now(),
                        int(song.reviewed),song.review_action))
            db.executemany('INSERT INTO catalog_song_recordings VALUES (?,?)',
                           [(song.id, recording.mbid) for recording in song.recordings])

    def songs(self, artist_mbid: str) -> list[Song]:
        recordings = {recording.mbid: recording for recording in self.recordings(artist_mbid)}
        with connect(self.path) as db:
            rows = db.execute('SELECT * FROM catalog_songs WHERE artist_mbid=? ORDER BY title,song_id', (artist_mbid,)).fetchall()
            links = {}
            for row in db.execute('SELECT sr.song_id,sr.recording_mbid FROM catalog_song_recordings sr JOIN catalog_songs s ON s.song_id=sr.song_id WHERE s.artist_mbid=?', (artist_mbid,)):
                links.setdefault(row[0], []).append(recordings[row[1]])
        return [Song(row['song_id'],row['title'], links.get(row['song_id'], []), tuple(json.loads(row['work_ids_json'])),
                     bool(row['pending']),json.loads(row['evidence_json']),row['primary_recording_mbid'],row['primary_reason'],
                     bool(row['reviewed']),row['review_action']) for row in rows]

    def save_related(self, recordings: list[dict], source: str) -> None:
        with self.transaction() as db:
            for item in recordings:
                db.execute('INSERT INTO catalog_related_recordings VALUES (?,?,?,?) ON CONFLICT(mbid) DO UPDATE SET payload_json=excluded.payload_json,source=excluded.source,verified_at=excluded.verified_at',
                           (item['id'],encode(item),source,utc_now()))

    def related(self) -> dict[str, dict]:
        with connect(self.path) as db:
            return {row[0]:json.loads(row[1]) for row in db.execute('SELECT mbid,payload_json FROM catalog_related_recordings')}

    def evidence_fetch_fresh(self, mbid: str, profile: str, max_age: float=7*86400) -> bool:
        with connect(self.path) as db:
            row=db.execute('SELECT fetched_at FROM catalog_evidence_fetches WHERE recording_mbid=? AND profile=?',(mbid,profile)).fetchone()
        return row is not None and time.time()-row[0] < max_age

    def save_recording_redirect(self, original: str, canonical: str, source: str) -> None:
        with connect(self.path) as db:
            db.execute('INSERT INTO catalog_recording_redirects VALUES (?,?,?,?) ON CONFLICT(original_mbid) DO UPDATE SET canonical_mbid=excluded.canonical_mbid,source=excluded.source,verified_at=excluded.verified_at',
                       (original,canonical,source,utc_now()))

    def recording_redirects(self) -> dict[str, str]:
        with connect(self.path) as db:
            return {row[0]:row[1] for row in db.execute('SELECT original_mbid,canonical_mbid FROM catalog_recording_redirects')}

    def mark_evidence_fetch(self, mbid: str, profile: str, error: str | None=None) -> None:
        with connect(self.path) as db:
            db.execute('INSERT INTO catalog_evidence_fetches VALUES (?,?,?,?,?) ON CONFLICT(recording_mbid,profile) DO UPDATE SET fetched_at=excluded.fetched_at,status=excluded.status,error=excluded.error',
                       (mbid,profile,time.time(),'not_found' if error else 'ok',error))

    def replace_identity_links(self, artist: Artist, links: dict[str,list[dict]]) -> None:
        with self.transaction() as db:
            db.execute('DELETE FROM catalog_identity_evidence WHERE artist_mbid=?',(artist.mbid,))
            for mbid,items in links.items():
                for item in items:
                    raw=encode(item)
                    db.execute('INSERT OR IGNORE INTO catalog_identity_evidence VALUES (?,?,?,?)',
                               (artist.mbid,mbid,sha256(raw.encode()).hexdigest(),raw))
