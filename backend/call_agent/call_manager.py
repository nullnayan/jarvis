# FILE: call_manager.py
# Manages live WhatsApp call conversation when Jarvis is asked to talk on User's behalf.
import asyncio
import re
import threading
import time
from openai import AsyncOpenAI
import psutil
from config import GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_BASE_URL, ROUTER_MODEL
from llm.prompts import CALL_AGENT_PROMPT
from server.messages import caption_msg, jarvis_speech_msg
from user_profile import get as profile_get

class CallManager:
    """Manages the lifecycle and conversation of a live call on User's behalf."""

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.is_active = False
        self.contact_name = ""
        self.call_type = "voice"
        self.has_greeted = False
        self.dialogue_history = []
        self._monitor_thread = None
        self._stop_monitor = threading.Event()
        self._lock = threading.Lock()

        # Initialize dual Groq clients for failover
        self.client_1 = AsyncOpenAI(api_key=GROQ_API_KEY_1, base_url=GROQ_BASE_URL)
        self.client_2 = AsyncOpenAI(api_key=GROQ_API_KEY_2, base_url=GROQ_BASE_URL)

    def start_call(self, contact_name: str, call_type: str = "voice"):
        """Activates Call Agent mode for a dialed WhatsApp call."""
        with self._lock:
            self.is_active = True
            self.contact_name = contact_name
            self.call_type = call_type
            self.has_greeted = False
            self.dialogue_history = []
            self._stop_monitor.clear()

        print(f"[CallAgent] Activated for {contact_name} ({call_type}). Waiting for pickup...")
        self.pipeline.set_state("listening")
        self.pipeline.send(caption_msg(f"[On Call: {contact_name}]"))

        # Start background window monitor to detect when call ends
        self._monitor_thread = threading.Thread(target=self._monitor_call_window, daemon=True)
        self._monitor_thread.start()

    def _monitor_call_window(self):
        """Watches for WhatsApp call window creation and its eventual closure."""
        time.sleep(3.0)  # Grace period for call window to spawn
        saw_call_window = False
        empty_count = 0

        while not self._stop_monitor.is_set():
            time.sleep(1.0)
            is_call_window_open = self._is_whatsapp_call_window_open()

            if is_call_window_open:
                saw_call_window = True
                empty_count = 0
            elif saw_call_window:
                # Call window was previously open and is now gone
                empty_count += 1
                if empty_count >= 2:
                    print("[CallAgent] WhatsApp call window closed. Ending call session.")
                    self.end_call(reason="caller_hung_up")
                    break

    def _is_whatsapp_call_window_open(self) -> bool:
        """Checks if a WhatsApp call window exists by inspecting window titles and processes."""
        try:
            import pygetwindow as gw
            for w in gw.getAllWindows():
                title = (w.title or "").strip().lower()
                # WhatsApp call window titles contain contact name, 'calling', 'ringing', or call timer '00:'
                if any(k in title for k in ("whatsapp call", "calling", "ringing", "00:", "01:", "02:")):
                    return True
                if self.contact_name.lower() in title and ("call" in title or "voice" in title or "video" in title):
                    return True
        except Exception:
            pass
        return False

    async def on_pickup_or_speech(self, text: str = "", lang: str = "en"):
        """Handles first greeting once connection or speech is detected, or answers caller."""
        if not self.is_active:
            return

        # Check if User is asking to take back the call
        if self._is_handover_command(text):
            await self.handover_to_user()
            return

        # First turn: deliver the introductory greeting
        if not self.has_greeted:
            self.has_greeted = True
            name = self.contact_name or "there"
            if lang in ("hi", "bho"):
                greeting = f"नमस्ते {name}, मैं जार्विस हूँ, नयन का AI असिस्टेंट। नयन अभी व्यस्त हैं, मैं आपकी क्या मदद कर सकता हूँ?"
                romanized = f"Namaste {name}, main Jarvis hoon, User ka AI assistant. User abhi vyast hain, main aapki kya madad kar sakta hoon?"
            else:
                greeting = f"Hello {name}, I am Jarvis, User's AI assistant. User has asked me to speak on his behalf. How can I help you today?"
                romanized = greeting
            print(f"[CallAgent] Delivering introduction: {romanized}")
            self.dialogue_history.append({"role": "assistant", "content": greeting})
            await self._speak(greeting, lang=lang)
            return

        # Subsequent turns: natural conversational reply
        if text and text.strip():
            await self.reply_to_caller(text, lang=lang)

    def _is_handover_command(self, text: str) -> bool:
        """Checks if User wants to take over the call or stop Jarvis."""
        lower = text.lower().strip()
        handover_phrases = [
            "i'll take over", "ill take over", "i will take over",
            "let me talk", "i'll talk", "ill talk", "i will talk",
            "jarvis stop", "stop talking", "give me the call",
            "i got this", "take back the call", "jarvis hang up", "hang up",
        ]
        return any(p in lower for p in handover_phrases)

    async def reply_to_caller(self, caller_text: str, lang: str = "en"):
        """Generates a natural, human-like conversational response to the caller."""
        print(f"[CallAgent] Caller said: '{caller_text}' (lang={lang})")
        self.dialogue_history.append({"role": "user", "content": caller_text})

        # Keep history compact (last 6 turns)
        history = self.dialogue_history[-6:]
        system_prompt = CALL_AGENT_PROMPT.format(
            caller_name=self.contact_name or "the caller",
            user_name=str(profile_get("name", "User")),
        )
        if lang in ("hi", "bho"):
            system_prompt += "\n\nCRITICAL: The caller is speaking in Hindi or Bhojpuri. Reply warmly and naturally in the same language!"

        messages = [{"role": "system", "content": system_prompt}, *history]

        response_text = ""
        # 1) Try Key 1 (primary)
        try:
            resp = await self.client_1.chat.completions.create(
                model=ROUTER_MODEL,
                messages=messages,
                temperature=0.4,
                max_tokens=150,
                timeout=8,
            )
            response_text = resp.choices[0].message.content.strip()
            response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
        except Exception as e:
            print(f"[CallAgent] Key 1 error: {e}, failing over to Key 2...")
            # 2) Failover to Key 2
            try:
                resp = await self.client_2.chat.completions.create(
                    model=ROUTER_MODEL,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=150,
                    timeout=8,
                )
                response_text = resp.choices[0].message.content.strip()
                response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
            except Exception as e2:
                print(f"[CallAgent] Key 2 failover error: {e2}")

        if not response_text:
            response_text = "माफ़ कीजियेगा, क्या आप दोबारा बोल सकते हैं?" if lang in ("hi", "bho") else "I apologize, I missed that. Could you please repeat?"

        # Clean markdown or quotes
        response_text = re.sub(r'[*_`#"]', '', response_text).strip()
        print(f"[CallAgent] Jarvis replying: {response_text}")
        self.dialogue_history.append({"role": "assistant", "content": response_text})
        await self._speak(response_text, lang=lang)

    async def _speak(self, text: str, lang: str = "en"):
        """Speaks response and returns pipeline to listening state."""
        self.pipeline.speaking = True
        self.pipeline.set_state("speaking")
        self.pipeline.send(caption_msg(text))
        self.pipeline.send(jarvis_speech_msg(text))
        await self.pipeline.tts.speak(text, lang=lang)
        self.pipeline.speaking = False
        self.pipeline.vad.reset()
        if self.is_active:
            self.pipeline.set_state("listening")
            self.pipeline.send(caption_msg(f"[On Call: {self.contact_name}]"))

    async def handover_to_user(self):
        """Hands the call back to User."""
        print("[CallAgent] Handover requested by user.")
        handover_text = "Certainly, boss. Handing the call over to you now."
        await self._speak(handover_text)
        self.end_call(reason="user_takeover")

    def end_call(self, reason: str = "normal"):
        """Ends the call agent session and returns Jarvis to idle."""
        with self._lock:
            if not self.is_active:
                return
            self.is_active = False
            self._stop_monitor.set()

        print(f"[CallAgent] Call session ended ({reason}). Returning to idle.")
        name = self.contact_name or "the contact"

        def _do_end():
            farewell = f"The call with {name} has ended, boss. Returning to standby."
            asyncio.create_task(self.pipeline.respond_and_idle(farewell))

        if self.pipeline.loop and not self.pipeline.loop.is_closed():
            self.pipeline.loop.call_soon_threadsafe(_do_end)
