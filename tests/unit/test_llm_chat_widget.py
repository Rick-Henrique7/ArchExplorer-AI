"""Tests for LlmChatWidget (Change 007 — Bloco G).

The widget renders a transcript, swaps adapters, and runs the agent
loop via QThreadPool. We use monkeypatched LiteLlmAdapter (FakeLitellm)
to drive deterministic tool-call responses.

These tests do NOT exercise the worker thread itself (PySide6's
QThreadPool scheduling is hard to assert on); they call the worker's
``run()`` directly via a small adapter — same pattern used by
``test_analysis_worker.py``.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.services import (
    FileSystemAgent,
    LlmResponse,
    LiteLlmAdapter,
    ToolCall,
)
from app.ui.llm_chat_widget import LlmChatWidget


@dataclass
class _FakeFunction:
    name: str
    arguments: str


@dataclass
class _FakeToolCall:
    function: _FakeFunction


@dataclass
class _FakeMessage:
    content: str = ""
    tool_calls: list | None = None


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def model_dump(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class _FakeModelResponse:
    choices: list
    usage: _FakeUsage


class _FakeLitellm:
    def __init__(self) -> None:
        self.calls = []
        self.responses: list[_FakeModelResponse] = []

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            return _FakeModelResponse(
                choices=[_FakeChoice(_FakeMessage(content=""))],
                usage=_FakeUsage(),
            )
        return self.responses.pop(0)


@pytest.fixture
def fake_litellm(monkeypatch):
    fake = _FakeLitellm()
    monkeypatch.setattr(
        "app.services.llm_adapter._try_import_litellm", lambda: fake,
    )
    return fake


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    p = tmp_path / "ws"
    p.mkdir()
    return p


@pytest.fixture
def adapter(fake_litellm) -> LiteLlmAdapter:
    return LiteLlmAdapter({
        "active_provider": "ollama_local",
        "providers": {"ollama_local": {"model": "qwen2.5-coder:3b"}},
    })


@pytest.fixture
def widget(qapp, adapter, workspace) -> LlmChatWidget:
    return LlmChatWidget(
        adapter=adapter,
        agent=FileSystemAgent(workspace_root=workspace),
    )


def test_widget_starts_with_disabled_run_when_no_adapter(qapp) -> None:
    w = LlmChatWidget(adapter=None)
    assert w._run_button.isEnabled() is False


def test_widget_enables_run_when_adapter_provided(widget: LlmChatWidget) -> None:
    assert widget._run_button.isEnabled() is True


def test_set_adapter_swaps_enabled(widget: LlmChatWidget, adapter) -> None:
    widget.set_adapter(None)
    assert widget._run_button.isEnabled() is False
    widget.set_adapter(adapter)
    assert widget._run_button.isEnabled() is True


def test_append_user_message_appears_in_transcript(widget: LlmChatWidget) -> None:
    widget.append_user_message("hello")
    assert "hello" in widget._transcript.toPlainText()
    assert "Você" in widget._transcript.toPlainText()


def test_clear_transcript(widget: LlmChatWidget) -> None:
    widget.append_user_message("hi")
    widget.clear_transcript()
    assert widget._transcript.toPlainText() == ""


def test_run_without_input_is_noop(
    widget: LlmChatWidget, fake_litellm,
) -> None:
    widget._input.setText("")
    widget._on_run()
    # No LLM calls fired.
    assert fake_litellm.calls == []


def test_run_with_input_invokes_llm_and_renders_response(
    widget: LlmChatWidget, fake_litellm,
) -> None:
    fake_litellm.responses = [
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(content="Hi back"))],
            usage=_FakeUsage(),
        ),
    ]
    widget._input.setText("hello")
    widget.run_agent_sync()
    # The run button is re-enabled after completion.
    assert widget._run_button.isEnabled() is True
    # Transcript contains both the user prompt and the LLM response.
    body = widget._transcript.toPlainText()
    assert "hello" in body
    assert "Hi back" in body


def test_run_with_tool_call_creates_file(
    widget: LlmChatWidget, fake_litellm, workspace,
) -> None:
    """The LLM emits create_file → the agent runs it → file exists."""
    fake_litellm.responses = [
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(
                tool_calls=[_FakeToolCall(_FakeFunction(
                    name="create_file",
                    arguments='{"file_path": "main.py", "content": "print(1)"}',
                ))],
            ))],
            usage=_FakeUsage(),
        ),
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(content="created"))],
            usage=_FakeUsage(),
        ),
    ]
    widget._input.setText("cria main.py")
    widget.run_agent_sync()
    # The file should have been written.
    assert (workspace / "main.py").exists()
    assert (workspace / "main.py").read_text(encoding="utf-8") == "print(1)"
    # Transcript mentions the tool call.
    body = widget._transcript.toPlainText()
    assert "create_file" in body
    assert "cria main.py" in body
    assert "created" in body


def test_run_with_missing_agent_shows_status(
    widget: LlmChatWidget, fake_litellm,
) -> None:
    widget.set_agent(None)
    widget._input.setText("hi")
    widget._on_run()
    assert "FileSystemAgent" in widget._status.text() or "configurados" in widget._status.text()


def test_run_with_missing_adapter_shows_status(
    widget: LlmChatWidget, fake_litellm,
) -> None:
    widget.set_adapter(None)
    widget._input.setText("hi")
    widget._on_run()
    assert "Adapter" in widget._status.text() or "configurados" in widget._status.text()


def test_run_with_litellm_error_renders_error_block(
    widget: LlmChatWidget, fake_litellm,
) -> None:
    """A litellm.completion exception becomes a user-visible error."""
    def boom(**k):
        raise RuntimeError("network down")
    fake_litellm.completion = boom  # type: ignore[assignment]
    widget._input.setText("hi")
    widget.run_agent_sync()
    body = widget._transcript.toPlainText()
    assert "Erro" in body or "network down" in body
    assert widget._run_button.isEnabled() is True
