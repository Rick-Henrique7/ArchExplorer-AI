"""Tests for the AIEngine, OllamaProvider, and MockAIProvider.

``OllamaProvider`` is exercised end-to-end via ``requests_mock`` so no
real HTTP traffic leaves the test process.
"""

from __future__ import annotations

import json

import pytest
import requests
import requests_mock

from app.services import (
    AIServiceUnavailableError,
    AIEngine,
    IAIProvider,
    MockAIProvider,
    OllamaProvider,
)


# ---------------------------------------------------------------------------
# MockAIProvider
# ---------------------------------------------------------------------------


def test_mock_returns_fixture_when_substring_matches() -> None:
    provider = MockAIProvider({"Hello": "World"})
    assert provider.generate("Hello, how are you?") == "World"


def test_mock_falls_back_to_deterministic_hash() -> None:
    provider = MockAIProvider()
    out1 = provider.generate("xyz unknown")
    out2 = provider.generate("xyz unknown")
    assert out1 == out2
    assert out1.startswith("[MOCK:")
    assert out1.endswith("]")


def test_mock_ignores_system_and_temperature_kwargs() -> None:
    provider = MockAIProvider()
    out = provider.generate("prompt", system="sys", temperature=0.5)
    assert isinstance(out, str)


def test_mock_add_fixture_extends_match_set() -> None:
    provider = MockAIProvider()
    provider.add_fixture("specific", "matched!")
    assert provider.generate("a specific trigger prompt") == "matched!"


def test_mock_satisfies_iai_provider_protocol() -> None:
    """Static structural check: MockAIProvider must be a valid IAIProvider."""
    provider: IAIProvider = MockAIProvider()
    assert hasattr(provider, "generate")


# ---------------------------------------------------------------------------
# OllamaProvider — HTTP mocked
# ---------------------------------------------------------------------------


def test_ollama_custom_timeout_is_accepted() -> None:
    """The timeout parameter is honored (no validation rejects large values)."""
    provider = OllamaProvider(timeout=300.0)
    # The provider should not raise on construction with a custom timeout.
    assert provider is not None


def test_ollama_app_uses_300s_timeout() -> None:
    """The app's bootstrap explicitly overrides to 300s for cold-reload safety.

    This test guards against a regression where someone removes the explicit
    timeout from app/main.py, which would cause the 120s default to
    re-emerge and the user-visible AI flow to time out on slow disks.
    """
    import inspect
    from app import main as app_main

    source = inspect.getsource(app_main)
    assert "OllamaProvider(timeout=300.0)" in source, (
        "app/main.py must instantiate OllamaProvider with timeout=300.0 "
        "to handle cold reloads of large models (1.9 GB+). Found:\n" + source
    )


def test_ollama_generate_success() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            text=json.dumps({"response": "Hello from Ollama"}),
        )
        provider = OllamaProvider()
        out = provider.generate("Hi")
        assert out == "Hello from Ollama"
        sent = m.last_request.json()
        assert sent["model"] == "qwen2.5-coder:3b"
        assert sent["prompt"] == "Hi"
        assert sent["stream"] is False


def test_ollama_generate_with_system_and_temperature() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            text=json.dumps({"response": "OK"}),
        )
        provider = OllamaProvider()
        provider.generate("Hi", system="You are a helper", temperature=0.5)
        sent = m.last_request.json()
        assert sent["system"] == "You are a helper"
        assert sent["options"]["temperature"] == 0.5


def test_ollama_generate_omits_optional_fields_when_not_provided() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            text=json.dumps({"response": "OK"}),
        )
        OllamaProvider().generate("Hi")
        sent = m.last_request.json()
        assert "system" not in sent
        assert "options" not in sent


def test_ollama_raises_on_connection_error() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            exc=requests.exceptions.ConnectionError("refused"),
        )
        provider = OllamaProvider()
        with pytest.raises(AIServiceUnavailableError) as exc_info:
            provider.generate("Hi")
        assert "Cannot reach Ollama" in exc_info.value.message


def test_ollama_raises_on_timeout() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            exc=requests.exceptions.Timeout("read timeout"),
        )
        with pytest.raises(AIServiceUnavailableError):
            OllamaProvider().generate("Hi")


