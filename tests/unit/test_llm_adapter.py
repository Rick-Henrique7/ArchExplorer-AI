"""Tests for LlmAdapter / LiteLlmAdapter / run_agent_loop (Change 007 — Bloco F).

We don't make real HTTP calls. The LiteLLM dependency is imported
lazily and the test fixtures monkey-patch ``_try_import_litellm`` to
return a ``FakeLitellm`` that records the kwargs and returns canned
``ModelResponse`` objects shaped like the real one.

This pattern keeps the test fast and hermetic while still exercising
every code path: provider dispatch, kwargs assembly, tool-call
parsing, agent-loop termination, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.services import LlmResponse, LiteLlmAdapter, ToolCall, run_agent_loop
from app.services.exceptions import LlmToolError


# ----- Fakes --------------------------------------------------------------


@dataclass
class _FakeUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def model_dump(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class _FakeFunction:
    name: str
    arguments: str   # litellm serializes args as a JSON string


@dataclass
class _FakeToolCall:
    function: _FakeFunction


@dataclass
class _FakeMessage:
    content: str = ""
    tool_calls: list[_FakeToolCall] | None = None


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeModelResponse:
    choices: list[_FakeChoice]
    usage: _FakeUsage


class FakeLitellm:
    """Drop-in replacement for litellm that records every call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        # Each entry is the response the fake will return for that
        # call. ``None`` defaults to "empty content, no tool calls".
        self.scripts: list[_FakeModelResponse] = []

    def set_responses(self, responses: list[_FakeModelResponse]) -> None:
        self.scripts = responses

    def completion(self, **kwargs) -> _FakeModelResponse:  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        if not self.scripts:
            return _FakeModelResponse(
                choices=[_FakeChoice(_FakeMessage(content=""))],
                usage=_FakeUsage(),
            )
        return self.scripts.pop(0)


@pytest.fixture
def fake_litellm(monkeypatch):
    """Install a FakeLitellm into the LiteLlmAdapter lazy import."""
    fake = FakeLitellm()
    monkeypatch.setattr(
        "app.services.llm_adapter._try_import_litellm", lambda: fake,
    )
    # Also patch where LiteLlmAdapter reads it from (the module
    # already imported the original function — override via the
    # adapter constructor).
    return fake


@pytest.fixture
def ollama_adapter(fake_litellm) -> LiteLlmAdapter:
    return LiteLlmAdapter({
        "active_provider": "ollama_local",
        "providers": {
            "ollama_local": {"model": "qwen2.5-coder:3b", "base_url": "http://x"},
        },
    })


# ----- LlmAdapter basics --------------------------------------------------

def test_litellm_adapter_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        LiteLlmAdapter({"active_provider": "made_up", "providers": {}})


def test_litellm_adapter_missing_litellm_raises_llm_tool_error() -> None:
    """Without the [llm] extra, generate() raises LlmToolError."""
    a = LiteLlmAdapter({"active_provider": "ollama_local", "providers": {}})
    a._litellm = None  # bypass the import success in __init__
    with pytest.raises(LlmToolError) as exc:
        a.generate("hello")
    # The exception message itself is the reason (positional first arg).
    assert exc.value.message == "litellm_missing"


def test_generate_uses_provider_prefix_and_default_model(
    ollama_adapter: LiteLlmAdapter, fake_litellm: FakeLitellm,
) -> None:
    fake_litellm.set_responses([
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(content="hi"))],
            usage=_FakeUsage(total_tokens=5),
        )
    ])
    resp = ollama_adapter.generate("hello")
    assert resp.content == "hi"
    assert resp.provider == "ollama_local"
    assert "ollama/" in resp.model
    # The fake recorded one call; the model arg was the prefixed one.
    assert fake_litellm.calls[0]["model"] == "ollama/qwen2.5-coder:3b"
    # api_base came from config.
    assert fake_litellm.calls[0]["api_base"] == "http://x"


def test_generate_picks_api_key_from_env(
    fake_litellm: FakeLitellm, monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-xyz")
    adapter = LiteLlmAdapter({
        "active_provider": "openai",
        "providers": {
            "openai": {"model": "gpt-4o", "api_key_env": "OPENAI_API_KEY"},
        },
    })
    fake_litellm.set_responses([
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(content="ok"))],
            usage=_FakeUsage(),
        )
    ])
    adapter.generate("x")
    assert fake_litellm.calls[0]["api_key"] == "sk-test-xyz"


def test_generate_parses_tool_calls(
    ollama_adapter: LiteLlmAdapter, fake_litellm: FakeLitellm,
) -> None:
    """Tool calls come back as a JSON-string in ``function.arguments``."""
    fake_litellm.set_responses([
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(
                content="",
                tool_calls=[_FakeToolCall(_FakeFunction(
                    name="create_file",
                    arguments='{"file_path": "x.py", "content": "y = 1"}',
                ))],
            ))],
            usage=_FakeUsage(),
        )
    ])
    resp = ollama_adapter.generate("x", tools=[{"type": "function"}])
    assert len(resp.tool_calls) == 1
    tc = resp.tool_calls[0]
    assert tc.name == "create_file"
    assert tc.arguments == {"file_path": "x.py", "content": "y = 1"}


def test_generate_surfaces_litellm_exception(
    ollama_adapter: LiteLlmAdapter, fake_litellm: FakeLitellm,
) -> None:
    """Any litellm exception becomes LlmToolError(tool_failed)."""
    def boom(**kwargs):
        raise RuntimeError("network down")
    fake_litellm.completion = boom  # type: ignore[assignment]
    with pytest.raises(LlmToolError) as exc:
        ollama_adapter.generate("x")
    assert "network down" in str(exc.value)


