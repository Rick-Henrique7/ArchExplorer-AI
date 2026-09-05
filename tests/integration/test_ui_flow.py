"""End-to-end test: file selection → AI analysis → rendered in VisualizerPanel.

Exercises the full signal flow without rendering the actual HTML
(``QWebEngineView`` renders asynchronously in Chromium, which we don't
need to wait for). We assert on the public ``last_markdown`` /
``last_error`` attributes the :class:`VisualizerPanel` exposes.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from app.services import AIEngine, MockAIProvider
from app.ui.main_window import MainWindow


# A canned LLM response that mimics what Qwen 2.5 Coder 3B might return.
_FIXTURE_MD = (
    "## Patterns\n- Singleton\n\n"
    "## Issues\n- Tight coupling between Calc and Logger\n\n"
    "## Suggestions\n- Extract a Logger interface\n\n"
    "```mermaid\n"
    "classDiagram\n"
    "  class Calc {\n"
    "    +add(a, b) int\n"
    "  }\n"
    "```\n"
)


@pytest.fixture
def mock_engine() -> AIEngine:
    return AIEngine(MockAIProvider({"Patterns": _FIXTURE_MD}))


def _drain_threadpool() -> None:
    """Wait for all queued QRunnables to complete and process their signals."""
    QThreadPool.globalInstance().waitForDone(5000)
    # Spinning the event loop ensures queued cross-thread signals are
    # delivered to slots in the main thread.
    QApplication.processEvents()


def test_file_selection_triggers_ai_and_updates_visualizer(
    qapp, tmp_path, mock_engine
) -> None:
    # Arrange: a small .py file
    py_file = tmp_path / "calc.py"
    py_file.write_text(
        "class Calc:\n    def add(self, a, b):\n        return a + b\n",
        encoding="utf-8",
    )

    # Build window with mock engine
    window = MainWindow(services={"ai_engine": mock_engine})

    # Act: simulate a file click via the signal
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()

    # Assert: editor got the file content
    assert "class Calc" in window._code_editor._editor.toPlainText()

    # Assert: visualizer got the markdown
    assert window._visualizer.last_markdown is not None
    assert "Singleton" in window._visualizer.last_markdown
    assert "classDiagram" in window._visualizer.last_markdown
    assert window._visualizer.last_error is None


def test_file_selection_with_invalid_extension_shows_error_without_ai(
    qapp, tmp_path, mock_engine
) -> None:
    # Arrange: a binary extension
    f = tmp_path / "x.exe"
    f.write_text("MZ", encoding="utf-8")
    window = MainWindow(services={"ai_engine": mock_engine})

    # Act
    window._file_explorer.file_selected.emit(str(f))
    _drain_threadpool()

    # Assert: editor is cleared, visualizer shows error (no AI call)
    assert window._code_editor._editor.toPlainText() == ""
    assert window._visualizer.last_markdown is None
    assert window._visualizer.last_error is not None
    assert "not supported" in window._visualizer.last_error


def test_file_selection_with_missing_file_shows_error(
    qapp, tmp_path, mock_engine
) -> None:
    window = MainWindow(services={"ai_engine": mock_engine})
    window._file_explorer.file_selected.emit(str(tmp_path / "ghost.py"))
    _drain_threadpool()
    assert window._visualizer.last_error is not None
    assert "does not exist" in window._visualizer.last_error


def test_file_selection_without_ai_engine_shows_clear_error(qapp, tmp_path) -> None:
    """Missing services['ai_engine'] must produce a friendly error."""
    py_file = tmp_path / "ok.py"
    py_file.write_text("x = 1", encoding="utf-8")
    window = MainWindow()  # no services
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()
    # Editor still shows the file (synchronous)
    assert "x = 1" in window._code_editor._editor.toPlainText()
    # But visualizer shows a configuration error
    assert window._visualizer.last_error is not None
    assert "No AI engine" in window._visualizer.last_error


def test_ai_service_failure_is_surfaced_to_visualizer(qapp, tmp_path) -> None:
    """When the engine raises, the visualizer shows the error message."""
    from app.services import AIServiceUnavailableError

    class FailingProvider:
        def generate(self, prompt, *, system=None, temperature=None):
            raise AIServiceUnavailableError("ollama down")

    engine = AIEngine(FailingProvider())
    py_file = tmp_path / "ok.py"
    py_file.write_text("x = 1", encoding="utf-8")
    window = MainWindow(services={"ai_engine": engine})
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()
    assert window._visualizer.last_error is not None
    assert "AI service unavailable" in window._visualizer.last_error
    assert "ollama down" in window._visualizer.last_error
