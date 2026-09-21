"""LLM adapter — multi-provider abstraction via LiteLLM (Change 007).

Public surface:

- :class:`LlmAdapter` — ``Protocol`` with ``generate`` + ``generate_stream``.
- :class:`LlmResponse` / :class:`ToolCall` — value objects returned to
  callers (GUI / workers).
- :class:`LiteLlmAdapter` — single concrete impl that talks to
  OpenAI / Anthropic / Gemini / Ollama / Cohere through ``litellm``.
- :func:`run_agent_loop` — Tool Use loop: takes the user's prompt,
  calls the LLM with ``tools=`` schemas, executes any tool calls via
  the :class:`~app.services.filesystem_agent.FileSystemAgent`, feeds
  results back, repeats until the LLM answers with content only
  (or ``max_iterations`` is hit).

## Why LiteLLM?

A single ``litellm.completion(...)`` call covers OpenAI, Anthropic,
Gemini, Ollama, Cohere, Azure, Bedrock and ~100 other providers.
For our use case the user picks a provider in a JSON config file
and we don't have to write per-provider auth + payload + error
handling.

The library is imported lazily — if the user doesn't install the
``[llm]`` extra, ``LiteLlmAdapter`` still imports but its
``generate()`` raises ``LlmAuthError`` on first call with a helpful
message ("run ``pip install arch-explorer-ai[llm]``").
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol, runtime_checkable

from app.services.exceptions import LlmToolError

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation the LLM asked us to perform.

    Attributes:
    - ``name``: tool identifier (matches the key in the schema list).
    - ``arguments``: parsed JSON dict (the LLM's payload).
    - ``raw``: the original payload (debug aid; differs from
      ``arguments`` only when the LLM uses stringified JSON instead
      of structured tool_calls).
    """

    name: str
    arguments: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LlmResponse:
    """The result of one LLM call.

    Either ``content`` is non-empty (the model answered), or
    ``tool_calls`` is non-empty (the model wants us to run a tool
    first). Both can be present in some providers — we treat the
    presence of tool_calls as "not done yet".
    """

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    provider: str = ""


@runtime_checkable
class LlmAdapter(Protocol):
    """The contract every LLM backend implements."""

    provider: str

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse: ...

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[str]: ...


# ---------------------------------------------------------------------------
# Tool schemas (Contrato 5 from the spec). Exposed as a module-level
# constant so the GUI and the FileSystemAgent agree on the wire format.
# ---------------------------------------------------------------------------

FILE_TOOL_CREATE_FILE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "create_file",
        "description": "Cria um novo arquivo de código na estrutura do projeto.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "pattern": r"^[a-zA-Z0-9._/\-]+$",
                    "description": "Caminho relativo ao workspace_root (sem ..).",
                },
                "content": {"type": "string", "description": "Conteúdo completo."},
            },
            "required": ["file_path", "content"],
            "additionalProperties": False,
        },
    },
}

FILE_TOOL_CREATE_DIR: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "create_directory",
        "description": "Cria uma nova pasta no projeto (recursivo).",
        "parameters": {
            "type": "object",
            "properties": {
                "dir_path": {"type": "string", "pattern": r"^[a-zA-Z0-9._/\-]+$"},
            },
            "required": ["dir_path"],
            "additionalProperties": False,
        },
    },
}

FILE_TOOL_READ_FILE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Lê o conteúdo de um arquivo existente (read-only).",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "pattern": r"^[a-zA-Z0-9._/\-]+$"},
            },
            "required": ["file_path"],
            "additionalProperties": False,
        },
    },
}

FILE_TOOL_LIST_DIR: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "list_directory",
        "description": "Lista arquivos e pastas de um diretório (read-only).",
        "parameters": {
            "type": "object",
            "properties": {
                "dir_path": {"type": "string", "pattern": r"^[a-zA-Z0-9._/\-]+$"},
            },
            "required": ["dir_path"],
            "additionalProperties": False,
        },
    },
}