def test_generate_stream_unsupported_with_tools(
    ollama_adapter: LiteLlmAdapter,
) -> None:
    with pytest.raises(LlmToolError):
        list(ollama_adapter.generate_stream("x", tools=[{"x": 1}]))


# ----- run_agent_loop -----------------------------------------------------


@dataclass
class _FakeToolExec:
    """Tool executor with the 4 file methods + a counter."""
    create_file: Any
    create_directory: Any
    read_file: Any
    list_directory: Any


def test_agent_loop_terminates_on_text_only(
    ollama_adapter: LiteLlmAdapter, fake_litellm: FakeLitellm,
) -> None:
    fake_litellm.set_responses([
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(content="done"))],
            usage=_FakeUsage(),
        )
    ])
    exec_calls: list = []
    exec_obj = _FakeToolExec(
        create_file=lambda **k: (exec_calls.append(("create_file", k)), "ok")[1],
        create_directory=lambda **k: (exec_calls.append(("create_directory", k)), "ok")[1],
        read_file=lambda **k: "content",
        list_directory=lambda **k: ["a", "b"],
    )
    final, transcript = run_agent_loop(
        adapter=ollama_adapter,
        user_prompt="hi",
        tool_executor=exec_obj,
        system_prompt="you are helpful",
        tools=[],
    )
    assert final == "done"
    # No tool calls → exec_calls is empty.
    assert exec_calls == []
    # Transcript has system + user + assistant.
    assert transcript[0]["role"] == "system"
    assert transcript[1]["role"] == "user"
    assert transcript[2]["role"] == "assistant"


def test_agent_loop_executes_tool_and_returns(
    ollama_adapter: LiteLlmAdapter, fake_litellm: FakeLitellm,
) -> None:
    """Round 1: tool call → execute → round 2: text answer."""
    fake_litellm.set_responses([
        # First round: model wants to write a file.
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(
                content="",
                tool_calls=[_FakeToolCall(_FakeFunction(
                    name="create_file",
                    arguments='{"file_path": "x.py", "content": "y = 1"}',
                ))],
            ))],
            usage=_FakeUsage(),
        ),
        # Second round: model answers with text.
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(content="created it"))],
            usage=_FakeUsage(),
        ),
    ])
    exec_obj = _FakeToolExec(
        create_file=lambda **k: "wrote",
        create_directory=lambda **k: "dir",
        read_file=lambda **k: "r",
        list_directory=lambda **k: [],
    )
    final, transcript = run_agent_loop(
        adapter=ollama_adapter,
        user_prompt="make x.py",
        tool_executor=exec_obj,
        system_prompt="",
        tools=[{"type": "function"}],
    )
    assert final == "created it"
    # Transcript: user, assistant(tool_call), tool, assistant(text).
    roles = [m["role"] for m in transcript]
    assert roles == ["user", "assistant", "tool", "assistant"]
    # The tool result was the string from the executor.
    assert transcript[2]["content"] == "wrote"


def test_agent_loop_surfaces_tool_error_to_llm(
    ollama_adapter: LiteLlmAdapter, fake_litellm: FakeLitellm,
) -> None:
    """LlmToolError is fed back as a tool result so the model can retry."""
    from app.services.exceptions import LlmToolError
    def boom(**k):
        raise LlmToolError("path_traversal", path="../escape")
    exec_obj = _FakeToolExec(
        create_file=boom,
        create_directory=lambda **k: "ok",
        read_file=lambda **k: "",
        list_directory=lambda **k: [],
    )
    fake_litellm.set_responses([
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(
                tool_calls=[_FakeToolCall(_FakeFunction(
                    name="create_file",
                    arguments='{"file_path": "../escape", "content": "x"}',
                ))],
            ))],
            usage=_FakeUsage(),
        ),
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(content="recovered"))],
            usage=_FakeUsage(),
        ),
    ])
    final, transcript = run_agent_loop(
        adapter=ollama_adapter,
        user_prompt="escape!",
        tool_executor=exec_obj,
        system_prompt="",
        tools=[{"type": "function"}],
    )
    assert final == "recovered"
    # The tool result message should mention ERROR and the reason.
    assert "ERROR" in transcript[2]["content"]
    assert "path_traversal" in transcript[2]["content"]


def test_agent_loop_max_iterations_limit(
    ollama_adapter: LiteLlmAdapter, fake_litellm: FakeLitellm,
) -> None:
    """Infinite-tool-call loop terminates at max_iterations."""
    # 3 rounds of tool calls, then a sentinel answer.
    fake_litellm.set_responses([
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(
                tool_calls=[_FakeToolCall(_FakeFunction(
                    name="create_file",
                    arguments='{"file_path": "x.py", "content": "1"}',
                ))],
            ))],
            usage=_FakeUsage(),
        ),
    ] * 5 + [
        _FakeModelResponse(
            choices=[_FakeChoice(_FakeMessage(content="ok"))],
            usage=_FakeUsage(),
        ),
    ])
    exec_obj = _FakeToolExec(
        create_file=lambda **k: "ok",
        create_directory=lambda **k: "ok",
        read_file=lambda **k: "ok",
        list_directory=lambda **k: [],
    )
    final, _ = run_agent_loop(
        adapter=ollama_adapter,
        user_prompt="loop",
        tool_executor=exec_obj,
        system_prompt="",
        tools=[],
        max_iterations=3,
    )
    # After 3 tool rounds the loop bails out.
    assert final == "(loop limit reached)"
