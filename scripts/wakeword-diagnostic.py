"""Short local microphone probe; audio stays in memory and is not transmitted."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.core.wakeword.wakeword_detector import WakeWordDetector

detectors = [WakeWordDetector(threshold=0.5) for _ in range(2)]
if any(not detector.available or detector.model is None for detector in detectors):
    raise SystemExit("The Hey JARVIS wake-word model is unavailable.")

stats = [
    {"frames": 0, "sum_squares": 0.0, "max_level": 0.0, "max_score": 0.0}
    for _ in range(2)
]


def on_audio(indata, _frames, _time_info, status):
    if status:
        print(f"Audio input warning: {status}", flush=True)
    for channel in range(2):
        frame = indata[:, channel]
        level = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
        detectors[channel].detect(frame)
        stats[channel]["frames"] += 1
        stats[channel]["sum_squares"] += level * level
        stats[channel]["max_level"] = max(stats[channel]["max_level"], level)
        stats[channel]["max_score"] = max(
            stats[channel]["max_score"], detectors[channel].last_confidence
        )


print("Speak ‘Hey JARVIS’ when the countdown ends. Probe lasts 8 seconds.", flush=True)
for number in range(3, 0, -1):
    print(f"{number}…", flush=True)
    time.sleep(1)

with sd.InputStream(samplerate=16000, channels=2, blocksize=480, dtype="float32", callback=on_audio):
    for remaining in range(8, 0, -1):
        print(f"Listening locally: {remaining}s", flush=True)
        time.sleep(1)

for channel, name in enumerate(("left", "right")):
    mean_level = (stats[channel]["sum_squares"] / max(stats[channel]["frames"], 1)) ** 0.5
    print(f"{name} channel: average RMS {mean_level:.4f}; peak RMS {stats[channel]['max_level']:.4f}")
    print(f"{name} channel: peak Hey JARVIS confidence {stats[channel]['max_score']:.3f} (threshold 0.500)")
