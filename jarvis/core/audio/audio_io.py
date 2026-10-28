import logging
import queue
import threading
from collections.abc import Callable

import numpy as np
import sounddevice as sd

logger = logging.getLogger("jarvis.audio")


class AudioIO:
    """Microphone capture (callback thread) + non-blocking speaker playback.

    Input frames arrive as float32 on the PortAudio thread. Output audio is
    queued as raw PCM16 bytes and written by a dedicated worker thread so the
    asyncio event loop is never blocked while JARVIS is speaking.
    """

    def __init__(self, sample_rate=16000, channels=1, chunk_size=512):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.input_stream = None
        self.output_stream = None
        self.input_queue = queue.Queue()
        self.is_recording = False
        self.is_playing = False

        self._out_queue: queue.Queue = queue.Queue(maxsize=400)
        self._out_thread: threading.Thread | None = None
        self._out_stop = threading.Event()
        self._out_rate = 24000

    # ------------------------------------------------------------------
    # input
    # ------------------------------------------------------------------
    def start_input(self, callback: Callable | None = None):
        def audio_callback(indata, frames, time, status):
            if status:
                logger.warning(f"Audio input status: {status}")
            audio_data = indata.copy()
            self.input_queue.put(audio_data)
            if callback:
                callback(audio_data)

        self.input_stream = sd.InputStream(
            channels=self.channels,
            samplerate=self.sample_rate,
            blocksize=self.chunk_size,
            callback=audio_callback,
            dtype='float32'
        )
        self.input_stream.start()
        self.is_recording = True
        logger.info("Audio input started")

    def stop_input(self):
        if self.input_stream:
            self.input_stream.stop()
            self.input_stream.close()
            self.input_stream = None
        self.is_recording = False
        logger.info("Audio input stopped")

    def read_chunk(self, timeout=1.0):
        try:
            return self.input_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # ------------------------------------------------------------------
    # output
    # ------------------------------------------------------------------
    def start_output(self, sample_rate: int = 24000) -> None:
        """Open the speaker stream once; audio is played from the queue."""
        if self.output_stream is not None:
            return
        self._out_rate = sample_rate
        self._out_stop.clear()
        self.output_stream = sd.OutputStream(
            channels=1,
            samplerate=self._out_rate,
            dtype='int16',
            blocksize=0,
        )
        self.output_stream.start()
        self._out_thread = threading.Thread(
            target=self._output_worker, name="jarvis-audio-out", daemon=True
        )
        self._out_thread.start()
        self.is_playing = True
        logger.info("Audio output started at %d Hz", self._out_rate)

    def enqueue(self, pcm16: bytes, sample_rate: int | None = None) -> None:
        """Queue PCM16 mono audio for playback (never blocks the caller)."""
        if sample_rate and sample_rate != self._out_rate and self.output_stream is None:
            self.start_output(sample_rate)
        if self.output_stream is None or not pcm16:
            return
        try:
            self._out_queue.put_nowait(pcm16)
        except queue.Full:
            # Drop the oldest chunk to keep latency bounded during barge-in.
            try:
                self._out_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._out_queue.put_nowait(pcm16)
            except queue.Full:
                pass

    def clear_output(self) -> None:
        """Flush queued playback immediately (model was interrupted)."""
        drained = 0
        while True:
            try:
                self._out_queue.get_nowait()
                drained += 1
            except queue.Empty:
                break
        if drained:
            logger.debug("Cleared %d queued audio chunks", drained)

    def output_pending(self) -> bool:
        return not self._out_queue.empty()

    def stop_output(self) -> None:
        self._out_stop.set()
        self.clear_output()
        thread, self._out_thread = self._out_thread, None
        if thread:
            thread.join(timeout=2.0)
        if self.output_stream:
            try:
                self.output_stream.stop()
                self.output_stream.close()
            except Exception:  # noqa: BLE001
                pass
            self.output_stream = None
        self.is_playing = False
        logger.info("Audio output stopped")

    def _output_worker(self) -> None:
        while not self._out_stop.is_set():
            try:
                chunk = self._out_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if chunk is None:
                break
            try:
                samples = np.frombuffer(chunk, dtype=np.int16)
                if self.output_stream is not None:
                    self.output_stream.write(samples)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Audio playback error: %s", exc)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def play_audio(self, audio_data: np.ndarray, sample_rate: int | None = None):
        """Backwards-compatible blocking play."""
        rate = sample_rate or self.sample_rate
        sd.play(audio_data, rate)
        sd.wait()

    def play_stream(self, audio_chunks, sample_rate: int | None = None):
        rate = sample_rate or self.sample_rate
        for chunk in audio_chunks:
            sd.play(chunk, rate)
            sd.wait()

    def play_chime(self, frequency: float = 880.0, duration: float = 0.16, volume: float = 0.25) -> None:
        """Short acknowledgment tone for wake-word detection."""
        try:
            rate = self._out_rate if self.output_stream else 24000
            t = np.linspace(0, duration, int(rate * duration), endpoint=False)
            tone = (np.sin(2 * np.pi * frequency * t) * volume * 32767).astype(np.int16)
            # Fade out so the tone does not click.
            fade = min(len(tone), int(rate * 0.02))
            if fade:
                tone[-fade:] = (tone[-fade:] * np.linspace(1, 0, fade)).astype(np.int16)
            self.enqueue(tone.tobytes(), sample_rate=rate if self.output_stream is None else None)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Chime failed: %s", exc)

    def list_devices(self):
        return sd.query_devices()

    def get_default_devices(self):
        return sd.default.device
