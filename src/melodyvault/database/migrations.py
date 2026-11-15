"""Append-only migrations. Never edit an already released migration."""
from dataclasses import dataclass
from hashlib import sha256
import sqlite3

@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        return sha256("\n".join(self.statements).encode("utf-8")).hexdigest()

MIGRATIONS = (
    Migration(1, "application_metadata", (
        "CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        "INSERT INTO app_metadata (key, value) VALUES ('application', 'MelodyVault')",
    )),
    Migration(2, "musicbrainz_catalog", (
        "CREATE TABLE catalog_artists (mbid TEXT PRIMARY KEY, name TEXT NOT NULL, payload_json TEXT NOT NULL, verified_at TEXT NOT NULL)",
        "CREATE TABLE catalog_queries (query_key TEXT PRIMARY KEY, artist_mbid TEXT NOT NULL REFERENCES catalog_artists(mbid))",
        "CREATE TABLE catalog_recordings (mbid TEXT PRIMARY KEY, title TEXT NOT NULL, normalized_title TEXT NOT NULL, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)",
        "CREATE INDEX idx_catalog_recording_title ON catalog_recordings(normalized_title)",
        "CREATE TABLE catalog_artist_recordings (artist_mbid TEXT NOT NULL REFERENCES catalog_artists(mbid), recording_mbid TEXT NOT NULL REFERENCES catalog_recordings(mbid), official INTEGER NOT NULL DEFAULT 0 CHECK(official IN (0,1)), origins_json TEXT NOT NULL, PRIMARY KEY(artist_mbid, recording_mbid))",
        "CREATE TABLE catalog_release_groups (mbid TEXT PRIMARY KEY, title TEXT NOT NULL, primary_type TEXT, payload_json TEXT NOT NULL)",
        "CREATE TABLE catalog_artist_groups (artist_mbid TEXT NOT NULL REFERENCES catalog_artists(mbid), group_mbid TEXT NOT NULL REFERENCES catalog_release_groups(mbid), PRIMARY KEY(artist_mbid, group_mbid))",
        "CREATE TABLE catalog_releases (mbid TEXT PRIMARY KEY, group_mbid TEXT REFERENCES catalog_release_groups(mbid), status TEXT, payload_json TEXT NOT NULL)",
        "CREATE TABLE catalog_tracks (mbid TEXT PRIMARY KEY, release_mbid TEXT NOT NULL REFERENCES catalog_releases(mbid), recording_mbid TEXT, title TEXT NOT NULL, medium_position INTEGER, position INTEGER, payload_json TEXT NOT NULL)",
        "CREATE INDEX idx_catalog_track_recording ON catalog_tracks(recording_mbid)",
        "CREATE TABLE catalog_runs (id TEXT PRIMARY KEY, query TEXT NOT NULL, artist_mbid TEXT REFERENCES catalog_artists(mbid), status TEXT NOT NULL CHECK(status IN ('running','completed','failed','cancelled','needs_selection')), phase TEXT NOT NULL, processed INTEGER NOT NULL DEFAULT 0, total INTEGER, error TEXT, summary_json TEXT, started_at TEXT NOT NULL, finished_at TEXT)",
        "CREATE TABLE catalog_http_cache (cache_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, fetched_at REAL NOT NULL)",
    )),
    Migration(3, "song_recording_evidence", (
        "CREATE TABLE catalog_recording_snapshots (recording_mbid TEXT NOT NULL REFERENCES catalog_recordings(mbid), payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, recorded_at TEXT NOT NULL, PRIMARY KEY(recording_mbid,payload_hash))",
        "INSERT INTO catalog_recording_snapshots SELECT mbid,'v2-original',payload_json,updated_at FROM catalog_recordings",
        "CREATE TABLE catalog_response_history (cache_key TEXT NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, fetched_at REAL NOT NULL, PRIMARY KEY(cache_key,payload_hash))",
        "INSERT INTO catalog_response_history SELECT cache_key,'v2-original',payload_json,fetched_at FROM catalog_http_cache",
        "CREATE TABLE catalog_recording_details (mbid TEXT PRIMARY KEY REFERENCES catalog_recordings(mbid), payload_json TEXT NOT NULL, verified_at TEXT NOT NULL)",
        "CREATE TABLE catalog_works (mbid TEXT PRIMARY KEY, title TEXT NOT NULL, payload_json TEXT NOT NULL, verified_at TEXT NOT NULL)",
        "CREATE TABLE catalog_songs (song_id TEXT PRIMARY KEY, artist_mbid TEXT NOT NULL REFERENCES catalog_artists(mbid), title TEXT NOT NULL, pending INTEGER NOT NULL CHECK(pending IN (0,1)), work_ids_json TEXT NOT NULL, primary_recording_mbid TEXT REFERENCES catalog_recordings(mbid), primary_reason TEXT NOT NULL, evidence_json TEXT NOT NULL, rule_version TEXT NOT NULL, updated_at TEXT NOT NULL)",
        "CREATE TABLE catalog_song_recordings (song_id TEXT NOT NULL REFERENCES catalog_songs(song_id) ON DELETE CASCADE, recording_mbid TEXT NOT NULL REFERENCES catalog_recordings(mbid), PRIMARY KEY(song_id,recording_mbid))",
    )),
    Migration(4, "evidence_review_audit", (
        "ALTER TABLE catalog_songs ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 0 CHECK(reviewed IN (0,1))",
        "ALTER TABLE catalog_songs ADD COLUMN review_action TEXT NOT NULL DEFAULT ''",
        "CREATE TABLE catalog_related_recordings (mbid TEXT PRIMARY KEY,payload_json TEXT NOT NULL,source TEXT NOT NULL,verified_at TEXT NOT NULL)",
        "CREATE TABLE catalog_evidence_fetches (recording_mbid TEXT NOT NULL,profile TEXT NOT NULL,fetched_at REAL NOT NULL,status TEXT NOT NULL,error TEXT,PRIMARY KEY(recording_mbid,profile))",
        "CREATE TABLE catalog_recording_redirects (original_mbid TEXT PRIMARY KEY,canonical_mbid TEXT NOT NULL,source TEXT NOT NULL,verified_at TEXT NOT NULL)",
        "CREATE TABLE catalog_identity_evidence (artist_mbid TEXT NOT NULL REFERENCES catalog_artists(mbid),recording_mbid TEXT NOT NULL REFERENCES catalog_recordings(mbid),evidence_key TEXT NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(artist_mbid,recording_mbid,evidence_key))",
        "CREATE TABLE catalog_review_events (id TEXT PRIMARY KEY,artist_mbid TEXT NOT NULL REFERENCES catalog_artists(mbid),action TEXT NOT NULL CHECK(action IN ('merge','reject','independent','undo')),payload_json TEXT NOT NULL,reason TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL,undo_of TEXT UNIQUE REFERENCES catalog_review_events(id),CHECK((action='undo' AND undo_of IS NOT NULL) OR (action<>'undo' AND undo_of IS NULL)))",
        "CREATE INDEX idx_review_artist_time ON catalog_review_events(artist_mbid,created_at,id)",
        "CREATE TRIGGER review_no_update BEFORE UPDATE ON catalog_review_events BEGIN SELECT RAISE(ABORT,'Review audit is append-only'); END",
        "CREATE TRIGGER review_no_delete BEFORE DELETE ON catalog_review_events BEGIN SELECT RAISE(ABORT,'Review audit is append-only'); END",
    )),
    Migration(5, "independent_tasks_and_source_search", (
        "CREATE TABLE catalog_task_cache (kind TEXT NOT NULL,entity_id TEXT NOT NULL,profile TEXT NOT NULL,status TEXT NOT NULL,checked_at REAL NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(kind,entity_id,profile))",
        "CREATE TABLE source_runs (id TEXT PRIMARY KEY,artist_mbid TEXT NOT NULL,status TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,summary_json TEXT NOT NULL)",
        "CREATE TABLE source_jobs (run_id TEXT NOT NULL REFERENCES source_runs(id),song_id TEXT NOT NULL,query_json TEXT NOT NULL,status TEXT NOT NULL,summary_json TEXT NOT NULL,PRIMARY KEY(run_id,song_id))",
        "CREATE TABLE source_attempts (id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES source_runs(id),song_id TEXT NOT NULL,provider TEXT NOT NULL,fingerprint TEXT NOT NULL,status TEXT NOT NULL,checked_at REAL NOT NULL,error TEXT NOT NULL,query_json TEXT NOT NULL,candidates_json TEXT NOT NULL)",
        "CREATE INDEX idx_source_attempt_cache ON source_attempts(provider,fingerprint,checked_at DESC)",
        "CREATE TABLE source_browser_checks (id TEXT PRIMARY KEY,url TEXT NOT NULL,status TEXT NOT NULL,checked_at TEXT NOT NULL,evidence_json TEXT NOT NULL)",
    )),
    Migration(6, "unified_artist_song_search", (
        "INSERT INTO app_metadata VALUES ('unified_revision','0')",
        "CREATE TABLE unified_index_meta (id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL)",
        "CREATE TABLE unified_artist_index (mbid TEXT PRIMARY KEY,payload_json TEXT NOT NULL,keys_json TEXT NOT NULL)",
        "CREATE TABLE unified_recording_index (artist_mbid TEXT NOT NULL,recording_mbid TEXT NOT NULL,payload_json TEXT NOT NULL,PRIMARY KEY(artist_mbid,recording_mbid))",
        "CREATE TABLE unified_title_keys (title_key TEXT NOT NULL,artist_mbid TEXT NOT NULL,recording_mbid TEXT NOT NULL,PRIMARY KEY(title_key,artist_mbid,recording_mbid))",
        "CREATE TABLE unified_search_cache (cache_key TEXT PRIMARY KEY,mode TEXT NOT NULL,artist_ids_json TEXT NOT NULL,payload_json TEXT NOT NULL,checked_at REAL NOT NULL)",
        "CREATE TABLE unified_confirmations (id TEXT PRIMARY KEY,query_json TEXT NOT NULL,artist_mbid TEXT NOT NULL,recording_mbid TEXT NOT NULL,song_id TEXT NOT NULL,candidate_json TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TABLE unified_user_aliases (title_key TEXT NOT NULL,artist_mbid TEXT NOT NULL,recording_mbid TEXT NOT NULL,PRIMARY KEY(title_key,artist_mbid,recording_mbid))",
        "CREATE TRIGGER unified_confirmation_no_update BEFORE UPDATE ON unified_confirmations BEGIN SELECT RAISE(ABORT,'Search selection audit is append-only'); END",
        "CREATE TRIGGER unified_confirmation_no_delete BEFORE DELETE ON unified_confirmations BEGIN SELECT RAISE(ABORT,'Search selection audit is append-only'); END",
        *tuple(f"CREATE TRIGGER unified_revision_{table}_{action.lower()} AFTER {action} ON {table} BEGIN UPDATE app_metadata SET value=CAST(value AS INTEGER)+1 WHERE key='unified_revision'; END"
               for table in ('catalog_artists','catalog_songs','catalog_song_recordings','catalog_recording_details','catalog_works')
               for action in ('INSERT','UPDATE','DELETE')),
    )),
    Migration(7, "licensed_local_downloads", (
        "CREATE TABLE download_settings (id INTEGER PRIMARY KEY CHECK(id=1),payload_json TEXT NOT NULL)",
        "CREATE TABLE download_jobs (id TEXT PRIMARY KEY,batch_id TEXT NOT NULL,dedupe_key TEXT NOT NULL,target_json TEXT NOT NULL,candidate_json TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL CHECK(state IN ('QUEUED','SEARCHING','VERIFYING','READY','DOWNLOADING','PAUSED','COMPLETED','FAILED','CANCELLED','SKIPPED')),reason_code TEXT NOT NULL DEFAULT '',reason TEXT NOT NULL DEFAULT '',dry_run INTEGER NOT NULL CHECK(dry_run IN (0,1)),settings_json TEXT NOT NULL,bytes_received INTEGER NOT NULL DEFAULT 0,total_bytes INTEGER NOT NULL DEFAULT 0,speed REAL NOT NULL DEFAULT 0,eta REAL,part_path TEXT NOT NULL DEFAULT '',etag TEXT NOT NULL DEFAULT '',last_modified TEXT NOT NULL DEFAULT '',resource_url TEXT NOT NULL DEFAULT '',attempt_count INTEGER NOT NULL DEFAULT 0,result_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",
        "CREATE UNIQUE INDEX idx_download_active ON download_jobs(dedupe_key) WHERE state IN ('QUEUED','SEARCHING','VERIFYING','READY','DOWNLOADING','PAUSED')",
        "CREATE INDEX idx_download_queue ON download_jobs(state,created_at)",
        "CREATE TABLE download_attempts (id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES download_jobs(id),number INTEGER NOT NULL,status TEXT NOT NULL,details_json TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TABLE downloaded_files (id TEXT PRIMARY KEY,provider TEXT NOT NULL,external_id TEXT NOT NULL,recording_id TEXT NOT NULL,fingerprint TEXT NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL,sha1 TEXT NOT NULL,bytes INTEGER NOT NULL,media_json TEXT NOT NULL,evidence_json TEXT NOT NULL,verified_at TEXT NOT NULL,UNIQUE(fingerprint,sha256))",
        "CREATE INDEX idx_download_file_source ON downloaded_files(provider,external_id)",
        "CREATE TABLE download_evidence (id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES download_jobs(id),step TEXT NOT NULL,decision TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL)",
        "CREATE TRIGGER download_evidence_no_update BEFORE UPDATE ON download_evidence BEGIN SELECT RAISE(ABORT,'Download evidence is append-only'); END",
        "CREATE TRIGGER download_evidence_no_delete BEFORE DELETE ON download_evidence BEGIN SELECT RAISE(ABORT,'Download evidence is append-only'); END",
    )),
    Migration(8, "dynamic_source_discovery", (
        "CREATE TABLE discovered_sources (domain TEXT PRIMARY KEY,name TEXT NOT NULL,first_url TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'unknown',review_status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',enabled INTEGER NOT NULL DEFAULT 1,manual_disabled INTEGER NOT NULL DEFAULT 0,provider TEXT NOT NULL DEFAULT '',discovered_at REAL NOT NULL,checked_at REAL NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'DISCOVERED',risk TEXT NOT NULL DEFAULT 'UNKNOWN',failures INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,hits INTEGER NOT NULL DEFAULT 0,last_error TEXT NOT NULL DEFAULT '')",
        "CREATE TABLE source_capabilities (domain TEXT PRIMARY KEY REFERENCES discovered_sources(domain),payload_json TEXT NOT NULL)",
        "CREATE TABLE source_discovery_history (id TEXT PRIMARY KEY,domain TEXT NOT NULL REFERENCES discovered_sources(domain),query TEXT NOT NULL,channel TEXT NOT NULL,url TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at REAL NOT NULL)",
        "CREATE TABLE source_verification_history (id TEXT PRIMARY KEY,domain TEXT NOT NULL REFERENCES discovered_sources(domain),action TEXT NOT NULL,payload_json TEXT NOT NULL,created_at REAL NOT NULL)",
        "CREATE TABLE source_discovery_cache (cache_key TEXT PRIMARY KEY,payload_json TEXT NOT NULL,checked_at REAL NOT NULL)",
        "CREATE INDEX idx_discovery_history_domain ON source_discovery_history(domain,created_at)",
        "CREATE INDEX idx_verification_history_domain ON source_verification_history(domain,created_at)",
    )),
    Migration(9, "automated_search_sessions", (
        "CREATE TABLE pipeline_sessions (id TEXT PRIMARY KEY, query_json TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT NOT NULL DEFAULT '{}', started_at TEXT NOT NULL, finished_at TEXT)",
        "CREATE TABLE pipeline_source_attempts (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES pipeline_sessions(id), payload_json TEXT NOT NULL, created_at TEXT NOT NULL)",
        "CREATE INDEX pipeline_attempts_session ON pipeline_source_attempts(session_id,created_at)",
    )),
    Migration(10, "personal_music_library", (
        "CREATE TABLE personal_music (id TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL, album TEXT NOT NULL DEFAULT '', duration REAL, format TEXT NOT NULL, path TEXT NOT NULL UNIQUE, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, source_type TEXT NOT NULL, created_at TEXT NOT NULL)",
        "CREATE INDEX personal_music_sha256 ON personal_music(sha256)",
    )),
)


def migrate(connection: sqlite3.Connection) -> int:
    versions = [m.version for m in MIGRATIONS]
    if versions != list(range(1, len(MIGRATIONS) + 1)):
        raise RuntimeError("Migration definitions must be consecutive from version 1")
    connection.execute("BEGIN IMMEDIATE")
    try:
        current = connection.execute("PRAGMA user_version").fetchone()[0]
        if current > len(MIGRATIONS):
            raise RuntimeError("Database is newer than this application; refusing downgrade")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, "
            "applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
        )
        history = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        expected = [(m.version, m.name, m.checksum) for m in MIGRATIONS[:current]]
        if [tuple(row) for row in history] != expected:
            raise RuntimeError("Database migration history is inconsistent or modified")
        for migration in MIGRATIONS[current:]:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version, name, checksum) VALUES (?, ?, ?)",
                (migration.version, migration.name, migration.checksum),
            )
            connection.execute(f"PRAGMA user_version = {migration.version}")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return len(MIGRATIONS)
