"""ArchExplorer AI — application entry point.

Run with::

    py -m app.main
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app import __version__
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

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
