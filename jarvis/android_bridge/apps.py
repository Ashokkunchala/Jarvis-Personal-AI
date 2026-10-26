"""Android application management: install, launch, stop, permissions, data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.android_bridge import adb


def list_packages(serial: str | None = None, kind: str = "third_party") -> dict[str, Any]:
    """kind: third_party | system | all | enabled | disabled"""
    flag = {
        "third_party": "-3",
        "system": "-s",
        "all": "",
        "enabled": "-e",
        "disabled": "-d",
    }.get(kind, "-3")
    args = ["pm", "list", "packages"]
    if flag:
        args.append(flag)
    res = adb.shell(args, device=serial, timeout=40)
    if not res["success"]:
        return res
    packages = sorted(line.replace("package:", "").strip() for line in res["stdout"].splitlines() if line.startswith("package:"))
    return {"success": True, "packages": packages, "count": len(packages), "kind": kind}


def search_packages(query: str, serial: str | None = None) -> dict[str, Any]:
    all_pkgs = list_packages(serial, kind="all")
    if not all_pkgs.get("success"):
        return all_pkgs
    query_l = query.lower().strip()
    matches = [p for p in all_pkgs["packages"] if query_l in p.lower()]
    return {"success": True, "matches": matches, "count": len(matches), "query": query}


def install_apk(apk_path: str, serial: str | None = None, grant_permissions: bool = True) -> dict[str, Any]:
    path = Path(apk_path).expanduser()
    if not path.is_file():
        return {"success": False, "error": f"APK not found: {path}"}
    if path.suffix.lower() != ".apk":
        return {"success": False, "error": "Only .apk files are supported"}
    args = ["install", "-r"]
    if grant_permissions:
        args += ["-g"]
    args.append(str(path))
    res = adb.run_adb(args, device=serial, timeout=adb.LONG_TIMEOUT)
    if res["success"] or "Success" in res.get("stdout", ""):
        return {"success": True, "apk": str(path), "output": res.get("stdout", "")}
    return res


def uninstall(package: str, serial: str | None = None, keep_data: bool = False) -> dict[str, Any]:
    args = ["uninstall"]
    if keep_data:
        args.append("-k")
    args.append(package)
    res = adb.run_adb(args, device=serial, timeout=60)
    if res["success"] and "Success" in res.get("stdout", ""):
        return {"success": True, "package": package}
    return res


def launch(package: str, activity: str | None = None, serial: str | None = None) -> dict[str, Any]:
    if activity:
        component = activity if activity.startswith(package) else f"{package}/{activity}"
        res = adb.shell(["am", "start", "-n", component], device=serial, timeout=25)
    else:
        res = adb.shell(
            ["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
            device=serial,
            timeout=25,
        )
    if res["success"] and "Error" not in res.get("stdout", "") + res.get("stderr", ""):
        return {"success": True, "package": package, "activity": activity}
    return res


def stop(package: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["am", "force-stop", package], device=serial, timeout=20)
    if res["success"]:
        return {"success": True, "package": package, "action": "force-stopped"}
    return res


def clear_data(package: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["pm", "clear", package], device=serial, timeout=30)
    if res["success"] and "Success" in res.get("stdout", ""):
        return {"success": True, "package": package, "action": "data-cleared"}
    return res


def grant_permission(package: str, permission: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["pm", "grant", package, permission], device=serial, timeout=20)
    if res["success"]:
        return {"success": True, "package": package, "permission": permission, "action": "granted"}
    return res


def revoke_permission(package: str, permission: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["pm", "revoke", package, permission], device=serial, timeout=20)
    if res["success"]:
        return {"success": True, "package": package, "permission": permission, "action": "revoked"}
    return res


def permissions(package: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["dumpsys", "package", package], device=serial, timeout=25)
    if not res["success"]:
        return res
    granted: list[str] = []
    requested: list[str] = []
    for line in res["stdout"].splitlines():
        line = line.strip()
        if line.endswith("granted=true") and "permission" in line:
            granted.append(line.split(":")[0].strip())
        elif line.endswith("granted=false") and "permission" in line:
            requested.append(line.split(":")[0].strip())
    return {"success": True, "package": package, "granted": granted, "denied": requested}


def package_info(package: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["dumpsys", "package", package], device=serial, timeout=25)
    if not res["success"]:
        return res
    info: dict[str, Any] = {"package": package}
    for line in res["stdout"].splitlines():
        line = line.strip()
        for key in ("versionName", "versionCode", "firstInstallTime", "lastUpdateTime", "installerPackageName"):
            if line.startswith(key + "="):
                info[key] = line.split("=", 1)[1]
        if line.startswith("flags=") and "flags" not in info:
            info["flags"] = line.split("=", 1)[1]
    info["system"] = "systemApp" in res["stdout"]
    return {"success": True, **info}


def launch_activity(package: str, activity: str, serial: str | None = None) -> dict[str, Any]:
    component = activity if activity.startswith(package) else f"{package}/{activity}"
    res = adb.shell(["am", "start", "-n", component], device=serial, timeout=25)
    if res["success"]:
        return {"success": True, "component": component}
    return res


def main_activity(package: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["cmd", "package", "resolve-activity", "--brief", package], device=serial, timeout=20)
    if not res["success"]:
        res = adb.shell(["pm", "resolve-activity", "--brief", package], device=serial, timeout=20)
    lines = [line.strip() for line in res.get("stdout", "").splitlines() if "/" in line]
    if lines:
        return {"success": True, "component": lines[-1]}
    return {"success": False, "error": "Could not resolve main activity"}


def set_default_browser(package: str, serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(
        ["cmd", "role", "add-role-holder", "android.app.role.BROWSER", package],
        device=serial,
        timeout=20,
    )
    if res["success"]:
        return {"success": True, "package": package, "role": "BROWSER"}
    return res


def running_activities(serial: str | None = None) -> dict[str, Any]:
    res = adb.shell(["dumpsys", "activity", "activities"], device=serial, timeout=25)
    if not res["success"]:
        return res
    current = None
    for line in res["stdout"].splitlines():
        line = line.strip()
        if line.startswith("ResumedActivity:") or line.startswith("topResumedActivity"):
            current = line.split(None, 1)[1] if " " in line else line
            break
    return {"success": True, "foreground": current}


def force_stop_all_except(packages: list[str], serial: str | None = None) -> dict[str, Any]:
    running = list_packages(serial, kind="third_party")
    if not running.get("success"):
        return running
    keep = {p.strip().lower() for p in packages}
    stopped = []
    for pkg in running["packages"]:
        if pkg.lower() in keep:
            continue
        res = adb.shell(["am", "force-stop", pkg], device=serial, timeout=15)
        if res["success"]:
            stopped.append(pkg)
    return {"success": True, "stopped": stopped, "count": len(stopped)}
