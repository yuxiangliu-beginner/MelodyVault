"""Validated non-secret configuration; parsing has no filesystem side effects."""
from dataclasses import dataclass
import os
from pathlib import Path
import tomllib

@dataclass(frozen=True)
class Settings:
    data_root: Path
    log_level: str = "INFO"

    @property
    def database_path(self) -> Path:
        return self.data_root / "database" / "melodyvault.sqlite3"

    @property
    def log_dir(self) -> Path:
        return self.data_root / "logs"

    def prepare(self) -> None:
        for name in ("database", "logs", "cache", "downloads", "credentials"):
            (self.data_root / name).mkdir(parents=True, exist_ok=True)


def default_data_root() -> Path:
    if os.name == "nt" and Path("D:/").is_dir():
        return Path("D:/MelodyVaultData")
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".local" / "share") / "MelodyVault"


def load_settings(config_path: Path | None = None, data_root: Path | None = None) -> Settings:
    document = {}
    if config_path is not None:
        with config_path.open("rb") as stream:
            document = tomllib.load(stream)
    if set(document) - {"storage", "logging"}:
        raise ValueError("Unknown configuration section")
    storage = document.get("storage", {})
    log_config = document.get("logging", {})
    if not isinstance(storage, dict) or not isinstance(log_config, dict):
        raise ValueError("Configuration sections must be tables")
    if set(storage) - {"data_root"} or set(log_config) - {"level"}:
        raise ValueError("Unknown configuration key")
    value = storage.get("data_root", "")
    if not isinstance(value, str):
        raise ValueError("storage.data_root must be a string")
    level = log_config.get("level", "INFO")
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ValueError("Invalid logging.level")
    configured = Path(value).expanduser() if value else None
    if configured is not None and not configured.is_absolute():
        assert config_path is not None
        configured = config_path.resolve().parent / configured
    env_root = os.environ.get("MELODYVAULT_DATA_DIR")
    selected = data_root or (Path(env_root).expanduser() if env_root else None)
    return Settings((selected or configured or default_data_root()).resolve(), level)
