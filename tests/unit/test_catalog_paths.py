"""Tests for the catalog DB path resolution (Change 006 — Bloco K).

Covers:

- ``default_catalog_path()`` creates the parent directory if missing.
- The CLI/env/QSettings precedence chain (highest to lowest).
- ``--catalog-db`` parsed by :func:`app.main._parse_args`.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from app.main import _parse_args, _resolve_catalog_db_path
from app.services import default_catalog_path


@pytest.fixture
def clean_env(monkeypatch):
    """Strip the catalog-related env var so tests don't leak state."""
    monkeypatch.delenv("ARCHEXPLORER_CATALOG_DB", raising=False)


def test_default_path_creates_parent_dir(tmp_path: Path, monkeypatch) -> None:
    """``default_catalog_path`` makes ``~/Documents/ArchExplorer`` on demand."""
    # Redirect HOME so we don't touch the real user directory.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    path = default_catalog_path()
    assert path.parent.exists()
    assert path.parent.is_dir()
    assert path.name == "catalogo.db"


def test_default_path_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    """Calling twice doesn't raise."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    default_catalog_path()
    default_catalog_path()
    assert (tmp_path / "Documents" / "ArchExplorer").is_dir()


# ----- _resolve_catalog_db_path -------------------------------------------

def test_cli_value_wins(tmp_path: Path, clean_env, monkeypatch) -> None:
    cli = str(tmp_path / "cli.db")
    result = _resolve_catalog_db_path(cli)
    assert result == Path(cli)


def test_env_var_used_when_no_cli(tmp_path: Path, clean_env, monkeypatch) -> None:
    monkeypatch.setenv("ARCHEXPLORER_CATALOG_DB", str(tmp_path / "env.db"))
    result = _resolve_catalog_db_path(None)
    assert result == tmp_path / "env.db"


def test_cli_overrides_env(tmp_path: Path, clean_env, monkeypatch) -> None:
    monkeypatch.setenv("ARCHEXPLORER_CATALOG_DB", str(tmp_path / "env.db"))
    cli = str(tmp_path / "cli.db")
    result = _resolve_catalog_db_path(cli)
    assert result == Path(cli)


def test_qsettings_used_when_no_cli_or_env(
    tmp_path: Path, clean_env, monkeypatch
) -> None:
    # Spy on QSettings().value to return our test path for the
    # ``catalog/db_path`` key, anything else stays default.
    class _FakeSettings:
        _db = str(tmp_path / "settings.db")

        def value(self, key, default="", type=None):
            if key == "catalog/db_path":
                return self._db
            return default
    monkeypatch.setattr(
        "app.main.QSettings", lambda *a, **k: _FakeSettings()
    )
    result = _resolve_catalog_db_path(None)
    assert result == tmp_path / "settings.db"


def test_default_used_when_nothing_configured(
    tmp_path: Path, clean_env, monkeypatch
) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    # Spy on QSettings() to return "" for our key.
    class _FakeSettings:
        def value(self, key, default="", type=None):
            return default
    monkeypatch.setattr(
        "app.main.QSettings", lambda *a, **k: _FakeSettings()
    )
    result = _resolve_catalog_db_path(None)
    assert result == tmp_path / "Documents" / "ArchExplorer" / "catalogo.db"


# ----- CLI parsing -------------------------------------------------------

def test_parse_args_accepts_catalog_db() -> None:
    args = _parse_args(["--catalog-db", "C:/tmp/my.db"])
    assert args.catalog_db == "C:/tmp/my.db"


def test_parse_args_catalog_db_optional() -> None:
    args = _parse_args([])
    assert args.catalog_db is None


def test_parse_args_version(capsys) -> None:
    """--version prints and exits."""
    with pytest.raises(SystemExit):
        _parse_args(["--version"])
    captured = capsys.readouterr()
    assert "ArchExplorer AI" in captured.out
