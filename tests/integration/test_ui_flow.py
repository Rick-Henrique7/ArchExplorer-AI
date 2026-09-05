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
    "## Padrões\n- Singleton\n\n"
    "## Problemas\n- Acoplamento forte entre Calc e Logger\n\n"
    "## Sugestões\n- Extrair uma interface Logger\n\n"
    "```mermaid\n"
    "classDiagram\n"
    "  class Calc {\n"
    "    +add(a, b) int\n"
    "  }\n"
    "```\n"
)


@pytest.fixture
def mock_engine() -> AIEngine:
    return AIEngine(MockAIProvider({"Padrões": _FIXTURE_MD}))


def _drain_threadpool() -> None:
    """Wait for all queued QRunnables to complete and process their signals."""
    QThreadPool.globalInstance().waitForDone(5000)
    # Spinning the event loop ensures queued cross-thread signals are
    # delivered to slots in the main thread.
    QApplication.processEvents()


def test_file_selection_does_not_auto_trigger_analysis(
    qapp, tmp_path, mock_engine
) -> None:
    """After the hotfix, clicking a file must NOT auto-invoke the AI.

    The user must click the manual Analisar button. The visualizer
    should show the idle state until that happens.
    """
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

    # Assert: visualizer is in the idle state (NO AI call happened)
    assert window._visualizer.last_markdown is None
    assert window._visualizer.last_error is None
    # The Analisar button is now enabled.
    assert window._visualizer._analyze_button.isEnabled() is True


def test_manual_analyze_button_triggers_ai(
    qapp, tmp_path, mock_engine
) -> None:
    """Clicking the Analisar button after a file selection runs the AI."""
    py_file = tmp_path / "calc.py"
    py_file.write_text(
        "class Calc:\n    def add(self, a, b):\n        return a + b\n",
        encoding="utf-8",
    )

    window = MainWindow(services={"ai_engine": mock_engine})
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()
    # No markdown yet.
    assert window._visualizer.last_markdown is None

    # Click the manual Analisar button.
    window._visualizer.analyze_requested.emit()
    _drain_threadpool()

    # Now the visualizer should have the analysis.
    assert window._visualizer.last_markdown is not None
    assert "Singleton" in window._visualizer.last_markdown
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


def test_analyze_without_ai_engine_shows_clear_error(qapp, tmp_path) -> None:
    """Missing services['ai_engine'] must produce a friendly error."""
    py_file = tmp_path / "ok.py"
    py_file.write_text("x = 1", encoding="utf-8")
    window = MainWindow()  # no services
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()
    # Editor still shows the file (synchronous).
    assert "x = 1" in window._code_editor._editor.toPlainText()
    # Visualizer is in idle (no error yet — only when user clicks Analisar).
    assert window._visualizer.last_error is None
    # Click Analisar — the broken engine must surface a clear error.
    window._visualizer.analyze_requested.emit()
    _drain_threadpool()
    assert window._visualizer.last_error is not None
    assert "Motor de IA" in window._visualizer.last_error or "No AI engine" in window._visualizer.last_error


def test_ai_service_failure_is_surfaced_to_visualizer(qapp, tmp_path) -> None:
    """When the engine raises on Analisar, the visualizer shows the error."""
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
    # Click Analisar — the broken provider must surface the error.
    window._visualizer.analyze_requested.emit()
    _drain_threadpool()
    assert window._visualizer.last_error is not None
    assert "AI service unavailable" in window._visualizer.last_error
    assert "ollama down" in window._visualizer.last_error


# ----- Cache behaviour (hotfix) --------------------------------------------


def test_second_analyze_with_unchanged_file_uses_cache(qapp, tmp_path, mock_engine) -> None:
    """After the first analysis, the same file's content is cached.

    A second Analisar click with the same content must NOT call the AI.
    """
    py_file = tmp_path / "x.py"
    py_file.write_text("x = 1\n", encoding="utf-8")
    window = MainWindow(services={"ai_engine": mock_engine})
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()
    # First analyze.
    window._visualizer.analyze_requested.emit()
    _drain_threadpool()
    first_md = window._visualizer.last_markdown
    assert first_md is not None
    # The fixture is keyed on "Singleton" — confirm the AI was actually called.
    assert "Singleton" in first_md

    # Swap the file out, then back in: same content, same cache hit.
    window._file_explorer.file_selected.emit(str(tmp_path / "other.py"))
    _drain_threadpool()
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()
    # The cache should have served the previous analysis (no second call).
    assert window._visualizer.last_markdown == first_md


def test_editing_file_invalidates_cache(qapp, tmp_path, mock_engine) -> None:
    """Saving the file (Ctrl+S) drops the cache entry."""
    py_file = tmp_path / "x.py"
    py_file.write_text("x = 1\n", encoding="utf-8")
    window = MainWindow(services={"ai_engine": mock_engine})
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()
    window._visualizer.analyze_requested.emit()
    _drain_threadpool()
    assert "Singleton" in window._visualizer.last_markdown  # cache or fresh

    # Edit and save.
    window._code_editor.set_content("x = 2\n", path=str(py_file), file_type="python")
    window._code_editor._editor.setPlainText("x = 2\n")
    window._code_editor._on_save_clicked()
    # The save signal should have invalidated the cache for this path.
    assert str(py_file) not in window._analysis_cache


def test_different_file_uses_separate_cache_entry(qapp, tmp_path, mock_engine) -> None:
    py1 = tmp_path / "a.py"
    py1.write_text("a = 1\n", encoding="utf-8")
    py2 = tmp_path / "b.py"
    py2.write_text("b = 2\n", encoding="utf-8")
    window = MainWindow(services={"ai_engine": mock_engine})
    window._file_explorer.file_selected.emit(str(py1))
    _drain_threadpool()
    window._visualizer.analyze_requested.emit()
    _drain_threadpool()
    window._file_explorer.file_selected.emit(str(py2))
    _drain_threadpool()
    window._visualizer.analyze_requested.emit()
    _drain_threadpool()
    # Both files have entries.
    assert str(py1) in window._analysis_cache
    assert str(py2) in window._analysis_cache
