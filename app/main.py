"""ArchExplorer AI — application entry point.

Run with::

    python -m app.main
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app import __version__
from app.services import AIEngine, OllamaProvider
from app.ui.main_window import MainWindow

APP_NAME = "ArchExplorer AI"
APP_ORG = "ArchExplorer"
APP_DOMAIN = "archexplorer.local"


def main() -> int:
    """Create the QApplication, show the main window, and run the event loop."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_ORG)
    app.setOrganizationDomain(APP_DOMAIN)

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

    window = MainWindow(services=services)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