FILE_TOOLS: list[dict[str, Any]] = [
    FILE_TOOL_CREATE_FILE,
    FILE_TOOL_CREATE_DIR,
    FILE_TOOL_READ_FILE,
    FILE_TOOL_LIST_DIR,
]


# ---------------------------------------------------------------------------
# Concrete adapter
# ---------------------------------------------------------------------------


# Per-provider default model + prefix for the litellm ``model=`` arg.
# The user can override per-provider in the JSON config.
_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai":       {"prefix": "openai",    "default_model": "gpt-4o"},
    "anthropic":    {"prefix": "anthropic", "default_model": "claude-3-5-sonnet-20241022"},
    "gemini":       {"prefix": "gemini",    "default_model": "gemini-1.5-pro"},
    "ollama_local": {"prefix": "ollama",    "default_model": "qwen2.5-coder:3b"},
    "cohere":       {"prefix": "cohere",    "default_model": "command-r-plus"},
}


class LiteLlmAdapter:
    """Single adapter that wraps ``litellm.completion`` for every provider.

    The config dict shape (one entry per provider):

    .. code-block:: python

        {
            "active_provider": "ollama_local",
            "providers": {
                "ollama_local": {"model": "qwen2.5-coder:3b",
                                 "base_url": "http://localhost:11434"},
                "openai":       {"model": "gpt-4o",
                                 "api_key_env": "OPENAI_API_KEY"},
                ...
            }
        }
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        active = config.get("active_provider", "")
        if active not in _PROVIDER_DEFAULTS:
            raise ValueError(
                f"Unknown active_provider {active!r}; "
                f"must be one of {list(_PROVIDER_DEFAULTS)}"
            )
        self.provider = active
        self._litellm = _try_import_litellm()

    # ----- Public API -----------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        if self._litellm is None:
            raise LlmToolError(
                "litellm_missing",
                hint=(
                    "Instale o extra [llm]: pip install arch-explorer-ai[llm]"
                ),
            )
        model_str = self._resolve_model()
        provider_cfg = self._provider_cfg()
        kwargs: dict[str, Any] = {
            "model": model_str,
            "messages": self._build_messages(prompt, system_prompt),
            "temperature": (
                temperature
                if temperature is not None
                else provider_cfg.get("temperature", 0.2)
            ),
            "max_tokens": (
                max_tokens
                if max_tokens is not None
                else provider_cfg.get("max_tokens", 4096)
            ),
        }
        # Provider-specific extras.
        if "base_url" in provider_cfg:
            kwargs["api_base"] = provider_cfg["base_url"]
        if "api_key_env" in provider_cfg:
            import os
            env_value = os.environ.get(provider_cfg["api_key_env"])
            if env_value:
                kwargs["api_key"] = env_value
        if tools:
            kwargs["tools"] = tools

        try:
            resp = self._litellm.completion(**kwargs)
        except Exception as exc:  # noqa: BLE001 — surface as LlmToolError
            raise LlmToolError(
                "tool_failed",
                detail=f"LLM call failed: {exc}",
                provider=self.provider,
            ) from exc

        return _litellm_response_to_ours(resp, self.provider, model_str)

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[str]:
        """Minimal streaming — yields raw text deltas.

        Tool Use over streaming is not supported in the initial
        cut; callers should use ``generate()`` when ``tools`` is
        non-empty.
        """
        if self._litellm is None:
            raise LlmToolError(
                "litellm_missing",
                hint="Install [llm] extra.",
            )
        if tools:
            raise LlmToolError(
                "stream_with_tools_unsupported",
                hint="Use generate() when tools is non-empty.",
            )
        model_str = self._resolve_model()
        kwargs: dict[str, Any] = {
            "model": model_str,
            "messages": self._build_messages(prompt, system_prompt),
            "stream": True,
        }
        provider_cfg = self._provider_cfg()
        if "base_url" in provider_cfg:
            kwargs["api_base"] = provider_cfg["base_url"]
        if "api_key_env" in provider_cfg:
            import os
            env_value = os.environ.get(provider_cfg["api_key_env"])
            if env_value:
                kwargs["api_key"] = env_value

        try:
            for chunk in self._litellm.completion(**kwargs):
                # ``chunk.choices[0].delta.content`` is a string or None.
                delta = _safe_attr(_safe_attr(chunk, "choices", [{}])[0], "delta", {})
                content = _safe_attr(delta, "content", None)
                if content:
                    yield content
        except Exception as exc:  # noqa: BLE001
            raise LlmToolError(
                "stream_failed",
                detail=f"LLM stream failed: {exc}",
            ) from exc

    # ----- Internal helpers -----------------------------------------------

    def _resolve_model(self) -> str:
        provider_cfg = self._provider_cfg()
        model_name = provider_cfg.get(
            "model", _PROVIDER_DEFAULTS[self.provider]["default_model"],
        )
        prefix = _PROVIDER_DEFAULTS[self.provider]["prefix"]
        return f"{prefix}/{model_name}"

    def _provider_cfg(self) -> dict[str, Any]:
        providers = self._config.get("providers") or {}
        cfg = providers.get(self.provider) or {}
        if not isinstance(cfg, dict):
            return {}
        return cfg

    @staticmethod
    def _build_messages(
        prompt: str, system_prompt: str,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _try_import_litellm() -> Any | None:
    """Import litellm lazily.

    Returns ``None`` when the package isn't installed, with a
    one-line log message. The adapter raises ``LlmToolError`` on
    the first ``generate()`` call so the user gets a clear path
    forward.
    """
    try:
        import litellm  # type: ignore
    except ImportError:
        _logger.warning(
            "litellm is not installed; LiteLlmAdapter will fail on use. "
            "Install with: pip install arch-explorer-ai[llm]",
        )
        return None
    return litellm


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Robust ``getattr`` that swallows anything unexpected.

    LiteLLM response objects vary slightly across providers and
    versions; rather than chain try/except at every read site,
    route them through this helper.
    """
    try:
        return getattr(obj, name)
    except Exception:  # noqa: BLE001
        return default


