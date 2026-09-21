"""Tests for FileSystemAgent sandbox (Change 007 — Bloco F — task F8).

Covers:

- Each tool's happy path.
- Path traversal rejection (``../escape``, ``/etc/passwd``).
- Invalid-character rejection (null bytes, backslashes, spaces).
- File size limit.
- Non-UTF-8 reads.
- Directory listing semantics.
- Construction outside of an existing workspace (mkdir -p behavior).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.exceptions import LlmToolError
from app.services.filesystem_agent import FileSystemAgent


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A per-test workspace under tmp_path/workspace."""
    p = tmp_path / "workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def agent(workspace: Path) -> FileSystemAgent:
    return FileSystemAgent(workspace_root=workspace)


# ----- Construction -----------------------------------------------------

def test_construct_creates_workspace_root(tmp_path: Path) -> None:
    """The agent creates the workspace dir if it doesn't exist."""
    target = tmp_path / "fresh" / "deep"
    assert not target.exists()
    FileSystemAgent(workspace_root=target)
    assert target.is_dir()


def test_workspace_root_property_is_resolved(
    agent: FileSystemAgent, workspace: Path,
) -> None:
    assert agent.workspace_root == workspace.resolve()


# ----- create_file -------------------------------------------------------

def test_create_file_writes_content(agent: FileSystemAgent, workspace: Path) -> None:
    msg = agent.create_file("hello.py", "print('hi')\n")
    assert "Created" in msg
    assert (workspace / "hello.py").read_text(encoding="utf-8") == "print('hi')\n"


def test_create_file_overwrites_existing(
    agent: FileSystemAgent, workspace: Path,
) -> None:
    agent.create_file("hello.py", "first")
    agent.create_file("hello.py", "second")
    assert (workspace / "hello.py").read_text(encoding="utf-8") == "second"


def test_create_file_creates_parent_dirs(
    agent: FileSystemAgent, workspace: Path,
) -> None:
    agent.create_file("deep/nested/file.py", "x = 1")
    assert (workspace / "deep" / "nested" / "file.py").exists()


def test_create_file_rejects_too_large(
    agent: FileSystemAgent,
) -> None:
    too_big = "x" * (1_048_577)  # 1 byte over the cap
    with pytest.raises(LlmToolError) as exc:
        agent.create_file("big.txt", too_big)
    assert exc.value.message == "file_too_large"


def test_create_file_rejects_path_traversal(agent: FileSystemAgent) -> None:
    """``../escape`` must not escape the workspace."""
    with pytest.raises(LlmToolError) as exc:
        agent.create_file("../escape.txt", "nope")
    assert exc.value.message == "path_traversal"


def test_create_file_rejects_absolute_paths(agent: FileSystemAgent) -> None:
    """/etc/passwd is rejected even though it passes the regex check
    (the regex allows ``/`` but the resolve() + startswith() check
    catches the escape).
    """
    # The regex matches ``/etc/passwd`` — but the resolved path is
    # outside the workspace, so the traversal guard fires.
    with pytest.raises(LlmToolError) as exc:
        agent.create_file("/etc/passwd", "nope")
    assert exc.value.message == "path_traversal"


def test_create_file_rejects_invalid_characters(agent: FileSystemAgent) -> None:
    """Spaces, null bytes, and ``\\`` are not allowed."""
    for bad in ["name with space.py", "evil\x00name.py", "back\\slash.py"]:
        with pytest.raises(LlmToolError) as exc:
            agent.create_file(bad, "x")
        assert exc.value.message == "invalid_chars"


def test_create_file_rejects_non_string_path(agent: FileSystemAgent) -> None:
    """A non-string path raises (defensive)."""
    with pytest.raises(LlmToolError):
        agent.create_file(123, "x")  # type: ignore[arg-type]


# ----- create_directory -------------------------------------------------

def test_create_directory_works(
    agent: FileSystemAgent, workspace: Path,
) -> None:
    msg = agent.create_directory("src")
    assert "Created" in msg
    assert (workspace / "src").is_dir()


def test_create_directory_recursive(
    agent: FileSystemAgent, workspace: Path,
) -> None:
    agent.create_directory("a/b/c")
    assert (workspace / "a" / "b" / "c").is_dir()


def test_create_directory_idempotent(agent: FileSystemAgent) -> None:
    """Creating an existing directory is a no-op (exist_ok=True)."""
    agent.create_directory("dup")
    agent.create_directory("dup")
    assert (agent.workspace_root / "dup").is_dir()


# ----- read_file --------------------------------------------------------

def test_read_file_returns_content(
    agent: FileSystemAgent, workspace: Path,
) -> None:
    target = workspace / "data.txt"
    target.write_text("hello world", encoding="utf-8")
    assert agent.read_file("data.txt") == "hello world"


def test_read_file_missing_raises(agent: FileSystemAgent) -> None:
    with pytest.raises(LlmToolError) as exc:
        agent.read_file("nope.txt")
    assert exc.value.message == "file_not_found"


def test_read_file_truncates_oversize(
    agent: FileSystemAgent, workspace: Path,
) -> None:
    big = "a" * 1_100_000
    target = workspace / "big.txt"
    target.write_text(big, encoding="utf-8")
    content = agent.read_file("big.txt")
    assert "[truncated]" in content
    # The on-disk file is untouched.
    assert target.read_text(encoding="utf-8") == big


def test_read_file_non_utf8_raises(
    agent: FileSystemAgent, workspace: Path,
) -> None:
    target = workspace / "binary.bin"
    target.write_bytes(b"\x80\x81\x82")  # invalid UTF-8
    with pytest.raises(LlmToolError) as exc:
        agent.read_file("binary.bin")
    assert exc.value.message == "not_utf8"


# ----- list_directory ---------------------------------------------------

def test_list_directory_returns_entries(
    agent: FileSystemAgent, workspace: Path,
) -> None:
    (workspace / "a.py").write_text("x")
    (workspace / "src").mkdir()
    entries = agent.list_directory(".")
    # Files come first (alphabetical), then dirs with trailing ``/``.
    assert entries == ["a.py", "src/"]


def test_list_directory_default_is_root(agent: FileSystemAgent) -> None:
    agent.create_file("z", "x")
    entries = agent.list_directory()  # no arg
    assert entries == ["z"]


def test_list_directory_not_a_dir(agent: FileSystemAgent) -> None:
    agent.create_file("solo.txt", "hi")
    with pytest.raises(LlmToolError) as exc:
        agent.list_directory("solo.txt")
    assert exc.value.message == "not_a_directory"


# ----- Cross-test guard -------------------------------------------------

def test_traversal_never_escapes_workspace(
    agent: FileSystemAgent, workspace: Path, tmp_path: Path,
) -> None:
    """All traversal variants are rejected, regardless of which tool."""
    variants = [
        ("create_file", {"file_path": "../escape", "content": "x"}),
        ("create_file", {"file_path": "a/../../etc", "content": "x"}),
        ("create_directory", {"dir_path": ".."}),
        ("read_file", {"file_path": "../etc/passwd"}),
        ("list_directory", {"dir_path": ".."}),
    ]
    for method_name, kwargs in variants:
        method = getattr(agent, method_name)
        with pytest.raises(LlmToolError) as exc:
            method(**kwargs)
        assert exc.value.message in {
            "path_traversal", "invalid_chars", "file_not_found",
            "not_a_directory",
        }, f"{method_name}({kwargs}) gave unexpected reason"
