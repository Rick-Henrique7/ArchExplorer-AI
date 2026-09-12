"""ArchExplorer AI — application entry point.

Run with::

    python -m app.main

Optional flags:

- ``--catalog-db PATH`` — override the SQLite database location for the
  personal catalog. Falls back to (in order): the ``ARCHEXPLORER_CATALOG_DB``
  environment variable, the QSettings key ``catalog/db_path``, and the
  default location at ``~/Documents/ArchExplorer/catalogo.db``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import __version__
from app.services import AIEngine, CatalogoService, OllamaProvider
from app.ui.main_window import MainWindow
from app.ui.theme import ThemeManager

APP_NAME = "ArchExplorer AI"
APP_ORG = "ArchExplorer"
APP_DOMAIN = "archexplorer.local"

# QSettings key for an optional override of the catalog DB path.
_QSETTINGS_CATALOG_DB = "catalog/db_path"

# Env var that takes precedence over the QSettings value (handy for
# one-off runs without touching the registry).
_ENV_CATALOG_DB = "ARCHEXPLORER_CATALOG_DB"

# Repo root (parent of the `app/` package directory).
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent
_APP_ICON_SVG: Path = _REPO_ROOT / "assets" / "app-icon.svg"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI flags.

    Kept tiny — we don't want a full argparse UI surface for a desktop
    tool that primarily launches via the bootstrap script. Adding more
    flags later is one line each.
    """
    parser = argparse.ArgumentParser(
        prog="ArchExplorer AI",
        description="Local desktop tool for architecture analysis.",
    )
    parser.add_argument(
        "--catalog-db",
        dest="catalog_db",
        default=None,
        help=(
            "Path to the catalog SQLite database. Overrides the "
            f"{_ENV_CATALOG_DB} env var and the QSettings "
            f"{_QSETTINGS_CATALOG_DB} key."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ArchExplorer AI {__version__}",
    )
    return parser.parse_args(argv)


def _resolve_catalog_db_path(cli_value: str | None) -> Path:
    """Pick the catalog DB path from CLI > env > QSettings > default.

    The function does NOT instantiate the service — it just resolves
    the path so :func:`main` can hand it off. This makes the priority
    chain easy to test in isolation if we ever need to.
    """
    if cli_value:
        return Path(cli_value).expanduser()
    env_value = os.environ.get(_ENV_CATALOG_DB)
    if env_value:
        return Path(env_value).expanduser()
    settings_value = QSettings().value(_QSETTINGS_CATALOG_DB, "", type=str)
    if settings_value:
        return Path(settings_value).expanduser()
    # default_catalog_path() also creates the parent directory.
    from app.services import default_catalog_path
    return default_catalog_path()


def main(argv: list[str] | None = None) -> int:
    """Create the QApplication, set up theming and services, show the window."""
    parsed = _parse_args(list(argv) if argv is not None else sys.argv[1:])

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_ORG)
    app.setOrganizationDomain(APP_DOMAIN)

    # App icon — appears in the title bar and (on Windows) the taskbar
    # when assets/app-icon.ico is generated. The SVG is the source of
    # truth; the .ico is rebuilt via scripts/build_app_icon.py when it
    # changes.
    if _APP_ICON_SVG.is_file():
        app.setWindowIcon(QIcon(str(_APP_ICON_SVG)))

    # Theme — load persisted preference (or system default) and apply QSS.
    theme_manager = ThemeManager(app)
    theme_manager.apply(theme_manager.current())

    # Catalog DB path: CLI > env > QSettings > default. The service
    # creates the parent directory if needed (handled by
    # ``default_catalog_path``; explicit overrides are created by the
    # ``__init__`` of ``CatalogoService`` itself).
    catalog_db_path = _resolve_catalog_db_path(parsed.catalog_db)
    catalog_service = CatalogoService(db_path=catalog_db_path)

    # Bootstrap default services. Tests override via
    # ``MainWindow(services={"ai_engine": AIEngine(MockAIProvider())})``.
    # Note on timeout: the default in ``OllamaProvider`` is 120s, but the
    # first request after the model is unloaded from RAM (Ollama default
    # idle: 5 min) triggers a cold reload from disk, which can take
    # 60-120s on slow disks for a 1.9-4.5 GB model. 300s gives a safe
    # buffer without changing the public default of OllamaProvider.
    services = {
        "ai_engine": AIEngine(OllamaProvider(timeout=300.0)),
        "catalog_service": catalog_service,
    }

    window = MainWindow(services=services, theme_manager=theme_manager)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
