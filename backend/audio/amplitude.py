# FILE: amplitude.py
# Calculates a clamped, display-friendly RMS amplitude value from microphone audio.
import numpy as np
from config import AMPLITUDE_SCALE

def calc_amplitude(chunk):
    if chunk.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float32))))
    return min(max(rms * AMPLITUDE_SCALE, 0.0), 1.0)
