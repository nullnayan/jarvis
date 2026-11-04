# FILE: transcriber.py
# Transcribes recorded speech using Groq Whisper API (cloud) for high accuracy.
import io
import time
import numpy as np
import soundfile as sf
from openai import OpenAI
from logger import get_logger
from config import (
    GROQ_API_KEY, GROQ_API_KEY_2, GROQ_API_KEY_3, GROQ_API_KEY_4,
    GROQ_API_KEY_5, GROQ_BASE_URL, SAMPLE_RATE, GROQ_WHISPER_MODEL, STT_MIN_RMS,
)

_log = get_logger(__name__)
print = _log.info

# Context prompt conditioning Whisper to recognize Jarvis commands, names, and bilingual Hindi/Bhojpuri terms accurately
STT_VOCABULARY_PROMPT = (
    "Jarvis, Ultron, User, London, WhatsApp, YouTube, Google, Chrome, VS Code, Python, "
    "website, browser, terminal, shutdown, restart, volume, timer, reminder, screenshot, "
    "Hindi, Hinglish, Bhojpuri, bhai, boss, suno, karo, chalao, kholo, band karo, batao, dikhao, kya, kaise."
)

WHISPER_NOISE_HALLUCINATIONS = {
    "thank you", "thank you.", "thank you!", "thank you very much", "thank you very much.",
    "thank you for watching", "thank you for watching.", "thank you for watching!",
    "thanks for watching", "thanks for watching.", "thanks for watching!",
    "so", "so,", "so.", "you", "you.", "bye", "bye.", "bye bye", "bye-bye",
    "subtitles by", "subtitles by amara.org", "amara.org",
    "please subscribe", "like and subscribe", "subscribe",
    "watching", "silent", "[music]", "music", "...", ".", "--"
}

class Transcriber:
    def __init__(self):
        keys = [GROQ_API_KEY, GROQ_API_KEY_2, GROQ_API_KEY_3, GROQ_API_KEY_4, GROQ_API_KEY_5]
        self.clients = [
            (OpenAI(api_key=key, base_url=GROQ_BASE_URL), f"Key {idx}")
            for idx, key in enumerate(keys, 1)
            if key and key.strip()
        ]
        self.cooldowns = {}
        self.client = self.clients[0][0] if self.clients else None
        print(f"Whisper ready (Groq cloud API, {len(self.clients)} key(s))")

    def _ordered_clients(self):
        now = time.time()
        active = [item for item in self.clients if self.cooldowns.get(item[1], 0) < now]
        cooling = [item for item in self.clients if self.cooldowns.get(item[1], 0) >= now]
        return active + cooling

    def transcribe(self, audio):
        if audio is None or len(audio) == 0:
            return "", "en"

        # 1. Ignore very short clicks/bumps (< 0.4s)
        duration = len(audio) / SAMPLE_RATE
        if duration < 0.4:
            return "", "en"

        # 2. Reject ambient room hiss, breathing, or crowd murmur below vocal RMS energy
        rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float32))))
        if rms < STT_MIN_RMS:
            return "", "en"

        # 3. Peak-normalize speech so normal and quiet voices reach full 16-bit dynamic depth
        peak = float(np.max(np.abs(audio)))
        if peak > 0.005:
            audio = (audio / peak * 0.95).astype(np.float32)

        try:
            # Convert numpy float32 audio to WAV bytes in memory
            buf = io.BytesIO()
            sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
            buf.seek(0)
            buf.name = "audio.wav"

            if not self.clients:
                print("[STT] No Groq API keys configured")
                return None, "en"

            response = None
            last_error = None
            for client, key_name in self._ordered_clients():
                try:
                    buf.seek(0)
                    response = client.audio.transcriptions.create(
                        model=GROQ_WHISPER_MODEL,
                        file=buf,
                        prompt=STT_VOCABULARY_PROMPT,
                        response_format="verbose_json",
                        temperature=0.0,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    err_text = str(exc).lower()
                    cooldown = 60.0 if "429" in err_text or "rate limit" in err_text or "quota" in err_text else 10.0
                    self.cooldowns[key_name] = time.time() + cooldown
                    print(f"[STT] {key_name} failed; trying next key: {exc}")

            if response is None:
                print(f"[STT] All transcription keys failed: {last_error}")
                return None, "en"

            if hasattr(response, "text"):
                text = response.text.strip()
                lang_raw = getattr(response, "language", "en") or "en"
            elif isinstance(response, dict):
                text = response.get("text", "").strip()
                lang_raw = response.get("language", "en") or "en"
            else:
                text = str(response).strip()
                lang_raw = "en"

            # 3. Filter common Whisper silence/noise hallucinations
            cleaned = text.lower().strip().rstrip('.!?,')
            if cleaned in WHISPER_NOISE_HALLUCINATIONS or cleaned.startswith("subtitles by"):
                print(f"[STT] Filtered Whisper noise hallucination: '{text}'")
                return "", "en"

            lang_lower = str(lang_raw).lower()
            if "hindi" in lang_lower or lang_lower == "hi":
                detected_lang = "hi"
            elif "bhojpuri" in lang_lower or lang_lower == "bho":
                detected_lang = "bho"
            else:
                detected_lang = "en"

            return text, detected_lang
        except Exception as e:
            print(f"Groq Whisper error: {e}")
            return None, "en"
