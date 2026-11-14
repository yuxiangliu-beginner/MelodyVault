from contextlib import contextmanager
from pathlib import Path
import sqlite3
from collections.abc import Iterator
from melodyvault.database.migrations import migrate

@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        yield connection
    finally:
        connection.close()


def initialize_database(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        return migrate(connection)
