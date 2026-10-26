import numpy as np
import sounddevice as sd
import queue
import threading
from typing import Callable, Optional
import logging

logger = logging.getLogger("jarvis.audio")


class AudioIO:
    def __init__(self, sample_rate=16000, channels=1, chunk_size=512):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.input_stream = None
        self.output_stream = None
        self.input_queue = queue.Queue()
        self.is_recording = False
        self.is_playing = False
        
    def start_input(self, callback: Optional[Callable] = None):
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
    
    def play_audio(self, audio_data: np.ndarray):
        sd.play(audio_data, self.sample_rate)
        sd.wait()
    
    def play_stream(self, audio_chunks):
        for chunk in audio_chunks:
            sd.play(chunk, self.sample_rate)
            sd.wait()
    
    def list_devices(self):
        return sd.query_devices()
    
    def get_default_devices(self):
        return sd.default.device