def _litellm_response_to_ours(
    resp: Any,
    provider: str,
    model_str: str,
) -> LlmResponse:
    """Translate a litellm ``ModelResponse`` into our :class:`LlmResponse`."""
    choice = _safe_attr(resp, "choices", [None])[0]
    message = _safe_attr(choice, "message", None)
    content = _safe_attr(message, "content", "") or ""
    tool_calls_raw = _safe_attr(message, "tool_calls", None) or []
    parsed_calls: list[ToolCall] = []
    for tc in tool_calls_raw:
        fn = _safe_attr(tc, "function", None)
        if fn is None:
            continue
        name = _safe_attr(fn, "name", "")
        args_raw = _safe_attr(fn, "arguments", "{}")
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
        except json.JSONDecodeError:
            args = {}
        parsed_calls.append(ToolCall(name=name, arguments=args, raw={}))
    usage = _safe_attr(resp, "usage", None)
    usage_dict: dict[str, Any] = {}
    if usage is not None:
        try:
            usage_dict = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
        except Exception:  # noqa: BLE001
            usage_dict = {}
    return LlmResponse(
        content=content,
        tool_calls=parsed_calls,
        usage=usage_dict,
        model=model_str,
        provider=provider,
    )


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


def run_agent_loop(
    *,
    adapter: LlmAdapter,
    user_prompt: str,
    tool_executor: Any,        # duck-typed: must expose the 4 file methods
    system_prompt: str,
    tools: list[dict[str, Any]],
    history: list[dict[str, Any]] | None = None,
    max_iterations: int = 10,
) -> tuple[str, list[dict[str, Any]]]:
    """Tool Use loop: prompt → tool_call(s) → execute → feed back → repeat.

    Returns ``(final_content, transcript)`` where ``transcript`` is the
    full message list including tool calls and tool results (useful
    for the GUI to show as a colored history).

    Termination:
    - Model returns no ``tool_calls`` → final ``content`` is the answer.
    - ``max_iterations`` reached → returns ``"(loop limit reached)"``.

    Failures of the executor surface as an ``LlmToolError``;
    the message is fed back to the LLM as a tool result so the model
    can self-correct on the next iteration (most providers accept
    a string payload on the ``tool`` role).
    """
    messages: list[dict[str, Any]] = list(history or [])
    if not messages:
        # First turn: build the initial system+user pair from the
        # top-level system_prompt / user_prompt.
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

    for iteration in range(max_iterations):
        resp = adapter.generate(
            "",  # unused — we pass messages directly via history arg below
            system_prompt="",
            tools=tools,
        ) if False else _adapter_generate_with_messages(adapter, messages, tools)

        # Record the assistant message for the transcript.
        assistant_payload: dict[str, Any] = {"role": "assistant"}
        if resp.content:
            assistant_payload["content"] = resp.content
        if resp.tool_calls:
            assistant_payload["tool_calls"] = [
                {
                    "id": f"call-{iteration}-{i}",
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for i, tc in enumerate(resp.tool_calls)
            ]
        messages.append(assistant_payload)

        if not resp.tool_calls:
            # Done — the model returned a final answer.
            return resp.content, messages

        # Execute each tool call and append the tool result to the
        # message history. We tolerate individual tool failures so
        # one bad call doesn't kill the loop.
        for i, tc in enumerate(resp.tool_calls):
            try:
                method = getattr(tool_executor, tc.name)
                result = method(**tc.arguments)
                tool_result = str(result)
            except LlmToolError as exc:
                # Feed the error back to the LLM — it may correct itself.
                tool_result = f"ERROR ({exc.context.get('reason', exc.__class__.__name__)}): {exc}"
            except Exception as exc:  # noqa: BLE001 — generic guard
                tool_result = f"ERROR: {exc}"
            messages.append({
                "role": "tool",
                "tool_call_id": f"call-{iteration}-{i}",
                "content": tool_result,
            })
    return "(loop limit reached)", messages


def _adapter_generate_with_messages(
    adapter: LlmAdapter,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> LlmResponse:
    """Internal helper that lets ``run_agent_loop`` pass a full message
    list to adapters (which otherwise take a single ``prompt``).

    The default :class:`LiteLlmAdapter` ignores ``prompt`` when ``tools``
    is set and uses the messages directly — but other adapters may
    not. We use duck-typing to call whichever signature the adapter
    supports.
    """
    if isinstance(adapter, LiteLlmAdapter):
        # Reach into the private helper so we can pass the full
        # message list. Using a private symbol keeps the public
        # Protocol surface small.
        return adapter._generate_with_messages(messages, tools=tools)
    raise LlmToolError(
        "adapter_does_not_support_loop",
        hint=(
            f"Adapter {type(adapter).__name__} doesn't implement message-"
            "based generation. Use LiteLlmAdapter."
        ),
    )


# Augment LiteLlmAdapter with a message-based helper. Defined here (not
# in the class body) to keep the diff against earlier versions small.
def _generate_with_messages(
    self: "LiteLlmAdapter",
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
) -> LlmResponse:
    if self._litellm is None:
        raise LlmToolError(
            "litellm_missing",
            hint="Install [llm] extra.",
        )
    model_str = self._resolve_model()
    provider_cfg = self._provider_cfg()
    kwargs: dict[str, Any] = {
        "model": model_str,
        "messages": list(messages),
        "temperature": provider_cfg.get("temperature", 0.2),
        "max_tokens": provider_cfg.get("max_tokens", 4096),
    }
    if "base_url" in provider_cfg:
        kwargs["api_base"] = provider_cfg["base_url"]
    if "api_key_env" in provider_cfg:
        import os
        env_value = os.environ.get(provider_cfg["api_key_env"])
        if env_value:
            kwargs["api_key"] = env_value
    if tools:
        kwargs["tools"] = tools
    try:
        resp = self._litellm.completion(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise LlmToolError(
            "tool_failed",
            detail=f"LLM call failed: {exc}",
            provider=self.provider,
        ) from exc
    return _litellm_response_to_ours(resp, self.provider, model_str)


# Bind to the class so the helper is callable as ``adapter._generate_with_messages``.
LiteLlmAdapter._generate_with_messages = _generate_with_messages  # type: ignore[attr-defined]
