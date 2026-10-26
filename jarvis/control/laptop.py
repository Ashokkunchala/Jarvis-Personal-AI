"""LaptopController — one facade over every local-machine control module.

Every method returns a dict with at least ``{"success": bool}``. Nothing here
requires the FastAPI backend; the CLI, the TUI and the Gemini tool loop all
talk to this object directly.
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis.control import (
    apps,
    audio,
    clipboard,
    files,
    info,
    input_ctl,
    network,
    notify,
    power,
    process,
    screen,
    shell,
    window,
)

logger = logging.getLogger("jarvis.control.laptop")


class LaptopController:
    """Aggregated local machine control surface."""

    # ------------------------------------------------------------------ apps
    def search_apps(self, query: str, limit: int = 15) -> list[dict[str, Any]]:
        return apps.search_apps(query, limit=limit)

    def open_app(self, app: str, args: str | None = None) -> dict[str, Any]:
        return apps.launch_app(app, args)

    def close_app(self, name: str, force: bool = False) -> dict[str, Any]:
        return apps.close_app(name, force=force)

    def list_running_apps(self) -> list[dict[str, Any]]:
        return apps.list_running_apps()

    # ----------------------------------------------------------------- audio
    def get_volume(self) -> dict[str, Any]:
        return audio.get_volume()

    def set_volume(self, level: int) -> dict[str, Any]:
        return audio.set_volume(level)

    def adjust_volume(self, delta: int) -> dict[str, Any]:
        return audio.adjust_volume(delta)

    def set_mute(self, muted: bool = True) -> dict[str, Any]:
        return audio.set_mute(muted)

    def toggle_mute(self) -> dict[str, Any]:
        return audio.toggle_mute()

    def list_audio_sessions(self) -> list[dict[str, Any]]:
        return audio.list_sessions()

    # ---------------------------------------------------------------- window
    def list_windows(self) -> list[dict[str, Any]]:
        return window.list_windows()

    def focus_window(self, title: str) -> dict[str, Any]:
        return window.focus_window(title)

    def minimize_window(self, title: str) -> dict[str, Any]:
        return window.minimize_window(title)

    def maximize_window(self, title: str) -> dict[str, Any]:
        return window.maximize_window(title)

    def restore_window(self, title: str) -> dict[str, Any]:
        return window.restore_window(title)

    def close_window(self, title: str) -> dict[str, Any]:
        return window.close_window(title)

    def move_window(self, title: str, x: int, y: int, width: int | None = None, height: int | None = None) -> dict[str, Any]:
        return window.move_window(title, x, y, width, height)

    def get_active_window(self) -> dict[str, Any]:
        return window.get_active_window()

    # ----------------------------------------------------------------- power
    def lock(self) -> dict[str, Any]:
        return power.lock()

    def sleep(self) -> dict[str, Any]:
        return power.sleep_()

    def hibernate(self) -> dict[str, Any]:
        return power.hibernate()

    def shutdown(self, delay: int = 10) -> dict[str, Any]:
        return power.shutdown(delay)

    def restart(self, delay: int = 10) -> dict[str, Any]:
        return power.restart(delay)

    def logoff(self, delay: int = 0) -> dict[str, Any]:
        return power.logoff(delay)

    def cancel_shutdown(self) -> dict[str, Any]:
        return power.cancel()

    # ----------------------------------------------------------------- screen
    def screenshot(self, path: str | None = None, region: dict[str, int] | None = None) -> dict[str, Any]:
        return screen.screenshot(path, region)

    def screen_size(self) -> dict[str, Any]:
        return screen.screen_size()

    def get_pixel_color(self, x: int, y: int) -> dict[str, Any]:
        return screen.get_pixel_color(x, y)

    def record_screen(self, duration: int = 10, path: str | None = None) -> dict[str, Any]:
        return screen.record_screen(duration, path)

    def ocr_screen(self, region: dict[str, int] | None = None) -> dict[str, Any]:
        return screen.ocr_screen(region)

    # ------------------------------------------------------------------ input
    def type_text(self, text: str, interval: float = 0.02) -> dict[str, Any]:
        return input_ctl.type_text(text, interval)

    def press_keys(self, keys: list[str]) -> dict[str, Any]:
        return input_ctl.press_keys(keys)

    def hotkey(self, *keys: str) -> dict[str, Any]:
        return input_ctl.hotkey(*keys)

    def click(self, x: int | None = None, y: int | None = None, button: str = "left", clicks: int = 1) -> dict[str, Any]:
        return input_ctl.click(x, y, button, clicks)

    def right_click(self, x: int, y: int) -> dict[str, Any]:
        return input_ctl.right_click(x, y)

    def double_click(self, x: int, y: int) -> dict[str, Any]:
        return input_ctl.double_click(x, y)

    def move_mouse(self, x: int, y: int, duration: float = 0.2) -> dict[str, Any]:
        return input_ctl.move_mouse(x, y, duration)

    def scroll(self, direction: str = "down", amount: int = 3) -> dict[str, Any]:
        return input_ctl.scroll(direction, amount)

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
        return input_ctl.drag(x1, y1, x2, y2)

    def mouse_position(self) -> dict[str, Any]:
        return input_ctl.mouse_position()

    def media_key(self, key: str) -> dict[str, Any]:
        return input_ctl.press_media(key)

    # ------------------------------------------------------------------ files
    def list_dir(self, path: str = ".", limit: int = 200) -> dict[str, Any]:
        return files.list_dir(path, limit)

    def search_files(self, query: str, roots: list[str] | None = None, max_results: int = 40) -> dict[str, Any]:
        return files.search_files(query, roots, max_results)

    def read_file(self, path: str, max_bytes: int = 64000) -> dict[str, Any]:
        return files.read_text(path, max_bytes)

    def write_file(self, path: str, content: str, append: bool = False) -> dict[str, Any]:
        return files.write_text(path, content, append)

    def copy_path(self, source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
        return files.copy(source, destination, overwrite)

    def move_path(self, source: str, destination: str) -> dict[str, Any]:
        return files.move(source, destination)

    def rename_path(self, path: str, new_name: str) -> dict[str, Any]:
        return files.rename(path, new_name)

    def delete_path(self, path: str, permanent: bool = False) -> dict[str, Any]:
        return files.delete(path, permanent)

    def create_folder(self, path: str) -> dict[str, Any]:
        return files.create_folder(path)

    def open_path(self, path: str) -> dict[str, Any]:
        return files.open_path(path)

    def file_info(self, path: str) -> dict[str, Any]:
        return files.file_info(path)

    def organize_folder(self, path: str) -> dict[str, Any]:
        return files.organize_folder(path)

    # --------------------------------------------------------------- process
    def list_processes(self, search: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return process.list_processes(search, limit)

    def kill_process(self, name: str, force: bool = False) -> dict[str, Any]:
        return process.terminate_process(name, force)

    def start_process(self, command: str, elevated: bool = False) -> dict[str, Any]:
        return process.start_process(command, elevated)

    def process_details(self, pid: int) -> dict[str, Any]:
        return process.process_details(pid)

    # -------------------------------------------------------------- clipboard
    def get_clipboard(self) -> dict[str, Any]:
        return clipboard.get_clipboard()

    def set_clipboard(self, text: str) -> dict[str, Any]:
        return clipboard.set_clipboard(text)

    # ---------------------------------------------------------------- network
    def public_ip(self) -> dict[str, Any]:
        return network.public_ip()

    def local_ip(self) -> dict[str, Any]:
        return network.local_ip()

    def ping(self, host: str = "8.8.8.8", count: int = 4) -> dict[str, Any]:
        return network.ping(host, count)

    def wifi_networks(self) -> dict[str, Any]:
        return network.wifi_networks()

    def current_wifi(self) -> dict[str, Any]:
        return network.current_wifi()

    def scan_ports(self, host: str = "127.0.0.1", ports: list[int] | None = None) -> dict[str, Any]:
        return network.scan_ports(host, ports)

    def listening_ports(self) -> list[dict[str, Any]]:
        return network.listening_ports()

    def active_connections(self) -> list[dict[str, Any]]:
        return network.active_connections()

    # ------------------------------------------------------------------ shell
    def run_shell(self, command: str, timeout: int = 60, cwd: str | None = None, dry_run: bool = False) -> dict[str, Any]:
        return shell.run(command, timeout=timeout, cwd=cwd, dry_run=dry_run)

    def classify_shell(self, command: str) -> str:
        return shell.classify(command)

    # ----------------------------------------------------------------- notify
    def notify(self, title: str, message: str, duration: int = 5) -> dict[str, Any]:
        return notify.notify(title, message, duration=duration)

    # ------------------------------------------------------------------- info
    def os_info(self) -> dict[str, Any]:
        return info.os_info()

    def cpu_usage(self, interval: float = 0.5) -> dict[str, Any]:
        return info.cpu_usage(interval)

    def memory_usage(self) -> dict[str, Any]:
        return info.memory_usage()

    def disk_usage(self, path: str = "C:\\") -> dict[str, Any]:
        return info.disk_usage(path)

    def battery(self) -> dict[str, Any]:
        return info.battery()

    def gpu_info(self) -> list[dict[str, Any]]:
        return info.gpu_info()

    def top_processes(self, limit: int = 10) -> list[dict[str, Any]]:
        return info.top_processes(limit)

    def status(self) -> dict[str, Any]:
        return info.summary()

    # --------------------------------------------------------------- overview
    def overview(self) -> dict[str, Any]:
        return {
            "success": True,
            "status": self.status(),
            "os": self.os_info(),
            "battery": self.battery(),
            "volume": self.get_volume(),
            "android_devices": [],
        }
