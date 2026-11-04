# FILE: wake_word.py
# Detects the Jarvis wake phrase using the OpenWakeWord pre-trained model.
import numpy as np
from openwakeword.model import Model
from openwakeword.utils import download_models
from config import WAKE_WORD_MODEL, WAKE_WORD_THRESHOLD
from logger import get_logger

_log = get_logger(__name__)

class WakeWord:
    def __init__(self):
        download_models(model_names=[WAKE_WORD_MODEL])
        self.model = Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx")
        self.model_name = WAKE_WORD_MODEL
        print(f"Wake-word model ready: {self.model_name}")

    def feed(self, chunk):
        samples = np.clip(chunk * 32767, -32768, 32767).astype(np.int16)
        scores = self.model.predict(samples)
        score = max(scores.values(), default=0.0)
        if score >= WAKE_WORD_THRESHOLD:
            self.reset()
            return True
        return False

    def reset(self):
        self.model.reset()
