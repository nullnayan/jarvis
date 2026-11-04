# FILE: backend/cloud/config.py
# Central configuration for Cloud Jarvis on Azure VM.
# Reads all secrets from environment variables or .env file.

import os
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
except ImportError:
    pass

# Server Network Settings
CLOUD_HOST = os.environ.get("CLOUD_HOST", "127.0.0.1")
CLOUD_PORT = int(os.environ.get("CLOUD_PORT", "8765"))

# Security & Authentication
# Shared secret required for PC Agent, Phone App, and jarvis.bat to connect
JARVIS_AUTH_TOKEN = os.environ.get("JARVIS_AUTH_TOKEN", "").strip()
CLOUD_ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get("CLOUD_ALLOWED_ORIGINS", "").split(",") if origin.strip()]

# Groq API Keys (Failover Pool)
GROQ_API_KEY_1 = os.environ.get("GROQ_API_KEY_1", "")
GROQ_API_KEY_2 = os.environ.get("GROQ_API_KEY_2", "")
GROQ_API_KEY_3 = os.environ.get("GROQ_API_KEY_3", "")
GROQ_API_KEY_4 = os.environ.get("GROQ_API_KEY_4", "")
GROQ_API_KEY_5 = os.environ.get("GROQ_API_KEY_5", "")
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_API_KEY = GROQ_API_KEY_1 or GROQ_API_KEY_2

# Models
ROUTER_MODEL = "openai/gpt-oss-120b"
BRAIN_MODEL = "openai/gpt-oss-120b"
CODER_MODEL = "openai/gpt-oss-120b"

# TTS Voice
DEFAULT_TTS_VOICE = os.environ.get("DEFAULT_TTS_VOICE", "en-GB-RyanNeural")
HINDI_TTS_VOICE = os.environ.get("HINDI_TTS_VOICE", "hi-IN-MadhurNeural")

# Twilio Voice (AI Call Secretary)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
USER_PHONE_NUMBER = os.environ.get("USER_PHONE_NUMBER", "")
TWILIO_WEBHOOK_BASE = os.environ.get("TWILIO_WEBHOOK_BASE", "http://127.0.0.1:8765")
