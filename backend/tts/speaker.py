# FILE: speaker.py
# Synthesizes speech with edge-tts and plays it through speakers, streaming amplitude to the UI.
# Persona-aware: Jarvis (British) vs Ultron (deep American) voice configuration.
import asyncio
import numpy as np
import sounddevice as sd
import edge_tts
import miniaudio
import re
from logger import get_logger
from config import (
    TTS_AMPLITUDE_SCALE,
    JARVIS_VOICE, JARVIS_RATE, JARVIS_PITCH,
    ULTRON_VOICE, ULTRON_RATE, ULTRON_PITCH,
    HINDI_VOICE, HINDI_RATE, HINDI_PITCH,
    BHOJPURI_VOICE, BHOJPURI_RATE, BHOJPURI_PITCH,
)
from server.messages import amplitude_msg
from tts.tts_amplitude import extract_amplitudes

_log = get_logger(__name__)
print = _log.info

def is_bhojpuri_speech(text: str) -> bool:
    t = text.lower()
    bho_tokens = [
        "ba", "baa", "batawa", "tohar", "tohaar", "sakeni", "karatani", "theek ba", "thik ba",
        "kaise ba", "ka ho", "kaa ho", "raua", "rauwa", "jhandwa", "ghamandwa", "sewa",
        "badhiya ba", "haal chaal", "ki haal"
    ]
    if any(re.search(r'\b' + re.escape(tok) + r'\b', t) for tok in bho_tokens):
        return True
    devanagari_markers = ["बा", "तोहार", "बतावा", "सकीं", "सकेनी", "रउवा", "ठीक बा", "बढ़िया बा", "हाल चाल", "मदद कर सकीं"]
    return any(m in text for m in devanagari_markers)

PERSONA_VOICES = {
    "jarvis": (JARVIS_VOICE, JARVIS_RATE, JARVIS_PITCH),
    "ultron": (ULTRON_VOICE, ULTRON_RATE, ULTRON_PITCH),
}

class Speaker:
    def __init__(self, server, loop):
        self.server = server
        self.loop = loop
        self.stop_event = asyncio.Event()
        self.persona = "jarvis"
        self.muted = False
        # Holds in-flight amplitude-send tasks (asyncio keeps only weak refs to
        # bare tasks; an unheld one can be garbage-collected mid-send).
        self._amp_tasks = set()

    def set_persona(self, persona: str) -> None:
        if persona in PERSONA_VOICES:
            self.persona = persona

    @staticmethod
    def _sentences(text: str) -> list[str]:
        parts = re.findall(r"[^.!?\n]+(?:[.!?]+|$)", text or "")
        return [part.strip() for part in parts if part.strip()]

    async def _synthesize(self, sentence: str, voice: str, rate: str, pitch: str):
        comm = edge_tts.Communicate(sentence, voice, rate=rate, pitch=pitch)
        mp3_data = bytearray()
        async for chunk in comm.stream():
            if self.stop_event.is_set():
                return None
            if chunk["type"] == "audio":
                mp3_data.extend(chunk["data"])
        if not mp3_data:
            return None
        decoded = miniaudio.mp3_read_f32(bytes(mp3_data))
        audio_np = np.array(decoded.samples, dtype=np.float32)
        if decoded.nchannels > 1:
            audio_np = audio_np.reshape(-1, decoded.nchannels)[:, 0]
        if len(audio_np) == 0:
            return None
        return audio_np, decoded.sample_rate

    async def _play(self, decoded_audio):
        if not decoded_audio or self.stop_event.is_set():
            return
        audio_np, sample_rate = decoded_audio
        amplitudes = extract_amplitudes(audio_np, sample_rate)

        def play_audio():
            sd.play(audio_np, samplerate=sample_rate)
            sd.wait()

        play_task = self.loop.run_in_executor(None, play_audio)
        duration = len(audio_np) / sample_rate
        frame_time = duration / len(amplitudes) if amplitudes else 0.033
        for amp in amplitudes:
            if self.stop_event.is_set():
                sd.stop()
                break
            amp_task = asyncio.create_task(self.server.send(amplitude_msg(min(amp * TTS_AMPLITUDE_SCALE, 1.0))))
            self._amp_tasks.add(amp_task)
            amp_task.add_done_callback(self._amp_tasks.discard)
            await asyncio.sleep(frame_time)
        await play_task

    async def speak(self, text: str, lang: str = "en") -> None:
        self.stop_event.clear()
        if self.muted:
            return
        # Ultron persona always uses Ultron voice; otherwise check language or Devanagari script
        if self.persona == "ultron":
            voice, rate, pitch = PERSONA_VOICES["ultron"]
        elif lang == "bho" or is_bhojpuri_speech(text):
            voice, rate, pitch = (BHOJPURI_VOICE, BHOJPURI_RATE, BHOJPURI_PITCH)
        elif lang == "hi" or re.search(r'[\u0900-\u097F]', text):
            voice, rate, pitch = (HINDI_VOICE, HINDI_RATE, HINDI_PITCH)
        else:
            voice, rate, pitch = PERSONA_VOICES.get(self.persona, PERSONA_VOICES["jarvis"])
        try:
            sentences = self._sentences(text)
            if not sentences:
                return

            current_task = asyncio.create_task(self._synthesize(sentences[0], voice, rate, pitch))
            for index, _sentence in enumerate(sentences):
                decoded_audio = await current_task
                if index + 1 < len(sentences):
                    current_task = asyncio.create_task(
                        self._synthesize(sentences[index + 1], voice, rate, pitch)
                    )
                if self.stop_event.is_set():
                    break
                await self._play(decoded_audio)
        except Exception as e:
            print(f"TTS Error: {e}")
        finally:
            final_task = asyncio.create_task(self.server.send(amplitude_msg(0.0)))
            self._amp_tasks.add(final_task)
            final_task.add_done_callback(self._amp_tasks.discard)

    def stop(self) -> None:
        self.stop_event.set()
        sd.stop()
        def _send_zero():
            task = asyncio.create_task(self.server.send(amplitude_msg(0.0)))
            self._amp_tasks.add(task)
            task.add_done_callback(self._amp_tasks.discard)
        self.loop.call_soon_threadsafe(_send_zero)

    def set_muted(self, muted: bool) -> None:
        """Silences TTS output. Muting also stops any currently-playing speech."""
        self.muted = bool(muted)
        if self.muted:
            self.stop()
