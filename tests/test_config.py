import pytest
from melodyvault.config import load_settings


def test_config_precedence_and_relative_path(tmp_path, monkeypatch):
    monkeypatch.delenv("MELODYVAULT_DATA_DIR", raising=False)
    config = tmp_path / "settings.toml"
    config.write_text('[storage]\ndata_root = "private"\n[logging]\nlevel = "DEBUG"\n', encoding="utf-8")
    assert load_settings(config).data_root == tmp_path / "private"
    assert load_settings(config).log_level == "DEBUG"
    monkeypatch.setenv("MELODYVAULT_DATA_DIR", str(tmp_path / "environment"))
    assert load_settings(config).data_root == tmp_path / "environment"
    assert load_settings(config, tmp_path / "cli").data_root == tmp_path / "cli"
    assert not (tmp_path / "private").exists()


@pytest.mark.parametrize("content", [
    '[logging]\nlevel = "SECRET"', '[storage]\ndata_root = 42',
    '[storage]\nunknown = "x"', '[typo]\nvalue = 1', 'logging = "INFO"',
])
def test_reject_invalid_settings(tmp_path, content):
    config = tmp_path / "invalid.toml"
    config.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(config)


def test_runtime_directories(tmp_path, monkeypatch):
    monkeypatch.delenv("MELODYVAULT_DATA_DIR", raising=False)
    settings = load_settings(data_root=tmp_path)
    settings.prepare()
    settings.prepare()
    for name in ("database", "logs", "cache", "downloads", "credentials"):
        assert (tmp_path / name).is_dir()
    assert settings.database_path == tmp_path / "database" / "melodyvault.sqlite3"


def test_missing_config_is_not_silently_ignored(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "missing.toml")
