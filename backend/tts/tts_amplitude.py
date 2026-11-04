# FILE: tts_amplitude.py
# Extracts frame-by-frame RMS amplitude from a PCM audio array for orb animation.
import numpy as np

def extract_amplitudes(audio: np.ndarray, sample_rate: int, frame_ms: int = 30) -> list[float]:
    samples_per_frame = int((frame_ms / 1000.0) * sample_rate)
    amplitudes = []
    for i in range(0, len(audio), samples_per_frame):
        frame = audio[i:i + samples_per_frame]
        if len(frame) > 0:
            rms = float(np.sqrt(np.mean(np.square(frame))))
            amplitudes.append(min(max(rms, 0.0), 1.0))
    return amplitudes
