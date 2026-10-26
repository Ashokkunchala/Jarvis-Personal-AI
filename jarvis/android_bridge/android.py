"""AndroidController — one facade over every ADB control module.

Backwards compatible with the original ``AndroidController`` API (``devices``,
``run_adb``, ``get_device_info``…) while exposing the full control surface:

    from jarvis.android_bridge import AndroidController
    az = AndroidController()
    az.battery()        # device state
    az.launch_app(...)  # app control
    az.tap(540, 1200)   # input injection
    az.screenshot()     # screen capture
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis.android_bridge import (
    adb,
    apps,
    comms,
    device,
    files,
    input_ctl,
    location,
    notifications,
    screen,
    settings_ctl,
    wireless,
)

logger = logging.getLogger("jarvis.android")


class AndroidController:
    """Full Android device control surface over ADB."""

    def __init__(self, serial: str | None = None):
        self._explicit_serial = serial
        self._devices: list[str] = []
        self.refresh_devices()

    # ------------------------------------------------------------ discovery
    @property
    def adb_path(self) -> str:
        return adb.find_adb()

    @property
    def devices(self) -> list[str]:
        return list(self._devices)

    def refresh_devices(self) -> list[str]:
        self._devices = adb.refresh_devices()
        return list(self._devices)

    @property
    def connected(self) -> bool:
        return bool(adb.pick_device(self._explicit_serial))

    @property
    def serial(self) -> str | None:
        return adb.pick_device(self._explicit_serial)

    def state(self) -> dict[str, Any]:
        return adb.device_state(self._explicit_serial)

    def _dev(self, serial: str | None = None) -> str | None:
        return serial or adb.pick_device(self._explicit_serial)

    def _require(self, serial: str | None = None):
        return adb.require_device(self._dev(serial))

    def run_adb(self, command: list[str], device: str | None = None) -> dict[str, Any]:  # noqa: A002
        return adb.run_adb(command, device=device)

    def shell(self, command: Any, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        return adb.shell(command, device=device)

    # ------------------------------------------------------------- device
    def get_device_info(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.device_info(serial)

    def battery(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.battery(serial)

    def screen_state(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device_module_helper(serial)

    def wake(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.wake(serial)

    def sleep_screen(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.sleep_screen(serial)

    def toggle_screen(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.toggle_screen(serial)

    def set_brightness(self, level: int, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.set_brightness(level, serial)

    def get_brightness(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.get_brightness(serial)

    def wifi(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.wifi(serial)

    def set_wifi(self, enabled: bool, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.set_wifi(enabled, serial)

    def bluetooth(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.bluetooth(serial)

    def set_bluetooth(self, enabled: bool, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.set_bluetooth(enabled, serial)

    def ringer_mode(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.ringer_mode(serial)

    def set_ringer_mode(self, mode: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.set_ringer_mode(mode, serial)

    def set_volume(self, stream: str, level: int, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.set_volume(stream, level, serial)

    def get_volume(self, stream: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.get_volume(stream, serial)

    def airplane_mode(self, enabled: bool, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.airplane_mode(enabled, serial)

    def do_not_disturb(self, enabled: bool, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.do_not_disturb(enabled, serial)

    def storage(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return device.storage(serial)

    # --------------------------------------------------------------- apps
    def list_apps(self, device: str | None = None, kind: str = "third_party") -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.list_packages(serial, kind)

    def search_apps(self, query: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.search_packages(query, serial)

    def install_app(self, apk_path: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.install_apk(apk_path, serial)

    def uninstall_app(self, package_name: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.uninstall(package_name, serial)

    def launch_app(self, package_name: str, activity: str | None = None, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.launch(package_name, activity, serial)

    def stop_app(self, package_name: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.stop(package_name, serial)

    def clear_app_data(self, package_name: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.clear_data(package_name, serial)

    def app_info(self, package_name: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.package_info(package_name, serial)

    def app_permissions(self, package_name: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.permissions(package_name, serial)

    def grant_permission(self, package_name: str, permission: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.grant_permission(package_name, permission, serial)

    def revoke_permission(self, package_name: str, permission: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.revoke_permission(package_name, permission, serial)

    def foreground_app(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return apps.running_activities(serial)

    # -------------------------------------------------------------- input
    def tap(self, x: int, y: int, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return input_ctl.tap(x, y, serial)

    def double_tap(self, x: int, y: int, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return input_ctl.double_tap(x, y, serial)

    def long_press(self, x: int, y: int, duration_ms: int = 800, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return input_ctl.long_press(x, y, duration_ms, serial)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return input_ctl.swipe(x1, y1, x2, y2, duration, serial)

    def swipe_direction(self, direction: str, distance: int = 400, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return input_ctl.swipe_direction(direction, distance, serial=serial)

    def type_text(self, text: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return input_ctl.type_text(text, serial)

    def press_key(self, keycode: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return input_ctl.press_key(keycode, serial)

    def press_keys(self, keys: list[str], device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return input_ctl.press_keys(keys, serial)

    def key_combo(self, *keys: str, device: str | None = None) -> dict[str, Any]:
        serial, err = self._require(device)
        if err:
            return err
        return input_ctl.combo(*keys, serial=serial)

    def home(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        return self.press_key("home", device)

    def back(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        return self.press_key("back", device)

    def recent(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        return self.press_key("recents", device)

    def open_notifications(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return input_ctl.notifications_panel(serial)

    # -------------------------------------------------------------- screen
    def screenshot(self, filename: str = "android_screenshot.png", device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return screen.screenshot(filename, serial)

    def record_screen(self, duration: int = 10, filename: str = "screenrecord.mp4", device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return screen.record_screen(duration, filename, serial=serial)

    def ui_dump(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return screen.ui_dump(serial=serial)

    def screen_size(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return screen.screen_size(serial)

    # -------------------------------------------------------------- files
    def list_files(self, path: str = "/sdcard", device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return files.list_dir(path, serial)

    def push_file(self, local: str, remote: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return files.push(local, remote, serial)

    def pull_file(self, remote: str, local: str | None = None, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return files.pull(remote, local, serial)

    def delete_file(self, path: str, recursive: bool = False, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return files.delete(path, recursive, serial)

    def read_file(self, path: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return files.read_text(path, serial=serial)

    def search_files(self, path: str, pattern: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return files.search(path, pattern, serial)

    # --------------------------------------------------------------- comms
    def setup_comms(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return comms.setup_comms(serial)

    def send_sms(self, number: str, message: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return comms.send_sms(number, message, serial)

    def read_sms(self, limit: int = 20, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return comms.read_sms(limit, serial)

    def call_log(self, limit: int = 20, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return comms.call_log(limit, serial)

    def contacts(self, limit: int = 50, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return comms.contacts(limit, serial)

    def dial(self, number: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return comms.dial(number, serial)

    def call(self, number: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return comms.call(number, serial)

    def end_call(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return comms.end_call(serial)

    def open_url(self, url: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return comms.open_url(url, serial)

    def share_text(self, text: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return comms.share_text(text, serial)

    # ------------------------------------------------------- notifications
    def recent_notifications(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return notifications.recent_notifications(serial)

    # ------------------------------------------------- settings & location
    def settings_get(self, namespace: str, key: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return settings_ctl.get(namespace, key, serial)

    def settings_put(self, namespace: str, key: str, value: str, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return settings_ctl.put(namespace, key, value, serial)

    def location(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return location.last_known_location(serial)

    def set_mock_location(self, latitude: float, longitude: float, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        return location.set_mock_location(latitude, longitude, serial=serial)

    # ------------------------------------------------------------ wireless
    def wireless_setup(self, device: str | None = None) -> dict[str, Any]:
        return wireless.setup_wireless(self._dev(device))

    def wireless_connect(self, host: str, port: int = 5555) -> dict[str, Any]:
        return wireless.connect(host, port)

    def wireless_disconnect(self, host: str | None = None) -> dict[str, Any]:
        return wireless.disconnect(host)

    def wireless_devices(self) -> dict[str, Any]:
        return wireless.wireless_devices()

    # ------------------------------------------------------------ reboot
    def reboot(self, device: str | None = None, target: str = "") -> dict[str, Any]:  # noqa: A002
        serial, err = self._require(device)
        if err:
            return err
        args = ["reboot"] + ([target] if target else [])
        return adb.run_adb(args, device=serial, timeout=30)

    def reboot_recovery(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        return self.reboot(device, "recovery")

    def reboot_bootloader(self, device: str | None = None) -> dict[str, Any]:  # noqa: A002
        return self.reboot(device, "bootloader")

    # ------------------------------------------------------------ bootstrap
    def setup(self) -> dict[str, Any]:
        """One-shot provisioning: ensure adb exists, detect devices, grant comms."""
        result: dict[str, Any] = {"success": True, "steps": []}
        boot = adb.bootstrap_adb()
        result["steps"].append({"step": "adb", **boot})
        if not boot.get("success"):
            result["success"] = False
            return result

        devices = self.refresh_devices()
        result["steps"].append({"step": "devices", "found": len(devices), "serials": devices})
        if not devices:
            result["success"] = False
            result["hint"] = (
                "Enable Developer options → USB debugging on the phone, plug it in, "
                "tap 'Allow' on the authorization prompt, then re-run."
            )
            return result

        grants = comms.setup_comms(devices[0])
        result["steps"].append({"step": "comms_permissions", **grants})
        result["overview"] = self.overview()
        return result

    # ------------------------------------------------------------ overview
    def overview(self) -> dict[str, Any]:
        devices = self.refresh_devices()
        info: dict[str, Any] = {"success": True, "count": len(devices), "devices": devices, "adb": self.adb_path}
        if devices:
            info["battery"] = self.battery()
            info["device"] = self.get_device_info()
            info["wifi"] = self.wifi()
        else:
            info["battery"] = {"success": False, "error": "No device connected"}
        return info


def device_module_helper(serial: str | None) -> dict[str, Any]:
    return device.screen_state(serial)
