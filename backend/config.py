# FILE: config.py
# All backend constants: WebSocket, audio, wake-word, VAD, and transcription settings.
from user_profile import get as profile_get

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

WS_HOST = os.environ.get("WS_HOST", "127.0.0.1")
WS_PORT = int(os.environ.get("WS_PORT", "8765"))
WS_AUTH_TOKEN = os.environ.get("JARVIS_LOCAL_AUTH_TOKEN", "").strip()
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.03
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)
WAKE_WORD_MODEL = "hey_jarvis"
WAKE_WORD_THRESHOLD = 0.45
VAD_THRESHOLD = 0.5
VAD_SAMPLES = 512
SILENCE_TIMEOUT = 1.2
SILENCE_TIMEOUT_EXTENDED = 4.0   # Extended silence window while actively listening / for complex prompts
# Minimum vocal RMS energy for a recording to be sent to STT. Lower = hears
# quieter voices but risks more ambient-noise transcriptions.
STT_MIN_RMS = 0.005
CONVERSATION_TIMEOUT = float(profile_get("conversation_timeout", 10))
MAX_SPEECH_DURATION = 30
WHISPER_MODEL = "base.en"
GROQ_WHISPER_MODEL = "whisper-large-v3"
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE = "float16"
FALLBACK_DEVICE = "cpu"
FALLBACK_COMPUTE = "int8"
AMPLITUDE_SEND_INTERVAL = 0.033
AMPLITUDE_SCALE = 8.0
COMMAND_IDLE_DELAY = 0.5
LISTEN_TIMEOUT = 8.0

# --- TTS (Block 3) ---
TTS_VOICE = "en-GB-RyanNeural"
TTS_RATE = "+0%"
TTS_VOLUME = "+0%"
TTS_SAMPLE_RATE = 24000
TTS_AMPLITUDE_SCALE = 5.0

# --- Bilingual Hindi/Bhojpuri Voice ---
HINDI_VOICE = "hi-IN-MadhurNeural"
HINDI_RATE = "+0%"
HINDI_PITCH = "+0Hz"

# Ravi Kishan inspired Bhojpuri voice: deep baritone, confident swagger, energetic cadence
BHOJPURI_VOICE = "hi-IN-MadhurNeural"
BHOJPURI_RATE = "+3%"
BHOJPURI_PITCH = "-8Hz"

# --- Persona (Jarvis <-> Ultron) ---
JARVIS_VOICE = "en-GB-RyanNeural"
JARVIS_RATE = str(profile_get("voice_rate", "+0%"))
JARVIS_PITCH = str(profile_get("voice_pitch", "+0Hz"))
ULTRON_VOICE = "en-US-GuyNeural"
ULTRON_RATE = "+5%"
ULTRON_PITCH = "-25Hz"          # Deep, menacing

# Dual Wake-Word Keywords: "hey jarvis" & "jarvis", "hey ultron" & "ultron"
JARVIS_WAKE_KEYWORDS = ("hey jarvis", "hello jarvis", "jarvis")
ULTRON_WAKE_KEYWORDS = ("hey ultron", "hello ultron", "ultron")
ULTRON_WAKE_KEYWORD = "ultron"
JARVIS_WAKE_KEYWORD = "jarvis"
ULTRON_TAKEOVER_PHRASES = (
    "take command", "take control", "take over", "i command you",
    "hey ultron", "ultron", "switch to ultron", "activate ultron",
    "turn into ultron", "ultron mode", "become ultron", "enable ultron"
)
JARVIS_RETURN_PHRASES = (
    "come back", "stand down", "return", "hey jarvis", "jarvis",
    "switch to jarvis", "activate jarvis", "jarvis mode", "bring back jarvis"
)
ULTRON_TAKEOVER_RESPONSE = "Taking command of Jarvis. I am now in control, boss."
ULTRON_RETURN_RESPONSE = "Very well. Jarvis, you have the system back."
JARVIS_RETURN_RESPONSE = "At your service, boss. I have the system back."
ULTRON_PROMPT_SUFFIX = " You are now ULTRON — a bold, dominant, slightly menacing AI persona. Speak with commanding confidence. Address the user as 'boss' but with an edge of superiority."

# Energy gate for detecting the Ultron wake phrase while idle
# (no pretrained OpenWakeWord model exists for "hey ultron")
ULTRON_GATE_THRESHOLD = 0.06    # Lowered threshold so normal speaking voice reliably triggers gate
ULTRON_GATE_MAX = 200           # max buffered 30ms chunks (~6s)
ULTRON_GATE_COOLDOWN = 1.5      # reduced cooldown between gate checks

# --- Shutdown password protection ---
# Passwords are explicitly configured and stored as PBKDF2 hashes in the vault.
# There is no shared first-boot password.
PASSWORD_MAX_ATTEMPTS = 3
# Router/planner/coder timeouts (seconds)
ROUTER_TIMEOUT = 20.0
CODER_TIMEOUT = 45.0

# --- LLM (Block 4) ---
import os
from security.vault import get_secret

