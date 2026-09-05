"""Tests for the AnalysisWorker (run synchronously in the test thread).

The worker is a QRunnable normally submitted to a QThreadPool. In these
tests we call ``worker.run()`` directly to keep the tests fast and
deterministic. Signal capture is done by connecting to a list.
"""

from __future__ import annotations

from app.services import (
    AIServiceUnavailableError,
    AIEngine,
    MockAIProvider,
)
from app.ui.analysis_worker import AIEditWorker, AnalysisWorker, ChatWorker


def test_worker_emits_finished_with_provider_response() -> None:
    provider = MockAIProvider({"Padrões": "## Padrões\n- Singleton"})
    engine = AIEngine(provider)
    worker = AnalysisWorker(
        ai_engine=engine,
        code_content="class Foo: pass",
        file_type="python",
    )
    captured: list[str] = []
    worker.signals.finished.connect(captured.append)
    worker.run()
    assert len(captured) == 1
    assert "Singleton" in captured[0]


def test_worker_emits_failed_on_ai_service_error() -> None:
    class FailingProvider:
        def generate(self, prompt, *, system=None, temperature=None):
            raise AIServiceUnavailableError("connection refused")

    engine = AIEngine(FailingProvider())
    worker = AnalysisWorker(
        ai_engine=engine,
        code_content="x",
        file_type="python",
    )
    captured: list[str] = []
    worker.signals.failed.connect(captured.append)
    worker.run()
    assert len(captured) == 1
    assert "AI service unavailable" in captured[0]
    assert "connection refused" in captured[0]


def test_worker_emits_failed_on_unexpected_error() -> None:
    class ExplodingProvider:
        def generate(self, prompt, *, system=None, temperature=None):
            raise ValueError("boom")

    engine = AIEngine(ExplodingProvider())
    worker = AnalysisWorker(
        ai_engine=engine,
        code_content="x",
        file_type="python",
    )
    captured: list[str] = []
    worker.signals.failed.connect(captured.append)
    worker.run()
    assert len(captured) == 1
    assert "ValueError" in captured[0]
    assert "boom" in captured[0]


def test_worker_emits_exactly_one_signal() -> None:
    """Success or failure, never both, never zero."""
    provider = MockAIProvider()
    engine = AIEngine(provider)
    worker = AnalysisWorker(
        ai_engine=engine,
        code_content="x",
        file_type="python",
    )
    finished: list[str] = []
    failed: list[str] = []
    worker.signals.finished.connect(finished.append)
    worker.signals.failed.connect(failed.append)
    worker.run()
    assert len(finished) + len(failed) == 1


def test_worker_passes_code_content_to_engine() -> None:
    captured_prompts: list[str] = []

    class SpyProvider:
        def generate(self, prompt, *, system=None, temperature=None):
            captured_prompts.append(prompt)
            return "ok"

    engine = AIEngine(SpyProvider())
    worker = AnalysisWorker(
        ai_engine=engine,
        code_content="class A:\n    pass\nclass B:\n    pass",
        file_type="python",
    )
    worker.run()
    assert len(captured_prompts) == 1
    # Both classes are present in the prompt
    assert "class A:" in captured_prompts[0]
    assert "class B:" in captured_prompts[0]


def test_worker_accepts_optional_file_label() -> None:
    """The file_label is for logging only; it does not affect the prompt."""
    provider = MockAIProvider()
    engine = AIEngine(provider)
    worker = AnalysisWorker(
        ai_engine=engine,
        code_content="x = 1",
        file_type="python",
        file_label="x.py",
    )
    captured: list[str] = []
    worker.signals.finished.connect(captured.append)
    worker.run()
    assert len(captured) == 1


# ---------------------------------------------------------------------------
# AIEditWorker (Change 005)
# ---------------------------------------------------------------------------


def test_ai_edit_worker_emits_new_content() -> None:
    provider = MockAIProvider({"Instrução do usuário:": "def foo():\n    pass\n"})
    engine = AIEngine(provider)
    worker = AIEditWorker(
        ai_engine=engine,
        current_content="x = 1",
        instruction="rename x to y",
        file_type="python",
        file_path="/tmp/x.py",
    )
    captured: list[str] = []
    worker.signals.finished.connect(captured.append)
    worker.run()
    assert len(captured) == 1
    assert "def foo" in captured[0]


def test_ai_edit_worker_emits_failed_on_ai_error() -> None:
    class FailingProvider:
        def generate(self, prompt, *, system=None, temperature=None):
            raise AIServiceUnavailableError("ollama down")

    engine = AIEngine(FailingProvider())
    worker = AIEditWorker(
        ai_engine=engine,
        current_content="x",
        instruction="do something",
        file_type="python",
    )
    captured: list[str] = []
    worker.signals.failed.connect(captured.append)
    worker.run()
    assert len(captured) == 1
    assert "AI service unavailable" in captured[0]


def test_ai_edit_worker_emits_failed_on_unexpected_error() -> None:
    class ExplodingProvider:
        def generate(self, prompt, *, system=None, temperature=None):
            raise RuntimeError("kaboom")

    engine = AIEngine(ExplodingProvider())
    worker = AIEditWorker(
        ai_engine=engine,
        current_content="x",
        instruction="do",
        file_type="python",
    )
    captured: list[str] = []
    worker.signals.failed.connect(captured.append)
    worker.run()
    assert len(captured) == 1
    assert "RuntimeError" in captured[0]


# ---------------------------------------------------------------------------
# ChatWorker (Change 005)
# ---------------------------------------------------------------------------


def test_chat_worker_emits_response() -> None:
    provider = MockAIProvider({"Usuário:": "Olá! Como posso ajudar?"})
    engine = AIEngine(provider)
    worker = ChatWorker(
        ai_engine=engine,
        prompt="Usuário: olá\nAssistente:",
        user_msg="olá",
    )
    captured: list[str] = []
    worker.signals.finished.connect(captured.append)
    worker.run()
    assert len(captured) == 1
    assert captured[0] == "Olá! Como posso ajudar?"


def test_chat_worker_emits_failed_on_ai_error() -> None:
    class FailingProvider:
        def generate(self, prompt, *, system=None, temperature=None):
            raise AIServiceUnavailableError("refused")

    engine = AIEngine(FailingProvider())
    worker = ChatWorker(
        ai_engine=engine,
        prompt="Usuário: oi\nAssistente:",
        user_msg="oi",
    )
    captured: list[str] = []
    worker.signals.failed.connect(captured.append)
    worker.run()
    assert len(captured) == 1
    assert "AI service unavailable" in captured[0]


def test_chat_worker_emits_failed_on_unexpected_error() -> None:
    class ExplodingProvider:
        def generate(self, prompt, *, system=None, temperature=None):
            raise ValueError("bad prompt")

    engine = AIEngine(ExplodingProvider())
    worker = ChatWorker(
        ai_engine=engine,
        prompt="x",
        user_msg="x",
    )
    captured: list[str] = []
    worker.signals.failed.connect(captured.append)
    worker.run()
    assert len(captured) == 1
    assert "ValueError" in captured[0]


def test_chat_worker_uses_conversational_temperature() -> None:
    """Chat replies should use a slightly higher temperature than edits (0.3)."""
    captured: dict = {}

    class _Capture:
        def generate(self, prompt, *, system=None, temperature=None):
            captured["temperature"] = temperature
            return "ok"

    engine = AIEngine(_Capture())
    worker = ChatWorker(ai_engine=engine, prompt="x", user_msg="x")
    worker.run()
    assert captured["temperature"] == 0.3
