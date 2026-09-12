"""Tests for CatalogoService (Bloco B + C + D).

Uses SQLite in-memory (`:memory:`) for speed and isolation. The
schema is the same as the production DB — same triggers, FTS5,
constraints — so tests exercise the real code path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import (
    CatalogoService,
    CatalogoError,
    Entry,
    normalize_tags,
)


@pytest.fixture
def service(tmp_path: Path) -> CatalogoService:
    """Fresh service per test, backed by an isolated SQLite file."""
    db_path = tmp_path / "test_catalogo.db"
    return CatalogoService(db_path=db_path)


# ----- Construction / schema ----------------------------------------------


def test_creates_db_file_if_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "sub" / "dir" / "x.db"
    assert not db_path.exists()
    CatalogoService(db_path=db_path)
    assert db_path.exists()


def test_schema_has_required_tables(service: CatalogoService) -> None:
    with service._connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {row["name"] for row in rows}
    assert "entries" in names
    assert "tags" in names
    assert "entry_tags" in names
    assert "_migrations" in names


def test_schema_has_fts5_virtual_table(service: CatalogoService) -> None:
    with service._connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entries_fts'"
        ).fetchall()
    assert len(rows) == 1, "FTS5 virtual table missing"


def test_schema_has_triggers(service: CatalogoService) -> None:
    with service._connect() as conn:
        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
    names = {row["name"] for row in triggers}
    assert "entries_ai" in names
    assert "entries_ad" in names
    assert "entries_au" in names


def test_existing_db_is_reopened_not_recreated(tmp_path: Path) -> None:
    db_path = tmp_path / "x.db"
    s1 = CatalogoService(db_path=db_path)
    e = s1.create_entry(title="test", code="x = 1")
    # New instance pointing to the same file should see the existing entry.
    s2 = CatalogoService(db_path=db_path)
    assert s2.get_entry(e.id) is not None


# ----- create_entry ------------------------------------------------------


def test_create_entry_returns_entry_with_id(service: CatalogoService) -> None:
    e = service.create_entry(
        title="Cache LRU",
        code="class LRU: pass",
        language="python",
        tags=["python", "cache"],
    )
    assert isinstance(e, Entry)
    assert e.id > 0
    assert e.title == "Cache LRU"
    assert e.language == "python"
    # Tags are returned alphabetically (case-insensitive).
    assert e.tags == ("cache", "python")


def test_create_entry_dedups_tags(service: CatalogoService) -> None:
    e = service.create_entry(
        title="X", code="y",
        tags=["Python", "python", "PYTHON", "cache"],
    )
    # Dedup + sorted alphabetically.
    assert e.tags == ("cache", "python")


def test_create_entry_persists_to_disk(service: CatalogoService) -> None:
    e = service.create_entry(title="X", code="y")
    # Re-fetch via get_entry
    fetched = service.get_entry(e.id)
    assert fetched is not None
    assert fetched.title == "X"


def test_create_entry_empty_title_raises(service: CatalogoService) -> None:
    with pytest.raises(CatalogoError, match="Title is required"):
        service.create_entry(title="", code="x")


def test_create_entry_whitespace_only_title_raises(service: CatalogoService) -> None:
    with pytest.raises(CatalogoError, match="Title is required"):
        service.create_entry(title="   \t\n", code="x")


def test_create_entry_too_long_title_raises(service: CatalogoService) -> None:
    with pytest.raises(CatalogoError, match="too long"):
        service.create_entry(title="a" * 201, code="x")


def test_create_entry_empty_code_raises(service: CatalogoService) -> None:
    with pytest.raises(CatalogoError, match="Code is required"):
        service.create_entry(title="x", code="")


def test_create_entry_too_long_code_raises(service: CatalogoService) -> None:
    with pytest.raises(CatalogoError, match="too long"):
        service.create_entry(title="x", code="x" * 100_001)


def test_create_entry_invalid_origin_line_raises(service: CatalogoService) -> None:
    with pytest.raises(CatalogoError, match="origin_line"):
        service.create_entry(title="x", code="y", origin_line=0)


def test_create_entry_stores_timestamps(service: CatalogoService) -> None:
    e = service.create_entry(title="x", code="y")
    assert e.created_at is not None
    assert e.updated_at is not None


def test_create_entry_with_origin(service: CatalogoService) -> None:
    e = service.create_entry(
        title="x", code="y", origin_path="/tmp/x.py", origin_line=42
    )
    fetched = service.get_entry(e.id)
    assert fetched is not None
    assert fetched.origin_path == "/tmp/x.py"
    assert fetched.origin_line == 42


# ----- get_entry ----------------------------------------------------------


def test_get_entry_returns_none_for_missing(service: CatalogoService) -> None:
    assert service.get_entry(99999) is None


# ----- update_entry -------------------------------------------------------


def test_update_entry_changes_specified_fields(service: CatalogoService) -> None:
    e = service.create_entry(title="old", code="old code", tags=["a"])
    updated = service.update_entry(e.id, title="new", code="new code", tags=["b", "c"])
    assert updated.title == "new"
    assert updated.code == "new code"
    assert updated.tags == ("b", "c")


def test_update_entry_leaves_unspecified_fields_alone(
    service: CatalogoService,
) -> None:
    e = service.create_entry(
        title="x", code="y", language="python", category="Patterns",
    )
    updated = service.update_entry(e.id, title="new")
    assert updated.title == "new"
    assert updated.language == "python"
    assert updated.category == "Patterns"


def test_update_entry_does_not_touch_tags_when_tags_none(
    service: CatalogoService,
) -> None:
    e = service.create_entry(title="x", code="y", tags=["a", "b"])
    updated = service.update_entry(e.id, title="new")  # tags not passed
    assert updated.tags == ("a", "b")


def test_update_entry_replaces_tags_when_empty_list(
    service: CatalogoService,
) -> None:
    e = service.create_entry(title="x", code="y", tags=["a", "b"])
    updated = service.update_entry(e.id, tags=[])
    assert updated.tags == ()


def test_update_entry_missing_raises(service: CatalogoService) -> None:
    with pytest.raises(CatalogoError, match="not found"):
        service.update_entry(99999, title="x")


def test_update_entry_validates_fields(service: CatalogoService) -> None:
    e = service.create_entry(title="x", code="y")
    with pytest.raises(CatalogoError, match="Code is required"):
        service.update_entry(e.id, code="")


def test_update_entry_bumps_updated_at(service: CatalogoService) -> None:
    import time
    e = service.create_entry(title="x", code="y")
    time.sleep(1.05)  # ensure timestamp differs at second granularity
    updated = service.update_entry(e.id, title="new")
    assert updated.updated_at > e.updated_at


# ----- delete_entry -------------------------------------------------------


def test_delete_entry_removes_it(service: CatalogoService) -> None:
    e = service.create_entry(title="x", code="y")
    service.delete_entry(e.id)
    assert service.get_entry(e.id) is None


def test_delete_entry_removes_tags_via_cascade(
    service: CatalogoService,
) -> None:
    e = service.create_entry(title="x", code="y", tags=["a", "b"])
    service.delete_entry(e.id)
    # Tags themselves remain (they can be reused), but the join rows are gone
    with service._connect() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) AS c FROM entry_tags WHERE entry_id = ?", (e.id,)
        ).fetchone()
    assert rows["c"] == 0


def test_delete_entry_missing_raises(service: CatalogoService) -> None:
    with pytest.raises(CatalogoError, match="not found"):
        service.delete_entry(99999)


# ----- list_entries -------------------------------------------------------


def test_list_entries_returns_all(service: CatalogoService) -> None:
    for i in range(5):
        service.create_entry(title=f"entry {i}", code=f"x = {i}")
    entries = service.list_entries()
    assert len(entries) == 5


def test_list_entries_orders_by_updated_at_desc(
    service: CatalogoService,
) -> None:
    import time
    e1 = service.create_entry(title="first", code="x")
    time.sleep(1.05)
    e2 = service.create_entry(title="second", code="y")
    entries = service.list_entries()
    assert [e.title for e in entries] == ["second", "first"]


def test_list_entries_filter_by_language(service: CatalogoService) -> None:
    service.create_entry(title="py1", code="x", language="python")
    service.create_entry(title="js1", code="y", language="javascript")
    py_only = service.list_entries(language="python")
    assert {e.title for e in py_only} == {"py1"}


def test_list_entries_filter_by_category(service: CatalogoService) -> None:
    service.create_entry(title="a", code="x", category="Performance")
    service.create_entry(title="b", code="y", category="Security")
    perf = service.list_entries(category="Performance")
    assert {e.title for e in perf} == {"a"}


def test_list_entries_filter_by_tag(service: CatalogoService) -> None:
    service.create_entry(title="a", code="x", tags=["python", "lru"])
    service.create_entry(title="b", code="y", tags=["python"])
    service.create_entry(title="c", code="z", tags=["sql"])
    lru = service.list_entries(tag="lru")
    assert {e.title for e in lru} == {"a"}


def test_list_entries_limit(service: CatalogoService) -> None:
    for i in range(10):
        service.create_entry(title=f"e{i}", code="x")
    assert len(service.list_entries(limit=3)) == 3


# ----- search_entries (FTS5) ---------------------------------------------


def test_search_finds_by_title(service: CatalogoService) -> None:
    service.create_entry(title="Cache LRU", code="x")
    service.create_entry(title="JWT middleware", code="y")
    results = service.search_entries("cache")
    assert {e.title for e in results} == {"Cache LRU"}


def test_search_finds_by_description(service: CatalogoService) -> None:
    service.create_entry(
        title="X", code="x", description="Implementação de cache LRU"
    )
    results = service.search_entries("LRU")
    assert len(results) == 1


def test_search_finds_by_code(service: CatalogoService) -> None:
    service.create_entry(title="X", code="class LRUCache:\n    pass")
    results = service.search_entries("LRUCache")
    assert len(results) == 1


def test_search_prefix_match(service: CatalogoService) -> None:
    """'cache*' should match 'cache', 'caching', 'cached', etc."""
    service.create_entry(title="caching helper", code="x")
    service.create_entry(title="JWT", code="y")
    results = service.search_entries("cach")
    assert {e.title for e in results} == {"caching helper"}


def test_search_multi_term_is_AND(service: CatalogoService) -> None:
    service.create_entry(title="Cache LRU", code="x")
    service.create_entry(title="Cache FIFO", code="y")
    service.create_entry(title="JWT", code="z")
    results = service.search_entries("cache lru")
    assert {e.title for e in results} == {"Cache LRU"}


def test_search_empty_query_returns_all(service: CatalogoService) -> None:
    service.create_entry(title="a", code="x")
    service.create_entry(title="b", code="y")
    results = service.search_entries("")
    assert len(results) == 2


def test_search_no_matches_returns_empty(service: CatalogoService) -> None:
    service.create_entry(title="X", code="y")
    assert service.search_entries("nothingmatches") == []


def test_search_results_have_tags(service: CatalogoService) -> None:
    e = service.create_entry(title="Cache LRU", code="x", tags=["python", "lru"])
    results = service.search_entries("cache")
    assert len(results) == 1
    assert results[0].tags == ("lru", "python")


# ----- list_tags / list_categories / list_languages / stats ----------------


def test_list_tags_returns_all_unique_tags(service: CatalogoService) -> None:
    service.create_entry(title="a", code="x", tags=["python", "cache"])
    service.create_entry(title="b", code="y", tags=["python", "lru"])
    tags = service.list_tags()
    names = {t.name for t in tags}
    assert names == {"python", "cache", "lru"}


def test_list_categories(service: CatalogoService) -> None:
    service.create_entry(title="a", code="x", category="Performance")
    service.create_entry(title="b", code="y", category="Performance")
    service.create_entry(title="c", code="z", category="Security")
    cats = service.list_categories()
    assert cats == ["Performance", "Security"]


def test_list_languages(service: CatalogoService) -> None:
    service.create_entry(title="a", code="x", language="python")
    service.create_entry(title="b", code="y", language="javascript")
    langs = service.list_languages()
    assert langs == ["javascript", "python"]  # alphabetical


def test_stats_counts_by_language_and_category(
    service: CatalogoService,
) -> None:
    service.create_entry(title="a", code="x", language="python", category="P")
    service.create_entry(title="b", code="y", language="python", category="P")
    service.create_entry(title="c", code="z", language="javascript", category="S")
    stats = service.stats()
    assert stats["total"] == 3
    assert stats["by_language"] == {"python": 2, "javascript": 1}
    assert stats["by_category"] == {"P": 2, "S": 1}


# ----- export_json / import_json -----------------------------------------


def test_export_json_returns_valid_payload(service: CatalogoService) -> None:
    service.create_entry(title="x", code="y", tags=["t1"])
    payload = service.export_json()
    data = json.loads(payload)  # type: ignore[name-defined]
    assert data["version"] == 1
    assert "exported_at" in data
    assert len(data["entries"]) == 1
    assert data["entries"][0]["title"] == "x"
    assert data["entries"][0]["tags"] == ["t1"]


def test_import_json_roundtrip(service: CatalogoService) -> None:
    service.create_entry(title="x", code="y", tags=["python"])
    service.create_entry(title="z", code="w", tags=["sql"])
    payload = service.export_json()
    # New empty service
    from pathlib import Path
    empty_path = Path(service.db_path).parent / "empty.db"
    empty = CatalogoService(db_path=empty_path)
    n = empty.import_json(payload)
    assert n == 2
    assert empty.list_entries()[0].title in {"x", "z"}


def test_import_json_malformed_raises(service: CatalogoService) -> None:
    with pytest.raises(CatalogoError, match="not valid JSON"):
        service.import_json("{ not json")


def test_import_json_missing_entries_key_raises(
    service: CatalogoService,
) -> None:
    with pytest.raises(CatalogoError, match="entries"):
        service.import_json(json.dumps({"version": 1}))


def test_import_json_creates_ids_new(service: CatalogoService) -> None:
    payload = json.dumps({
        "version": 1,
        "entries": [
            {"title": "x", "code": "y", "tags": ["python"], "language": "text",
             "description": None, "category": None, "origin_path": None,
             "origin_line": None, "is_public": False,
             "created_at": "2024-01-01T00:00:00", "updated_at": "2024-01-01T00:00:00"},
        ],
    })
    n = service.import_json(payload)
    assert n == 1
    # New id assigned (not 1, since there's no entry before)
    assert service.list_entries()[0].id > 0


# ----- default_catalog_path ------------------------------------------------


def test_default_catalog_path_returns_under_documents(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from app.services.catalog_service import default_catalog_path
    p = default_catalog_path()
    assert p.parent.name == "ArchExplorer"
    assert p.name == "catalogo.db"
