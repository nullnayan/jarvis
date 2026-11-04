# FILE: backend/laptop_agent/audio_router.py
"""
Virtual Audio Router for Jarvis Laptop Call Secretary.
Routes caller voice into Whisper STT and routes Jarvis TTS into the call
without playing any audio through physical speakers.
"""

import io
import logging
import wave
from typing import Optional, Tuple
import sounddevice as sd
import numpy as np

log = logging.getLogger("jarvis.audio_router")


class AudioRouter:
    """Manages virtual audio endpoints for silent in-call processing."""

    def __init__(self):
        self.virtual_input_idx: Optional[int] = None   # CABLE Output (captures caller audio)
        self.virtual_output_idx: Optional[int] = None  # CABLE Input (sends Jarvis voice to caller)
        self.sample_rate = 16000
        self.channels = 1
        self.detect_devices()

    def detect_devices(self) -> Tuple[Optional[int], Optional[int]]:
        """Scans for VB-Audio Cable or virtual audio devices."""
        devices = sd.query_devices()
        in_idx = None
        out_idx = None

        for idx, dev in enumerate(devices):
            name = dev.get("name", "").lower()
            in_ch = dev.get("max_input_channels", 0)
            out_ch = dev.get("max_output_channels", 0)

            # CABLE Output has input channels (we record from it to hear caller)
            if ("cable" in name or "vb-audio" in name or "virtual" in name) and in_ch > 0 and in_idx is None:
                in_idx = idx

            # CABLE Input has output channels (we play into it to talk to caller)
            if ("cable" in name or "vb-audio" in name or "virtual" in name) and out_ch > 0 and out_idx is None:
                out_idx = idx

        self.virtual_input_idx = in_idx
        self.virtual_output_idx = out_idx

        log.info(f"AudioRouter devices: Capture(In)={in_idx}, Inject(Out)={out_idx}")
        return in_idx, out_idx

    def list_all_devices(self) -> list:
        """Returns all available system audio devices."""
        devs = []
        for idx, dev in enumerate(sd.query_devices()):
            devs.append({
                "index": idx,
                "name": dev.get("name"),
                "inputs": dev.get("max_input_channels"),
                "outputs": dev.get("max_output_channels"),
            })
        return devs

    def record_audio_chunk(self, duration_seconds: float = 3.0) -> np.ndarray:
        """Records a chunk of audio from the virtual capture device."""
        device = self.virtual_input_idx if self.virtual_input_idx is not None else sd.default.device[0]
        frames = int(duration_seconds * self.sample_rate)
        recording = sd.rec(
            frames,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            device=device,
        )
        sd.wait()
        return recording

    def play_audio_bytes(self, wav_bytes: bytes) -> None:
        """Plays audio bytes directly into the virtual output device (into caller's ear)."""
        device = self.virtual_output_idx if self.virtual_output_idx is not None else sd.default.device[1]
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                frames = wf.readframes(wf.getnframes())
                data = np.frombuffer(frames, dtype=np.int16)
                if channels > 1:
                    data = data.reshape(-1, channels)
                sd.play(data, samplerate=sample_rate, device=device)
                sd.wait()
        except Exception as e:
            log.error(f"Failed to play audio bytes: {e}")


audio_router = AudioRouter()
