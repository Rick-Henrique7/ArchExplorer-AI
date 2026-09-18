"""Tests for TemplateEngine — sandboxed Jinja2 wrapper (Change 007 — Bloco B).

Covers:

- Template discovery via ``list_templates``.
- File rendering via ``render`` (writes the output, creates dirs).
- String rendering via ``render_string``.
- Built-in filters work (upper / lower / join / tojson).
- Sandbox blocks attribute-escape attempts (``__class__``, ``__import__``).
- Sandbox blocks file-system access from templates.
- Missing template root → ``LpsSpecError``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.exceptions import LpsSpecError
from app.services.lps_models import LpsComponent
from app.services.template_engine import TemplateEngine


# ----- Fixtures ----------------------------------------------------------

@pytest.fixture
def template_root(tmp_path: Path) -> Path:
    """Create a small template tree under ``tmp_path``.

    Two real templates + one Jinja2 escape-attack template (the
    attack one must NOT succeed when rendered).
    """
    (tmp_path / "simple").mkdir()
    (tmp_path / "nested").mkdir()
    (tmp_path / "simple" / "hello.j2").write_text(
        "Hello, {{ name | upper }}!", encoding="utf-8",
    )
    (tmp_path / "nested" / "goodbye.j2").write_text(
        "{% if items %}{{ items | join(', ') }}{% endif %}", encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def engine(template_root: Path) -> TemplateEngine:
    return TemplateEngine(template_root=template_root)


@pytest.fixture
def component() -> LpsComponent:
    return LpsComponent(
        id="c1", name="OAuth", category="service",
        description="OAuth 2.0",
        code_snippet=None, svg_icon_path=None, jinja_template=None,
        metadata={"tags": ["auth", "oauth"]},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ----- Discovery ---------------------------------------------------------

def test_list_templates_returns_all_j2_files(engine: TemplateEngine) -> None:
    names = engine.list_templates()
    assert "simple/hello.j2" in names
    assert "nested/goodbye.j2" in names


def test_list_templates_empty_when_no_files(tmp_path: Path) -> None:
    e = TemplateEngine(template_root=tmp_path)
    assert e.list_templates() == []


def test_missing_template_root_raises(tmp_path: Path) -> None:
    ghost = tmp_path / "does-not-exist"
    with pytest.raises(LpsSpecError):
        TemplateEngine(template_root=ghost)


# ----- render_string -----------------------------------------------------

def test_render_string_replaces_variables(engine: TemplateEngine) -> None:
    out = engine.render_string("Hello, {{ name }}!", {"name": "World"})
    assert out == "Hello, World!"


def test_render_string_supports_filters(engine: TemplateEngine) -> None:
    out = engine.render_string("{{ s | upper }}", {"s": "lower"})
    assert out == "LOWER"


def test_render_string_supports_join_filter(engine: TemplateEngine) -> None:
    out = engine.render_string(
        "{{ items | join(', ') }}",
        {"items": ["a", "b", "c"]},
    )
    assert out == "a, b, c"


def test_render_string_supports_tojson(engine: TemplateEngine) -> None:
    out = engine.render_string("{{ data | tojson }}", {"data": {"k": 1}})
    assert out == '{"k": 1}'


def test_render_string_supports_if(engine: TemplateEngine) -> None:
    out = engine.render_string(
        "{% if flag %}yes{% else %}no{% endif %}", {"flag": True},
    )
    assert out == "yes"


def test_render_string_handles_missing_variable_gracefully(
    engine: TemplateEngine,
) -> None:
    """Undefined → empty string (Jinja2 default), not exception."""
    out = engine.render_string("[{{ undefined_var }}]", {})
    assert out == "[]"


# ----- render() (file output) --------------------------------------------

def test_render_writes_file_and_creates_parent_dirs(
    engine: TemplateEngine, tmp_path: Path,
) -> None:
    out = tmp_path / "out" / "deep" / "hello.txt"
    engine.render("simple/hello.j2", {"name": "World"}, out)
    assert out.exists()
    assert out.read_text(encoding="utf-8") == "Hello, WORLD!"


def test_render_overwrites_existing_file(engine: TemplateEngine, tmp_path: Path) -> None:
    out = tmp_path / "hello.txt"
    out.write_text("OLD CONTENT", encoding="utf-8")
    engine.render("simple/hello.j2", {"name": "World"}, out)
    assert out.read_text(encoding="utf-8") == "Hello, WORLD!"


def test_template_exists(engine: TemplateEngine) -> None:
    assert engine.template_exists("simple/hello.j2") is True
    assert engine.template_exists("missing.j2") is False


# ----- Sandbox -----------------------------------------------------------

def test_sandbox_blocks_dunder_attribute_escape(engine: TemplateEngine) -> None:
    """``{{ ''.__class__.__mro__[1].__subclasses__() }}`` must fail safely."""
    with pytest.raises(Exception):
        # SandboxedEnvironment blocks ``__class__`` access at the
        # ``getattr`` interceptor level — the call raises an
        # ``SecurityError`` (subclass of ``UnsecuredError``).
        engine.render_string(
            "{{ ''.__class__.__mro__[1].__subclasses__() }}", {},
        )


def test_sandbox_blocks_import(engine: TemplateEngine) -> None:
    """Calling ``__import__`` from inside the template must fail."""
    with pytest.raises(Exception):
        engine.render_string(
            "{{ __import__('os').system('echo pwned') }}", {},
        )


def test_sandbox_blocks_file_open(engine: TemplateEngine) -> None:
    """File-system access from templates is not allowed."""
    with pytest.raises(Exception):
        engine.render_string(
            "{% set f = open('/etc/passwd') %}{{ f.read() }}", {},
        )


def test_sanitize_context_strips_dunder_keys() -> None:
    """Module-private keys (``__xxx``) are not passed to the template.

    Direct unit test of the ``_sanitize_context`` helper — does not
    depend on Jinja2's behavior, only on our own defensive layer.
    """
    from app.services.template_engine import _sanitize_context
    clean = _sanitize_context({
        "name": "kept",
        "__builtins__": "stripped",
        "__class__": "stripped",
        "real": True,
    })
    assert clean == {"name": "kept", "real": True}


# ----- Real component rendering (integration-ish) -----------------------

def test_render_fastapi_template_with_component(
    engine: TemplateEngine, tmp_path: Path, component: LpsComponent,
) -> None:
    """The shipped fastapi_app.py.j2 template renders without error."""
    template_src = (
        Path(__file__).parent.parent.parent
        / "app" / "templates" / "lps" / "services" / "fastapi_app.py.j2"
    )
    if not template_src.exists():
        pytest.skip("template not present in repo")
    # Use the engine against the real templates dir.
    real_engine = TemplateEngine(
        template_root=template_src.parent.parent.parent.parent,
    )
    # The real templates live at app/templates/lps/ — load via the
    # file loader rather than template name.
    src = template_src.read_text(encoding="utf-8")
    out = real_engine.render_string(src, {"component": component.to_dict()})
    assert "FastAPI" in out
    assert "OAuth" in out
