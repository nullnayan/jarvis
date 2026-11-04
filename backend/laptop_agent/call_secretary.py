# FILE: backend/laptop_agent/call_secretary.py
"""
Laptop-Bridged AI Call Secretary for Jarvis.
Listens for calls bridged via Windows Phone Link / Bluetooth HFP,
silently answers, conducts the Hindi-first conversational loop,
classifies urgency, and alerts the user on their phone if urgent.
"""

import asyncio
import io
import json
import logging
import os
import re
import time
import wave
from typing import Optional
from security.transport import require_secure_gateway

import edge_tts
import numpy as np
from openai import AsyncOpenAI

from backend.laptop_agent.audio_router import audio_router
from backend.laptop_agent.power_manager import power_manager

log = logging.getLogger("jarvis.laptop_secretary")

# Groq API keys from root config / env
GROQ_API_KEYS = [k for k in [
    os.environ.get("GROQ_API_KEY_1", ""),
    os.environ.get("GROQ_API_KEY_2", ""),
    os.environ.get("GROQ_API_KEY_3", ""),
    os.environ.get("GROQ_API_KEY_4", ""),
    os.environ.get("GROQ_API_KEY_5", ""),
] if k.strip()]

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
CLOUD_BASE_URL = os.environ.get("CLOUD_URL", "http://127.0.0.1:8765").rstrip("/")
CLOUD_TOKEN = os.environ.get("JARVIS_AUTH_TOKEN", "").strip()

HINDI_GREETING = (
    "Namaste. Main Jarvis hoon, User ka AI assistant. "
    "User abhi uplabdh nahi hain. "
    "Kripya apna naam aur sandesh bataiye."
)

ENGLISH_GREETING = (
    "Hello. I am Jarvis, User's AI assistant. "
    "User is currently unavailable. "
    "Please state your name and leave a message."
)


