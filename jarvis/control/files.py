"""File system operations: search, copy, move, delete, rename, read, organise."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.control.files")

# Dangerous locations that require explicit confirmation upstream
PROTECTED_PREFIXES = [
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    str(Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu"),
]


def _protected(path: str | Path) -> bool:
    resolved = str(Path(path).expanduser().resolve(strict=False)).lower()
    return any(resolved.startswith(p.lower()) for p in PROTECTED_PREFIXES)


def home_dir() -> dict[str, Any]:
    return {"success": True, "path": str(Path.home())}


def resolve(path: str) -> Path:
    return Path(path).expanduser()


def list_dir(path: str = ".", limit: int = 200) -> dict[str, Any]:
    target = resolve(path)
    if not target.exists():
        return {"success": False, "error": f"Not found: {target}"}
    if target.is_file():
        return {"success": True, "type": "file", "path": str(target), "size": target.stat().st_size}
    entries = []
    try:
        for i, child in enumerate(sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))):
            if i >= limit:
                break
            try:
                stat = child.stat()
                size, is_dir = stat.st_size, child.is_dir()
            except OSError:
                size, is_dir = None, child.is_dir()
            entries.append({"name": child.name, "dir": is_dir, "size": size, "path": str(child)})
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {target}"}
    return {"success": True, "type": "dir", "path": str(target), "entries": entries, "count": len(entries)}


def search_files(
    query: str,
    roots: list[str] | None = None,
    max_results: int = 40,
    file_glob: str | None = None,
) -> dict[str, Any]:
    """Search file names under *roots* (default: home + drives' user folders)."""
    if not roots:
        home = Path.home()
        roots = [str(home / "Desktop"), str(home / "Documents"), str(home / "Downloads")]
        for drive in ("C:", "D:", "E:"):
            if Path(drive + "\\").exists():
                roots.append(drive + "\\")

    query_l = query.lower()
    matches: list[dict[str, Any]] = []
    searched = 0
    for root in roots:
        base = resolve(root)
        if not base.is_dir():
            continue
        pattern = file_glob or f"*{query}*"
        try:
            for path in base.rglob(pattern):
                searched += 1
                if searched > 20000:
                    break
                name = path.name.lower()
                if query_l in name or file_glob:
                    try:
                        size = path.stat().st_size if path.is_file() else None
                    except OSError:
                        size = None
                    matches.append({"name": path.name, "path": str(path), "size": size})
                    if len(matches) >= max_results:
                        return {"success": True, "matches": matches, "count": len(matches), "truncated": True}
        except (PermissionError, OSError):
            continue
    return {"success": True, "matches": matches, "count": len(matches), "truncated": False}


def read_text(path: str, max_bytes: int = 64000) -> dict[str, Any]:
    target = resolve(path)
    if not target.is_file():
        return {"success": False, "error": f"Not a file: {target}"}
    try:
        data = target.read_bytes()[:max_bytes]
        text = data.decode("utf-8", errors="replace")
        return {"success": True, "path": str(target), "content": text, "truncated": len(data) >= max_bytes}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def write_text(path: str, content: str, append: bool = False) -> dict[str, Any]:
    target = resolve(path)
    if _protected(target):
        return {"success": False, "error": "Refusing to write into a protected system location"}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as fh:
            fh.write(content)
        return {"success": True, "path": str(target), "bytes": len(content.encode("utf-8")), "append": append}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def copy(source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
    src, dst = resolve(source), resolve(destination)
    if not src.exists():
        return {"success": False, "error": f"Not found: {src}"}
    if dst.exists() and not overwrite:
        return {"success": False, "error": f"Destination exists: {dst} (set overwrite=true)"}
    if _protected(dst):
        return {"success": False, "error": "Refusing to copy into a protected system location"}
    try:
        if src.is_dir():
            if dst.exists():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copytree(src, dst)
        else:
            if dst.is_dir():
                dst = dst / src.name
            shutil.copy2(src, dst)
        return {"success": True, "source": str(src), "destination": str(dst)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def move(source: str, destination: str) -> dict[str, Any]:
    src, dst = resolve(source), resolve(destination)
    if not src.exists():
        return {"success": False, "error": f"Not found: {src}"}
    if _protected(src) or _protected(dst):
        return {"success": False, "error": "Refusing to move a protected system path"}
    try:
        if dst.is_dir():
            dst = dst / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"success": True, "source": str(src), "destination": str(dst)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def rename(path: str, new_name: str) -> dict[str, Any]:
    src = resolve(path)
    if not src.exists():
        return {"success": False, "error": f"Not found: {src}"}
    if _protected(src):
        return {"success": False, "error": "Refusing to rename a protected system path"}
    dst = src.parent / new_name
    try:
        src.rename(dst)
        return {"success": True, "path": str(dst)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def delete(path: str, permanent: bool = False) -> dict[str, Any]:
    """Move to Recycle Bin unless permanent=true."""
    src = resolve(path)
    if not src.exists():
        return {"success": False, "error": f"Not found: {src}"}
    if _protected(src):
        return {"success": False, "error": "Refusing to delete a protected system path"}
    try:
        if permanent:
            if src.is_dir():
                shutil.rmtree(src)
            else:
                src.unlink()
        else:
            import send2trash  # type: ignore[import-not-found]

            send2trash.send2trash(str(src))
        return {"success": True, "path": str(src), "permanent": permanent}
    except ImportError:
        # send2trash not installed -> fall back to permanent delete only if asked
        if permanent:
            return {"success": False, "error": "permanent delete failed"}
        try:
            if src.is_dir():
                shutil.rmtree(src)
            else:
                src.unlink()
            return {"success": True, "path": str(src), "permanent": True, "warning": "Recycle Bin unavailable; deleted permanently"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def create_folder(path: str) -> dict[str, Any]:
    target = resolve(path)
    if _protected(target):
        return {"success": False, "error": "Refusing to create folders in a protected system location"}
    try:
        target.mkdir(parents=True, exist_ok=True)
        return {"success": True, "path": str(target)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def open_path(path: str) -> dict[str, Any]:
    target = resolve(path)
    if not target.exists():
        return {"success": False, "error": f"Not found: {target}"}
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
        return {"success": True, "path": str(target)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def file_info(path: str) -> dict[str, Any]:
    target = resolve(path)
    if not target.exists():
        return {"success": False, "error": f"Not found: {target}"}
    try:
        stat = target.stat()
        return {
            "success": True,
            "path": str(target),
            "name": target.name,
            "is_dir": target.is_dir(),
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "extension": target.suffix,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def organize_folder(path: str) -> dict[str, Any]:
    """Sort files in a folder into type-based subfolders (Documents, Images, ...)."""
    target = resolve(path)
    if not target.is_dir():
        return {"success": False, "error": f"Not a directory: {target}"}
    categories = {
        "Documents": {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".md"},
        "Images": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"},
        "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"},
        "Audio": {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"},
        "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
        "Code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".html", ".css", ".json"},
    }
    moved: list[dict[str, str]] = []
    for item in sorted(target.iterdir()):
        if item.is_dir():
            continue
        ext = item.suffix.lower()
        dest_folder = None
        for folder, exts in categories.items():
            if ext in exts:
                dest_folder = folder
                break
        if dest_folder is None:
            continue
        dest_dir = target / dest_folder
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / item.name
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{item.stem}_{counter}{item.suffix}"
            counter += 1
        try:
            shutil.move(str(item), str(dest))
            moved.append({"from": item.name, "to": str(dest.relative_to(target))})
        except Exception:
            continue
    return {"success": True, "moved": moved, "count": len(moved)}
