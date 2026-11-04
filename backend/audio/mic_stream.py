# FILE: mic_stream.py
# Captures mono microphone audio in fixed-size chunks and delivers it to a callback.
import sounddevice as sd
from config import CHANNELS, CHUNK_SAMPLES, SAMPLE_RATE

class MicStream:
    def __init__(self, on_chunk):
        self.on_chunk = on_chunk
        self.stream = None

    def start(self):
        if self.stream:
            return
        def callback(indata, _frames, _time, status):
            if status:
                print(f"Microphone status: {status}")
            self.on_chunk(indata[:, 0].copy())
        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
            blocksize=CHUNK_SAMPLES, dtype="float32", callback=callback)
        self.stream.start()
        print("Microphone stream started")

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