def test_ollama_raises_on_http_error() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            status_code=500,
            text="internal error",
        )
        with pytest.raises(AIServiceUnavailableError) as exc_info:
            OllamaProvider().generate("Hi")
        assert exc_info.value.context.get("status") == 500


def test_ollama_raises_on_http_404() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            status_code=404,
            text="model not found",
        )
        with pytest.raises(AIServiceUnavailableError):
            OllamaProvider().generate("Hi")


def test_ollama_raises_on_invalid_json() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            text="not json at all",
        )
        with pytest.raises(AIServiceUnavailableError) as exc_info:
            OllamaProvider().generate("Hi")
        assert "not valid JSON" in exc_info.value.message


def test_ollama_raises_on_missing_response_field() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            text=json.dumps({"other": "field"}),
        )
        with pytest.raises(AIServiceUnavailableError):
            OllamaProvider().generate("Hi")


def test_ollama_uses_injected_session() -> None:
    custom_session = requests.Session()
    with requests_mock.Mocker(session=custom_session) as m:
        m.post(
            "http://localhost:11434/api/generate",
            text=json.dumps({"response": "ok"}),
        )
        provider = OllamaProvider(session=custom_session)
        assert provider.generate("Hi") == "ok"


def test_ollama_uses_custom_base_url_and_model() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://example.com:9999/api/generate",
            text=json.dumps({"response": "ok"}),
        )
        provider = OllamaProvider(
            base_url="http://example.com:9999/",
            model="custom-model",
        )
        assert provider.generate("Hi") == "ok"
        sent = m.last_request.json()
        assert sent["model"] == "custom-model"


def test_ollama_strips_trailing_slash_from_base_url() -> None:
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            text=json.dumps({"response": "ok"}),
        )
        provider = OllamaProvider(base_url="http://localhost:11434/")
        assert provider.base_url == "http://localhost:11434"
        provider.generate("Hi")


# ---------------------------------------------------------------------------
# AIEngine — orchestrator
# ---------------------------------------------------------------------------


def test_engine_provider_property_returns_injected_provider() -> None:
    provider = MockAIProvider()
    engine = AIEngine(provider)
    assert engine.provider is provider


def test_engine_generate_component_uses_prompt_template() -> None:
    provider = MockAIProvider({"Requirements:": "GENERATED_CODE"})
    engine = AIEngine(provider)
    out = engine.generate_component("Implement a Calculator", "/path/to/calc.py")
    assert out == "GENERATED_CODE"


def test_engine_generate_component_passes_context_path() -> None:
    captured: list[str] = []
    provider = MockAIProvider()
    # Replace the fallback capture by hooking add_fixture with the
    # context_path substring.
    engine = AIEngine(provider)
    provider.add_fixture("/some/path/file.py", "matched_by_path")
    out = engine.generate_component("reqs", "/some/path/file.py")
    assert out == "matched_by_path"


def test_engine_analyze_architecture_uses_provider() -> None:
    provider = MockAIProvider({"Patterns": "## Patterns\n- Singleton"})
    engine = AIEngine(provider)
    out = engine.analyze_architecture("class Foo: pass", "python")
    assert "Singleton" in out


def test_engine_extract_uml_structure() -> None:
    mermaid = "```mermaid\nclassDiagram\n  class Foo\n```"
    provider = MockAIProvider({"Convert the following": mermaid})
    engine = AIEngine(provider)
    out = engine.extract_uml_structure("class Foo: pass")
    assert "classDiagram" in out


def test_engine_extract_uml_structure_works_with_ollama_mocked() -> None:
    """End-to-end: AIEngine with OllamaProvider, HTTP mocked."""
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            text=json.dumps(
                {"response": "```mermaid\nclassDiagram\n  A --> B\n```"}
            ),
        )
        engine = AIEngine(OllamaProvider())
        out = engine.extract_uml_structure("class A:\n  pass\nclass B:\n  pass")
        assert "classDiagram" in out


def test_engine_propagates_provider_errors() -> None:
    """If the provider raises, the engine must not swallow it."""
    with requests_mock.Mocker() as m:
        m.post(
            "http://localhost:11434/api/generate",
            status_code=500,
            text="boom",
        )
        engine = AIEngine(OllamaProvider())
        with pytest.raises(AIServiceUnavailableError):
            engine.extract_uml_structure("class A: pass")
