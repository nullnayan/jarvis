# FILE: backend/pc_agent/voice.py
# Voice feedback engine for Jarvis PC Agent.
# Speaks through laptop speakers when jarvis.bat is open.

import asyncio
import os
import psutil
import sounddevice as sd
import numpy as np
import edge_tts
import miniaudio
from logger import get_logger

_log = get_logger(__name__)


def is_jarvis_bat_running() -> bool:
    """Checks if the full voice assistant (jarvis.bat / main.py) is running on this PC."""
    try:
        my_pid = os.getpid()
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            if p.info['pid'] != my_pid and p.info['name'] and 'python' in p.info['name'].lower():
                cmdline = p.info.get('cmdline') or []
                if any(arg.endswith('main.py') or 'main.py' in arg for arg in cmdline if not arg.startswith('-c')):
                    return True
    except Exception as e:
        _log.debug(f"[PC Voice] Error checking process: {e}")
    return False


async def _play_edge_tts(text: str, voice: str = "en-GB-RyanNeural") -> bool:
    try:
        clean_text = text.replace("**", "").replace("*", "").replace("`", "")
        comm = edge_tts.Communicate(clean_text, voice)
        mp3_data = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                mp3_data.extend(chunk["data"])
        if not mp3_data:
            return False
        decoded = miniaudio.mp3_read_f32(bytes(mp3_data))
        samples = np.array(decoded.samples, dtype=np.float32)
        if decoded.nchannels > 1:
            samples = samples.reshape(-1, decoded.nchannels)[:, 0]
        sd.play(samples, samplerate=decoded.sample_rate)
        sd.wait()
        return True
    except Exception as e:
        _log.warning(f"[PC Voice] Edge-TTS error: {e}")
        return False


def speak_on_pc(text: str) -> bool:
    """Plays speech through the PC speakers. Uses Edge-TTS, falls back to Windows SAPI."""
    try:
        success = asyncio.run(_play_edge_tts(text))
        if success:
            return True
    except Exception:
        pass

    # Windows SAPI Fallback (100% offline, guaranteed)
    try:
        import subprocess
        escaped = text.replace("'", "''").replace('"', '')
        cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{escaped}')"
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], shell=False, timeout=10, check=False)
        return True
    except Exception as e:
        _log.error(f"[PC Voice] SAPI fallback failed: {e}")
        return False
