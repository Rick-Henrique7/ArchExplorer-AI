"""Integration test against a real Ollama server.

These tests are **skipped by default** to keep CI fast and offline-safe.
Enable them locally with::

    $env:OLLAMA_TEST = '1'
    py -m pytest tests/integration/

Required: an Ollama server running on ``localhost:11434`` with
``qwen2.5-coder:3b`` pulled.
"""

from __future__ import annotations

import os

import pytest

from app.services import AIEngine, OllamaProvider

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("OLLAMA_TEST"),
        reason="set OLLAMA_TEST=1 to run live Ollama integration tests",
    ),
]


def test_ollama_smoke_prompt_returns_ok() -> None:
    """Sanity check: the live Ollama server responds to a minimal prompt.

    The 3B model occasionally wraps 'OK' in a markdown fence or adds
    a trailing newline, so we strip and uppercase before comparing.
    """
    provider = OllamaProvider(model="qwen2.5-coder:3b", timeout=120.0)
    response = provider.generate(
        "Reply with the single word: OK. Nothing else.",
        temperature=0.0,
    )
    assert response.strip().upper() == "OK"


def test_ollama_engine_extract_uml_structure_returns_mermaid_block() -> None:
    """End-to-end: AIEngine.extract_uml_structure produces a usable diagram."""
    provider = OllamaProvider(model="qwen2.5-coder:3b", timeout=120.0)
    engine = AIEngine(provider)
    code = "class User:\n    pass\nclass Order:\n    pass"
    response = engine.extract_uml_structure(code)
    assert "classDiagram" in response or "class" in response
    # The response should be sanitizable by MermaidRenderer.
    from app.services import MermaidRenderer
    sanitized = MermaidRenderer().sanitize(response)
    assert sanitized.strip(), "MermaidRenderer could not extract a diagram"
