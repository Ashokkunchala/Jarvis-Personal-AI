import webrtcvad
import numpy as np
import collections
import logging

logger = logging.getLogger("jarvis.vad")


class VADProcessor:
    def __init__(self, aggressiveness=2, sample_rate=16000, frame_duration_ms=30, padding_duration_ms=300):
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.padding_duration_ms = padding_duration_ms
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        self.num_padding_frames = int(padding_duration_ms / frame_duration_ms)
        self.ring_buffer = collections.deque(maxlen=self.num_padding_frames)
        self.triggered = False
        self.voiced_frames = []
        
    def is_speech(self, frame):
        """Check if frame contains speech"""
        try:
            # Convert float32 to int16
            if frame.dtype == np.float32:
                frame_int16 = (frame * 32768).astype(np.int16)
            else:
                frame_int16 = frame.astype(np.int16)
            return self.vad.is_speech(frame_int16.tobytes(), self.sample_rate)
        except Exception as e:
            logger.error(f"VAD error: {e}")
            return False
    
    def process_frame(self, frame):
        """Process frame and return (is_speech, utterance_complete, utterance_audio)"""
        is_speech = self.is_speech(frame)
        
        if not self.triggered:
            self.ring_buffer.append((frame, is_speech))
            num_voiced = len([f for f, speech in self.ring_buffer if speech])
            if num_voiced > 0.9 * self.ring_buffer.maxlen:
                self.triggered = True
                logger.debug("Speech started")
                # Add buffered frames
                for f, s in self.ring_buffer:
                    self.voiced_frames.append(f)
                self.ring_buffer.clear()
            return False, False, None
        else:
            self.voiced_frames.append(frame)
            self.ring_buffer.append((frame, is_speech))
            num_unvoiced = len([f for f, speech in self.ring_buffer if not speech])
            if num_unvoiced > 0.9 * self.ring_buffer.maxlen:
                self.triggered = False
                logger.debug("Speech ended")
                utterance = np.concatenate(self.voiced_frames)
                self.voiced_frames = []
                self.ring_buffer.clear()
                return True, True, utterance
            return True, False, None
    
    def reset(self):
        self.triggered = False
        self.voiced_frames = []
        self.ring_buffer.clear()
