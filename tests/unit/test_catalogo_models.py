"""Tests for the catalog models (Entry, Tag) and normalize_tags.

Pure-Python tests — no SQLite required. Lives in tests/unit/ rather
than tests/integration/ because the dataclasses have no I/O.
"""

from __future__ import annotations

import pytest

from app.services import Entry, Tag, normalize_tags


# ----- normalize_tags -----------------------------------------------------


def test_normalize_tags_lowercases_and_strips() -> None:
    assert normalize_tags(["  Python  ", "CACHE", "lru"]) == ("python", "cache", "lru")


def test_normalize_tags_dedups_case_insensitive() -> None:
    assert normalize_tags(["python", "Python", "PYTHON", "py"]) == ("python", "py")


def test_normalize_tags_drops_empty() -> None:
    assert normalize_tags(["", "  ", "\t", "python"]) == ("python",)


def test_normalize_tags_caps_at_20() -> None:
    raw = [f"tag{i}" for i in range(30)]
    assert len(normalize_tags(raw)) == 20


def test_normalize_tags_drops_invalid_chars() -> None:
    # Tags with spaces, uppercase (we'll lowercase first), or non-alnum
    assert normalize_tags(["valid_tag", "tag with space", "tag-with-dash", "UPPER"]) == (
        "valid_tag", "tag-with-dash", "upper",
    )


def test_normalize_tags_accepts_tuples() -> None:
    assert normalize_tags(("python", "lru")) == ("python", "lru")


def test_normalize_tags_empty_input() -> None:
    assert normalize_tags([]) == ()
    assert normalize_tags(()) == ()


# ----- Entry dataclass ----------------------------------------------------


def test_entry_minimal_construction() -> None:
    e = Entry(id=1, title="Cache LRU", code="...")
    assert e.id == 1
    assert e.title == "Cache LRU"
    assert e.code == "..."
    assert e.language == "text"
    assert e.description is None
    assert e.category is None
    assert e.tags == ()
    assert e.is_public is False


def test_entry_is_frozen() -> None:
    e = Entry(id=1, title="X", code="Y")
    with pytest.raises(Exception):  # FrozenInstanceError, AttributeError, etc.
        e.title = "mutated"  # type: ignore[misc]


def test_entry_to_dict_roundtrip() -> None:
    e = Entry(
        id=42,
        title="Cache LRU",
        code="class LRU: pass",
        language="python",
        description="LRU cache",
        category="Performance",
        origin_path="/tmp/x.py",
        origin_line=10,
        is_public=True,
        tags=("python", "cache"),
    )
    d = e.to_dict()
    assert d["id"] == 42
    assert d["title"] == "Cache LRU"
    assert d["language"] == "python"
    assert d["is_public"] is True
    assert d["tags"] == ["python", "cache"]
    # Roundtrip
    e2 = Entry.from_dict(d)
    assert e2 == e


def test_entry_tags_is_tuple_not_list() -> None:
    """Frozen dataclass requires hashable fields; tags must be a tuple."""
    e = Entry(id=1, title="x", code="y", tags=("a", "b"))  # type: ignore[arg-type]
    assert isinstance(e.tags, tuple)


def test_entry_default_timestamps_are_close() -> None:
    """Default factory uses datetime.utcnow() — two consecutive calls
    should be within a few seconds of each other."""
    e1 = Entry(id=1, title="x", code="y")
    e2 = Entry(id=2, title="x", code="y")
    delta = abs((e1.created_at - e2.created_at).total_seconds())
    assert delta < 5


# ----- Tag dataclass ------------------------------------------------------


def test_tag_construction() -> None:
    t = Tag(id=1, name="python")
    assert t.id == 1
    assert t.name == "python"


def test_tag_is_frozen() -> None:
    t = Tag(id=1, name="python")
    with pytest.raises(Exception):
        t.name = "java"  # type: ignore[misc]
