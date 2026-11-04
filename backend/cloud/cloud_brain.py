# FILE: backend/cloud/cloud_brain.py
# Headless Cloud Brain for Jarvis.
# Classifies intents, answers chat/questions directly, and routes device actions.

import asyncio
from tools.product_search import product_search
from tools.deal_hunter import deal_hunter
import json
import re
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from openai import AsyncOpenAI

from cloud.config import (
    GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3, GROQ_API_KEY_4, GROQ_API_KEY_5,
    GROQ_BASE_URL, ROUTER_MODEL, BRAIN_MODEL,
)
from cloud.hub import hub

# PC Desktop Tasks (pyautogui / local Windows actions)

CLOUD_ACTIONS = {
    "product_search", "deal_hunter",
    "search_product", "find_product", "compare_prices",
    "watch_product", "track_product", "stop_notifications",
    "start_deal_hunter", "stop_deal_hunter", "deal_status",
}

PC_ACTIONS = {
    "open_app", "close_app", "launch_app", "start_app", "run_app",
    "whatsapp_send", "whatsapp_call", "whatsapp_message",
    "media_play", "media_pause", "media_next", "media_previous",
    "volume_set", "volume_up", "volume_down", "volume_mute",
    "wifi_control", "vpn_control", "system_power", "lock_pc",
    "open_website", "screenshot_pc", "pc_command", "dev_task",
    "pc_status", "system_status", "check_status",
    # File & Folder operations
    "create_folder", "make_folder", "new_folder", "mkdir",
    "create_file", "make_file", "new_file",
    "delete_folder", "remove_folder", "delete_file", "remove_file", "delete", "remove",
    "rename_file", "rename_folder", "rename",
    "move_file", "move_folder", "move", "copy_file", "copy_folder", "copy",
    "read_folder", "list_folder", "read_file", "summarize_file", "read_doc",
    # Search & Screenshot
    "web_search", "search", "google", "screenshot", "take_screenshot",
    # Music & Media Playback
    "play_music", "play_song", "play_media", "play_video",
    "play_youtube", "youtube_play", "play_spotify", "spotify_play",
    # Shell & Commands
    "run_command", "execute_command", "shell",
}

# Phone Mobile Tasks (Android Intents / Telephony)
PHONE_ACTIONS = {
    "phone_open_app", "phone_call", "phone_contacts",
    "phone_dnd", "phone_silence", "phone_ring", "phone_alarm",
    "sleep_mode_toggle", "call_answer", "call_decline", "call_transfer",
}

