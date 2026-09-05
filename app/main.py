"""ArchExplorer AI — application entry point.

Run with::

    python -m app.main
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import __version__
from app.services import AIEngine, OllamaProvider
from app.ui.main_window import MainWindow
from app.ui.theme import ThemeManager

APP_NAME = "ArchExplorer AI"
APP_ORG = "ArchExplorer"
APP_DOMAIN = "archexplorer.local"

# Repo root (parent of the `app/` package directory).
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent
_APP_ICON_SVG: Path = _REPO_ROOT / "assets" / "app-icon.svg"


def main() -> int:
    """Create the QApplication, set up theming and services, show the window."""
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

    # Bootstrap default services. Tests override via
    # ``MainWindow(services={"ai_engine": AIEngine(MockAIProvider())})``.
    # Note on timeout: the default in ``OllamaProvider`` is 120s, but the
    # first request after the model is unloaded from RAM (Ollama default
    # idle: 5 min) triggers a cold reload from disk, which can take
    # 60-120s on slow disks for a 1.9-4.5 GB model. 300s gives a safe
    # buffer without changing the public default of OllamaProvider.
    services = {
        "ai_engine": AIEngine(OllamaProvider(timeout=300.0)),
    }

    window = MainWindow(services=services, theme_manager=theme_manager)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
