import sqlite3
import pytest
from melodyvault.database import connect, initialize_database
from melodyvault.database import migrations

SCHEMA_VERSION = len(migrations.MIGRATIONS)


def test_initialize_reopen_and_preserve_user_data(tmp_path):
    path = tmp_path / "database" / "app.sqlite3"
    assert initialize_database(path) == SCHEMA_VERSION
    with connect(path) as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        db.execute("INSERT INTO app_metadata VALUES ('test', 'persistent')")
    assert initialize_database(path) == SCHEMA_VERSION
    with connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
        assert db.execute("SELECT value FROM app_metadata WHERE key='test'").fetchone()[0] == 'persistent'
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_connection_is_closed(tmp_path):
    path = tmp_path / "app.sqlite3"
    initialize_database(path)
    with connect(path) as db:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")


def test_failed_upgrade_is_atomic_and_can_retry(tmp_path, monkeypatch):
    path = tmp_path / "app.sqlite3"
    initialize_database(path)
    original = migrations.MIGRATIONS
    broken = migrations.Migration(SCHEMA_VERSION + 1, "broken", (
        "CREATE TABLE upgrade_probe (id INTEGER)", "INVALID SQL",
    ))
    monkeypatch.setattr(migrations, "MIGRATIONS", original + (broken,))
    with pytest.raises(sqlite3.Error):
        initialize_database(path)
    with connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='upgrade_probe'").fetchall()
        assert db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == SCHEMA_VERSION
    fixed = migrations.Migration(SCHEMA_VERSION + 1, "fixed", ("CREATE TABLE upgrade_probe (id INTEGER)",))
    monkeypatch.setattr(migrations, "MIGRATIONS", original + (fixed,))
    assert initialize_database(path) == SCHEMA_VERSION + 1
    assert initialize_database(path) == SCHEMA_VERSION + 1


def test_upgrade_from_phase0_preserves_metadata(tmp_path, monkeypatch):
    path = tmp_path / "phase0.sqlite3"
    original = migrations.MIGRATIONS
    monkeypatch.setattr(migrations, "MIGRATIONS", original[:1])
    assert initialize_database(path) == 1
    with connect(path) as db:
        db.execute("INSERT INTO app_metadata VALUES ('existing', 'keep-me')")
        checksum = db.execute("SELECT checksum FROM schema_migrations WHERE version=1").fetchone()[0]
    monkeypatch.setattr(migrations, "MIGRATIONS", original)
    assert initialize_database(path) == SCHEMA_VERSION
    with connect(path) as db:
        assert db.execute("SELECT value FROM app_metadata WHERE key='existing'").fetchone()[0] == 'keep-me'
        assert db.execute("SELECT checksum FROM schema_migrations WHERE version=1").fetchone()[0] == checksum


def test_refuse_future_schema_without_downgrade(tmp_path):
    path = tmp_path / "app.sqlite3"
    initialize_database(path)
    with connect(path) as db:
        db.execute("PRAGMA user_version = 999")
    with pytest.raises(RuntimeError, match="newer"):
        initialize_database(path)
    with connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 999


def test_refuse_modified_migration_history(tmp_path):
    path = tmp_path / "app.sqlite3"
    initialize_database(path)
    with connect(path) as db:
        db.execute("UPDATE schema_migrations SET checksum='tampered'")
    with pytest.raises(RuntimeError, match="inconsistent"):
        initialize_database(path)