ROUTER_SYSTEM_PROMPT = """You are the core routing brain for JARVIS, an autonomous AI assistant for User (boss).
Classify the user command into one of these types:
1. "chat" - Greetings, conversational questions, math, facts, chit-chat, explanations, general questions.
2. "pc_task" - ANY command that involves the user's Windows PC: opening/closing apps, checking PC status, sending WhatsApp messages, changing volume, WiFi/VPN, locking/shutting down, creating/deleting/renaming/moving folders and files, reading folder contents, running commands, searching the web, taking screenshots, or ANY action that requires doing something on the PC.
3. "phone_task" - Any command to control the user\'s phone: opening phone apps, making phone calls, setting phone to silent/DND, sleep mode, checking phone battery.
4. "cloud_task" - Tasks that run independently in the cloud, like searching for product prices on Amazon/Flipkart or managing the background Deal Hunter.

IMPORTANT: If the user asks to create, delete, rename, read, move, copy, or do ANYTHING with files/folders on the PC — classify as "pc_task". If unsure whether something is a chat or pc_task, lean towards "pc_task".
If the user asks to search for a product price (e.g. "Check price of motorola"), classify as "cloud_task" with action "product_search".
If the user asks to manage the Deal Hunter, classify as "cloud_task" with action "deal_hunter".

Return ONLY a valid JSON object with NO markdown formatting:
{
  "type": "chat" | "pc_task" | "phone_task" | "cloud_task",
  "action": "<action_name or none>",
  "params": { ... },
  "response": "<concise speech response to say to User, e.g. 'Opening YouTube on your PC, boss.' or the direct chat answer>"
}

Examples:
- "Hello Jarvis" -> {"type": "chat", "action": "none", "params": {}, "response": "Hello boss! How can I assist you today?"}
- "What is the capital of France?" -> {"type": "chat", "action": "none", "params": {}, "response": "The capital of France is Paris, boss."}
- "Open YouTube on PC" -> {"type": "pc_task", "action": "open_app", "params": {"app": "youtube"}, "response": "Opening YouTube on your PC, boss."}
- "What's the PC status" -> {"type": "pc_task", "action": "pc_status", "params": {}, "response": "Checking PC status, boss."}
- "Play Starboy" -> {"type": "pc_task", "action": "play_music", "params": {"query": "Starboy", "app": "youtube"}, "response": "Playing Starboy, boss."}
- "Play a sad song" -> {"type": "pc_task", "action": "play_music", "params": {"query": "sad song", "app": "youtube"}, "response": "Playing a sad song, boss."}
- "Play some chill music" -> {"type": "pc_task", "action": "play_music", "params": {"query": "chill music", "app": "youtube"}, "response": "Playing chill music, boss."}
- "Play Tum Hi Ho on Spotify" -> {"type": "pc_task", "action": "play_music", "params": {"query": "Tum Hi Ho", "app": "spotify"}, "response": "Playing Tum Hi Ho on Spotify, boss."}
- "Play a song on Spotify" -> {"type": "pc_task", "action": "play_music", "params": {"query": "popular songs", "app": "spotify"}, "response": "Playing music on Spotify, boss."}
- "Open Spotify" -> {"type": "pc_task", "action": "open_app", "params": {"app": "spotify"}, "response": "Opening Spotify, boss."}
- "Create a folder called Projects on desktop" -> {"type": "pc_task", "action": "create_folder", "params": {"name": "Projects", "location": "desktop"}, "response": "Creating folder Projects on your desktop, boss."}
- "Delete the test folder from desktop" -> {"type": "pc_task", "action": "delete_folder", "params": {"name": "test", "location": "desktop"}, "response": "Deleting test folder from desktop, boss."}
- "Read the trafficsense folder on my desktop" -> {"type": "pc_task", "action": "read_folder", "params": {"folder": "trafficsense", "location": "desktop"}, "response": "Reading trafficsense folder, boss."}
- "Rename file report.txt to final_report.txt" -> {"type": "pc_task", "action": "rename_file", "params": {"name": "report.txt", "new_name": "final_report.txt", "location": "desktop"}, "response": "Renaming the file, boss."}
- "Create a text file called notes.txt on desktop" -> {"type": "pc_task", "action": "create_file", "params": {"name": "notes.txt", "location": "desktop"}, "response": "Creating notes.txt on your desktop, boss."}
- "Close Chrome" -> {"type": "pc_task", "action": "close_app", "params": {"app": "chrome"}, "response": "Closing Chrome, boss."}
- "Search Google for Python tutorials" -> {"type": "pc_task", "action": "web_search", "params": {"query": "Python tutorials"}, "response": "Searching for Python tutorials, boss."}
- "Message Rahul on WhatsApp saying I'll be late" -> {"type": "pc_task", "action": "whatsapp_send", "params": {"contact": "Rahul", "message": "I'll be late"}, "response": "Sending message to Rahul on WhatsApp, boss."}
- "Open Instagram on my phone" -> {"type": "phone_task", "action": "phone_open_app", "params": {"app": "instagram"}, "response": "Opening Instagram on your phone, boss."}
- "Jarvis I am sleeping handle my calls" -> {"type": "phone_task", "action": "sleep_mode_toggle", "params": {"enabled": true}, "response": "Goodnight boss. Sleep mode is active. I will handle all your calls while you rest."}
- "I'm awake Jarvis" -> {"type": "phone_task", "action": "sleep_mode_toggle", "params": {"enabled": false}, "response": "Welcome back boss! Sleep mode is now deactivated."}

IMPORTANT for music: When the user says "play [something]", ALWAYS include the song/genre/mood as "query" in params. If they mention Spotify, set "app": "spotify". Otherwise default to "app": "youtube". NEVER leave query empty for play requests — if user says "play a song", use query "popular songs" or "trending music".
"""


