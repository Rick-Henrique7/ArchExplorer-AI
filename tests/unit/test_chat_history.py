"""Tests for the chat history features of VisualizerPanel (Change 005)."""

from __future__ import annotations

import os

from app.ui.visualizer import _CHAT_HISTORY_MAX, ChatTurn, VisualizerPanel


# ----- ChatTurn dataclass -------------------------------------------------


def test_chat_turn_defaults_assistant_to_none() -> None:
    turn = ChatTurn(user="hi")
    assert turn.assistant is None
    assert turn.file_path is None
    assert turn.timestamp  # auto-set


def test_chat_turn_preserves_explicit_values() -> None:
    turn = ChatTurn(
        user="hi",
        assistant="hello!",
        file_path="/tmp/x.py",
        timestamp="2026-01-01T00:00:00",
    )
    assert turn.assistant == "hello!"
    assert turn.file_path == "/tmp/x.py"
    assert turn.timestamp == "2026-01-01T00:00:00"


# ----- chat_history: LRU + cap --------------------------------------------


def test_initial_chat_history_is_empty(qapp) -> None:
    panel = VisualizerPanel()
    assert panel.chat_history == []


def test_start_chat_appends_turn(qapp) -> None:
    panel = VisualizerPanel()
    panel.start_chat("hello")
    assert len(panel.chat_history) == 1
    turn = panel.chat_history[0]
    assert turn.user == "hello"
    assert turn.assistant is None


def test_add_chat_response_marks_turn_as_answered(qapp) -> None:
    panel = VisualizerPanel()
    panel.start_chat("hello")
    panel.add_chat_response("hello", "hi back!")
    assert panel.chat_history[0].assistant == "hi back!"


def test_add_chat_response_ignores_unknown_message(qapp) -> None:
    """If the turn was cleared in between, the response is dropped silently."""
    panel = VisualizerPanel()
    panel.start_chat("hello")
    panel.clear_chat()
    panel.add_chat_response("hello", "orphan response")
    assert panel.chat_history == []


def test_lru_cap_drops_oldest_turn(qapp) -> None:
    panel = VisualizerPanel()
    # Insert more than the cap.
    for i in range(_CHAT_HISTORY_MAX + 5):
        panel.start_chat(f"msg {i}")
    # History should be capped at the limit, with the OLDEST dropped.
    assert len(panel.chat_history) == _CHAT_HISTORY_MAX
    assert panel.chat_history[0].user == f"msg 5"  # first 5 dropped
    assert panel.chat_history[-1].user == f"msg {_CHAT_HISTORY_MAX + 4}"


def test_clear_chat_resets_history_and_shows_idle(qapp) -> None:
    panel = VisualizerPanel()
    panel.start_chat("a")
    panel.start_chat("b")
    assert len(panel.chat_history) == 2
    panel.clear_chat()
    assert panel.chat_history == []
    assert panel.last_markdown is None
    assert panel.last_error is None


def test_start_chat_ignores_empty_message(qapp) -> None:
    panel = VisualizerPanel()
    panel.start_chat("")
    panel.start_chat("   ")
    assert panel.chat_history == []


def test_start_chat_strips_whitespace(qapp) -> None:
    panel = VisualizerPanel()
    panel.start_chat("  hello  \n")
    assert panel.chat_history[0].user == "hello"


# ----- File context binding ------------------------------------------------


def test_set_file_context_stores_path_and_content(qapp) -> None:
    panel = VisualizerPanel()
    panel.set_file_context("/tmp/x.py", "print('hi')")
    assert panel._file_context_path == "/tmp/x.py"
    assert panel._file_context_content == "print('hi')"


def test_set_file_context_can_be_cleared_with_none(qapp) -> None:
    panel = VisualizerPanel()
    panel.set_file_context("/tmp/x.py", "x")
    panel.set_file_context(None, None)
    assert panel._file_context_path is None
    assert panel._file_context_content is None


# ----- build_chat_prompt ---------------------------------------------------


def test_build_chat_prompt_without_file_context_just_message(qapp) -> None:
    panel = VisualizerPanel()
    prompt = panel.build_chat_prompt("what is X?")
    assert "what is X?" in prompt
    assert "Contexto" not in prompt
    assert "Histórico recente" not in prompt


def test_build_chat_prompt_with_file_context_includes_basename_and_code(
    qapp,
) -> None:
    panel = VisualizerPanel()
    panel.set_file_context(os.path.join("some", "deep", "calc.py"), "x = 1")
    prompt = panel.build_chat_prompt("explain x")
    assert "calc.py" in prompt
    assert "x = 1" in prompt
    assert "explain x" in prompt


def test_build_chat_prompt_includes_recent_history(qapp) -> None:
    panel = VisualizerPanel()
    panel.start_chat("first question")
    panel.add_chat_response("first question", "first answer")
    panel.start_chat("second question")
    panel.add_chat_response("second question", "second answer")
    prompt = panel.build_chat_prompt("third question")
    assert "first question" in prompt
    assert "first answer" in prompt
    assert "second question" in prompt
    assert "second answer" in prompt
    assert "third question" in prompt


def test_build_chat_prompt_excludes_pending_turns(qapp) -> None:
    """Pending turns (no assistant response yet) should not leak into the prompt."""
    panel = VisualizerPanel()
    panel.start_chat("first question")
    panel.add_chat_response("first question", "first answer")
    panel.start_chat("still pending")  # no add_chat_response
    prompt = panel.build_chat_prompt("new question")
    assert "still pending" not in prompt
    assert "first answer" in prompt


# ----- chat_requested signal ----------------------------------------------


def test_chat_requested_signal_is_emitted(qapp) -> None:
    panel = VisualizerPanel()
    captured: list[str] = []
    panel.chat_requested.connect(captured.append)
    panel.start_chat("ping")
    assert captured == ["ping"]


def test_chat_requested_signal_not_emitted_for_empty(qapp) -> None:
    panel = VisualizerPanel()
    captured: list[str] = []
    panel.chat_requested.connect(captured.append)
    panel.start_chat("")
    assert captured == []


# ----- theme API -----------------------------------------------------------


def test_set_theme_remembered_for_internal_renders(qapp) -> None:
    panel = VisualizerPanel()
    panel.set_theme("light")
    # _current_theme is private but used by _render_chat_history; just
    # confirm the setter sticks.
    assert panel._current_theme == "light"


# ----- spinner in loading HTML --------------------------------------------


def test_loading_html_template_has_spinner_and_keyframes() -> None:
    """The static loading template must contain the spinner SVG and CSS animation."""
    tpl = VisualizerPanel._LOADING_HTML_TEMPLATE
    assert "@keyframes" in tpl
    assert "spinner" in tpl.lower()
    assert "<svg" in tpl
    assert "<circle" in tpl
