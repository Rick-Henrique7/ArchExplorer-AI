"""Shared pytest fixtures for the ArchExplorer AI test suite.

The skeleton ships one fixture: a session-scoped ``QApplication`` that
runs in headless (``offscreen``) mode so tests can run in CI without a
display.
"""

from __future__ import annotations

import os

# Must be set BEFORE QApplication is constructed, hence at import time.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return a process-wide QApplication, creating it if needed."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
        # Set org/app name so QSettings() inside MainWindow and friends
        # has a stable target. These match app/main.py; tests that need
        # a private INI file pass their own QSettings explicitly.
        QCoreApplication.setOrganizationName("ArchExplorer-Test")
        QCoreApplication.setApplicationName("ArchExplorer-AI-Test")
    yield app
    # Do not call app.quit() — leaving the app alive across the session
    # is the documented pattern and avoids teardown-order surprises.
