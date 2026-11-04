# FILE: vad.py
# Uses Silero VAD to buffer speech and detect the silence that ends an utterance.
import numpy as np
import torch
from config import MAX_SPEECH_DURATION, SAMPLE_RATE, SILENCE_TIMEOUT, VAD_SAMPLES, VAD_THRESHOLD, STT_MIN_RMS
from logger import get_logger

_log = get_logger(__name__)

class VoiceActivityDetector:
    def __init__(self):
        self.model, _utils = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
        self.silence_timeout = SILENCE_TIMEOUT
        self.reset()
        print("Silero VAD ready")

    def set_silence_timeout(self, timeout: float):
        self.silence_timeout = float(timeout)

    def reset(self):
        self.recording = False
        self.silence = 0.0
        self.audio = []
        self.pending = np.empty(0, dtype=np.float32)
        self.model.reset_states()

    def _probability(self, chunk):
        self.pending = np.concatenate((self.pending, chunk))
        if self.pending.size < VAD_SAMPLES:
            return None
        frame, self.pending = self.pending[:VAD_SAMPLES], self.pending[VAD_SAMPLES:]
        return float(self.model(torch.from_numpy(frame), SAMPLE_RATE).item())

    def feed(self, chunk):
        probability = self._probability(chunk)
        if probability is None:
            return "silence"
        speaking = probability >= VAD_THRESHOLD
        if speaking and not self.recording:
            chunk_rms = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float32))))
            if chunk_rms >= STT_MIN_RMS:
                self.recording = True
                print(f"[VAD] Speech started (prob={probability:.3f}, rms={chunk_rms:.4f})")
        if self.recording:
            self.audio.append(chunk.copy())
            self.silence = 0.0 if speaking else self.silence + chunk.size / SAMPLE_RATE
            duration = sum(piece.size for piece in self.audio) / SAMPLE_RATE
            if self.silence >= self.silence_timeout or duration >= MAX_SPEECH_DURATION:
                print(f"[VAD] Speech ended (silence={self.silence:.2f}s, duration={duration:.1f}s)")
                if duration < 0.4:
                    self.reset()
                    return "silence"
                return "done"
        return "speech" if speaking else "silence"

    def get_audio(self):
        return np.concatenate(self.audio) if self.audio else np.empty(0, dtype=np.float32)
