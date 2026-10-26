import numpy as np
import logging
from pathlib import Path
import os

logger = logging.getLogger("jarvis.wakeword")

try:
    import openwakeword
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False
    logger.warning("openWakeWord not installed")


class WakeWordDetector:
    def __init__(self, model_name="jarvis", threshold=0.5, models_dir=None):
        self.model_name = model_name
        self.threshold = threshold
        self.models_dir = models_dir or Path("jarvis/models/wakeword")
        self.model = None
        self.available = OPENWAKEWORD_AVAILABLE
        self._audio_buffer = np.empty(0, dtype=np.int16)
        self._prediction_count = 0
        self.last_confidence = 0.0
        
        if self.available:
            self._load_model()
    
    def _load_model(self):
        try:
            # Try to load custom model or download default
            model_path = self.models_dir / f"{self.model_name}.onnx"
            if model_path.exists():
                self.model = Model(inference_framework="onnx")
                # Load specific model
                logger.info(f"Loading wake word model from {model_path}")
            else:
                # Download and use default models
                openwakeword.utils.download_models()
                self.model = Model()
                logger.info("Loaded default openWakeWord models")
        except Exception as e:
            logger.error(f"Failed to load wake word model: {e}")
            self.available = False
    
    def detect(self, audio_frame):
        if not self.available or self.model is None:
            return False, 0.0
        
        try:
            # audio_frame should be numpy array of int16
            if audio_frame.dtype == np.float32:
                audio_int16 = (audio_frame * 32768).astype(np.int16)
            else:
                audio_int16 = audio_frame
            
            audio_int16 = np.asarray(audio_int16, dtype=np.int16).reshape(-1)
            self._audio_buffer = np.concatenate((self._audio_buffer, audio_int16))
            # openWakeWord consumes 80 ms (1280 samples) per prediction at 16 kHz.
            while self._audio_buffer.size >= 1280:
                frame = self._audio_buffer[:1280]
                self._audio_buffer = self._audio_buffer[1280:]
                prediction = self.model.predict(frame)
                self._prediction_count += 1
                matches = [
                    (key, float(score))
                    for key, score in prediction.items()
                    if self.model_name.lower() in key.lower()
                ]
                self.last_confidence = max((score for _, score in matches), default=0.0)
                if self._prediction_count == 1:
                    logger.info("Wake-word model outputs: %s", ", ".join(prediction))
                if self._prediction_count % 20 == 0:
                    logger.info(
                        "Hey JARVIS confidence %.3f (activation threshold %.2f)",
                        self.last_confidence,
                        self.threshold,
                    )
                for key, score in matches:
                    if score >= self.threshold:
                        logger.info(f"Wake word detected: {key} ({score:.3f})")
                        return True, score
            return False, 0.0
        except Exception as e:
            logger.error(f"Wake word detection error: {e}")
            return False, 0.0
    
    def reset(self):
        self._audio_buffer = np.empty(0, dtype=np.int16)
        if self.model:
            self.model.reset()
