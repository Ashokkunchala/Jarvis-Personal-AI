"""Tests for read-only local document memory (SQLite FTS5)."""

from __future__ import annotations

import os

import pytest

from jarvis.memory.doc_memory import DocMemory


@pytest.fixture()
def memory(tmp_path):
    return DocMemory(tmp_path / "docs.db")


@pytest.fixture()
def notes(tmp_path):
    folder = tmp_path / "fde-notes"
    folder.mkdir()
    (folder / "kubernetes.md").write_text(
        "# Kubernetes notes\n\nA pod is the smallest deployable unit.\n"
        "Use readiness probes before traffic.\n",
        encoding="utf-8",
    )
    (folder / "aws.md").write_text(
        "# AWS\n\nS3 stores objects. EC2 runs compute.\n", encoding="utf-8",
    )
    sub = folder / "terraform"
    sub.mkdir()
    (sub / "state.txt").write_text("Terraform state must be locked.\n", encoding="utf-8")
    return folder


def test_add_root_and_search_with_citations(memory, notes):
    result = memory.add_root(notes)
    assert result["added"] == 3
    hits = memory.search("readiness probes")
    assert hits["results"], "expected a hit for the kubernetes note"
    top = hits["results"][0]
    assert top["path"].endswith("kubernetes.md")
    assert top["line"] == 4
    assert top["citation"].endswith("kubernetes.md:4")
    assert "readiness" in top["snippet"].lower()


def test_search_requires_a_query(memory, notes):
    memory.add_root(notes)
    assert memory.search("   ")["results"] == []


def test_reindex_is_incremental(memory, notes):
    memory.add_root(notes)
    stats = memory.reindex()
    assert stats["added"] == 0 and stats["skipped"] == 3
    target = notes / "aws.md"
    target.write_text("# AWS\n\nS3 stores objects. Lambda runs functions.\n", encoding="utf-8")
    stats = memory.reindex()
    assert stats["updated"] == 1
    assert memory.search("Lambda")["results"][0]["path"].endswith("aws.md")


def test_deleted_files_leave_the_index(memory, notes):
    memory.add_root(notes)
    os.remove(notes / "aws.md")
    stats = memory.reindex()
    assert stats["removed"] == 1
    assert memory.search("EC2")["results"] == []


def test_secret_shaped_files_are_never_indexed(memory, notes):
    (notes / ".env").write_text("GEMINI_API_KEY=abc123\n", encoding="utf-8")
    (notes / "server.pem").write_text("dummy\n", encoding="utf-8")
    (notes / "app.key").write_text("dummy\n", encoding="utf-8")
    (notes / "credentials.txt").write_text("user pass\n", encoding="utf-8")
    leaked = notes / "leaked.md"
    leaked.write_text("# notes\n-----BEGIN PRIVATE KEY-----\nfake\n", encoding="utf-8")
    memory.add_root(notes)
    status = memory.status()
    assert status["indexed_docs"] == 3  # only the three real notes
    assert memory.search("GEMINI_API_KEY")["results"] == []
    assert memory.search("PRIVATE KEY")["results"] == []


def test_noisy_dirs_and_large_files_are_skipped(memory, notes):
    git = notes / ".git"
    git.mkdir()
    (git / "notes.md").write_text("internal git file\n", encoding="utf-8")
    big = notes / "huge.md"
    big.write_text("x" * (600 * 1024), encoding="utf-8")
    memory.add_root(notes)
    assert memory.status()["indexed_docs"] == 3


def test_add_root_validates(memory, tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        memory.add_root(tmp_path / "nope")
    file_path = tmp_path / "file.md"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Not a folder"):
        memory.add_root(file_path)


def test_remove_root_forgets_everything_but_keeps_files(memory, notes):
    memory.add_root(notes)
    result = memory.remove_root(notes)
    assert result["removed"] is True and result["forgotten_docs"] == 3
    assert memory.search("pod")["results"] == []
    assert (notes / "kubernetes.md").exists()  # source files are never touched


def test_forget_single_file_and_clear(memory, notes):
    memory.add_root(notes)
    target = notes / "aws.md"
    assert memory.forget(target)["forgotten"] is True
    assert memory.status()["indexed_docs"] == 2
    cleared = memory.clear()
    assert cleared["forgotten_docs"] == 2
    assert memory.list_roots() == []
    assert memory.status()["indexed_docs"] == 0


def test_vanished_root_is_dropped_on_reindex(memory, notes, tmp_path):
    memory.add_root(notes)
    for child in sorted(notes.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink()
        else:
            child.rmdir()
    notes.rmdir()
    stats = memory.reindex()
    assert stats["removed"] == 3
    assert memory.status()["indexed_docs"] == 0
