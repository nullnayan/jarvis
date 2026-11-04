# FILE: backend/cloud/twilio_handler.py
# Jarvis AI Call Secretary — Twilio Voice Webhook Handler
# Handles incoming forwarded calls, Hindi-first language adaptation,
# urgency detection, call recording, hold/bridge flow, and notifications.

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from twilio.request_validator import RequestValidator
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Dial, Enqueue, Gather, Play, Say, VoiceResponse

from cloud.config import (
    USER_PHONE_NUMBER,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    TWILIO_WEBHOOK_BASE,
)

log = logging.getLogger("jarvis.twilio")

async def require_twilio_signature(request: Request):
    """Authenticate every webhook against the configured external URL, not an untrusted Host header."""
    if not TWILIO_AUTH_TOKEN or not TWILIO_WEBHOOK_BASE:
        raise HTTPException(status_code=403, detail="Twilio is not configured")
    url = TWILIO_WEBHOOK_BASE.rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    form = await request.form()
    signature = request.headers.get("X-Twilio-Signature", "")
    if not RequestValidator(TWILIO_AUTH_TOKEN).validate(url, form, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


router = APIRouter(dependencies=[Depends(require_twilio_signature)])

# ---------------------------------------------------------------------------
# Twilio REST client (lazy-init)
# ---------------------------------------------------------------------------
_twilio_client: Optional[TwilioClient] = None

def get_twilio_client() -> TwilioClient:
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _twilio_client


# ---------------------------------------------------------------------------
# Language Response Templates  (Hindi-first, auto-switch to English)
# ---------------------------------------------------------------------------
RESPONSES = {
    "greeting": {
        "hi": (
            "Namaste. Main Jarvis hoon, User ka AI assistant. "
            "User abhi uplabdh nahi hain. "
            "Kripya apna naam aur sandesh bataiye."
        ),
        "en": (
            "Hello. I am Jarvis, User's AI assistant. "
            "User is currently unavailable. "
            "Please state your name and leave a message."
        ),
    },
    "ask_urgency": {
        "hi": "Kya aapka koi urgent sandesh hai? Haan ya nahi bataiye.",
        "en": "Is this an urgent matter? Please say yes or no.",
    },
    "ask_urgent_message": {
        "hi": "Kripya apna urgent sandesh bataiye. Main User tak pahunchaunga.",
        "en": "Please describe your urgent message. I will relay it to User immediately.",
    },
    "hold_urgent": {
        "hi": "Samajh gaya. Kripya hold karein. Main User ko abhi contact karta hoon.",
        "en": "Understood. Please hold. I am contacting User right now.",
    },
    "thank_normal": {
        "hi": "Dhanyavaad. Maine aapka sandesh note kar liya hai. User ko bata dunga.",
        "en": "Thank you. I have noted your message and will inform User.",
    },
    "will_call_back": {
        "hi": "User aapko jaldi wapas call karenge. Dhanyavaad.",
        "en": "User will call you back shortly. Thank you.",
    },
    "reject_not_contact": {
        "hi": "Kshama karein. User abhi uplabdh nahi hain. Dhanyavaad.",
        "en": "Sorry, User is currently unavailable. Thank you.",
    },
    "no_response": {
        "hi": "Koi jawab nahi mila. Baad mein call karein. Dhanyavaad.",
        "en": "No response detected. Please call again later. Thank you.",
    },
    "owner_intro": {
        "en": "Boss, {name} is calling. Their message: {message}. Say 'connect' to join them, or 'no' to decline.",
    },
    "caller_connected": {
        "hi": "User se connect kar raha hoon. Kripya wait karein.",
        "en": "Connecting you to User now. Please wait.",
    },
    "caller_declined": {
        "hi": "User abhi busy hain. Woh aapko jaldi call karenge.",
        "en": "User is busy right now. He will call you back shortly.",
    },
}

TWILIO_VOICE_HINDI = "Polly.Aditi"      # AWS Polly Hindi voice via Twilio
TWILIO_VOICE_ENGLISH = "Polly.Matthew"  # Natural English male voice


# ---------------------------------------------------------------------------
# In-Memory Call Session State
# ---------------------------------------------------------------------------
@dataclass
class CallSession:
    call_sid: str
    caller_number: str
    caller_name: str
    started_at: float = field(default_factory=time.time)
    transcription: str = ""
    urgency: str = "unknown"          # "normal" | "urgent" | "unknown"
    urgent_message: str = ""
    status: str = "active"            # "active" | "on_hold" | "bridged" | "completed"
    language: str = "hi"              # "hi" | "en" — detected from caller's speech
    recording_url: Optional[str] = None
    recording_duration: int = 0
    owner_call_sid: Optional[str] = None
    conference_name: Optional[str] = None


# call_sid → CallSession
active_calls: dict[str, CallSession] = {}

# Call history log for wake-up summary
call_log: list[dict] = []

# contact whitelist: phone_number → name (synced from phone app)
contact_whitelist: dict[str, str] = {}


def _url(path: str) -> str:
    """Build full webhook URL."""
    base = TWILIO_WEBHOOK_BASE.rstrip("/")
    return f"{base}/twilio{path}"


def _say(response: VoiceResponse, text: str, lang: str) -> None:
    """Append a <Say> verb with correct voice for the detected language."""
    voice = TWILIO_VOICE_HINDI if lang == "hi" else TWILIO_VOICE_ENGLISH
    tts_lang = "hi-IN" if lang == "hi" else "en-US"
    response.say(text, voice=voice, language=tts_lang)


def _normalize_number(number: str) -> str:
    """Strip spaces and normalize phone number to E.164."""
    n = number.strip().replace(" ", "").replace("-", "")
    if not n.startswith("+"):
        n = "+" + n
    return n


def _get_caller_name(caller_number: str) -> Optional[str]:
    """Look up caller in the contact whitelist. Returns name or None."""
    norm = _normalize_number(caller_number)
    # Try exact match first
    if norm in contact_whitelist:
        return contact_whitelist[norm]
    # Try last 10 digits match (handles +91 prefix differences)
    short = norm[-10:]
    for num, name in contact_whitelist.items():
        if num[-10:] == short:
            return name
    return None


def _detect_language(speech_result: str) -> str:
    """
    Detect if caller spoke Hindi or English from the transcription.
    Hindi is characterised by Devanagari characters or common Hindi romanised words.
    """
    if not speech_result:
        return "hi"

    # If Devanagari characters present → definitely Hindi
    for ch in speech_result:
        if "\u0900" <= ch <= "\u097F":
            return "hi"

    # Common Hindi romanised words
    hindi_words = {
        "haan", "nahi", "nahin", "kya", "mera", "meri", "main", "aur",
        "hai", "hain", "tha", "thi", "baat", "karo", "karna", "chahiye",
        "thoda", "zyada", "bilkul", "shukriya", "dhanyavaad", "namaste",
        "bhaiya", "didi", "bhai", "yaar", "accha", "theek", "sahi",
    }
    words = set(speech_result.lower().split())
    if words & hindi_words:
        return "hi"

    return "en"


async def _classify_urgency(text: str) -> str:
    """Use LLM to classify if the caller's message is urgent or normal."""
    try:
        from cloud.cloud_brain import cloud_brain
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an urgency classifier for an AI phone assistant. "
                    "Classify the caller's message as 'urgent' or 'normal'. "
                    "Urgent = medical emergency, accident, someone in danger, time-critical matter, "
                    "or caller explicitly uses words like urgent, emergency, accident, hospital, danger, help. "
                    "Normal = everything else (social calls, call me back, casual messages, questions). "
                    "Reply ONLY with valid JSON: {\"urgency\": \"urgent\"} or {\"urgency\": \"normal\"}"
                ),
            },
            {"role": "user", "content": f"Caller said: \"{text}\""},
        ]
        raw = await cloud_brain._call_llm(messages, temperature=0.0, max_tokens=30)
        import re, json as _json
        cleaned = re.sub(r"```.*?```", "", raw, flags=re.DOTALL).strip()
        result = _json.loads(cleaned)
        return result.get("urgency", "normal")
    except Exception as e:
        log.warning(f"[Twilio] Urgency classification failed: {e}")
        # Fall back to keyword matching
        urgent_words = {
            "urgent", "emergency", "accident", "hospital", "danger",
            "help", "hurt", "injured", "dying", "fire", "police",
            "ambulance", "critical", "immediately", "asap",
            "jaldi", "emergency hai", "hospital", "accident",
        }
        lower = text.lower()
        for w in urgent_words:
            if w in lower:
                return "urgent"
        return "normal"


