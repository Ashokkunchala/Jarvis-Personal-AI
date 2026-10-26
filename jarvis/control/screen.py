"""Screen capture: screenshots, region capture, pixel colour and screen recording."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.control.screen")


def screen_size() -> dict[str, Any]:
    try:
        import mss

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            return {"success": True, "width": monitor["width"], "height": monitor["height"]}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def screenshot(path: str | None = None, region: dict[str, int] | None = None) -> dict[str, Any]:
    """Capture the full screen or a {left, top, width, height} region."""
    try:
        import mss

        if not path:
            out_dir = Path("data/screenshots")
            out_dir.mkdir(parents=True, exist_ok=True)
            path = str(out_dir / f"screenshot_{int(time.time())}.png")
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with mss.mss() as sct:
            if region:
                monitor = {
                    "left": int(region.get("left", 0)),
                    "top": int(region.get("top", 0)),
                    "width": int(region.get("width", 100)),
                    "height": int(region.get("height", 100)),
                }
            else:
                monitor = sct.monitors[0]
            sct.grab(monitor).save(path)
        return {"success": True, "path": str(path), "absolute": str(Path(path).resolve())}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def get_pixel_color(x: int, y: int) -> dict[str, Any]:
    try:
        import mss

        with mss.mss() as sct:
            pixel = sct.grab({"left": int(x), "top": int(y), "width": 1, "height": 1})
            r, g, b = pixel.rgb[0], pixel.rgb[1], pixel.rgb[2]
        return {"success": True, "x": int(x), "y": int(y), "rgb": [r, g, b], "hex": f"#{r:02x}{g:02x}{b:02x}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def list_monitors() -> list[dict[str, Any]]:
    try:
        import mss

        with mss.mss() as sct:
            return [
                {
                    "index": i,
                    "left": m["left"],
                    "top": m["top"],
                    "width": m["width"],
                    "height": m["height"],
                }
                for i, m in enumerate(sct.monitors)
            ]
    except Exception as exc:
        logger.warning("Could not list monitors: %s", exc)
        return []


def record_screen(duration: int = 10, path: str | None = None) -> dict[str, Any]:
    """Record the screen to an .avi using OpenCV (optional dependency)."""
    try:
        import cv2
        import mss
        import numpy as np
    except ImportError as exc:
        return {"success": False, "error": f"Screen recording needs opencv-python and numpy: {exc}"}

    duration = max(1, min(int(duration), 120))
    if not path:
        out_dir = Path("data/recordings")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = str(out_dir / f"recording_{int(time.time())}.avi")
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    try:
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            width, height = monitor["width"], monitor["height"]
            # Downscale very large screens to keep file sizes sane
            scale = min(1.0, 1280 / max(width, 1))
            out_w, out_h = int(width * scale), int(height * scale)
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(path, fourcc, 15.0, (out_w, out_h))
            if not writer.isOpened():
                return {"success": False, "error": "Could not open video writer"}
            frames = int(duration * 15)
            for _ in range(frames):
                frame = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                if scale < 1.0:
                    frame = cv2.resize(frame, (out_w, out_h))
                writer.write(frame)
            writer.release()
        return {"success": True, "path": str(path), "duration": duration, "fps": 15}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def ocr_screen(region: dict[str, int] | None = None) -> dict[str, Any]:
    """OCR text on screen via Tesseract (optional dependency)."""
    try:
        import mss
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        return {"success": False, "error": f"OCR needs pillow + pytesseract + tesseract: {exc}"}
    try:
        with mss.mss() as sct:
            monitor = region or sct.monitors[0]
            img = Image.frombytes("RGB", sct.grab(monitor).size, sct.grab(monitor).rgb)
        text = pytesseract.image_to_string(img)
        return {"success": True, "text": text.strip()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