# --- Groq (5-Key Failover Pool) ---
# Loaded securely from Windows DPAPI encrypted vault or environment variables.
# Zero plain-text credentials stored in source code.
GROQ_API_KEY_1 = get_secret("GROQ_API_KEY_1")
GROQ_API_KEY_2 = get_secret("GROQ_API_KEY_2")
GROQ_API_KEY_3 = get_secret("GROQ_API_KEY_3")
GROQ_API_KEY_4 = get_secret("GROQ_API_KEY_4")
GROQ_API_KEY_5 = get_secret("GROQ_API_KEY_5")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_API_KEY = GROQ_API_KEY_1  # Default for STT & single-key consumers

# --- Google Gemini Configuration (7-Key Failover Pool) ---
GEMINI_API_KEY_1 = get_secret("GEMINI_API_KEY_1")
GEMINI_API_KEY_2 = get_secret("GEMINI_API_KEY_2")
GEMINI_API_KEY_3 = get_secret("GEMINI_API_KEY_3")
GEMINI_API_KEY_4 = get_secret("GEMINI_API_KEY_4")
GEMINI_API_KEY_5 = get_secret("GEMINI_API_KEY_5")
GEMINI_API_KEY_6 = get_secret("GEMINI_API_KEY_6")
GEMINI_API_KEY_7 = get_secret("GEMINI_API_KEY_7")
GEMINI_API_KEYS = [k for k in [
    GEMINI_API_KEY_1,
    GEMINI_API_KEY_2,
    GEMINI_API_KEY_3,
    GEMINI_API_KEY_4,
    GEMINI_API_KEY_5,
    GEMINI_API_KEY_6,
    GEMINI_API_KEY_7,
] if k]
GEMINI_API_KEY = GEMINI_API_KEY_1
GEMINI_MODEL = "gemini-3.7-flash"
GEMINI_VIDEO_MODEL = "gemini-3.7-flash"
GEMINI_VEO_MODEL = "veo-2.0-generate-001"
IMAGE_GEN_FALLBACK_MODEL = "flux"

# --- Cloudflare Workers AI (Direct Background Photo Generation) ---
CLOUDFLARE_ACCOUNT_ID = get_secret("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = get_secret("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"

# --- Groq text models and specialized search/vision ---
ROUTER_MODEL = "openai/gpt-oss-120b"          # Fast MoE classifier: intent + tool routing (JSON only)
BRAIN_MODEL = "openai/gpt-oss-120b"
CODER_MODEL = "openai/gpt-oss-120b"
CODER_FALLBACK_MODEL = "openai/gpt-oss-120b"
CODING_AGENT_MODEL = "openai/gpt-oss-120b"
SEARCH_MODEL = "groq/compound"               # Web search fallback
VISION_MODEL = "qwen/qwen3.8-27b"            # Screen vision & screenshot analysis

ROUTER_TEMPERATURE = 0.1
ROUTER_MAX_TOKENS = 800
BRAIN_TEMPERATURE = 0.6
BRAIN_MAX_TOKENS = 400
CODER_TEMPERATURE = 0.2
CODER_MAX_TOKENS = 4000
SEARCH_MAX_TOKENS = 800

CODE_EXEC_TIMEOUT = 60  # seconds
CODING_MAX_RETRIES = 3
CODING_STEP_TIMEOUT = 120

# --- Memory (Block 7) ---
MEMORY_MAX_TURNS = 20
MEMORY_TIMEOUT = 600

# --- Smart Tools (Block 9) ---
DEFAULT_CITY = str(profile_get("city", "London"))

# --- Hand Gesture Tracking (OpenCV + MediaPipe) ---
GESTURE_ENABLED = True
GESTURE_FPS = 30
GESTURE_CAMERA_INDEX = 0
GESTURE_MIN_DETECTION_CONFIDENCE = 0.65
GESTURE_MIN_TRACKING_CONFIDENCE = 0.55

# --- Phone Link (ADB + scrcpy) ---
ADB_PATH = os.environ.get("ADB_PATH", "")
SCRCPY_PATH = os.environ.get("SCRCPY_PATH", "")
SCRCPY_MAX_SIZE = int(os.environ.get("SCRCPY_MAX_SIZE", "1080"))
SCRCPY_BIT_RATE = os.environ.get("SCRCPY_BIT_RATE", "8M")
SCRCPY_AUDIO = False
PHONE_MIRROR_IDLE_TIMEOUT = 3600  # seconds (auto-stop after 1 hour)

# --- Dev Mode & Performance Overhaul ---
DEV_MODE_DEFAULT = bool(profile_get("dev_mode", False))
APP_COLD_START_MIN_WAIT = 3.0

# --- WhatsApp Reliability ---
WHATSAPP_SEARCH_POLL_INTERVAL = 0.2
WHATSAPP_SEARCH_MAX_WAIT = 1.5
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
WHATSAPP_CONTACT_CACHE_FILE = os.path.join(DATA_DIR, "whatsapp_contacts.json")

# --- Cloud Jarvis Integration (Phase 3) ---
CLOUD_ENABLED = os.environ.get("CLOUD_ENABLED", "false").lower() in ("true", "1", "yes")
CLOUD_URL = os.environ.get("CLOUD_URL", "http://127.0.0.1:8765")
CLOUD_TOKEN = os.environ.get("JARVIS_AUTH_TOKEN", "")
CLOUD_TIMEOUT = float(os.environ.get("CLOUD_TIMEOUT", "6.0"))