async def _notify_phone(caller_name: str, caller_number: str, message: str = "", recording_url: str = "") -> None:
    """Send call notification to phone app via WebSocket."""
    try:
        from cloud.hub import hub
        await hub.broadcast_to_phones({
            "type": "call_notification",
            "caller_name": caller_name,
            "caller_number": caller_number,
            "message": message,
            "recording_url": recording_url,
            "timestamp": time.time(),
        })
    except Exception as e:
        log.warning(f"[Twilio] Failed to notify phone: {e}")


async def _send_urgent_alert(session: CallSession) -> None:
    """Notify phone to remove DND + disable forwarding, then call User via Twilio."""
    try:
        from cloud.hub import hub
        # 1. Tell phone to remove DND and disable call forwarding
        await hub.broadcast_to_phones({
            "type": "urgent_alert",
            "caller_name": session.caller_name,
            "caller_number": session.caller_number,
            "urgent_message": session.urgent_message,
            "call_sid": session.call_sid,
            "timestamp": time.time(),
        })
        await hub.broadcast_to_phones({
            "type": "execute_task",
            "action": "phone_dnd",
            "params": {"enabled": False},
        })
        await hub.broadcast_to_phones({
            "type": "execute_task",
            "action": "disable_call_forwarding",
            "params": {},
        })

        # 2. Wait 3 seconds for forwarding to deactivate on the phone
        await asyncio.sleep(3)

        # 3. Call User via Twilio
        client = get_twilio_client()
        owner_call = client.calls.create(
            to=USER_PHONE_NUMBER,
            from_=TWILIO_PHONE_NUMBER,
            url=_url(f"/owner-answer?call_sid={session.call_sid}"),
            status_callback=_url("/status"),
            status_callback_event=["completed"],
        )
        session.owner_call_sid = owner_call.sid
        log.info(f"[Twilio] Calling User for urgent alert. User call SID: {owner_call.sid}")

    except Exception as e:
        log.error(f"[Twilio] Failed to send urgent alert: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Webhook 1: Incoming call entry point
# ---------------------------------------------------------------------------
@router.post("/voice")
async def voice_entry(
    CallSid: str = Form(""),
    From: str = Form(""),
    To: str = Form(""),
    CallStatus: str = Form(""),
):
    response = VoiceResponse()
    caller_number = _normalize_number(From) if From else ""
    caller_name = _get_caller_name(caller_number)

    log.info(f"[Twilio] Incoming call from {caller_number} (name={caller_name}), SID={CallSid}")

    # If whitelist is populated and caller is not in it — reject politely
    if contact_whitelist and caller_name is None:
        log.info(f"[Twilio] Caller {caller_number} not in whitelist — rejecting.")
        _say(response, RESPONSES["reject_not_contact"]["hi"], "hi")
        return Response(content=str(response), media_type="application/xml")

    caller_name = caller_name or "Unknown Caller"

    # Create session
    session = CallSession(
        call_sid=CallSid,
        caller_number=caller_number,
        caller_name=caller_name,
    )
    active_calls[CallSid] = session

    # Notify phone that Jarvis is handling this call
    asyncio.create_task(_notify_phone(caller_name, caller_number))

    # Start recording (records both legs; callback fires when call ends)
    response.record(
        recording_status_callback=_url("/recording"),
        recording_status_callback_event=["completed"],
        recording_status_callback_method="POST",
        action=_url(f"/after-record?call_sid={CallSid}"),
        max_length=300,
        trim="trim-silence",
        play_beep=False,
    )

    return Response(content=str(response), media_type="application/xml")


# ---------------------------------------------------------------------------
# Webhook 2: After recording starts — greet and gather caller's message
# ---------------------------------------------------------------------------
@router.post("/after-record")
async def after_record(
    call_sid: str = "",
    CallSid: str = Form(""),
):
    sid = call_sid or CallSid
    response = VoiceResponse()
    session = active_calls.get(sid)
    lang = session.language if session else "hi"

    gather = Gather(
        input="speech",
        language="hi-IN" if lang == "hi" else "en-US",
        speech_timeout="auto",
        action=_url(f"/gather?call_sid={sid}"),
        method="POST",
    )
    gather.say(
        RESPONSES["greeting"][lang],
        voice=TWILIO_VOICE_HINDI if lang == "hi" else TWILIO_VOICE_ENGLISH,
        language="hi-IN" if lang == "hi" else "en-US",
    )
    response.append(gather)

    # If no input
    _say(response, RESPONSES["no_response"]["hi"], "hi")
    return Response(content=str(response), media_type="application/xml")


# ---------------------------------------------------------------------------
# Webhook 3: Caller's first speech — detect language + classify urgency
# ---------------------------------------------------------------------------
@router.post("/gather")
async def gather_message(
    call_sid: str = "",
    SpeechResult: str = Form(""),
    Confidence: str = Form(""),
    CallSid: str = Form(""),
):
    sid = call_sid or CallSid
    response = VoiceResponse()
    session = active_calls.get(sid)

    if not session:
        _say(response, RESPONSES["no_response"]["hi"], "hi")
        return Response(content=str(response), media_type="application/xml")

    speech = (SpeechResult or "").strip()
    log.info(f"[Twilio] Caller said: '{speech}' (confidence={Confidence})")

    # Detect language from what caller said
    detected_lang = _detect_language(speech)
    session.language = detected_lang
    session.transcription = speech

    if not speech:
        _say(response, RESPONSES["no_response"][detected_lang], detected_lang)
        return Response(content=str(response), media_type="application/xml")

    # Classify urgency
    urgency = await _classify_urgency(speech)
    session.urgency = urgency
    log.info(f"[Twilio] Urgency classification: {urgency}")

    if urgency == "urgent":
        # Ask caller to describe their urgent message specifically
        gather = Gather(
            input="speech",
            language="hi-IN" if detected_lang == "hi" else "en-US",
            speech_timeout="auto",
            action=_url(f"/urgent-message?call_sid={sid}"),
            method="POST",
        )
        gather.say(
            RESPONSES["ask_urgent_message"][detected_lang],
            voice=TWILIO_VOICE_HINDI if detected_lang == "hi" else TWILIO_VOICE_ENGLISH,
            language="hi-IN" if detected_lang == "hi" else "en-US",
        )
        response.append(gather)
    else:
        # Normal call — thank and hang up
        session.status = "completed"
        _say(response, RESPONSES["thank_normal"][detected_lang], detected_lang)
        response.hangup()
        # Log and notify
        _add_to_log(session)
        asyncio.create_task(_notify_phone(
            session.caller_name, session.caller_number,
            message=speech,
        ))

    return Response(content=str(response), media_type="application/xml")


# ---------------------------------------------------------------------------
# Webhook 4: Caller provides their urgent message details
# ---------------------------------------------------------------------------
@router.post("/urgent-message")
async def urgent_message(
    call_sid: str = "",
    SpeechResult: str = Form(""),
    CallSid: str = Form(""),
):
    sid = call_sid or CallSid
    response = VoiceResponse()
    session = active_calls.get(sid)

    if not session:
        _say(response, RESPONSES["no_response"]["hi"], "hi")
        return Response(content=str(response), media_type="application/xml")

    urgent_msg = (SpeechResult or "").strip()
    session.urgent_message = urgent_msg
    lang = session.language
    log.info(f"[Twilio] Urgent message from {session.caller_name}: '{urgent_msg}'")

    # Tell caller to hold
    _say(response, RESPONSES["hold_urgent"][lang], lang)

    # Put caller in a conference room (hold music plays automatically)
    conference_name = f"jarvis_urgent_{sid[:8]}"
    session.conference_name = conference_name
    session.status = "on_hold"

    dial = Dial()
    dial.conference(
        conference_name,
        wait_url="http://twimlets.com/holdmusic?Bucket=com.twilio.music.classical",
        wait_method="GET",
        muted=False,
        start_conference_on_enter=True,
        end_conference_on_exit=False,
    )
    response.append(dial)

    # Trigger alert to User (non-blocking)
    asyncio.create_task(_send_urgent_alert(session))

    return Response(content=str(response), media_type="application/xml")


# ---------------------------------------------------------------------------
# Webhook 5: User picks up the urgent callback call
# ---------------------------------------------------------------------------
@router.post("/owner-answer")
async def owner_answer(
    call_sid: str = "",
    CallSid: str = Form(""),
):
    """TwiML for the outbound call Twilio makes to User."""
    # call_sid here is the ORIGINAL caller's SID (passed as query param)
    response = VoiceResponse()
    session = active_calls.get(call_sid)

    if not session:
        response.say("Sorry boss, call session expired.", voice=TWILIO_VOICE_ENGLISH, language="en-US")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    intro_text = RESPONSES["owner_intro"]["en"].format(
        name=session.caller_name,
        message=session.urgent_message or session.transcription or "No message recorded.",
    )

    gather = Gather(
        input="speech",
        language="en-US",
        speech_timeout=10,
        action=_url(f"/owner-decision?call_sid={call_sid}"),
        method="POST",
    )
    gather.say(intro_text, voice=TWILIO_VOICE_ENGLISH, language="en-US")
    response.append(gather)

    # If User doesn't respond, decline by default
    response.say("No response detected. Declining the call.", voice=TWILIO_VOICE_ENGLISH, language="en-US")
    response.redirect(_url(f"/owner-decision?call_sid={call_sid}&decision=no"))

    return Response(content=str(response), media_type="application/xml")


# ---------------------------------------------------------------------------
# Webhook 6: User says "connect" or "no"
# ---------------------------------------------------------------------------
@router.post("/owner-decision")
async def owner_decision(
    call_sid: str = "",
    decision: str = "",
    SpeechResult: str = Form(""),
    CallSid: str = Form(""),
):
    owner_sid = CallSid  # This is User's call SID
    original_sid = call_sid
    response = VoiceResponse()
    session = active_calls.get(original_sid)

    speech = (SpeechResult or decision or "").lower().strip()
    log.info(f"[Twilio] User decision: '{speech}' for call {original_sid}")

    connect_words = {"connect", "join", "yes", "bridge", "connect me", "join me", "haan", "ha", "ok"}
    should_connect = any(w in speech for w in connect_words)

    if session and should_connect and session.conference_name:
        session.status = "bridged"
        _say(response, "Connecting you now boss.", "en")
        # Join User into the same conference room as the caller
        dial = Dial()
        dial.conference(
            session.conference_name,
            start_conference_on_enter=True,
            end_conference_on_exit=True,   # Hang up everyone when User leaves
            muted=False,
        )
        response.append(dial)
        log.info(f"[Twilio] Bridging User into conference {session.conference_name}")

        # Update caller — tell them User is joining
        try:
            client = get_twilio_client()
            client.calls(original_sid).update(
                twiml=f"<Response><Say voice='{TWILIO_VOICE_HINDI}' language='hi-IN'>"
                      f"{RESPONSES['caller_connected']['hi']}</Say></Response>"
            )
        except Exception as e:
            log.warning(f"[Twilio] Could not update caller TwiML: {e}")

    else:
        # User declined
        session and setattr(session, "status", "completed")
        response.say("Understood boss. Telling them you'll call back.", voice=TWILIO_VOICE_ENGLISH, language="en-US")
        response.hangup()

        # Tell caller User will call back
        if session:
            try:
                lang = session.language
                client = get_twilio_client()
                client.calls(original_sid).update(
                    twiml=f"<Response><Say voice='{TWILIO_VOICE_HINDI if lang == 'hi' else TWILIO_VOICE_ENGLISH}' "
                          f"language='{'hi-IN' if lang == 'hi' else 'en-US'}'>"
                          f"{RESPONSES['caller_declined'][lang]}</Say><Hangup/></Response>"
                )
            except Exception as e:
                log.warning(f"[Twilio] Could not update caller: {e}")

    _add_to_log(session)
    return Response(content=str(response), media_type="application/xml")


# ---------------------------------------------------------------------------
# Webhook 7: Recording complete — push to phone notification
# ---------------------------------------------------------------------------
@router.post("/recording")
async def recording_complete(
    CallSid: str = Form(""),
    RecordingUrl: str = Form(""),
    RecordingDuration: str = Form("0"),
    RecordingSid: str = Form(""),
):
    log.info(f"[Twilio] Recording complete for {CallSid}: {RecordingUrl}")
    session = active_calls.get(CallSid)

    # Twilio recording URL needs .mp3 appended
    mp3_url = f"{RecordingUrl}.mp3" if RecordingUrl and not RecordingUrl.endswith(".mp3") else RecordingUrl

    if session:
        session.recording_url = mp3_url
        session.recording_duration = int(RecordingDuration or 0)

    # Push updated notification with recording to phone
    try:
        from cloud.hub import hub
        name = session.caller_name if session else "Unknown"
        number = session.caller_number if session else ""
        msg = session.urgent_message or session.transcription if session else ""
        await hub.broadcast_to_phones({
            "type": "call_notification",
            "caller_name": name,
            "caller_number": number,
            "message": msg,
            "recording_url": mp3_url,
            "recording_duration": int(RecordingDuration or 0),
            "timestamp": time.time(),
        })
    except Exception as e:
        log.warning(f"[Twilio] Failed to push recording notification: {e}")

    return Response(content="", status_code=204)


# ---------------------------------------------------------------------------
# Webhook 8: Call status update
# ---------------------------------------------------------------------------
@router.post("/status")
async def call_status(
    CallSid: str = Form(""),
    CallStatus: str = Form(""),
    Duration: str = Form("0"),
):
    log.info(f"[Twilio] Call status: {CallSid} → {CallStatus} (duration={Duration}s)")
    session = active_calls.get(CallSid)
    if session and CallStatus in ("completed", "failed", "busy", "no-answer"):
        session.status = "completed"
        _add_to_log(session)
        active_calls.pop(CallSid, None)
    return Response(content="", status_code=204)


# ---------------------------------------------------------------------------
# REST: Get/clear contact whitelist (called by phone app via WebSocket hub)
# ---------------------------------------------------------------------------
def update_contact_whitelist(contacts: dict) -> None:
    """Update the in-memory contact whitelist. Called from hub when phone sends contacts."""
    global contact_whitelist
    contact_whitelist.clear()
    contact_whitelist.update(contacts)
    log.info(f"[Twilio] Contact whitelist updated: {len(contact_whitelist)} contacts")


# ---------------------------------------------------------------------------
# REST: Get call log (for wake-up summary)
# ---------------------------------------------------------------------------
def get_call_log() -> list:
    return list(call_log)


def clear_call_log() -> None:
    call_log.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _add_to_log(session: Optional[CallSession]) -> None:
    if not session:
        return
    entry = {
        "call_sid": session.call_sid,
        "caller_name": session.caller_name,
        "caller_number": session.caller_number,
        "started_at": session.started_at,
        "transcription": session.transcription,
        "urgency": session.urgency,
        "urgent_message": session.urgent_message,
        "status": session.status,
        "language": session.language,
        "recording_url": session.recording_url,
        "recording_duration": session.recording_duration,
    }
    call_log.append(entry)
    log.info(f"[Twilio] Logged call: {session.caller_name} ({session.urgency})")
