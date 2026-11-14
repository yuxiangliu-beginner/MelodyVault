"""SQLite connections and transactional migrations."""
from melodyvault.database.core import connect, initialize_database
__all__ = ["connect", "initialize_database"]