class LaptopCallSecretary:
    """Manages call screening lifecycle on the Windows laptop."""

    def __init__(self):
        self._is_active = False
        self._current_key_idx = 0
        self.groq_client = AsyncOpenAI(
            api_key=GROQ_API_KEYS[0] if GROQ_API_KEYS else "none",
            base_url=GROQ_BASE_URL
        )

    def _rotate_groq_key(self):
        if GROQ_API_KEYS:
            self._current_key_idx = (self._current_key_idx + 1) % len(GROQ_API_KEYS)
            self.groq_client = AsyncOpenAI(
                api_key=GROQ_API_KEYS[self._current_key_idx],
                base_url=GROQ_BASE_URL
            )

    async def start_service(self):
        """Starts the laptop call secretary service with Windows Away Mode."""
        self._is_active = True
        power_manager.configure_power_plan(screen_timeout_minutes=3)
        power_manager.enable_away_mode()
        log.info("Laptop Call Secretary STARTED in Low-Power Away Mode.")

    def stop_service(self):
        """Stops the secretary service and restores normal sleep."""
        self._is_active = False
        power_manager.disable_away_mode()
        log.info("Laptop Call Secretary STOPPED.")

    async def text_to_speech_bytes(self, text: str, voice: str = "hi-IN-MadhurNeural") -> bytes:
        """Converts text to MP3/WAV audio bytes using Edge TTS."""
        communicate = edge_tts.Communicate(text, voice)
        mp3_buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_buffer.write(chunk["data"])
        return mp3_buffer.getvalue()

    async def transcribe_audio(self, audio_data: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribes recorded audio chunk using Groq Whisper."""
        try:
            # Save numpy array to in-memory WAV
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data.tobytes())
            wav_io.seek(0)
            wav_io.name = "caller.wav"

            resp = await self.groq_client.audio.transcriptions.create(
                file=wav_io,
                model="whisper-large-v3",
                response_format="text"
            )
            return str(resp).strip()
        except Exception as e:
            log.error(f"Whisper transcription error: {e}")
            self._rotate_groq_key()
            return ""

    async def classify_urgency(self, text: str) -> str:
        """Classifies if caller's message is urgent using Groq LLM."""
        try:
            resp = await self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Classify caller message as 'urgent' or 'normal'. "
                            "Urgent = accident, emergency, medical, hospital, time-critical danger. "
                            "Reply ONLY valid JSON: {\"urgency\": \"urgent\"} or {\"urgency\": \"normal\"}"
                        )
                    },
                    {"role": "user", "content": text}
                ],
                temperature=0.0,
                max_tokens=30
            )
            raw = resp.choices[0].message.content or ""
            cleaned = re.sub(r"```.*?```", "", raw, flags=re.DOTALL).strip()
            data = json.loads(cleaned)
            return data.get("urgency", "normal")
        except Exception as e:
            log.warning(f"Urgency classification fallback: {e}")
            lower = text.lower()
            if any(w in lower for w in ("urgent", "emergency", "accident", "hospital", "danger", "jaldi")):
                return "urgent"
            return "normal"

    async def _hangup_call(self):
        """Hangs up the current active call via ADB."""
        try:
            import subprocess
            subprocess.run(["adb", "shell", "input", "keyevent", "6"], capture_output=True, timeout=3)
            log.info("Call ended via KEYCODE_ENDCALL (6).")
        except Exception as e:
            log.warning(f"Could not hang up call via ADB: {e}")

    async def _answer_call(self):
        """Answers an incoming ringing call via ADB."""
        try:
            import subprocess
            # Send headset hook (79) and call button (5) to reliably answer
            subprocess.run(["adb", "shell", "input", "keyevent", "79"], capture_output=True, timeout=3)
            subprocess.run(["adb", "shell", "input", "keyevent", "5"], capture_output=True, timeout=3)
            log.info("Sent KEYCODE_HEADSETHOOK and KEYCODE_CALL to answer call.")
        except Exception as e:
            log.warning(f"Could not answer call via ADB: {e}")

    def _get_phone_call_state(self) -> tuple[int, str]:
        """Returns (call_state, incoming_number) from Android telephony registry.
        0 = IDLE, 1 = RINGING, 2 = OFFHOOK / ACTIVE
        """
        try:
            import subprocess
            out = subprocess.check_output(["adb", "shell", "dumpsys", "telephony.registry"], text=True, timeout=3)
            state_match = re.search(r"mCallState=(\d)", out)
            num_match = re.search(r"mCallIncomingNumber=(.*)", out)
            state = int(state_match.group(1)) if state_match else 0
            number = num_match.group(1).strip() if num_match else ""
            return state, number
        except Exception:
            return 0, ""

    def _resolve_caller_name(self, number: str) -> str:
        """Looks up contact name for number via ADB ContactsProvider."""
        if not number:
            return "Unknown Caller"
        try:
            import subprocess
            cmd = [
                "adb", "shell", "content", "query",
                "--uri", f"content://com.android.contacts/data/phones/filter/{number}",
                "--projection", "display_name"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            match = re.search(r"display_name=([^\r\n,]+)", res.stdout)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
        return number or "Unknown Caller"

    async def handle_incoming_call(self, caller_name: str = "Unknown", caller_number: str = ""):
        """Full silent conversation flow when a call arrives."""
        log.info(f"Handling call from {caller_name} ({caller_number}) silently...")

        # 1. Speak greeting into virtual audio
        greeting_audio = await self.text_to_speech_bytes(HINDI_GREETING)
        audio_router.play_audio_bytes(greeting_audio)

        # 2. Record caller's response (5 seconds)
        caller_audio = audio_router.record_audio_chunk(duration_seconds=5.0)
        caller_text = await self.transcribe_audio(caller_audio)
        log.info(f"Caller said: '{caller_text}'")

        if not caller_text:
            closing = await self.text_to_speech_bytes("Koi jawab nahi mila. Dhanyavaad.")
            audio_router.play_audio_bytes(closing)
            await self._hangup_call()
            return

        # 3. Classify urgency
        urgency = await self.classify_urgency(caller_text)
        log.info(f"Call urgency: {urgency}")

        if urgency == "urgent":
            hold_audio = await self.text_to_speech_bytes("Yeh zaroori lag raha hai. Kripya hold karein, main User ko connect karta hoon.")
            audio_router.play_audio_bytes(hold_audio)

            # 4. Send high priority wake-up alert to phone (Cloud + Direct ADB broadcast)
            await self._alert_phone_urgent(caller_name, caller_number, caller_text)

            # 5. Wait up to 20 seconds for User's decision from phone
            log.info("Waiting up to 20s for User to accept or decline...")
            decision = await self._wait_for_urgent_decision(timeout_seconds=20)
            log.info(f"User's decision: {decision}")

            if decision == "connect":
                log.info("User accepted call. Exiting audio loop — phone has full control.")
                # Jarvis exits the audio stream immediately so User speaks directly
                return
            else:
                # User declined or 20-second timer expired
                busy_msg = "User sir abhi vyast hain aur baat nahi kar sakte. Maine aapka sandesh note kar liya hai. Dhanyavaad."
                busy_audio = await self.text_to_speech_bytes(busy_msg)
                audio_router.play_audio_bytes(busy_audio)
                log.info("Informed caller: boss is busy. Concluding call.")
                await self._hangup_call()
        else:
            thank_audio = await self.text_to_speech_bytes("Dhanyavaad. Maine aapka sandesh note kar liya hai. User ko bata dunga.")
            audio_router.play_audio_bytes(thank_audio)
            await self._notify_phone(caller_name, caller_text)
            await self._hangup_call()

    async def _wait_for_urgent_decision(self, timeout_seconds: int = 20) -> str:
        """Polls Cloud Hub for User's decision (connect / decline)."""
        if not CLOUD_TOKEN:
            return "timeout"
        require_secure_gateway(CLOUD_BASE_URL)
        import httpx
        start_time = time.time()
        async with httpx.AsyncClient(timeout=3.0) as client:
            while time.time() - start_time < timeout_seconds:
                try:
                    resp = await client.get(
                        f"{CLOUD_BASE_URL}/api/urgent-decision", params={"token": CLOUD_TOKEN}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        dec = data.get("decision")
                        if dec in ("connect", "decline"):
                            return dec
                except Exception:
                    pass
                await asyncio.sleep(1.0)
        return "timeout"

    async def _alert_phone_urgent(self, caller_name: str, caller_number: str, message: str):
        """Sends an urgent wake-up signal to phone via Azure VM WebSocket Hub and direct ADB broadcast."""
        # 1. Direct ADB intent broadcast to phone (immediate local triggering)
        try:
            import subprocess
            cmd = [
                "adb", "shell", "am", "broadcast",
                "-a", "com.jarvis.companion.URGENT_ALERT",
                "--es", "caller_name", caller_name,
                "--es", "caller_number", caller_number,
                "--es", "message", message
            ]
            subprocess.run(cmd, capture_output=True, timeout=3)
            log.info("Dispatched direct ADB URGENT_ALERT broadcast to companion app.")
        except Exception as e:
            log.warning(f"Direct ADB alert broadcast error: {e}")

        # 2. Cloud Hub WebSocket push (for remote connectivity)
        if not CLOUD_TOKEN:
            log.warning("Cloud urgent alert skipped: configure JARVIS_AUTH_TOKEN.")
            return
        require_secure_gateway(CLOUD_BASE_URL)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{CLOUD_BASE_URL}/api/urgent-alert",
                    json={
                        "caller_name": caller_name,
                        "caller_number": caller_number,
                        "message": message,
                        "token": CLOUD_TOKEN
                    }
                )
        except Exception as e:
            log.error(f"Failed to push urgent alert to phone via Cloud: {e}")

    async def _notify_phone(self, caller_name: str, message: str):
        """Sends a regular call summary to phone via Azure VM WebSocket Hub."""
        if not CLOUD_TOKEN:
            log.warning("Cloud notification skipped: configure JARVIS_AUTH_TOKEN.")
            return
        require_secure_gateway(CLOUD_BASE_URL)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{CLOUD_BASE_URL}/api/chat",
                    json={
                        "message": f"[MISSED CALL LOG] {caller_name}: {message}",
                        "token": CLOUD_TOKEN,
                        "role": "pc"
                    }
                )
        except Exception as e:
            log.error(f"Failed to push notification to phone: {e}")

    async def run_call_monitor_daemon(self):
        """Continuous loop monitoring for answered calls on VB-Cable."""
        await self.start_service()
        log.info("Jarvis Call Secretary Daemon is RUNNING. Standing by for auto-answered calls on VB-Cable...")

        import sounddevice as sd
        # Flush initial device transient
        try:
            sd.rec(int(16000 * 0.2), samplerate=16000, channels=1, dtype='int16', device=1)
            sd.wait()
        except Exception:
            pass

        consecutive_audio_hits = 0
        in_call = False

        while self._is_active:
            try:
                if not in_call:
                    # Sample 250ms of audio from VB-Cable
                    chunk = sd.rec(int(16000 * 0.25), samplerate=16000, channels=1, dtype='int16', device=1)
                    sd.wait()
                    peak = int(np.max(np.abs(chunk)))

                    if peak > 150:
                        consecutive_audio_hits += 1
                        log.debug(f"Audio activity detected on VB-Cable: Peak={peak} (hit {consecutive_audio_hits}/2)")
                    else:
                        consecutive_audio_hits = 0

                    # 2 consecutive hits (~500ms of sustained audio) confirms an active call!
                    if consecutive_audio_hits >= 2:
                        log.info(f"Active incoming call detected on VB-Cable (Peak={peak})! Starting screening flow...")
                        in_call = True
                        consecutive_audio_hits = 0

                        # Wait 1s for carrier channel audio to stabilize
                        await asyncio.sleep(1.0)

                        # Fetch caller number if available
                        caller_number = ""
                        try:
                            import subprocess
                            out = subprocess.check_output(["adb", "shell", "dumpsys", "telephony.registry"], text=True, timeout=1)
                            m = re.search(r"mCallIncomingNumber=(.*)", out)
                            if m:
                                caller_number = m.group(1).strip()
                        except Exception:
                            pass

                        caller_name = self._resolve_caller_name(caller_number) if caller_number else "Caller"
                        await self.handle_incoming_call(caller_name=caller_name, caller_number=caller_number)

                        # Wait until audio is silent again before listening for next call
                        log.info("Call screening concluded. Waiting for line to clear...")
                        await asyncio.sleep(3.0)
                        in_call = False
                else:
                    await asyncio.sleep(1.0)

                await asyncio.sleep(0.1)
            except Exception as e:
                log.error(f"Error in call monitor loop: {e}")
                await asyncio.sleep(1.0)



laptop_secretary = LaptopCallSecretary()


if __name__ == "__main__":
    from pathlib import Path
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
        else:
            load_dotenv()
    except ImportError:
        pass

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(laptop_secretary.run_call_monitor_daemon())
