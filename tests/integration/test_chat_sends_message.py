"""Integration test: chat input -> ChatWorker -> add_chat_response."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from app.services import AIEngine, MockAIProvider
from app.ui.main_window import MainWindow


_ASSISTANT_REPLY = "Here is a thoughtful answer to your question."


@pytest.fixture
def chat_engine() -> AIEngine:
    return AIEngine(MockAIProvider({"Usuário:": _ASSISTANT_REPLY}))


def _drain_threadpool() -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    QApplication.processEvents()


def test_chat_message_round_trip_updates_history(qapp, tmp_path, chat_engine) -> None:
    """Send a chat message -> worker fills in the assistant reply -> history grows."""
    py_file = tmp_path / "x.py"
    py_file.write_text("x = 1\n", encoding="utf-8")

    window = MainWindow(services={"ai_engine": chat_engine})
    # Bind a file so the visualizer has context for the prompt.
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()
    # Editor + visualizer should now reflect the file.
    assert window._code_editor.current_path() == str(py_file)

    # Type a message into the chat input and click Send.
    window._visualizer._input.setPlainText("what does this file do?")
    window._visualizer._on_send_clicked()

    # A pending turn should be in history immediately.
    assert len(window._visualizer.chat_history) == 1
    assert window._visualizer.chat_history[0].user == "what does this file do?"
    assert window._visualizer.chat_history[0].assistant is None

    # Drain the worker.
    _drain_threadpool()

    # The assistant reply should have been attached.
    assert window._visualizer.chat_history[0].assistant == _ASSISTANT_REPLY
    # And the visualizer should be showing markdown again.
    assert window._visualizer.last_markdown is not None
    assert _ASSISTANT_REPLY in window._visualizer.last_markdown


def test_chat_emits_signal_for_mainwindow_to_handle(
    qapp, tmp_path, chat_engine
) -> None:
    """start_chat must emit chat_requested; MainWindow wires it to ChatWorker."""
    py_file = tmp_path / "x.py"
    py_file.write_text("x = 1\n", encoding="utf-8")
    window = MainWindow(services={"ai_engine": chat_engine})
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()

    captured: list[str] = []
    window._visualizer.chat_requested.connect(captured.append)
    # Type a message in the input, then trigger the send handler.
    window._visualizer._input.setPlainText("what does this file do?")
    window._visualizer._on_send_clicked()
    assert captured == ["what does this file do?"]


def test_chat_without_ai_engine_surfaces_error(qapp, tmp_path) -> None:
    """If services has no ai_engine, chat must show a friendly error."""
    py_file = tmp_path / "x.py"
    py_file.write_text("x = 1\n", encoding="utf-8")
    window = MainWindow()  # no services
    window._file_explorer.file_selected.emit(str(py_file))
    _drain_threadpool()
    window._visualizer._input.setPlainText("hi")
    window._visualizer._on_send_clicked()
    _drain_threadpool()
    # The pending turn was added but no assistant response came back.
    assert len(window._visualizer.chat_history) == 1
    assert window._visualizer.chat_history[0].assistant is None
    # Visualizer shows the "no AI engine" error.
    assert window._visualizer.last_error is not None
    assert "No AI engine" in window._visualizer.last_error
