import json
import os
import subprocess
import sys
import pytest
from melodyvault.database.migrations import MIGRATIONS


def run_app(*args):
    return subprocess.run([sys.executable, "-m", "melodyvault", *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          timeout=30, env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def test_headless_database_entrypoint(tmp_path):
    result = run_app("--data-dir", tmp_path, "--init-db")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schema_version"] == len(MIGRATIONS)
    assert (tmp_path / "database" / "melodyvault.sqlite3").is_file()
    assert (tmp_path / "logs" / "melodyvault.log").is_file()


@pytest.mark.gui
def test_real_qt_event_loop(tmp_path):
    result = run_app("--data-dir", tmp_path, "--smoke")
    assert result.returncode == 0, result.stderr
    assert "GUI_SMOKE_OK" in result.stdout


def test_configuration_error_has_nonzero_exit(tmp_path):
    result = run_app("--config", tmp_path / "missing.toml", "--data-dir", tmp_path / "runtime", "--init-db")
    assert result.returncode == 1
    assert "FileNotFoundError" in result.stderr
    assert not (tmp_path / "runtime").exists()


def test_version_does_not_create_runtime_files(tmp_path):
    result = run_app("--data-dir", tmp_path / "runtime", "--version")
    assert result.returncode == 0
    assert "MelodyVault 0.1.0" in result.stdout
    assert not (tmp_path / "runtime").exists()
