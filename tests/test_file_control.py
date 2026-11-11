"""Safety tests for local file operations."""

from __future__ import annotations

import sys
import types

from jarvis.control import files


def test_delete_does_not_permanently_delete_when_recycle_bin_support_is_missing(
    tmp_path, monkeypatch
):
    target = tmp_path / "keep-unless-recycle-bin-available.txt"
    target.write_text("important", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "send2trash", None)

    result = files.delete(str(target))

    assert result["success"] is False
    assert result["permanent"] is False
    assert "explicitly request permanent deletion" in result["error"]
    assert target.read_text(encoding="utf-8") == "important"


def test_delete_uses_recycle_bin_integration_when_available(tmp_path, monkeypatch):
    target = tmp_path / "recycle-me.txt"
    target.write_text("recoverable", encoding="utf-8")
    trashed: list[str] = []
    monkeypatch.setitem(
        sys.modules,
        "send2trash",
        types.SimpleNamespace(send2trash=lambda path: trashed.append(path)),
    )

    result = files.delete(str(target))

    assert result == {"success": True, "path": str(target), "permanent": False}
    assert trashed == [str(target)]
    assert target.exists()


def test_permanent_delete_only_runs_when_explicitly_requested(tmp_path):
    target = tmp_path / "permanent-delete.txt"
    target.write_text("delete", encoding="utf-8")

    result = files.delete(str(target), permanent=True)

    assert result == {"success": True, "path": str(target), "permanent": True}
    assert not target.exists()


def test_transfer_preview_reports_affected_items_and_bytes(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("abc", encoding="utf-8")
    (source / "b.txt").write_text("de", encoding="utf-8")
    destination = tmp_path / "destination"

    preview = files.preview_copy(str(source), str(destination))

    assert preview["success"] is True
    assert preview["estimated_affected_items"] == 3
    assert preview["estimated_bytes"] == 5
    assert preview["effective_destination"] == str(destination)
    assert preview["destination_exists"] is False


def test_transfer_into_source_descendant_is_rejected(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    nested = source / "nested"
    nested.mkdir()

    assert files.copy(str(source), str(nested))["success"] is False
    assert files.move(str(source), str(nested))["success"] is False
    assert files.preview_copy(str(source), str(nested))["success"] is False
    assert files.preview_move(str(source), str(nested))["success"] is False
    assert source.is_dir()


def test_copy_preview_requires_explicit_overwrite_for_existing_destination(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    destination.write_text("old", encoding="utf-8")

    blocked = files.preview_copy(str(source), str(destination))
    approved = files.preview_copy(str(source), str(destination), overwrite=True)

    assert blocked["success"] is False
    assert approved["success"] is True
    assert approved["overwrite_requested"] is True
    assert approved["existing_destination"]["estimated_bytes"] == 3


def test_move_preview_reports_overwrite_and_move_protects_existing_directory(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    destination.write_text("old", encoding="utf-8")

    blocked = files.preview_move(str(source), str(destination))
    approved = files.preview_move(str(source), str(destination), overwrite=True)

    assert blocked["success"] is False
    assert approved["success"] is True
    assert approved["overwrite_requested"] is True
    assert approved["existing_destination"]["estimated_bytes"] == 3

    folder = tmp_path / "existing-folder"
    (folder / source.name).mkdir(parents=True)
    assert files.move(str(source), str(folder), overwrite=True)["success"] is False
    assert files.preview_move(str(source), str(folder), overwrite=True)["success"] is False
    assert source.exists()
