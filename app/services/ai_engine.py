"""AI engine — abstraction over local LLMs (Qwen 2.5 Coder via Ollama).

Three pieces:

- :class:`IAIProvider` (Protocol) — the contract every backend implements.
- :class:`OllamaProvider` — real HTTP client for a local Ollama server.
- :class:`MockAIProvider` — deterministic provider for tests and offline dev.
- :class:`AIEngine` — orchestrator exposing the 3 documented pipelines.

The engine never parses the LLM output — that is the
:class:`MermaidRenderer`'s job (or the caller's, for free-form answers).
"""

from __future__ import annotations

from typing import Final, Protocol

import requests

from app.services.exceptions import AIServiceUnavailableError


# ---------------------------------------------------------------------------
# Provider contract
# ---------------------------------------------------------------------------


class IAIProvider(Protocol):
    """Structural interface for any text-generation backend.

    Any class with a compatible ``generate`` method is acceptable — no
    inheritance required. ``AIEngine`` is typed against this Protocol.
    """

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
    ) -> str:
        ...


# ---------------------------------------------------------------------------
# Real backend: Ollama (HTTP)
# ---------------------------------------------------------------------------


class OllamaProvider:
    """HTTP client for a local Ollama server.

    Parameters
    ----------
    base_url:
        Ollama server root. Trailing slash is stripped.
    model:
        Name of the model to use (must be pulled on the server first).
    timeout:
        Per-request timeout in seconds. LLM inference is slow on CPU.
    session:
        Optional ``requests.Session`` (e.g. for retry, mocking, or auth).
        A new session is created if omitted.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:3b",
        timeout: float = 120.0,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._session = session or requests.Session()

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
    ) -> str:
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if system is not None:
            payload["system"] = system
        if temperature is not None:
            payload["options"] = {"temperature": temperature}

        url = f"{self._base_url}/api/generate"
        try:
            response = self._session.post(url, json=payload, timeout=self._timeout)
        except requests.RequestException as exc:
            raise AIServiceUnavailableError(
                f"Cannot reach Ollama at {url}",
                url=url,
                cause=str(exc),
            ) from exc

        if response.status_code >= 400:
            raise AIServiceUnavailableError(
                f"Ollama returned HTTP {response.status_code}",
                url=url,
                status=response.status_code,
                body=response.text[:500],
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise AIServiceUnavailableError(
                "Ollama response is not valid JSON",
                url=url,
            ) from exc

        text = data.get("response")
        if not isinstance(text, str):
            raise AIServiceUnavailableError(
                "Ollama response missing 'response' field",
                url=url,
            )
        return text


# ---------------------------------------------------------------------------
# Mock backend (tests + offline dev)
# ---------------------------------------------------------------------------


class MockAIProvider:
    """Deterministic provider for tests and offline development.

    Substring-matched fixtures take precedence. When no fixture matches,
    a stable pseudo-response derived from the prompt hash is returned
    (stable within a single Python process; PYTHONHASHSEED is disabled
    by pytest by default in some configs — tests should not rely on
    cross-run stability of the hash).
    """

    def __init__(self, fixtures: dict[str, str] | None = None) -> None:
        self._fixtures: dict[str, str] = dict(fixtures or {})

    def add_fixture(self, substring: str, response: str) -> None:
        """Register a new substring → response mapping."""
        self._fixtures[substring] = response

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
    ) -> str:
        del system, temperature  # not used in the mock
        for substring, response in self._fixtures.items():
            if substring in prompt:
                return response
        return f"[MOCK:{hash(prompt) & 0xFFFF:04x}]"


# ---------------------------------------------------------------------------
# Pipeline prompts
# ---------------------------------------------------------------------------


GENERATE_COMPONENT_PROMPT: Final[str] = """You are a code generator.
Create a {component_type} component at: {context_path}

Requirements:
{requirements}

Output the complete file content only. No explanations, no markdown fences.
"""


ANALYZE_ARCHITECTURE_PROMPT: Final[str] = """You are an expert software architect.
Analyze the following {file_type} code:

```
{code_content}
```

Identify:
- Architectural patterns used
- Coupling issues
- Responsibility leaks
- Refactoring suggestions

Respond in markdown with sections: ## Patterns, ## Issues, ## Suggestions.
"""


EXTRACT_UML_STRUCTURE_PROMPT: Final[str] = """Convert the following code into a Mermaid.js class diagram.

Code:
```
{code_content}
```

Output ONLY the Mermaid.js code inside a ```mermaid``` block. No explanations, no other text.
"""


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class AIEngine:
    """Three pipelines over any :class:`IAIProvider`.

    The engine builds a prompt from a class-level template, delegates the
    actual generation to the injected provider, and returns the raw
    response. No parsing — that is :class:`MermaidRenderer`'s job (or the
    caller's, for free-form answers).
    """

    def __init__(self, provider: IAIProvider) -> None:
        self._provider = provider

    @property
    def provider(self) -> IAIProvider:
        return self._provider

    def generate_component(
        self,
        prompt: str,
        context_path: str,
        *,
        component_type: str = "Python",
    ) -> str:
        """Generate a new component file from a high-level description.

        ``prompt`` is the requirements/spec; ``context_path`` is the
        intended file location (used to anchor the LLM's output).
        """
        full_prompt = GENERATE_COMPONENT_PROMPT.format(
            component_type=component_type,
            context_path=context_path,
            requirements=prompt,
        )
        return self._provider.generate(full_prompt)

    def analyze_architecture(self, code_content: str, file_type: str) -> str:
        """Ask the LLM to critique a code file's architecture."""
        full_prompt = ANALYZE_ARCHITECTURE_PROMPT.format(
            file_type=file_type,
            code_content=code_content,
        )
        return self._provider.generate(full_prompt, temperature=0.2)

    def extract_uml_structure(self, code_content: str) -> str:
        """Ask the LLM to convert a code file into Mermaid.js syntax."""
        full_prompt = EXTRACT_UML_STRUCTURE_PROMPT.format(code_content=code_content)
        return self._provider.generate(full_prompt, temperature=0.1)
