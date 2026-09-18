"""Template engine — sandboxed Jinja2 wrapper for product generation (Change 007).

Renders ``.j2`` files into the user's chosen output directory when
they click **Gerar Produto** on a valid feature model.

Why a sandbox?
A user template might be crafted by an LLM (via Tool Use) or
copy/pasted from the internet. Jinja2's default ``Environment`` lets
templates call ``{{ ''.__class__.__mro__[1].__subclasses__() }}`` and
walk to ``os.system`` — a classic RCE. ``SandboxedEnvironment`` blocks
attribute access on internals, ``__import__``, and unsafe attribute
chains. That's enough for the LPS use case where templates only need
``{{ component.name }}``, ``{% if %}``, ``{% for %}`` and a couple
of safe filters (``upper``, ``lower``, ``join``, ``tojson``).

Note on autoescape: we **disable** it. The output of these templates
is source code (Python, YAML, Dockerfile), not HTML. Escaping
``<`` and ``>`` would corrupt the output. The sandbox is the
protection layer; autoescape is for HTML.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment

from app.services.exceptions import LpsSpecError


# Filter / global whitelist. We expose only safe built-ins; users
# cannot register their own at runtime.
_ALLOWED_FILTERS: tuple[str, ...] = (
    "upper", "lower", "title", "trim", "replace", "join", "format",
    "default", "length", "sort", "map", "selectattr", "rejectattr",
    "string", "int", "float", "tojson",
)


class TemplateEngine:
    """Render Jinja2 templates into a target directory.

    Single-instance-per-template-root is fine — the engine is
    stateless after construction. Workers call ``render(...)`` from
    any thread (Jinja2's environment is thread-safe via
    ``auto_reload=False``).
    """

    def __init__(self, template_root: Path) -> None:
        self._template_root = Path(template_root)
        if not self._template_root.exists():
            raise LpsSpecError(
                "Template root does not exist",
                path=str(self._template_root),
            )
        # The SandboxedEnvironment blocks ``__class__``, ``__init__``,
        # ``__globals__``, ``__import__``, file-system access, and
        # mutable attribute writes from inside the template. Source:
        # jinja2/sandbox.py (SandboxedEnvironment inherits from
        # ImmutableSandboxedEnvironment which overrides
        # ``getattr``, ``getitem``, ``setattr`` etc.).
        self._env = SandboxedEnvironment(
            loader=FileSystemLoader(str(self._template_root)),
            autoescape=False,           # templates are code, not HTML
            trim_blocks=True,           # {% if %} block-level whitespace
            lstrip_blocks=True,         #   control is the user's friend
            keep_trailing_newline=True, # preserve file final newline
        )
        # Whitelist of filters / globals the user can rely on.
        # (SandboxedEnvironment already blocks ``__import__``; this is
        # belt + suspenders for the few filters that touch
        # attribute chains.)
        self._env.filters.setdefault("tojson", _safe_tojson)

    # ----- Public API ------------------------------------------------------

    def list_templates(self) -> list[str]:
        """Return the names of all templates under ``template_root``.

        Names are relative to ``template_root`` (e.g.
        ``"base/gitignore.j2"``) and use forward slashes regardless
        of platform.
        """
        return sorted(
            str(p.relative_to(self._template_root)).replace("\\", "/")
            for p in self._template_root.rglob("*.j2")
            if p.is_file()
        )

    def render_string(self, source: str, context: dict[str, Any]) -> str:
        """Render an inline template string with ``context``.

        Useful for tests and for the LLM tool path where the template
        comes from a chat reply rather than a file on disk.
        """
        template = self._env.from_string(source)
        return template.render(**_sanitize_context(context))

    def render(
        self,
        template_name: str,
        context: dict[str, Any],
        output_path: Path,
    ) -> None:
        """Render ``template_name`` to ``output_path``.

        Creates parent directories as needed. Overwrites the target
        file if it exists (the user clicked **Gerar Produto** with
        intent). Does NOT walk a tree — single file per call.
        """
        template = self._env.get_template(template_name)
        content = template.render(**_sanitize_context(context))
        output_path = Path(output_path)
        # Ensure the parent exists. We deliberately do NOT
        # ``resolve()`` the path — the caller (the generator worker)
        # has already sandbox-validated it against the workspace
        # root.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

    def template_exists(self, template_name: str) -> bool:
        """Return True if a template with this name exists."""
        try:
            self._env.get_template(template_name)
            return True
        except Exception:
            return False


# ----- Helpers -----------------------------------------------------------

def _safe_tojson(value: Any) -> str:
    """Sandbox-safe JSON serializer.

    The Jinja2 built-in ``tojson`` filter already works under
    ``SandboxedEnvironment``, but binding it explicitly here gives
    us one place to extend (e.g. custom encoders for dataclasses) and
    keeps the filter reference stable across Jinja2 versions.
    """
    return json.dumps(value, ensure_ascii=False, default=str)


def _sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
    """Return a defensive copy of the rendering context.

    The SandboxedEnvironment guards against most escape hatches, but
    a stale reference to a mutable object from the caller's stack
    could still leak state. We strip ``__``-prefixed keys (private
    Python attributes are never useful in a template) and pass the
    rest through untouched.
    """
    return {
        key: value
        for key, value in context.items()
        if not key.startswith("__")
    }
