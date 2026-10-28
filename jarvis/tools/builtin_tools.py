"""Built-in tool definitions: every laptop and Android capability.

Handlers are bound at call time through module-level singletons so the
registry can be built cheaply and controllers are only constructed when a
tool actually runs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from jarvis.tools.registry import Risk, Tool, ToolRegistry

logger = logging.getLogger("jarvis.tools.builtin")

_laptop = None
_android = None


def get_laptop():
    global _laptop
    if _laptop is None:
        from jarvis.control.laptop import LaptopController

        _laptop = LaptopController()
    return _laptop


def get_android():
    global _android
    if _android is None:
        from jarvis.android_bridge import AndroidController

        _android = AndroidController()
    return _android


def _open_app_and_type(app_name: str, text: str, wait_seconds: float = 1.5) -> dict[str, Any]:
    """Launch/focus an app and type text into its active window; never submits it."""
    if not text:
        return {"success": False, "error": "No text supplied; nothing was typed."}
    launch_result = get_laptop().open_app(app_name)
    if not isinstance(launch_result, dict) or not launch_result.get("success", False):
        return {"success": False, "stage": "launch", "result": launch_result}
    # Give Windows time to create and focus the new application window.
    time.sleep(max(0.5, min(float(wait_seconds), 5.0)))
    type_result = get_laptop().type_text(text)
    if not isinstance(type_result, dict) or not type_result.get("success", False):
        return {
            "success": False,
            "stage": "type",
            "launched": launch_result,
            "result": type_result,
            "error": "Application launched, but typing failed. Check input automation permissions and focus the editor manually.",
        }
    return {
        "success": True,
        "launched": launch_result,
        "typed_chars": type_result.get("typed_chars", len(text)),
        "submitted": False,
        "message": f"Typed {type_result.get('typed_chars', len(text))} characters into {app_name}; nothing was sent or submitted.",
    }


def reset_controllers() -> None:
    """Drop cached controllers (used by tests)."""
    global _laptop, _android
    _laptop = _android = None


# --------------------------------------------------------------------------
# JSON schema helpers
# --------------------------------------------------------------------------
def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _str(description: str, enum: list[str] | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"type": "string", "description": description}
    if enum:
        d["enum"] = enum
    return d


def _int(description: str, minimum: int | None = None, maximum: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"type": "integer", "description": description}
    if minimum is not None:
        d["minimum"] = minimum
    if maximum is not None:
        d["maximum"] = maximum
    return d


def _num(description: str) -> dict[str, Any]:
    return {"type": "number", "description": description}


def _bool(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


def _array(description: str, items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "description": description, "items": items}


DEVICE = {"type": "string", "description": "ADB serial; omit when only one device is connected."}
DEVICE_DESC = "ADB serial of the target phone; omit if only one device is connected."


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------
def build_registry(force: bool = False) -> ToolRegistry:
    """Create and populate the global tool registry."""
    registry = getattr(build_registry, "_instance", None)
    if registry is not None and not force:
        return registry

    registry = ToolRegistry()
    _register_system(registry)
    _register_apps(registry)
    _register_audio(registry)
    _register_windows(registry)
    _register_power(registry)
    _register_screen(registry)
    _register_input(registry)
    _register_files(registry)
    _register_process(registry)
    _register_clipboard(registry)
    _register_network(registry)
    _register_shell(registry)
    _register_notify(registry)
    _register_android_device(registry)
    _register_android_apps(registry)
    _register_android_input(registry)
    _register_android_screen(registry)
    _register_android_files(registry)
    _register_android_comms(registry)
    _register_android_system(registry)

    build_registry._instance = registry  # type: ignore[attr-defined]
    logger.info("Registered %d tools across %d categories", len(registry), len(registry.categories()))
    return registry


# ------------------------------------------------------------------- system
def _register_system(r: ToolRegistry) -> None:
    r.register(Tool(
        name="system_status",
        description="Snapshot of this laptop: OS, CPU %, RAM %, battery %, free disk.",
        parameters=_obj({}),
        handler=lambda: get_laptop().status(),
        risk=Risk.SAFE, category="system",
    ))
    r.register(Tool(
        name="cpu_usage",
        description="Current CPU utilisation per core plus core count and clock speed.",
        parameters=_obj({"interval": _num("Sampling interval in seconds (0-2).")}),
        handler=lambda interval=0.5: get_laptop().cpu_usage(interval),
        risk=Risk.SAFE, category="system",
    ))
    r.register(Tool(
        name="memory_usage",
        description="RAM and swap usage in GB and percent.",
        parameters=_obj({}),
        handler=lambda: get_laptop().memory_usage(),
        risk=Risk.SAFE, category="system",
    ))
    r.register(Tool(
        name="disk_usage",
        description="Disk space for a drive path (default C:\\).",
        parameters=_obj({"path": _str("Drive path, e.g. 'C:\\\\'.")}),
        handler=lambda path="C:\\": get_laptop().disk_usage(path),
        risk=Risk.SAFE, category="system",
    ))
    r.register(Tool(
        name="battery_status",
        description="Laptop battery percentage, charging state and time remaining.",
        parameters=_obj({}),
        handler=lambda: get_laptop().battery(),
        risk=Risk.SAFE, category="system",
    ))
    r.register(Tool(
        name="os_info",
        description="OS version, hostname, architecture and Python version of this machine.",
        parameters=_obj({}),
        handler=lambda: get_laptop().os_info(),
        risk=Risk.SAFE, category="system",
    ))
    r.register(Tool(
        name="gpu_info",
        description="Graphics adapters and driver versions installed.",
        parameters=_obj({}),
        handler=lambda: get_laptop().gpu_info(),
        risk=Risk.SAFE, category="system",
    ))
    r.register(Tool(
        name="top_processes",
        description="Top processes by memory usage.",
        parameters=_obj({"limit": _int("How many processes to return.", 1, 50)}),
        handler=lambda limit=10: get_laptop().top_processes(limit),
        risk=Risk.SAFE, category="system",
    ))


# -------------------------------------------------------------------- apps
def _register_apps(r: ToolRegistry) -> None:
    r.register(Tool(
        name="open_app",
        description="Launch a Windows application (by name like 'chrome', 'vscode', or an exact path).",
        parameters=_obj(
            {"app_name": _str("Application name or path, e.g. 'chrome', 'notepad', 'spotify'.")},
            ["app_name"],
        ),
        handler=lambda app_name: get_laptop().open_app(app_name),
        risk=Risk.LOW, category="apps",
    ))
    r.register(Tool(
        name="open_website",
        description="Open a website visibly in the user's default browser. Use for requests such as 'open YouTube', 'open Google', or a supplied URL. Do not merely say it is opening; call this tool and report its actual result.",
        parameters=_obj({"url": _str("Website domain or HTTP(S) URL, e.g. 'youtube.com' or 'https://web.whatsapp.com'.")}, ["url"]),
        handler=lambda url: get_laptop().open_app(url if url.startswith(("http://", "https://")) else "https://" + url),
        risk=Risk.LOW, category="apps",
    ))
    r.register(Tool(
        name="open_app_and_type",
        description="Open a desktop application and type supplied text into its focused window. Use when the user asks you to write/create text directly in Notepad, an editor, or another app. This only types; it never presses Enter to send, submit, or execute the text.",
        parameters=_obj({
            "app_name": _str("Target application, e.g. 'notepad', 'whatsapp', 'code'."),
            "text": _str("Exact text to type into the application."),
            "wait_seconds": _num("Seconds to wait for the application window before typing (0.5 to 5; default 1.5)."),
        }, ["app_name", "text"]),
        handler=lambda app_name, text, wait_seconds=1.5: _open_app_and_type(app_name, text, wait_seconds),
        risk=Risk.LOW, category="apps",
    ))
    r.register(Tool(
        name="close_app",
        description="Close a running application by name (terminates its processes).",
        parameters=_obj(
            {"app_name": _str("Application name to close."), "force": _bool("Use kill instead of graceful terminate.")},
            ["app_name"],
        ),
        handler=lambda app_name, force=False: get_laptop().close_app(app_name, force),
        risk=Risk.MEDIUM, category="apps", requires_confirmation=True,
    ))
    r.register(Tool(
        name="search_apps",
        description="Search installed applications by partial name and return matching launch targets.",
        parameters=_obj(
            {"query": _str("Text to search for, e.g. 'code' or 'spotify'."), "limit": _int("Max results.", 1, 30)},
            ["query"],
        ),
        handler=lambda query, limit=15: get_laptop().search_apps(query, limit),
        risk=Risk.SAFE, category="apps",
    ))
    r.register(Tool(
        name="list_running_apps",
        description="List applications currently running with their PID and memory use.",
        parameters=_obj({}),
        handler=lambda: get_laptop().list_running_apps(),
        risk=Risk.SAFE, category="apps",
    ))


# ------------------------------------------------------------------- audio
def _register_audio(r: ToolRegistry) -> None:
    r.register(Tool(
        name="get_volume",
        description="Read the current system volume (0-100) and mute state.",
        parameters=_obj({}),
        handler=lambda: get_laptop().get_volume(),
        risk=Risk.SAFE, category="audio",
    ))
    r.register(Tool(
        name="set_volume",
        description="Set the system volume to an absolute percentage (0-100).",
        parameters=_obj({"level": _int("Volume 0-100.", 0, 100)}, ["level"]),
        handler=lambda level: get_laptop().set_volume(level),
        risk=Risk.LOW, category="audio",
    ))
    r.register(Tool(
        name="adjust_volume",
        description="Raise or lower system volume by a delta (positive or negative, e.g. +10 or -20).",
        parameters=_obj({"delta": _int("Change in percent, e.g. 10 or -10.", -100, 100)}, ["delta"]),
        handler=lambda delta: get_laptop().adjust_volume(delta),
        risk=Risk.LOW, category="audio",
    ))
    r.register(Tool(
        name="mute",
        description="Mute or unmute the system audio output.",
        parameters=_obj({"muted": _bool("True to mute, false to unmute.")}, ["muted"]),
        handler=lambda muted: get_laptop().set_mute(muted),
        risk=Risk.LOW, category="audio",
    ))
    r.register(Tool(
        name="toggle_mute",
        description="Toggle the system mute state.",
        parameters=_obj({}),
        handler=lambda: get_laptop().toggle_mute(),
        risk=Risk.LOW, category="audio",
    ))
    r.register(Tool(
        name="media_key",
        description="Press a media key: play_pause, next, previous, volume_up, volume_down, mute.",
        parameters=_obj({"key": _str("Media key name.", ["play_pause", "play", "pause", "next", "previous", "volume_up", "volume_down", "mute"])}, ["key"]),
        handler=lambda key: get_laptop().media_key(key),
        risk=Risk.LOW, category="audio",
    ))
    r.register(Tool(
        name="audio_sessions",
        description="Per-application audio sessions with their volumes.",
        parameters=_obj({}),
        handler=lambda: get_laptop().list_audio_sessions(),
        risk=Risk.SAFE, category="audio",
    ))


# ------------------------------------------------------------------ window
def _register_windows(r: ToolRegistry) -> None:
    r.register(Tool(
        name="list_windows",
        description="List visible top-level windows with titles and PIDs.",
        parameters=_obj({}),
        handler=lambda: get_laptop().list_windows(),
        risk=Risk.SAFE, category="window",
    ))
    r.register(Tool(
        name="focus_window",
        description="Bring a window to the foreground by (partial) title match.",
        parameters=_obj({"title": _str("Window title or a unique substring of it.")}, ["title"]),
        handler=lambda title: get_laptop().focus_window(title),
        risk=Risk.LOW, category="window",
    ))
    r.register(Tool(
        name="minimize_window",
        description="Minimise a window by title.",
        parameters=_obj({"title": _str("Window title.")}, ["title"]),
        handler=lambda title: get_laptop().minimize_window(title),
        risk=Risk.LOW, category="window",
    ))
    r.register(Tool(
        name="maximize_window",
        description="Maximise a window by title.",
        parameters=_obj({"title": _str("Window title.")}, ["title"]),
        handler=lambda title: get_laptop().maximize_window(title),
        risk=Risk.LOW, category="window",
    ))
    r.register(Tool(
        name="restore_window",
        description="Restore a minimised window by title.",
        parameters=_obj({"title": _str("Window title.")}, ["title"]),
        handler=lambda title: get_laptop().restore_window(title),
        risk=Risk.LOW, category="window",
    ))
    r.register(Tool(
        name="close_window",
        description="Close a window by title (sends WM_CLOSE; apps may prompt to save).",
        parameters=_obj({"title": _str("Window title.")}, ["title"]),
        handler=lambda title: get_laptop().close_window(title),
        risk=Risk.MEDIUM, category="window", requires_confirmation=True,
    ))
    r.register(Tool(
        name="move_window",
        description="Move/resize a window to an absolute screen rectangle.",
        parameters=_obj(
            {
                "title": _str("Window title."),
                "x": _int("Left coordinate."),
                "y": _int("Top coordinate."),
                "width": _int("Width in pixels (optional)."),
                "height": _int("Height in pixels (optional)."),
            },
            ["title", "x", "y"],
        ),
        handler=lambda title, x, y, width=None, height=None: get_laptop().move_window(title, x, y, width, height),
        risk=Risk.LOW, category="window",
    ))
    r.register(Tool(
        name="active_window",
        description="Get the title, class and PID of the currently focused window.",
        parameters=_obj({}),
        handler=lambda: get_laptop().get_active_window(),
        risk=Risk.SAFE, category="window",
    ))


# ------------------------------------------------------------------- power
def _register_power(r: ToolRegistry) -> None:
    r.register(Tool(
        name="lock_pc",
        description="Lock the Windows workstation immediately.",
        parameters=_obj({}),
        handler=lambda: get_laptop().lock(),
        risk=Risk.LOW, category="power",
    ))
    r.register(Tool(
        name="sleep_pc",
        description="Put the computer to sleep.",
        parameters=_obj({}),
        handler=lambda: get_laptop().sleep(),
        risk=Risk.MEDIUM, category="power", requires_confirmation=True,
    ))
    r.register(Tool(
        name="hibernate_pc",
        description="Hibernate the computer.",
        parameters=_obj({}),
        handler=lambda: get_laptop().hibernate(),
        risk=Risk.MEDIUM, category="power", requires_confirmation=True,
    ))
    r.register(Tool(
        name="shutdown_pc",
        description="Schedule Windows shutdown after a delay in seconds (default 10).",
        parameters=_obj({"delay": _int("Seconds before shutdown.", 0, 3600)}, ["delay"]),
        handler=lambda delay=10: get_laptop().shutdown(delay),
        risk=Risk.HIGH, category="power", requires_confirmation=True,
    ))
    r.register(Tool(
        name="restart_pc",
        description="Schedule Windows restart after a delay in seconds (default 10).",
        parameters=_obj({"delay": _int("Seconds before restart.", 0, 3600)}, ["delay"]),
        handler=lambda delay=10: get_laptop().restart(delay),
        risk=Risk.HIGH, category="power", requires_confirmation=True,
    ))
    r.register(Tool(
        name="logoff_pc",
        description="Sign out the current Windows user.",
        parameters=_obj({}),
        handler=lambda: get_laptop().logoff(),
        risk=Risk.HIGH, category="power", requires_confirmation=True,
    ))
    r.register(Tool(
        name="cancel_shutdown",
        description="Cancel a pending scheduled shutdown or restart.",
        parameters=_obj({}),
        handler=lambda: get_laptop().cancel_shutdown(),
        risk=Risk.LOW, category="power",
    ))


# ------------------------------------------------------------------ screen
def _register_screen(r: ToolRegistry) -> None:
    r.register(Tool(
        name="screenshot",
        description="Capture the laptop screen (full screen or a region) and return the saved image path.",
        parameters=_obj(
            {
                "path": _str("Optional output file path; a timestamped file is used when omitted."),
                "left": _int("Region left edge (requires top/width/height)."),
                "top": _int("Region top edge."),
                "width": _int("Region width."),
                "height": _int("Region height."),
            }
        ),
        handler=lambda path=None, left=None, top=None, width=None, height=None: get_laptop().screenshot(
            path,
            {"left": left, "top": top, "width": width, "height": height}
            if None not in (left, top, width, height)
            else None,
        ),
        risk=Risk.LOW, category="screen",
    ))
    r.register(Tool(
        name="screen_size",
        description="Resolution of the primary display.",
        parameters=_obj({}),
        handler=lambda: get_laptop().screen_size(),
        risk=Risk.SAFE, category="screen",
    ))
    r.register(Tool(
        name="pixel_color",
        description="Colour at an exact screen coordinate as hex and RGB.",
        parameters=_obj({"x": _int("X coordinate."), "y": _int("Y coordinate.")}, ["x", "y"]),
        handler=lambda x, y: get_laptop().get_pixel_color(x, y),
        risk=Risk.SAFE, category="screen",
    ))
    r.register(Tool(
        name="record_screen",
        description="Record the screen for N seconds to an .avi file (needs opencv-python).",
        parameters=_obj(
            {"duration": _int("Seconds to record, 1-120.", 1, 120), "path": _str("Optional output path.")},
            ["duration"],
        ),
        handler=lambda duration=10, path=None: get_laptop().record_screen(duration, path),
        risk=Risk.MEDIUM, category="screen", requires_confirmation=True,
    ))


# ------------------------------------------------------------------- input
def _register_input(r: ToolRegistry) -> None:
    r.register(Tool(
        name="type_text",
        description="Type text on the laptop keyboard into the currently focused window.",
        parameters=_obj({"text": _str("Text to type."), "interval": _num("Seconds between keystrokes.")}, ["text"]),
        handler=lambda text, interval=0.02: get_laptop().type_text(text, interval),
        risk=Risk.LOW, category="input",
    ))
    r.register(Tool(
        name="press_keys",
        description="Press a key or combination: single key ('enter', 'esc') or a combo list like ['ctrl','c'].",
        parameters=_obj({"keys": _array("Keys to press in order/combination.", _str("Key name."))}, ["keys"]),
        handler=lambda keys: get_laptop().press_keys(keys),
        risk=Risk.LOW, category="input",
    ))
    r.register(Tool(
        name="hotkey",
        description="Press a hotkey combination such as win+d, alt+tab, ctrl+s, win+l.",
        parameters=_obj({"keys": _array("Keys in the combination.", _str("Key name."))}, ["keys"]),
        handler=lambda keys: get_laptop().press_keys(keys),
        risk=Risk.LOW, category="input",
    ))

    r.register(Tool(
        name="click",
        description="Left or right click at screen coordinates (or current pointer if omitted).",
        parameters=_obj(
            {"x": _int("X coordinate."), "y": _int("Y coordinate."),
             "button": _str("Mouse button.", ["left", "right", "middle"]),
             "clicks": _int("Number of clicks.", 1, 3)},
        ),
        handler=lambda x=None, y=None, button="left", clicks=1: get_laptop().click(x, y, button, clicks),
        risk=Risk.LOW, category="input",
    ))
    r.register(Tool(
        name="double_click",
        description="Double-click at screen coordinates.",
        parameters=_obj({"x": _int("X coordinate."), "y": _int("Y coordinate.")}, ["x", "y"]),
        handler=lambda x, y: get_laptop().double_click(x, y),
        risk=Risk.LOW, category="input",
    ))
    r.register(Tool(
        name="move_mouse",
        description="Move the mouse pointer to coordinates.",
        parameters=_obj({"x": _int("X coordinate."), "y": _int("Y coordinate."), "duration": _num("Seconds to glide.")}, ["x", "y"]),
        handler=lambda x, y, duration=0.2: get_laptop().move_mouse(x, y, duration),
        risk=Risk.LOW, category="input",
    ))
    r.register(Tool(
        name="scroll",
        description="Scroll the mouse wheel at the current pointer position.",
        parameters=_obj(
            {"direction": _str("Scroll direction.", ["up", "down"]), "amount": _int("Clicks to scroll, 1-20.", 1, 20)},
            ["direction"],
        ),
        handler=lambda direction="down", amount=3: get_laptop().scroll(direction, amount),
        risk=Risk.LOW, category="input",
    ))
    r.register(Tool(
        name="drag",
        description="Drag the mouse from one point to another.",
        parameters=_obj(
            {"x1": _int("Start X."), "y1": _int("Start Y."), "x2": _int("End X."), "y2": _int("End Y.")},
            ["x1", "y1", "x2", "y2"],
        ),
        handler=lambda x1, y1, x2, y2: get_laptop().drag(x1, y1, x2, y2),
        risk=Risk.LOW, category="input",
    ))
    r.register(Tool(
        name="mouse_position",
        description="Current mouse pointer coordinates.",
        parameters=_obj({}),
        handler=lambda: get_laptop().mouse_position(),
        risk=Risk.SAFE, category="input",
    ))


# ------------------------------------------------------------------- files
def _register_files(r: ToolRegistry) -> None:
    r.register(Tool(
        name="list_directory",
        description="List the contents of a folder (default: current directory).",
        parameters=_obj({"path": _str("Folder path."), "limit": _int("Max entries.", 1, 500)}),
        handler=lambda path=".", limit=200: get_laptop().list_dir(path, limit),
        risk=Risk.SAFE, category="files",
    ))
    r.register(Tool(
        name="search_files",
        description="Search for files by name under common folders (Desktop, Documents, Downloads, drives).",
        parameters=_obj(
            {
                "query": _str("File name fragment to search for."),
                "roots": _array("Optional folders to search.", _str("Folder path.")),
                "max_results": _int("Max matches.", 1, 100),
            },
            ["query"],
        ),
        handler=lambda query, roots=None, max_results=40: get_laptop().search_files(query, roots, max_results),
        risk=Risk.SAFE, category="files",
    ))
    r.register(Tool(
        name="read_file",
        description="Read a text file and return its contents (truncated at 64 KB).",
        parameters=_obj({"path": _str("File path.")}, ["path"]),
        handler=lambda path: get_laptop().read_file(path),
        risk=Risk.SAFE, category="files",
    ))
    r.register(Tool(
        name="write_file",
        description="Create or overwrite a text file (never inside Windows system folders).",
        parameters=_obj(
            {"path": _str("File path."), "content": _str("Text to write."), "append": _bool("Append instead of overwrite.")},
            ["path", "content"],
        ),
        handler=lambda path, content, append=False: get_laptop().write_file(path, content, append),
        risk=Risk.MEDIUM, category="files", requires_confirmation=True,
    ))
    r.register(Tool(
        name="copy_file",
        description="Copy a file or folder to a destination path.",
        parameters=_obj(
            {"source": _str("Source path."), "destination": _str("Destination path."), "overwrite": _bool("Overwrite existing.")},
            ["source", "destination"],
        ),
        handler=lambda source, destination, overwrite=False: get_laptop().copy_path(source, destination, overwrite),
        risk=Risk.MEDIUM, category="files",
    ))
    r.register(Tool(
        name="move_file",
        description="Move/rename a file or folder.",
        parameters=_obj({"source": _str("Source path."), "destination": _str("Destination path.")}, ["source", "destination"]),
        handler=lambda source, destination: get_laptop().move_path(source, destination),
        risk=Risk.MEDIUM, category="files",
    ))
    r.register(Tool(
        name="delete_file",
        description="Delete a file or folder (Recycle Bin by default; permanent when requested).",
        parameters=_obj(
            {"path": _str("Path to delete."), "permanent": _bool("Skip the Recycle Bin.")},
            ["path"],
        ),
        handler=lambda path, permanent=False: get_laptop().delete_path(path, permanent),
        risk=Risk.HIGH, category="files", requires_confirmation=True,
    ))
    r.register(Tool(
        name="create_folder",
        description="Create a directory (including parents).",
        parameters=_obj({"path": _str("Folder path to create.")}, ["path"]),
        handler=lambda path: get_laptop().create_folder(path),
        risk=Risk.LOW, category="files",
    ))
    r.register(Tool(
        name="open_path",
        description="Open a file or folder with its default Windows application.",
        parameters=_obj({"path": _str("File or folder path.")}, ["path"]),
        handler=lambda path: get_laptop().open_path(path),
        risk=Risk.LOW, category="files",
    ))
    r.register(Tool(
        name="file_info",
        description="Metadata for a path: size, type, modified time.",
        parameters=_obj({"path": _str("File or folder path.")}, ["path"]),
        handler=lambda path: get_laptop().file_info(path),
        risk=Risk.SAFE, category="files",
    ))
    r.register(Tool(
        name="organize_folder",
        description="Sort a folder's files into type subfolders (Documents, Images, Videos, ...).",
        parameters=_obj({"path": _str("Folder to organise.")}, ["path"]),
        handler=lambda path: get_laptop().organize_folder(path),
        risk=Risk.MEDIUM, category="files", requires_confirmation=True,
    ))


# ----------------------------------------------------------------- process
def _register_process(r: ToolRegistry) -> None:
    r.register(Tool(
        name="list_processes",
        description="List running processes sorted by memory, optionally filtered by name.",
        parameters=_obj({"search": _str("Substring filter."), "limit": _int("Max results.", 1, 300)}),
        handler=lambda search=None, limit=100: get_laptop().list_processes(search, limit),
        risk=Risk.SAFE, category="process",
    ))
    r.register(Tool(
        name="process_details",
        description="Full details for a process by PID.",
        parameters=_obj({"pid": _int("Process ID.")}, ["pid"]),
        handler=lambda pid: get_laptop().process_details(pid),
        risk=Risk.SAFE, category="process",
    ))
    r.register(Tool(
        name="kill_process",
        description="Terminate a process by name. Critical Windows processes are protected.",
        parameters=_obj(
            {"name": _str("Process name, e.g. 'chrome'."), "force": _bool("Kill instead of graceful terminate.")},
            ["name"],
        ),
        handler=lambda name, force=False: get_laptop().kill_process(name, force),
        risk=Risk.HIGH, category="process", requires_confirmation=True,
    ))
    r.register(Tool(
        name="start_process",
        description="Start a program or command, optionally with UAC elevation.",
        parameters=_obj(
            {"command": _str("Command or program to start."), "elevated": _bool("Request administrator elevation.")},
            ["command"],
        ),
        handler=lambda command, elevated=False: get_laptop().start_process(command, elevated),
        risk=Risk.MEDIUM, category="process", requires_confirmation=True,
    ))


# --------------------------------------------------------------- clipboard
def _register_clipboard(r: ToolRegistry) -> None:
    r.register(Tool(
        name="get_clipboard",
        description="Read the current Windows clipboard text.",
        parameters=_obj({}),
        handler=lambda: get_laptop().get_clipboard(),
        risk=Risk.SAFE, category="clipboard",
    ))
    r.register(Tool(
        name="set_clipboard",
        description="Replace the Windows clipboard with given text.",
        parameters=_obj({"text": _str("Text to place on the clipboard.")}, ["text"]),
        handler=lambda text: get_laptop().set_clipboard(text),
        risk=Risk.LOW, category="clipboard",
    ))


# ----------------------------------------------------------------- network
def _register_network(r: ToolRegistry) -> None:
    r.register(Tool(
        name="public_ip",
        description="Public IPv4 address of this machine.",
        parameters=_obj({}),
        handler=lambda: get_laptop().public_ip(),
        risk=Risk.SAFE, category="network",
    ))
    r.register(Tool(
        name="local_ip",
        description="Local LAN IP address and hostname.",
        parameters=_obj({}),
        handler=lambda: get_laptop().local_ip(),
        risk=Risk.SAFE, category="network",
    ))
    r.register(Tool(
        name="ping",
        description="Ping a host and return average latency.",
        parameters=_obj(
            {"host": _str("Hostname or IP."), "count": _int("Packet count.", 1, 10)},
            ["host"],
        ),
        handler=lambda host="8.8.8.8", count=4: get_laptop().ping(host, count),
        risk=Risk.SAFE, category="network",
    ))
    r.register(Tool(
        name="wifi_networks",
        description="Scan for nearby Wi-Fi networks with signal strengths.",
        parameters=_obj({}),
        handler=lambda: get_laptop().wifi_networks(),
        risk=Risk.SAFE, category="network",
    ))
    r.register(Tool(
        name="current_wifi",
        description="SSID, signal and channel of the connected Wi-Fi network.",
        parameters=_obj({}),
        handler=lambda: get_laptop().current_wifi(),
        risk=Risk.SAFE, category="network",
    ))
    r.register(Tool(
        name="scan_ports",
        description="TCP scan a short list of common ports on a host.",
        parameters=_obj(
            {"host": _str("Target host."), "ports": _array("Ports to scan.", _int("Port number."))},
            ["host"],
        ),
        handler=lambda host="127.0.0.1", ports=None: get_laptop().scan_ports(host, ports),
        risk=Risk.MEDIUM, category="network", requires_confirmation=True,
    ))
    r.register(Tool(
        name="listening_ports",
        description="Ports this machine is listening on with owning PIDs.",
        parameters=_obj({}),
        handler=lambda: get_laptop().listening_ports(),
        risk=Risk.SAFE, category="network",
    ))
    r.register(Tool(
        name="active_connections",
        description="Established network connections with remote endpoints.",
        parameters=_obj({}),
        handler=lambda: get_laptop().active_connections(),
        risk=Risk.SAFE, category="network",
    ))


# ------------------------------------------------------------------- shell
def _register_shell(r: ToolRegistry) -> None:
    r.register(Tool(
        name="run_shell",
        description=(
            "Run a shell command on this laptop. Read-only commands (dir, ipconfig, tasklist…) "
            "run directly; anything destructive or unknown requires user confirmation and may be blocked."
        ),
        parameters=_obj(
            {
                "command": _str("The shell command to execute."),
                "timeout": _int("Seconds before timeout.", 5, 300),
                "cwd": _str("Optional working directory."),
            },
            ["command"],
        ),
        handler=lambda command, timeout=60, cwd=None: get_laptop().run_shell(command, timeout, cwd),
        risk=Risk.HIGH, category="shell", requires_confirmation=True,
    ))


# ------------------------------------------------------------------ notify
def _register_notify(r: ToolRegistry) -> None:
    r.register(Tool(
        name="show_notification",
        description="Show a Windows toast notification with a title and message.",
        parameters=_obj(
            {"title": _str("Notification title."), "message": _str("Notification body."), "duration": _int("Seconds, 2-30.", 2, 30)},
            ["title", "message"],
        ),
        handler=lambda title, message, duration=5: get_laptop().notify(title, message, duration),
        risk=Risk.LOW, category="notify",
    ))


# ----------------------------------------------------------- android device
def _register_android_device(r: ToolRegistry) -> None:
    dev = r.register
    dev(Tool(
        name="android_status",
        description="Connected Android devices with model, Android version, battery and Wi-Fi.",
        parameters=_obj({}),
        handler=lambda: get_android().overview(),
        risk=Risk.SAFE, category="android_device",
    ))
    dev(Tool(
        name="android_battery",
        description="Phone battery percentage, charging state and temperature.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().battery(device),
        risk=Risk.SAFE, category="android_device", requires_device=True,
    ))
    dev(Tool(
        name="android_info",
        description="Phone model, brand, Android version, resolution and build.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().get_device_info(device),
        risk=Risk.SAFE, category="android_device", requires_device=True,
    ))
    dev(Tool(
        name="android_storage",
        description="Phone storage usage per mount point.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().storage(device),
        risk=Risk.SAFE, category="android_device", requires_device=True,
    ))
    dev(Tool(
        name="android_wake",
        description="Wake the phone screen.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().wake(device),
        risk=Risk.LOW, category="android_device", requires_device=True,
    ))
    dev(Tool(
        name="android_sleep",
        description="Turn the phone screen off.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().sleep_screen(device),
        risk=Risk.LOW, category="android_device", requires_device=True,
    ))
    dev(Tool(
        name="android_set_brightness",
        description="Set phone screen brightness (0-255).",
        parameters=_obj(
            {"level": _int("Brightness 0-255.", 0, 255), "device": DEVICE},
            ["level"],
        ),
        handler=lambda level, device=None: get_android().set_brightness(level, device),
        risk=Risk.LOW, category="android_device", requires_device=True,
    ))
    dev(Tool(
        name="android_wifi",
        description="Read phone Wi-Fi state, SSID and signal level.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().wifi(device),
        risk=Risk.SAFE, category="android_device", requires_device=True,
    ))
    dev(Tool(
        name="android_set_wifi",
        description="Turn the phone Wi-Fi on or off.",
        parameters=_obj({"enabled": _bool("True to enable Wi-Fi."), "device": DEVICE}, ["enabled"]),
        handler=lambda enabled, device=None: get_android().set_wifi(enabled, device),
        risk=Risk.MEDIUM, category="android_device", requires_device=True, requires_confirmation=True,
    ))
    dev(Tool(
        name="android_set_bluetooth",
        description="Turn the phone Bluetooth on or off.",
        parameters=_obj({"enabled": _bool("True to enable Bluetooth."), "device": DEVICE}, ["enabled"]),
        handler=lambda enabled, device=None: get_android().set_bluetooth(enabled, device),
        risk=Risk.MEDIUM, category="android_device", requires_device=True, requires_confirmation=True,
    ))
    dev(Tool(
        name="android_ringer_mode",
        description="Get or set ringer mode: normal, vibrate or silent.",
        parameters=_obj(
            {"mode": _str("Leave empty to read current mode.", ["normal", "vibrate", "silent"]), "device": DEVICE},
        ),
        handler=lambda mode=None, device=None: (
            get_android().set_ringer_mode(mode, device) if mode else get_android().ringer_mode(device)
        ),
        risk=Risk.LOW, category="android_device", requires_device=True,
    ))
    dev(Tool(
        name="android_set_volume",
        description="Set a phone volume stream (music/ring/notification/alarm/system) to a level 0-15.",
        parameters=_obj(
            {
                "stream": _str("Audio stream.", ["music", "ring", "notification", "alarm", "system"]),
                "level": _int("Volume 0-15.", 0, 15),
                "device": DEVICE,
            },
            ["stream", "level"],
        ),
        handler=lambda stream, level, device=None: get_android().set_volume(stream, level, device),
        risk=Risk.LOW, category="android_device", requires_device=True,
    ))
    dev(Tool(
        name="android_dnd",
        description="Enable or disable Do Not Disturb on the phone.",
        parameters=_obj({"enabled": _bool("True to enable DND."), "device": DEVICE}, ["enabled"]),
        handler=lambda enabled, device=None: get_android().do_not_disturb(enabled, device),
        risk=Risk.LOW, category="android_device", requires_device=True,
    ))
    dev(Tool(
        name="android_airplane_mode",
        description="Toggle airplane mode on the phone.",
        parameters=_obj({"enabled": _bool("True to enable airplane mode."), "device": DEVICE}, ["enabled"]),
        handler=lambda enabled, device=None: get_android().airplane_mode(enabled, device),
        risk=Risk.MEDIUM, category="android_device", requires_device=True, requires_confirmation=True,
    ))


# ------------------------------------------------------------ android apps
def _register_android_apps(r: ToolRegistry) -> None:
    r.register(Tool(
        name="android_list_apps",
        description="List installed packages on the phone (third-party, system or all).",
        parameters=_obj(
            {"kind": _str("Package set.", ["third_party", "system", "all", "enabled", "disabled"]), "device": DEVICE},
        ),
        handler=lambda kind="third_party", device=None: get_android().list_apps(device, kind),
        risk=Risk.SAFE, category="android_apps", requires_device=True,
    ))
    r.register(Tool(
        name="android_search_apps",
        description="Find installed package names by partial match.",
        parameters=_obj({"query": _str("Package name fragment."), "device": DEVICE}, ["query"]),
        handler=lambda query, device=None: get_android().search_apps(query, device),
        risk=Risk.SAFE, category="android_apps", requires_device=True,
    ))
    r.register(Tool(
        name="android_launch_app",
        description="Launch an Android app by package name (find it first with android_search_apps).",
        parameters=_obj(
            {"package_name": _str("Package id, e.g. 'com.whatsapp'."), "activity": _str("Optional explicit activity."), "device": DEVICE},
            ["package_name"],
        ),
        handler=lambda package_name, activity=None, device=None: get_android().launch_app(package_name, activity, device),
        risk=Risk.LOW, category="android_apps", requires_device=True,
    ))
    r.register(Tool(
        name="android_stop_app",
        description="Force-stop an Android app.",
        parameters=_obj({"package_name": _str("Package id."), "device": DEVICE}, ["package_name"]),
        handler=lambda package_name, device=None: get_android().stop_app(package_name, device),
        risk=Risk.MEDIUM, category="android_apps", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_install_apk",
        description="Install an .apk file from this computer onto the phone.",
        parameters=_obj({"apk_path": _str("Path to the .apk on this computer."), "device": DEVICE}, ["apk_path"]),
        handler=lambda apk_path, device=None: get_android().install_app(apk_path, device),
        risk=Risk.MEDIUM, category="android_apps", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_uninstall_app",
        description="Uninstall a package from the phone.",
        parameters=_obj({"package_name": _str("Package id."), "device": DEVICE}, ["package_name"]),
        handler=lambda package_name, device=None: get_android().uninstall_app(package_name, device),
        risk=Risk.HIGH, category="android_apps", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_clear_data",
        description="Clear an app's storage and cache (equivalent to 'clear data').",
        parameters=_obj({"package_name": _str("Package id."), "device": DEVICE}, ["package_name"]),
        handler=lambda package_name, device=None: get_android().clear_app_data(package_name, device),
        risk=Risk.HIGH, category="android_apps", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_app_info",
        description="Version, install times and system flag for a package.",
        parameters=_obj({"package_name": _str("Package id."), "device": DEVICE}, ["package_name"]),
        handler=lambda package_name, device=None: get_android().app_info(package_name, device),
        risk=Risk.SAFE, category="android_apps", requires_device=True,
    ))
    r.register(Tool(
        name="android_app_permissions",
        description="Granted and denied permissions for a package.",
        parameters=_obj({"package_name": _str("Package id."), "device": DEVICE}, ["package_name"]),
        handler=lambda package_name, device=None: get_android().app_permissions(package_name, device),
        risk=Risk.SAFE, category="android_apps", requires_device=True,
    ))
    r.register(Tool(
        name="android_grant_permission",
        description="Grant a runtime permission to an app via adb.",
        parameters=_obj(
            {"package_name": _str("Package id."), "permission": _str("e.g. android.permission.CAMERA."), "device": DEVICE},
            ["package_name", "permission"],
        ),
        handler=lambda package_name, permission, device=None: get_android().grant_permission(package_name, permission, device),
        risk=Risk.MEDIUM, category="android_apps", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_foreground_app",
        description="Which app is currently in the foreground on the phone.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().foreground_app(device),
        risk=Risk.SAFE, category="android_apps", requires_device=True,
    ))


# ----------------------------------------------------------- android input
def _register_android_input(r: ToolRegistry) -> None:
    r.register(Tool(
        name="android_tap",
        description="Tap a point on the phone screen.",
        parameters=_obj({"x": _int("X in device pixels."), "y": _int("Y in device pixels."), "device": DEVICE}, ["x", "y"]),
        handler=lambda x, y, device=None: get_android().tap(x, y, device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))
    r.register(Tool(
        name="android_long_press",
        description="Long-press a point on the phone screen.",
        parameters=_obj(
            {"x": _int("X."), "y": _int("Y."), "duration_ms": _int("Press duration ms, 100-5000.", 100, 5000), "device": DEVICE},
            ["x", "y"],
        ),
        handler=lambda x, y, duration_ms=800, device=None: get_android().long_press(x, y, duration_ms, device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))
    r.register(Tool(
        name="android_swipe",
        description="Swipe between two points on the phone screen.",
        parameters=_obj(
            {"x1": _int("Start X."), "y1": _int("Start Y."), "x2": _int("End X."), "y2": _int("End Y."),
             "duration_ms": _int("Duration ms.", 50, 5000), "device": DEVICE},
            ["x1", "y1", "x2", "y2"],
        ),
        handler=lambda x1, y1, x2, y2, duration_ms=300, device=None: get_android().swipe(x1, y1, x2, y2, duration_ms, device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))
    r.register(Tool(
        name="android_swipe_direction",
        description="Swipe up/down/left/right from screen centre (scroll, go back gesture, open notifications).",
        parameters=_obj(
            {"direction": _str("Swipe direction.", ["up", "down", "left", "right"]),
             "distance": _int("Pixels to travel.", 50, 2000), "device": DEVICE},
            ["direction"],
        ),
        handler=lambda direction, distance=400, device=None: get_android().swipe_direction(direction, distance, device=device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))
    r.register(Tool(
        name="android_type",
        description="Type text into the focused field on the phone.",
        parameters=_obj({"text": _str("Text to type."), "device": DEVICE}, ["text"]),
        handler=lambda text, device=None: get_android().type_text(text, device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))
    r.register(Tool(
        name="android_press_key",
        description=(
            "Press an Android key: home, back, recents, enter, tab, volume_up, volume_down, power, "
            "play_pause, an Android keycode like KEYCODE_APP_SWITCH, or a single letter/digit."
        ),
        parameters=_obj({"key": _str("Key name or keycode."), "device": DEVICE}, ["key"]),
        handler=lambda key, device=None: get_android().press_key(key, device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))
    r.register(Tool(
        name="android_key_combo",
        description="Press an Android key combination (e.g. volume_down + power for screenshot).",
        parameters=_obj({"keys": _array("Keys in the combination.", _str("Key name.")), "device": DEVICE}, ["keys"]),
        handler=lambda keys, device=None: get_android().key_combo(*keys, device=device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))
    r.register(Tool(
        name="android_home",
        description="Press the phone Home button.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().home(device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))
    r.register(Tool(
        name="android_back",
        description="Press the phone Back button.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().back(device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))
    r.register(Tool(
        name="android_recents",
        description="Open the phone's recent-apps switcher.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().recent(device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))
    r.register(Tool(
        name="android_open_notifications",
        description="Pull down the phone's notification shade.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().open_notifications(device),
        risk=Risk.LOW, category="android_input", requires_device=True,
    ))


# ----------------------------------------------------------- android screen
def _register_android_screen(r: ToolRegistry) -> None:
    r.register(Tool(
        name="android_screenshot",
        description="Capture the phone screen and return the local image path.",
        parameters=_obj({"filename": _str("Optional local output path."), "device": DEVICE}),
        handler=lambda filename="android.png", device=None: get_android().screenshot(filename, device),
        risk=Risk.LOW, category="android_screen", requires_device=True,
    ))
    r.register(Tool(
        name="android_record_screen",
        description="Record the phone screen for N seconds and return the .mp4 path.",
        parameters=_obj(
            {"duration": _int("Seconds, 3-180.", 3, 180), "filename": _str("Optional output path."), "device": DEVICE},
            ["duration"],
        ),
        handler=lambda duration=10, filename="screenrecord.mp4", device=None: get_android().record_screen(duration, filename, device),
        risk=Risk.MEDIUM, category="android_screen", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_ui_dump",
        description="Dump the current screen's UI hierarchy (text, ids, bounds) — use to find tappable elements.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().ui_dump(device),
        risk=Risk.SAFE, category="android_screen", requires_device=True,
    ))
    r.register(Tool(
        name="android_screen_size",
        description="Phone screen resolution in pixels.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().screen_size(device),
        risk=Risk.SAFE, category="android_screen", requires_device=True,
    ))


# ----------------------------------------------------------- android files
def _register_android_files(r: ToolRegistry) -> None:
    r.register(Tool(
        name="android_list_files",
        description="List files on the phone (default /sdcard).",
        parameters=_obj({"path": _str("Device folder."), "device": DEVICE}),
        handler=lambda path="/sdcard", device=None: get_android().list_files(path, device),
        risk=Risk.SAFE, category="android_files", requires_device=True,
    ))
    r.register(Tool(
        name="android_push_file",
        description="Copy a file from this computer to the phone.",
        parameters=_obj(
            {"local": _str("Local path."), "remote": _str("Device destination path."), "device": DEVICE},
            ["local", "remote"],
        ),
        handler=lambda local, remote, device=None: get_android().push_file(local, remote, device),
        risk=Risk.MEDIUM, category="android_files", requires_device=True,
    ))
    r.register(Tool(
        name="android_pull_file",
        description="Copy a file from the phone to this computer.",
        parameters=_obj(
            {"remote": _str("Device path."), "local": _str("Local destination."), "device": DEVICE},
            ["remote"],
        ),
        handler=lambda remote, local=None, device=None: get_android().pull_file(remote, local, device),
        risk=Risk.LOW, category="android_files", requires_device=True,
    ))
    r.register(Tool(
        name="android_delete_file",
        description="Delete a file on the phone (system roots are refused).",
        parameters=_obj(
            {"path": _str("Device path."), "recursive": _bool("Delete directories recursively."), "device": DEVICE},
            ["path"],
        ),
        handler=lambda path, recursive=False, device=None: get_android().delete_file(path, recursive, device),
        risk=Risk.HIGH, category="android_files", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_read_file",
        description="Read a text file from the phone.",
        parameters=_obj({"path": _str("Device file path."), "device": DEVICE}, ["path"]),
        handler=lambda path, device=None: get_android().read_file(path, device),
        risk=Risk.SAFE, category="android_files", requires_device=True,
    ))
    r.register(Tool(
        name="android_search_files",
        description="Find files on the phone by name pattern.",
        parameters=_obj(
            {"path": _str("Folder to search."), "pattern": _str("Name pattern, e.g. 'photo'."), "device": DEVICE},
            ["path", "pattern"],
        ),
        handler=lambda path, pattern, device=None: get_android().search_files(path, pattern, device),
        risk=Risk.SAFE, category="android_files", requires_device=True,
    ))


# ----------------------------------------------------------- android comms
def _register_android_comms(r: ToolRegistry) -> None:
    r.register(Tool(
        name="android_send_sms",
        description=(
            "Compose an SMS to a phone number. Opens the messaging app pre-filled; "
            "use android_send_sms_direct only if the device allows silent sends."
        ),
        parameters=_obj(
            {"number": _str("Recipient phone number."), "message": _str("SMS body."), "device": DEVICE},
            ["number", "message"],
        ),
        handler=lambda number, message, device=None: get_android().send_sms(number, message, device),
        risk=Risk.MEDIUM, category="android_comms", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_read_sms",
        description="Read recent SMS messages from the phone inbox.",
        parameters=_obj({"limit": _int("How many messages.", 1, 100), "device": DEVICE}),
        handler=lambda limit=20, device=None: get_android().read_sms(limit, device),
        risk=Risk.MEDIUM, category="android_comms", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_call_log",
        description="Read the phone's recent call history.",
        parameters=_obj({"limit": _int("How many entries.", 1, 100), "device": DEVICE}),
        handler=lambda limit=20, device=None: get_android().call_log(limit, device),
        risk=Risk.MEDIUM, category="android_comms", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_contacts",
        description="List contacts (name and phone number) from the phone.",
        parameters=_obj({"limit": _int("How many contacts.", 1, 300), "device": DEVICE}),
        handler=lambda limit=50, device=None: get_android().contacts(limit, device),
        risk=Risk.MEDIUM, category="android_comms", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_dial",
        description="Open the dialer with a number prefilled.",
        parameters=_obj({"number": _str("Phone number."), "device": DEVICE}, ["number"]),
        handler=lambda number, device=None: get_android().dial(number, device),
        risk=Risk.LOW, category="android_comms", requires_device=True,
    ))
    r.register(Tool(
        name="android_call",
        description="Place an actual phone call (requires CALL_PHONE permission).",
        parameters=_obj({"number": _str("Phone number."), "device": DEVICE}, ["number"]),
        handler=lambda number, device=None: get_android().call(number, device),
        risk=Risk.HIGH, category="android_comms", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_open_url",
        description="Open a URL on the phone in its default browser.",
        parameters=_obj({"url": _str("URL to open."), "device": DEVICE}, ["url"]),
        handler=lambda url, device=None: get_android().open_url(url, device),
        risk=Risk.LOW, category="android_comms", requires_device=True,
    ))
    r.register(Tool(
        name="android_share_text",
        description="Open the Android share sheet with text ready to send.",
        parameters=_obj({"text": _str("Text to share."), "device": DEVICE}, ["text"]),
        handler=lambda text, device=None: get_android().share_text(text, device),
        risk=Risk.LOW, category="android_comms", requires_device=True,
    ))
    r.register(Tool(
        name="android_recent_notifications",
        description="Currently posted notifications on the phone with app, title and text.",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().recent_notifications(device),
        risk=Risk.MEDIUM, category="android_comms", requires_device=True, requires_confirmation=True,
    ))


# ---------------------------------------------------------- android system
def _register_android_system(r: ToolRegistry) -> None:
    r.register(Tool(
        name="android_settings_get",
        description="Read an Android system setting.",
        parameters=_obj(
            {"namespace": _str("Settings namespace.", ["system", "secure", "global"]),
             "key": _str("Setting key."), "device": DEVICE},
            ["namespace", "key"],
        ),
        handler=lambda namespace, key, device=None: get_android().settings_get(namespace, key, device),
        risk=Risk.SAFE, category="android_system", requires_device=True,
    ))
    r.register(Tool(
        name="android_settings_put",
        description="Write an Android system setting (e.g. system/screen_off_timeout).",
        parameters=_obj(
            {"namespace": _str("Settings namespace.", ["system", "secure", "global"]),
             "key": _str("Setting key."), "value": _str("New value."), "device": DEVICE},
            ["namespace", "key", "value"],
        ),
        handler=lambda namespace, key, value, device=None: get_android().settings_put(namespace, key, value, device),
        risk=Risk.MEDIUM, category="android_system", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_location",
        description="Last known GPS location of the phone (latitude/longitude).",
        parameters=_obj({"device": DEVICE}),
        handler=lambda device=None: get_android().location(device),
        risk=Risk.MEDIUM, category="android_system", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_mock_location",
        description="Set a mock GPS location on the phone (requires developer mock-location permission).",
        parameters=_obj(
            {"latitude": _num("Latitude."), "longitude": _num("Longitude."), "device": DEVICE},
            ["latitude", "longitude"],
        ),
        handler=lambda latitude, longitude, device=None: get_android().set_mock_location(latitude, longitude, device),
        risk=Risk.HIGH, category="android_system", requires_device=True, requires_confirmation=True,
    ))
    r.register(Tool(
        name="android_wireless_connect",
        description="Connect to the phone over Wi-Fi for wireless adb (pairing code may be required first).",
        parameters=_obj(
            {"host": _str("Phone IP or IP:port."), "port": _int("Port, default 5555.", 1, 65535)},
            ["host"],
        ),
        handler=lambda host, port=5555: get_android().wireless_connect(host, port),
        risk=Risk.LOW, category="android_system",
    ))
    r.register(Tool(
        name="android_reboot",
        description="Reboot the phone (normal, recovery or bootloader).",
        parameters=_obj(
            {"target": _str("Reboot target: leave empty for a normal reboot, or 'recovery' / 'bootloader'."), "device": DEVICE},
        ),
        handler=lambda target="", device=None: get_android().reboot(device, target),
        risk=Risk.HIGH, category="android_system", requires_device=True, requires_confirmation=True,
    ))