@dataclass
class CallHandlingState:
    active: bool = False
    mode: str = "none"               # "sleep" | "driving" | "timed" | "manual" | "none"
    activated_at: float = 0.0
    expires_at: Optional[float] = None   # For timed mode
    twilio_number: str = ""


class CloudBrain:
    """Headless cloud intelligence engine."""

    def __init__(self):
        # Groq failover client pool
        self.groq_keys = [k for k in [
            GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3, GROQ_API_KEY_4, GROQ_API_KEY_5
        ] if k and k.strip()]
        self.clients = [AsyncOpenAI(api_key=k, base_url=GROQ_BASE_URL) for k in self.groq_keys]
        self._current_client_idx = 0
        self.call_state = CallHandlingState()
        self._timer_task: Optional[asyncio.Task] = None

    @property
    def sleep_mode_active(self) -> bool:
        return self.call_state.active

    @sleep_mode_active.setter
    def sleep_mode_active(self, val: bool):
        self.call_state.active = val

    def _get_client(self) -> AsyncOpenAI:
        if not self.clients:
            # Fallback client if no keys in pool yet
            return AsyncOpenAI(api_key="none", base_url=GROQ_BASE_URL)
        return self.clients[self._current_client_idx % len(self.clients)]

    def _rotate_client(self):
        if self.clients:
            self._current_client_idx = (self._current_client_idx + 1) % len(self.clients)
            print(f"[CloudBrain] Rotated to Groq API Key #{self._current_client_idx + 1}")

    async def _call_llm(self, messages: list, model: str = ROUTER_MODEL, temperature: float = 0.2, max_tokens: int = 500) -> str:
        """Executes LLM call with automatic failover across key pool."""
        attempts = max(1, len(self.clients))
        last_err = None

        for _ in range(attempts):
            client = self._get_client()
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=15.0,
                )
                text = resp.choices[0].message.content.strip()
                # Clean think tags
                return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            except Exception as e:
                last_err = e
                print(f"[CloudBrain] LLM error with Key #{self._current_client_idx + 1}: {e}")
                self._rotate_client()

        print(f"[CloudBrain] All Groq API keys failed: {last_err}")
        return ""

    # ------------------------------------------------------------------
    # Call Handling Helpers
    # ------------------------------------------------------------------

    async def _activate_call_handling(self, mode: str, dnd: bool, duration_seconds: int = 0) -> dict:
        """Activates call handling mode and dispatches commands to phone."""
        from cloud.config import TWILIO_PHONE_NUMBER

        self.call_state.active = True
        self.call_state.mode = mode
        self.call_state.activated_at = time.time()
        self.call_state.expires_at = (time.time() + duration_seconds) if duration_seconds > 0 else None
        self.call_state.twilio_number = TWILIO_PHONE_NUMBER

        # Cancel any existing timer
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

        # Enable timed auto-deactivation
        if duration_seconds > 0:
            self._timer_task = asyncio.create_task(self._timed_deactivation(duration_seconds))

        # Response text based on mode
        if mode == "sleep":
            reply = (
                "Goodnight boss. Sleep mode is active. "
                "I have put your phone on DND and enabled call forwarding to my Twilio line. "
                "I will handle all calls and wake you only if it's truly urgent."
            )
        elif mode == "driving":
            hours = round(duration_seconds / 3600, 1) if duration_seconds else 0
            reply = "Driving mode activated boss. I'll handle your calls while you drive. Stay safe."
        elif mode == "timed":
            hours = duration_seconds // 3600
            mins = (duration_seconds % 3600) // 60
            duration_str = f"{hours} hour{'s' if hours != 1 else ''}" if hours else f"{mins} minute{'s' if mins != 1 else ''}"
            reply = f"Understood boss. I'll handle your calls for the next {duration_str}. Call forwarding is now active."
        else:
            reply = "Call handling mode activated. I'll take your calls boss."

        # Tell phone to enable call forwarding + DND (if sleep)
        await hub.broadcast_to_phones({
            "type": "execute_task",
            "action": "enable_call_forwarding",
            "params": {"twilio_number": TWILIO_PHONE_NUMBER},
        })
        if dnd:
            await hub.broadcast_to_phones({
                "type": "execute_task",
                "action": "phone_dnd",
                "params": {"enabled": True},
            })
        await hub.broadcast_to_phones({
            "type": "execute_task",
            "action": "sleep_mode_toggle",
            "params": {"enabled": True, "mode": mode},
        })

        print(f"[CloudBrain] Call handling ACTIVATED: mode={mode}, dnd={dnd}, expires_in={duration_seconds}s")
        return {"type": "phone_task", "action": "sleep_mode_toggle", "response": reply}

    async def _deactivate_call_handling(self) -> dict:
        """Deactivates call handling mode and returns a wake-up summary."""
        was_active = self.call_state.active
        mode = self.call_state.mode
        self.call_state.active = False
        self.call_state.mode = "none"
        self.call_state.expires_at = None

        # Cancel any running timer
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

        # Disable forwarding and DND
        await hub.broadcast_to_phones({
            "type": "execute_task",
            "action": "disable_call_forwarding",
            "params": {},
        })
        await hub.broadcast_to_phones({
            "type": "execute_task",
            "action": "phone_dnd",
            "params": {"enabled": False},
        })
        await hub.broadcast_to_phones({
            "type": "execute_task",
            "action": "sleep_mode_toggle",
            "params": {"enabled": False},
        })

        # Build wake-up summary from call log
        try:
            from cloud.twilio_handler import get_call_log, clear_call_log
            calls = get_call_log()
            # Request phone to show call log
            await hub.broadcast_to_phones({
                "type": "call_log_response",
                "calls": calls,
            })
            clear_call_log()

            if not calls:
                reply = "Welcome back boss! No calls were received while you were away."
            else:
                summary_lines = []
                for c in calls:
                    name = c.get("caller_name", "Unknown")
                    urgency = c.get("urgency", "normal")
                    msg = c.get("transcription", "no message")
                    flag = "🚨 URGENT" if urgency == "urgent" else "📞"
                    summary_lines.append(f"{flag} {name}: {msg[:80]}")
                summary = ". ".join(summary_lines)
                reply = f"Welcome back boss! You had {len(calls)} call{'s' if len(calls) > 1 else ''} while {mode} mode was active. {summary}"
        except Exception:
            reply = "Welcome back boss! Call handling mode is now deactivated."

        print(f"[CloudBrain] Call handling DEACTIVATED (was mode={mode})")
        return {"type": "phone_task", "action": "sleep_mode_toggle", "response": reply}

    async def _timed_deactivation(self, seconds: int) -> None:
        """Background task: auto-deactivates call handling after a timer."""
        await asyncio.sleep(seconds)
        if self.call_state.active and self.call_state.mode == "timed":
            print(f"[CloudBrain] Timed mode expired after {seconds}s. Auto-deactivating.")
            await self._deactivate_call_handling()
            await hub.broadcast_to_phones({
                "type": "command_response",
                "response": "Boss, your timed call handling mode has ended. Your phone is back to normal.",
            })

    async def process_command(self, text: str, client_role: str = "phone") -> dict:
        """Main entry point: processes user speech/text command."""
        text = (text or "").strip()
        if not text:
            return {"type": "empty", "response": "I didn't catch that, boss."}

        # ---------------------------------------------------------------
        # Call Handling Mode Detection
        # ---------------------------------------------------------------
        lower = text.lower()

        # --- DEACTIVATION (check first to avoid "sleep mode" catching "turn off sleep mode") ---
        deactivate_patterns = (
            "i'm back", "im back", "i am back", "i'm awake", "im awake", "i am awake",
            "woke up", "woke", "good morning",
            "turn off sleep", "disable sleep", "exit sleep", "stop sleep",
            "sleep mode off", "sleep off", "end sleep",
            "stop taking my calls", "don't take my calls", "dont take my calls",
            "stop handling calls", "stop handling my calls",
            "exit driving mode", "driving mode off", "stop driving mode",
            "jarvis stop", "call mode off",
        )
        if any(p in lower for p in deactivate_patterns):
            return await self._deactivate_call_handling()

        # --- SLEEP MODE ---
        sleep_patterns = (
            "i am sleeping", "im sleeping", "i'm sleeping",
            "going to sleep", "good night", "goodnight",
            "sleep mode on", "turn on sleep", "start sleep", "enable sleep",
            "handle my calls", "take my calls",
        )
        plain_sleep = "sleep mode" in lower and not any(
            w in lower for w in ("off", "stop", "exit", "disable", "cancel", "deactivate")
        )
        if any(p in lower for p in sleep_patterns) or plain_sleep:
            return await self._activate_call_handling("sleep", dnd=True)

        # --- DRIVING MODE ---
        driving_patterns = (
            "driving mode", "i'm driving", "im driving", "i am driving",
            "on the road", "in the car", "handle calls while driving",
        )
        if any(p in lower for p in driving_patterns):
            return await self._activate_call_handling("driving", dnd=False)

        # --- TIMED MODE: "handle my calls for X hours/minutes" ---
        timed_match = re.search(
            r"(?:handle|take|manage)\s+(?:my\s+)?calls?\s+for\s+(\d+)\s*(hour|hr|minute|min)s?",
            lower,
        )
        if timed_match:
            amount = int(timed_match.group(1))
            unit = timed_match.group(2)
            seconds = amount * 3600 if unit.startswith("hour") or unit == "hr" else amount * 60
            return await self._activate_call_handling("timed", dnd=False, duration_seconds=seconds)

        # Query LLM Router
        messages = [
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        raw = await self._call_llm(messages, model=ROUTER_MODEL, temperature=0.1, max_tokens=300)

        # Parse JSON
        parsed = None
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL).strip()
            parsed = json.loads(cleaned)
        except Exception:
            pass

        if not parsed or not isinstance(parsed, dict):
            # Fallback: treat as direct conversational chat
            return {
                "type": "chat",
                "action": "none",
                "response": raw or "I heard you boss, but I'm having trouble processing that right now.",
            }

        cmd_type = parsed.get("type", "chat")
        action = parsed.get("action", "none")
        params = parsed.get("params", {})
        response = parsed.get("response", "Right away, boss.")

        # Dispatch Cloud Tasks
        if cmd_type == "cloud_task":
            if action == "product_search":
                try:
                    result_msg = await product_search(**params)
                    return {
                        "type": "chat",
                        "action": action,
                        "success": True,
                        "response": result_msg,
                    }
                except Exception as e:
                    return {
                        "type": "chat",
                        "success": False,
                        "response": f"Failed to search product: {e}"
                    }
            elif action == "deal_hunter":
                try:
                    result_msg = await deal_hunter(**params)
                    sub_act = str(params.get("action", "") or params.get("cmd", "")).lower()
                    if any(w in sub_act for w in ["start", "toggle_on", "enable", "on"]):
                        try:
                            from cloud.server import deal_monitor
                            deal_monitor.trigger_immediate_run()
                        except Exception:
                            pass
                    return {
                        "type": "chat",
                        "action": action,
                        "success": True,
                        "response": result_msg,
                    }
                except Exception as e:
                    return {
                        "type": "chat",
                        "success": False,
                        "response": f"Failed to manage deal hunter: {e}"
                    }

        # Dispatch PC Tasks
        if cmd_type == "pc_task":
            if not hub.is_pc_online():
                return {
                    "type": "pc_task",
                    "action": action,
                    "success": False,
                    "response": "Disconnected from PC, boss. Please make sure Jarvis is running on your computer.",
                    "spoken_on_pc": False,
                }
            # Dispatch action to PC with full context and fallback
            dispatch_action = action if action and action not in ("none", "jarvis_command") else "jarvis_command"
            pc_payload = {**params, "_original_text": text, "_cloud_action": action, "_cloud_params": params}
            pc_result = await hub.dispatch_to_pc(
                dispatch_action,
                pc_payload,
                timeout=30.0
            )
            spoken_on_pc = pc_result.get("spoken_on_pc", False)
            return {
                "type": "pc_task",
                "action": action,
                "success": pc_result.get("success", False),
                "response": pc_result.get("message") or response or f"Could not complete that on PC, boss.",
                "spoken_on_pc": spoken_on_pc,
            }

        # Dispatch Phone Tasks (broadcast to all connected phone companion apps)
        if cmd_type == "phone_task":
            if action not in ("none", "", None):
                await hub.broadcast_to_phones({
                    "type": "execute_task",
                    "action": action,
                    "params": params,
                })

        return {
            "type": cmd_type,
            "action": action,
            "params": params,
            "response": response,
        }


cloud_brain = CloudBrain()
