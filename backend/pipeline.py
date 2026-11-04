# FILE: pipeline.py
# Orchestrates microphone chunks through wake word, VAD, transcription, and UI messages.
import asyncio
import json
import os
import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from audio.amplitude import calc_amplitude
from audio.mic_stream import MicStream
from audio.transcriber import Transcriber
from audio.vad import VoiceActivityDetector
from audio.wake_word import WakeWord
from config import (
    AMPLITUDE_SEND_INTERVAL, COMMAND_IDLE_DELAY, LISTEN_TIMEOUT,
    SILENCE_TIMEOUT, SILENCE_TIMEOUT_EXTENDED, CONVERSATION_TIMEOUT,
    ULTRON_WAKE_KEYWORD, JARVIS_WAKE_KEYWORD,
    ULTRON_WAKE_KEYWORDS, JARVIS_WAKE_KEYWORDS,
    ULTRON_TAKEOVER_PHRASES, JARVIS_RETURN_PHRASES,
    ULTRON_TAKEOVER_RESPONSE, ULTRON_RETURN_RESPONSE, JARVIS_RETURN_RESPONSE,
    ULTRON_GATE_THRESHOLD, ULTRON_GATE_MAX, ULTRON_GATE_COOLDOWN,
    PASSWORD_MAX_ATTEMPTS,
    GESTURE_ENABLED, GESTURE_FPS, GESTURE_CAMERA_INDEX,
    GESTURE_MIN_DETECTION_CONFIDENCE, GESTURE_MIN_TRACKING_CONFIDENCE,
)
import re
from logger import get_logger
from server.messages import amplitude_msg, caption_msg, state_msg, persona_msg, user_speech_msg, jarvis_speech_msg, dodge_msg, hand_gesture_msg, approval_request_msg, approval_result_msg, self_audit_msg, permission_request_msg
from tts.speaker import Speaker
from llm.brain import Brain
from llm.tools import TOOL_HANDLERS
from call_agent.call_manager import CallManager
from tools.coding_agent import CodingAgent
from tools.routines import set_pipeline as set_routines_pipeline
from tools.scheduler import set_pipeline as set_scheduler_pipeline
from tools.window_manager import set_pipeline as set_window_manager_pipeline
from tools.context import get_context_summary
try:
    from vision.hand_tracker import HandTracker
except ImportError:
    HandTracker = None

_log = get_logger(__name__)
print = _log.info

_OPEN_INTENT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "shared",
    "open_intent.json",
)
with open(_OPEN_INTENT_PATH, "r", encoding="utf-8") as _open_intent_file:
    OPEN_INTENT_VERBS = tuple(json.load(_open_intent_file))

INLINE_TOOLS = frozenset({
    "set_timer", "routines_tool", "scheduler_tool", "gesture_control",
    "get_datetime", "clipboard", "clipboard_history", "persistent_memory",
    "volume_control", "get_battery_status",
})

# Direct tool results that should be spoken instead of replaced by router prose.
# Kept centrally so voice and typed commands stay behaviorally identical.
PASSTHROUGH_TOOLS = frozenset({
    "get_datetime", "get_weather", "clipboard", "brightness_control",
    "bluetooth_control", "wifi_control", "performance_control", "datetime_control",
    "vpn_control", "media_control", "get_battery_status", "volume_control",
    "execute_code", "web_search", "gesture_control", "generate_image", "system_power",
    "video_tool", "persistent_memory", "doc_reader", "code_reviewer", "youtube_intel",
    "system_health", "clipboard_history", "routines_tool", "scheduler_tool",
    "music_control", "security_settings", "run_shell_command", "self_code", "self_audit",
    "self_fix", "computer_use", "screenshot",
})

ERROR_PREFIXES = (
    "an error occurred",
    "error:",
    "failed to",
    "could not ",
    "cannot ",
    "access is denied",
    "permission denied",
    "execution blocked:",
)

def format_tts_response(tool_res: str | None) -> str:
    """Ensures user receives clean concise speech and never raw technical errors."""
    if not tool_res:
        return "An error occurred, boss."
    res_lower = str(tool_res).strip().lower()
    if res_lower.startswith(ERROR_PREFIXES):
        return "An error occurred, boss."
    return tool_res


def shutdown_password_matches(digits: str) -> bool:
    from security.credentials import verify_shutdown_password
    return verify_shutdown_password(digits)

def _permission_decision(tool_name: str, params: dict, source: str, grants: list):
    """Runs the permission engine. Returns (decision, reason)."""
    from security.permissions import check_permission, PermissionResult
    decision = check_permission(tool_name, params, source=source, grants=grants)
    return decision.result, decision.reason


def is_open_action(text: str = "", result: dict | None = None) -> bool:
    """Detects whether user text or LLM action is meant to launch/open an application, browser, or window."""
    txt = (text or "").lower()
    if any(k in txt for k in ["gesture", "hand tracking"]):
        return False
    if result and result.get("tool") == "gesture_control":
        return False
    if any(re.search(r'\b' + re.escape(v) + r'\b', txt) for v in OPEN_INTENT_VERBS):
        return True
    if result:
        tool = result.get("tool")
        if tool in ("whatsapp_open",):
            return True
        if tool == "vpn_control" and result.get("params", {}).get("action") == "open":
            return True
        if tool == "bluetooth_control" and result.get("params", {}).get("action") == "open_settings":
            return True
        if tool == "execute_code":
            code = str(result.get("params", {}).get("code", "")).lower()
            task = str(result.get("task_description", "")).lower()
            resp = str(result.get("response", "")).lower()
            if any(k in code for k in ["startfile", "popen", "webbrowser", "start "]):
                return True
            if any(k in task for k in ["open", "launch", "start", "browser", "youtube", "app", "window"]):
                return True
            if any(k in resp for k in ["opening", "launching", "starting"]):
                return True
    return False

class AudioPipeline:
    def __init__(self, server, loop):
        self.server, self.loop = server, loop
        self.wake, self.vad, self.stt = WakeWord(), VoiceActivityDetector(), Transcriber()
        self.mic = MicStream(self.on_audio_thread)
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.stt_pool = ThreadPoolExecutor(max_workers=1)
        self.state, self.last_amplitude = "idle", 0.0
        self.tts = Speaker(server, loop)
        self.brain = Brain()
        self.speaking = False
        self.mic_muted = False
        self.listen_start = 0.0
        self.pending_action = None  # Holds actions requiring verbal confirmation
        self.pending_approval = None  # Proposed self-fix; never applied without an explicit yes.
        self.persona = "jarvis"
        self.detected_lang = "en"
        # Energy gate for Ultron wake-phrase detection (no pretrained model exists)
        self.gate_buffer = []
        self.gate_active = False
        self.gate_silence = 0.0
        self.gate_last_check = 0.0
        # Password gate for shutdown/restart: {"tool","params","attempts","purpose"} or None
        self.pending_password = None
        # Session-level permission grants (future UI); all "once" by default
        self.grants = []
        self.call_agent = CallManager(self)
        self.hand_tracker = None
        self.coding_agent = CodingAgent(self.brain, self)
        self.dev_mode = getattr(self.brain, "dev_mode", False)
        self.background_tasks = {}
        self.conversation_start = 0.0
        set_routines_pipeline(self)
        set_scheduler_pipeline(self)
        set_window_manager_pipeline(self)
        if GESTURE_ENABLED and HandTracker:
            self.hand_tracker = HandTracker(
                on_gesture_callback=self._on_hand_gesture,
                camera_index=GESTURE_CAMERA_INDEX,
                fps=GESTURE_FPS,
                min_detection_confidence=GESTURE_MIN_DETECTION_CONFIDENCE,
                min_tracking_confidence=GESTURE_MIN_TRACKING_CONFIDENCE
            )

    def _on_hand_gesture(self, gesture_data: dict):
        self.send(hand_gesture_msg(gesture_data))

    def start_gesture_tracking(self):
        if self.hand_tracker and not self.hand_tracker.is_running():
            self.hand_tracker.start()

    def stop_gesture_tracking(self):
        if self.hand_tracker and self.hand_tracker.is_running():
            self.hand_tracker.stop()

    def set_persona(self, persona: str) -> None:
        self.persona = persona
        self.tts.set_persona(persona)
        self.brain.set_persona(persona)
        self.send(persona_msg(persona))
        print(f"[Persona] Switched to {persona}")

    def _check_persona_switch(self, text: str) -> bool:
        """Checks transcribed idle speech for persona takeover/return phrases.
        Returns True if a switch was handled."""
        lower = text.lower()
        has_ultron = ULTRON_WAKE_KEYWORD in lower
        has_jarvis = JARVIS_WAKE_KEYWORD in lower
        if self.persona == "jarvis" and has_ultron and any(p in lower for p in ULTRON_TAKEOVER_PHRASES):
            print("[Persona] Ultron takeover detected")
            self.set_persona("ultron")
            asyncio.create_task(self.respond_and_idle(ULTRON_TAKEOVER_RESPONSE))
            return True
        if self.persona == "ultron" and has_jarvis and any(p in lower for p in JARVIS_RETURN_PHRASES):
            print("[Persona] Jarvis return detected")
            self.set_persona("jarvis")
            asyncio.create_task(self.respond_and_idle(JARVIS_RETURN_RESPONSE))
            return True
        # In ultron mode, "hey jarvis" also returns control (wake word works there)
        if self.persona == "ultron" and has_jarvis and not has_ultron:
            print("[Persona] Jarvis wake word in ultron mode — returning control")
            self.set_persona("jarvis")
            asyncio.create_task(self.respond_and_idle(JARVIS_RETURN_RESPONSE))
            return True
        return False

    def start(self):
        from tools.timer import set_pipeline as set_timer_pipeline
        set_timer_pipeline(self)
        from tools.whatsapp import set_pipeline as set_whatsapp_pipeline
        set_whatsapp_pipeline(self)
        from tools.gesture_tool import set_pipeline as set_gesture_pipeline
        set_gesture_pipeline(self)
        self.mic.start()

    def stop(self):
        self.stop_gesture_tracking()
        self.mic.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.stt_pool.shutdown(wait=False, cancel_futures=True)

    async def shutdown_jarvis(self):
        """Cleanly terminates Jarvis: closes Electron UI, finishes speaking, closes terminal, and exits."""
        print("[Pipeline] Initiating clean Jarvis self-termination...")
        from server.messages import app_exit_msg
        try:
            self.send(app_exit_msg())
        except Exception:
            pass

        try:
            self.stop()
        except Exception:
            pass

        # Give TTS audio time to complete playback (2.2 seconds)
        await asyncio.sleep(2.2)

        # Close terminal window and terminate parent shell
        try:
            from tools.system_power import close_current_terminal
            close_current_terminal()
        except Exception as e:
            print(f"[Pipeline] Error closing terminal: {e}")

        try:
            await self.server.stop()
        except Exception:
            pass

        import os
        os._exit(0)

    def on_audio_thread(self, chunk):
        self.loop.call_soon_threadsafe(self.on_audio, chunk)

    def send(self, message):
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.server.send(message))
            )

    async def _run_tool(self, tool_name: str, handler, params: dict, source: str = "runtime"):
        # Blocking handlers run off the asyncio event loop. A small inline set
        # is reserved for handlers that intentionally schedule asyncio work.
        started = time.monotonic()
        try:
            if tool_name not in INLINE_TOOLS:
                result = await self.loop.run_in_executor(self.pool, handler, params)
            else:
                result = handler(params)
            return result
        finally:
            try:
                from security.audit_log import log_action
                log_action({"source": source, "tool": tool_name, "params": params,
                            "permission_result": "EXECUTED", "result_summary": "completed",
                            "duration_ms": round((time.monotonic() - started) * 1000)})
            except Exception:
                pass

    def _track_background_task(self, task, name: str):
        """Keep fire-and-forget work observable instead of losing task exceptions."""
        self.background_tasks[name] = task

        def _finished(done_task):
            if self.background_tasks.get(name) is done_task:
                self.background_tasks.pop(name, None)
            if done_task.cancelled():
                return
            error = done_task.exception()
            if error:
                print(f"[Pipeline] Background task '{name}' failed: {error}")

        task.add_done_callback(_finished)
        return task

    async def _start_self_audit(self, scope: str, lang: str = "en"):
        """Run the synchronous audit off-loop and announce its concise result."""
        from self_dev.auditor import run_audit

        future = self.loop.run_in_executor(self.pool, run_audit, scope or "changed")
        task = asyncio.ensure_future(future)

        def _report(done_task):
            if done_task.cancelled():
                return
            try:
                findings = done_task.result()
                self.send(self_audit_msg(findings))
                counts = {level: sum(f.get("severity") == level for f in findings) for level in ("high", "medium")}
                titles = ", ".join(str(f.get("title", "issue")) for f in findings[:3])
                message = f"I found {len(findings)} issues, boss. {counts['high']} high, {counts['medium']} medium."
                if titles:
                    message += f" The top ones are: {titles}."
            except Exception as exc:
                print(f"[Audit] Failed: {exc}")
                message = "My audit could not complete, boss."
            asyncio.create_task(self.respond_and_idle(message, lang=lang))

        task.add_done_callback(_report)
        self._track_background_task(task, "audit")
        await self.respond_and_idle("Auditing my code now, boss.", lang=lang)

    async def _consume_pending_approval(self, text: str, lang: str = "en") -> bool:
        """Handle a single-use, expiring self-fix proposal before normal dispatch."""
        proposal = self.pending_approval
        if not proposal:
            return False
        if time.monotonic() > proposal["expires_at"]:
            self.pending_approval = None
            await self.respond_and_idle("That proposed fix expired without changes, boss.", lang=lang)
            return True
        lower = text.lower().strip()
        if "show me" in lower:
            self.send(approval_request_msg(proposal["id"], [{key: proposal[key] for key in ("path", "diff", "added", "removed")}]))
            print(f"[SelfFix] Proposed diff for {proposal['path']}:\n{proposal['diff']}")
            await self.respond("I have shown the proposed change. Approve it, boss?", lang=lang)
            return True
        if any(word in lower for word in ("yes", "confirm", "approve", "do it", "proceed", "go ahead", "okay", "ok")):
            self.pending_approval = None
            self.send(approval_result_msg(proposal["id"], True))
            from self_dev.patcher import apply_patch, run_tests_and_revert_if_broken
            ok, message = await self.loop.run_in_executor(self.pool, apply_patch, proposal)
            if ok:
                ok, message = await self.loop.run_in_executor(self.pool, run_tests_and_revert_if_broken, proposal)
            if ok:
                message += " Restart me to load that change, boss."
            await self.respond_and_idle(message, lang=lang)
            return True
        if any(word in lower for word in ("no", "reject", "cancel", "stop", "abort", "don't", "dont")):
            self.pending_approval = None
            self.send(approval_result_msg(proposal["id"], False))
            await self.respond_and_idle("Okay, I will not change anything, boss.", lang=lang)
            return True
        self.pending_approval = None
        return False

    async def handle_text_command(self, text: str, lang: str = "en"):
        """Compatibility entry point for chained text commands.

        All command sources ultimately use process_command, so chain steps receive
        the same confirmation, tool, and response behavior as voice commands.
        """
        return await self.process_command(text, lang=lang)

    def set_state(self, value):
        self.state = value
        self.send(state_msg(value))

    def _feed_persona_gate(self, chunk):
        """Accumulates loud speech while idle; when a burst ends, transcribes it
        and checks for persona switch phrases ('hey ultron take command' etc.)."""
        amp = calc_amplitude(chunk)
        now = time.monotonic()
        if amp > ULTRON_GATE_THRESHOLD:
            self.gate_active = True
            self.gate_silence = 0.0
            self.gate_buffer.append(chunk)
            if len(self.gate_buffer) > ULTRON_GATE_MAX:
                self.gate_buffer.pop(0)
        elif self.gate_active:
            self.gate_silence += len(chunk) / 16000.0
            self.gate_buffer.append(chunk)
            if len(self.gate_buffer) > ULTRON_GATE_MAX:
                self.gate_buffer.pop(0)
            if self.gate_silence >= 1.0:
                self.gate_active = False
                self.gate_silence = 0.0
                if not self.gate_buffer:
                    return
                duration = sum(len(c) for c in self.gate_buffer) / 16000.0
                if duration < 0.6:
                    self.gate_buffer = []
                    return
                audio = np.concatenate(self.gate_buffer)
                self.gate_buffer = []
                rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float32))))
                if rms < 0.015:
                    return
                if now - self.gate_last_check < ULTRON_GATE_COOLDOWN:
                    return
                self.gate_last_check = now
                asyncio.create_task(self._persona_gate_check(audio))

    def _check_password(self, text: str) -> bool:
        """Handles utterances while a password is awaited (shutdown or change flow).
        Returns True if the utterance was consumed (matched/cancelled/attempt counted)."""
        pending = self.pending_password
        lower = text.lower().strip()
        from utils.digits import spoken_to_digits
        digits = spoken_to_digits(lower)
        purpose = pending.get("purpose", "shutdown")

        if any(w in lower for w in ["no", "cancel", "stop", "abort", "nevermind", "never mind"]):
            self.pending_password = None
            asyncio.create_task(self.respond_and_idle("Cancelled, boss."))
            return True

        if purpose == "shutdown":
            return self._check_shutdown_password(pending, digits)
        if purpose == "change_verify":
            return self._check_change_verify(pending, digits)
        if purpose == "change_new":
            return self._check_change_new(pending, digits)
        if purpose == "change_confirm":
            return self._check_change_confirm(pending, digits)
        return False

    def _check_shutdown_password(self, pending, digits: str) -> bool:
        # Require an exact digit sequence; accepting a substring lets values such
        # as 11110 or 51111 bypass the intended password gate.
        if shutdown_password_matches(digits):
            self.pending_password = None
            pending["params"]["_password_ok"] = True
            asyncio.create_task(self._execute_password_confirmed(pending))
            return True
        pending["attempts"] += 1
        if pending["attempts"] >= PASSWORD_MAX_ATTEMPTS:
            self.pending_password = None
            asyncio.create_task(self.respond_and_idle("Too many failed attempts, boss. Shutdown cancelled."))
        else:
            asyncio.create_task(self.respond(f"Incorrect password, boss. {PASSWORD_MAX_ATTEMPTS - pending['attempts']} attempts remaining."))
        return True

    def _check_change_verify(self, pending, digits: str) -> bool:
        # Verify the CURRENT password before accepting a new one.
        if shutdown_password_matches(digits):
            pending["purpose"] = "change_new"
            pending["attempts"] = 0
            asyncio.create_task(self.respond("Say the new password, boss."))
            return True
        pending["attempts"] += 1
        if pending["attempts"] >= PASSWORD_MAX_ATTEMPTS:
            self.pending_password = None
            asyncio.create_task(self.respond_and_idle("Too many failed attempts, boss. Password change cancelled."))
        else:
            asyncio.create_task(self.respond(f"Incorrect password, boss. {PASSWORD_MAX_ATTEMPTS - pending['attempts']} attempts remaining."))
        return True

    def _check_change_new(self, pending, digits: str) -> bool:
        from security.credentials import validate_new_password
        ok, reason = validate_new_password(digits)
        if not ok:
            asyncio.create_task(self.respond(reason))
            return True
        pending["new_password"] = digits
        pending["purpose"] = "change_confirm"
        asyncio.create_task(self.respond("Say it again to confirm, boss."))
        return True

    def _check_change_confirm(self, pending, digits: str) -> bool:
        if digits == pending.get("new_password"):
            from security.credentials import set_shutdown_password
            ok, msg = set_shutdown_password(digits)
            self.pending_password = None
            asyncio.create_task(self.respond_and_idle(msg))
        else:
            pending["purpose"] = "change_new"
            pending.pop("new_password", None)
            asyncio.create_task(self.respond("That did not match, boss. Say the new password again."))
        return True

    async def _execute_password_confirmed(self, pending):
        tool_name = pending["tool"]
        params = dict(pending["params"])
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            await self.respond_and_idle("An error occurred, boss.")
            return
        try:
            tool_res = await self._run_tool(tool_name, handler, params)
            print(f"[Password] Executed: {tool_name} -> {tool_res}")
            await self.respond_and_idle(format_tts_response(tool_res))
        except Exception as e:
            print(f"[Password] Execution error ({tool_name}): {e}")
            await self.respond_and_idle("An error occurred, boss.")

    async def _persona_gate_check(self, audio):
        try:
            res = await self.loop.run_in_executor(self.stt_pool, self.stt.transcribe, audio)
            text = res[0] if isinstance(res, tuple) else res
            lang = res[1] if isinstance(res, tuple) and len(res) > 1 else "en"
            if not text:
                return
            print(f"[PersonaGate] Heard while idle: {text}")
            lower = text.lower().strip()

            # 1. Check Ultron wake words ("hey ultron" or "ultron")
            is_ultron_wake = any(re.search(r'\b' + re.escape(w) + r'\b', lower) for w in ULTRON_WAKE_KEYWORDS)
            is_ultron_takeover = is_ultron_wake or any(p in lower for p in ULTRON_TAKEOVER_PHRASES)

            if is_ultron_takeover:
                if self.persona != "ultron":
                    print("[Persona] Ultron takeover detected via wake word")
                    self.set_persona("ultron")
                cmd = re.sub(r'^(hey\s+ultron|hello\s+ultron|ultron|take\s+command|take\s+control|take\s+over|i\s+command\s+you)[\s,:]*', '', lower, flags=re.IGNORECASE).strip()
                if cmd:
                    print(f"[UltronWake] Immediate command: {cmd}")
                    self.set_state("thinking")
                    self.send(caption_msg("Processing..."))
                    await self.process_command(cmd, lang=lang, original_text=text)
                else:
                    print("[UltronWake] Ultron wake word detected — entering listening state")
                    self.listen_start = time.monotonic()
                    self.vad.reset()
                    self.set_state("listening")
                    self.send(caption_msg("Ultron listening..."))
                    await self.tts.speak(ULTRON_TAKEOVER_RESPONSE, lang="en")
                return

            # 2. Check Jarvis wake words ("hey jarvis" or "jarvis")
            is_jarvis_wake = any(re.search(r'\b' + re.escape(w) + r'\b', lower) for w in JARVIS_WAKE_KEYWORDS)
            is_jarvis_return = is_jarvis_wake or any(p in lower for p in JARVIS_RETURN_PHRASES)

            if is_jarvis_return:
                if self.persona == "ultron":
                    print("[Persona] Jarvis return detected via wake word")
                    self.set_persona("jarvis")
                cmd = re.sub(r'^(hey\s+jarvis|hello\s+jarvis|jarvis|come\s+back|stand\s+down|return)[\s,:]*', '', lower, flags=re.IGNORECASE).strip()
                if cmd:
                    print(f"[JarvisWake] Immediate command: {cmd}")
                    self.set_state("thinking")
                    self.send(caption_msg("Processing..."))
                    await self.process_command(cmd, lang=lang, original_text=text)
                else:
                    print("[JarvisWake] Jarvis wake word detected — entering listening state")
                    self.listen_start = time.monotonic()
                    self.vad.reset()
                    self.set_state("listening")
                    self.send(caption_msg("Listening..."))
                return
        except Exception as e:
            print(f"[PersonaGate] Error: {e}")

    def on_audio(self, chunk):
        if self.mic_muted:
            return
        now = time.monotonic()
        if now - self.last_amplitude >= AMPLITUDE_SEND_INTERVAL:
            self.last_amplitude = now
            self.send(amplitude_msg(calc_amplitude(chunk)))
        if self.state == "idle" and not self.speaking:
            self._feed_persona_gate(chunk)
            if self.wake.feed(chunk):
                print("Wake word detected (OpenWakeWord)")
                self.listen_start = time.monotonic()
                self.vad.reset()
                self.vad.set_silence_timeout(SILENCE_TIMEOUT_EXTENDED)
                self.set_state("listening")
                self.send(caption_msg("Listening..."))
        elif self.state == "listening":
            if self.call_agent and self.call_agent.is_active:
                # Keep alive while on live call — never time out to idle
                self.listen_start = time.monotonic()
            elif not self.vad.recording and time.monotonic() - self.listen_start > LISTEN_TIMEOUT:
                print("[Pipeline] Listen timeout — no speech detected, returning to idle")
                self.vad.reset()
                self.vad.set_silence_timeout(SILENCE_TIMEOUT)
                self.set_state("idle")
                return
            if self.vad.feed(chunk) == "done":
                audio = self.vad.get_audio()
                self.set_state("thinking")
                self.send(caption_msg("Processing..."))
                asyncio.create_task(self.transcribe(audio))
        elif self.state == "conversation":
            if not self.vad.recording and time.monotonic() - self.conversation_start > CONVERSATION_TIMEOUT:
                print("[Pipeline] Conversation timeout (10s) reached — returning to idle")
                self.vad.reset()
                self.vad.set_silence_timeout(SILENCE_TIMEOUT)
                self.set_state("idle")
                return
            if self.vad.feed(chunk) == "done":
                audio = self.vad.get_audio()
                self.set_state("thinking")
                self.send(caption_msg("Processing..."))
                asyncio.create_task(self.transcribe(audio))

    async def transcribe(self, audio):
        try:
            res = await self.loop.run_in_executor(self.stt_pool, self.stt.transcribe, audio)
            text, lang = res if isinstance(res, tuple) else (res, "en")
            self.detected_lang = lang

            if text is None:
                await self.respond_and_idle("I couldn't reach my transcription service, boss.", lang=lang)
                return

            if not text:
                if self.call_agent and self.call_agent.is_active:
                    self.set_state("listening")
                    return
                print("[Pipeline] No valid speech or noise filtered — returning to idle")
                self.vad.reset()
                self.set_state("idle")
                return

            # Check if user requested persona switch while listening
            if self._check_persona_switch(text):
                return

            # Strip leading wake words ("hey jarvis", "jarvis", "hey ultron", "ultron")
            cleaned_text = re.sub(r'^(hey\s+jarvis|hello\s+jarvis|jarvis|hey\s+ultron|hello\s+ultron|ultron)[\s,:]*', '', text, flags=re.IGNORECASE).strip()
            # Strip immediate trigger word ("now", "ab", "abhi") if user signaled instant execution
            cleaned_text = re.sub(r'[\s,]+(now|ab|abhi)$', '', cleaned_text, flags=re.IGNORECASE).strip()
            if not cleaned_text:
                if self.persona == "ultron":
                    await self.respond_and_idle("I am listening, boss.", lang="en")
                elif lang == "bho" or any(w in text.lower() for w in ["bhojpuri", "haal chaal", "kaise ba", "ki haal"]):
                    await self.respond_and_idle("सब ठीक बा बॉस! तू बतावा, कइसे मदद कर सकीं तोहार?", display_text="Sab theek ba boss! Tu batawa, kaise madad kar sakeni tohar?", lang="bho")
                else:
                    await self.respond_and_idle("At your service, boss.", lang=lang)
                return

            await self.process_command(cleaned_text, lang=lang, original_text=text)
        except Exception as e:
            print(f"Pipeline transcribe error: {e}")
            self.speaking = False
            self.vad.reset()
            self.set_state("idle")
            self.send(caption_msg("An error occurred, boss."))
            await self.tts.speak("An error occurred, boss.", lang=self.detected_lang)

    async def _think(self, text: str, lang: str = "en") -> dict:
        """Processes input via Cloud Jarvis on Azure with automatic local Brain fallback."""
        # Dev mode stays with local CodingAgent/local tools for full power
        if self.dev_mode:
            return await self.brain.think(text, lang=lang)

        from config import CLOUD_ENABLED, CLOUD_URL, CLOUD_TOKEN, CLOUD_TIMEOUT
        if CLOUD_ENABLED and CLOUD_URL:
            from security.transport import require_secure_gateway
            require_secure_gateway(CLOUD_URL)
            try:
                import httpx
                async with httpx.AsyncClient(timeout=CLOUD_TIMEOUT) as client:
                    resp = await client.post(
                        f"{CLOUD_URL}/api/chat",
                        json={
                            "message": text,
                            "token": CLOUD_TOKEN,
                            "role": "voice_client",
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        cmd_type = data.get("type", "chat")
                        action = data.get("action", "none")
                        params = data.get("params", {})
                        speech = data.get("response", "Right away, boss.")

                        # If chat, explanation, or general query
                        if cmd_type in ("chat", "phone_task") or action in ("none", "", None):
                            return {
                                "tool": None,
                                "response": speech,
                                "response_tts": speech,
                                "source": "cloud",
                            }
                        # If PC task
                        return {
                            "tool": action,
                            "params": params,
                            "response": speech,
                            "response_tts": speech,
                            "source": "cloud",
                            "_already_executed": True,
                        }
            except Exception as e:
                print(f"[Pipeline] Cloud Brain unreachable ({e}), using local Brain fallback.")

        # Fallback to local Brain
        return await self.brain.think(text, lang=lang)

    async def process_command(self, text: str, lang: str = "en", original_text: str = "", source: str = "voice"):
        try:
            disp_text = original_text or text
            print(f"[STT] Processing ({lang}): {text}")
            self.send(caption_msg(disp_text))
            self.send(user_speech_msg(disp_text))
            if is_open_action(text):
                self.send(dodge_msg("bottom-right"))

            # 0. If CallAgent is active, handle live call dialogue directly
            if self.call_agent and self.call_agent.is_active:
                await self.call_agent.on_pickup_or_speech(text, lang=lang)
                return

            # 0.1 Password gate takes highest priority when awaiting a shutdown password
            if self.pending_password:
                if self._check_password(text):
                    return

            if await self._consume_pending_approval(text, lang=lang):
                return

            # Check if user is confirming/cancelling pending dependency installs in CodingAgent
            if self.coding_agent and self.coding_agent.pending_installs is not None:
                lower = text.lower().strip()
                if any(w in lower for w in ["yes", "confirm", "sure", "do it", "proceed", "go ahead", "okay", "ok", "install", "install them", "yes install"]):
                    pkgs = self.coding_agent.pending_installs if isinstance(self.coding_agent.pending_installs, list) else []
                    self.coding_agent.pending_installs = True  # signal approval
                    print(f"[Confirmation] User approved installing {len(pkgs)} packages.")
                    await self.respond_and_idle(f"Installing {len(pkgs)} packages, boss.", lang=lang)
                    return
                elif any(w in lower for w in ["no", "cancel", "stop", "don't", "dont", "abort", "nevermind", "never mind", "skip", "skip it"]):
                    self.coding_agent.pending_installs = False  # signal decline
                    print("[Confirmation] User declined dependency installation.")
                    await self.respond_and_idle("Skipping package installation, boss.", lang=lang)
                    return
                else:
                    print("[Confirmation] Pending install — awaiting yes/no.")
                    return

            # Check if user is confirming/cancelling pending plan approval in CodingAgent
            if self.coding_agent and getattr(self.coding_agent, "pending_plan_approval", None) is True:
                lower = text.lower().strip()
                if any(w in lower for w in ["yes", "confirm", "sure", "do it", "proceed", "go ahead", "okay", "ok", "start", "build it", "yes proceed"]):
                    self.coding_agent.pending_plan_approval = "approved"
                    print("[Confirmation] User approved coding plan.")
                    await self.respond_and_idle("Starting development, boss.", lang=lang)
                    return
                elif any(w in lower for w in ["no", "cancel", "stop", "don't", "dont", "abort", "nevermind", "never mind"]):
                    self.coding_agent.pending_plan_approval = "declined"
                    print("[Confirmation] User declined coding plan.")
                    await self.respond_and_idle("Plan cancelled, boss.", lang=lang)
                    return
                else:
                    print("[Confirmation] Pending coding plan approval — awaiting yes/no.")
                    return

            # Dev mode voice toggle
            lower_clean = text.lower().strip(" .!,")
            DEV_ON_PHRASES = ("development mode", "dev mode", "coding mode", "developer mode", "start dev mode", "enable dev mode")
            DEV_OFF_PHRASES = ("normal mode", "exit dev mode", "exit development mode", "stop dev mode", "disable dev mode", "standard mode")
            if any(p == lower_clean or lower_clean.startswith(p + " ") or lower_clean.endswith(" " + p) or f" {p} " in f" {lower_clean} " for p in DEV_ON_PHRASES):
                self.dev_mode = True
                self.brain.set_dev_mode(True)
                await self.respond_and_idle("Development mode activated, boss. Full coding capabilities online.", lang=lang)
                return
            if any(p == lower_clean or lower_clean.startswith(p + " ") or lower_clean.endswith(" " + p) or f" {p} " in f" {lower_clean} " for p in DEV_OFF_PHRASES):
                self.dev_mode = False
                self.brain.set_dev_mode(False)
                await self.respond_and_idle("Back to normal mode, boss. Fast and light.", lang=lang)
                return

            # 1. Check if user is confirming or cancelling a pending destructive action
            if self.pending_action:
                lower = text.lower().strip()
                if any(w in lower for w in ["yes", "confirm", "sure", "do it", "proceed", "go ahead", "delete", "okay", "ok", "empty"]):
                    # A multi-step plan awaiting approval: execute only on explicit yes.
                    if self.pending_action.get("kind") == "plan":
                        plan = self.pending_action
                        self.pending_action = None
                        print("[Planner] Plan approved by user. Executing steps.")
                        from llm.planner import Planner
                        planner = Planner(self.brain)
                        try:
                            result = await planner.execute_steps(plan["steps"], self, lang=plan.get("lang", lang))
                            await self.respond_and_idle(result, lang=lang)
                        except Exception as e:
                            print(f"[Planner] Plan execution error: {e}")
                            await self.respond_and_idle("An error occurred while running the plan, boss.", lang=lang)
                        return
                    # Shutdown/restart additionally require the spoken password
                    if self.pending_action["tool"] == "system_power" and self.pending_action["params"].get("action") in ("shutdown", "restart"):
                        pending = self.pending_action
                        self.pending_action = None
                        self.pending_password = {"tool": pending["tool"], "params": pending["params"], "attempts": 0, "purpose": "shutdown"}
                        print("[Password] Shutdown confirmation accepted — password required")
                        await self.respond("Password required to shut down the computer, boss. Please speak the code.", lang=lang)
                        return
                    pending = self.pending_action
                    self.pending_action = None
                    tool_name = pending["tool"]
                    params = pending["params"]
                    print(f"[Confirmation] Confirmed by user. Executing: {tool_name}")
                    handler = TOOL_HANDLERS.get(tool_name)
                    if handler:
                        try:
                            if is_open_action("", pending):
                                self.send(dodge_msg("bottom-right"))
                            tool_res = await self._run_tool(tool_name, handler, params, source=source)
                            print(f"[Confirmation] Executed: {tool_name} -> {tool_res}")
                            tts_text = format_tts_response(tool_res)
                            await self.respond_and_idle(tts_text, lang=lang)
                        except Exception as e:
                            print(f"[Confirmation] Execution error ({tool_name}): {e}")
                            await self.respond_and_idle("An error occurred, boss.", lang=lang)
                    else:
                        await self.respond_and_idle("An error occurred, boss.", lang=lang)
                    return
                elif any(w in lower for w in ["no", "cancel", "stop", "don't", "dont", "abort", "nevermind", "never mind"]):
                    self.pending_action = None
                    print("[Confirmation] Action cancelled by user.")
                    await self.respond_and_idle("Action cancelled, boss.", lang=lang)
                    return
                else:
                    print(f"[Confirmation] Discarding pending action for new instruction: {text}")
                    self.pending_action = None

            # Check for live task status query while coding agent is active
            lower_txt = text.lower().strip()
            status_triggers = ["what are you working on", "what are you doing", "what is the progress", "what's the progress", "kya kar rahe ho", "kya ho raha hai"]
            if any(trig in lower_txt for trig in status_triggers) and self.coding_agent and self.coding_agent.is_running:
                status_text = self.coding_agent.get_status()
                await self.respond_and_idle(status_text, lang=lang)
                return

            # 2. Process with LLM Brain (Cloud-first with local fallback)
            result = await self._think(text, lang=lang)
            display_resp = result.get("response", "Done, boss.")
            tts_resp = result.get("response_tts") or display_resp
            print(f"[Brain] Result: tool={result.get('tool')}, response={display_resp[:60]}")

            if result.get("tool"):
                # If tool was already executed on PC via CloudBridge roundtrip, do not execute twice
                if result.get("_already_executed"):
                    print(f"[Pipeline] Tool '{result.get('tool')}' was executed via CloudBridge; speaking response.")
                    await self.respond_and_idle(tts_resp, display_text=display_resp, lang=lang)
                    return

                tool_name = result["tool"]
                params = result.get("params", {})
                needs_confirm = bool(result.get("confirm", False))

                # Permission engine: enforce USER_INITIATED_ONLY and level gating.
                perm_result, perm_reason = _permission_decision(tool_name, params, source, self.grants)
                if perm_result == "DENY":
                    self.send(permission_request_msg(tool_name, perm_reason or "denied"))
                    print(f"[Permission] DENY {tool_name}: {perm_reason}")
                    try:
                        from security.audit_log import log_action
                        log_action({"source": source, "tool": tool_name, "params": params,
                                    "permission_result": "DENY", "result_summary": "denied"})
                    except Exception:
                        pass
                    await self.respond_and_idle(perm_reason or "That action is not permitted, boss.", lang=lang)
                    return
                if perm_result == "CONFIRM_REQUIRED":
                    needs_confirm = True

                # Background Multitasking: CodingAgent runs concurrently
                if tool_name == "coding_agent":
                    task_desc = params.get("task", text)
                    print(f"[Pipeline] Launching CodingAgent in background: {task_desc}")
                    bg_task = asyncio.create_task(self.coding_agent.execute_task(task_desc, lang=lang))
                    self._track_background_task(bg_task, "coding")
                    return

                # Chain command execution: sequentially execute each step
                if tool_name == "execute_chain":
                    steps = params.get("steps", [])
                    print(f"[Pipeline] Executing chain of {len(steps)} steps: {steps}")
                    for step in steps:
                        step_str = step.get("task", step) if isinstance(step, dict) else str(step)
                        await self.process_command(step_str, lang=lang, source="chain")
                        await asyncio.sleep(1.0)
                    return

                # Multi-step task planner
                if tool_name == "execute_plan":
                    from llm.planner import Planner
                    task = params.get("task", text)
                    planner = Planner(self.brain)
                    await planner.execute(task, self, lang=lang)
                    return

                if needs_confirm:
                    self.pending_action = {"tool": tool_name, "params": params}
                    question = tts_resp
                    if not question or not question.strip().endswith("?"):
                        question = "Are you sure you want to proceed with this action, boss?"
                    print(f"[Confirmation] Action requires confirmation. Asking user: '{question}'")
                    await self.respond(question, display_text=display_resp, lang=lang)
                    return

                handler = TOOL_HANDLERS.get(tool_name)
                if handler:
                    try:
                        if is_open_action(text, result):
                            self.send(dodge_msg("bottom-right"))
                        tool_res = await self._run_tool(tool_name, handler, params, source=source)
                        print(f"Tool executed: {tool_name} -> {tool_res}")
                        tts_text = format_tts_response(tool_res)
                        if tts_text == "An error occurred, boss.":
                            await self.respond_and_idle("An error occurred, boss.", lang=lang)
                            return
                        if tool_name == "self_audit" and tool_res == "AUDIT_REQUESTED":
                            await self._start_self_audit(str(params.get("scope", "changed")), lang=lang)
                            return
                        if tool_name == "self_fix" and isinstance(tool_res, dict):
                            if tool_res.get("error"):
                                await self.respond_and_idle(tool_res["error"], lang=lang)
                                return
                            tool_res["expires_at"] = time.monotonic() + 120
                            self.pending_approval = tool_res
                            total = int(tool_res.get("added", 0)) + int(tool_res.get("removed", 0))
                            await self.respond(f"I want to change {total} lines in {tool_res['path']}. Approve, boss?", lang=lang)
                            return
                        # Security settings: arm the password-change state machine
                        if tool_name == "security_settings" and tool_res == "PASSWORD_CHANGE_REQUESTED":
                            self.pending_password = {"tool": "security_settings", "params": params, "attempts": 0, "purpose": "change_verify"}
                            print("[Password] Password change requested — verifying current password")
                            await self.respond("Say your current password, boss.", lang=lang)
                            return
                        if tool_name == "security_settings" and tool_res == "REVOKE_ALL_GRANTS":
                            self.grants = []
                            await self.respond_and_idle("All permissions have been revoked, boss.", lang=lang)
                            return
                        if tool_name in PASSTHROUGH_TOOLS and tool_res:
                            if tool_name == "system_power" and params.get("action") in ("exit_jarvis", "close_jarvis", "close_terminal", "exit", "quit"):
                                await self.respond(tts_text, lang=lang)
                                await self.shutdown_jarvis()
                                return
                            await self.respond_and_idle(tts_text, lang=lang)
                            return
                    except Exception as e:
                        print(f"Tool execution error ({tool_name}): {e}")
                        await self.respond_and_idle("An error occurred, boss.", lang=lang)
                        return
                else:
                    self.send(caption_msg("[Tool not available]"))
                    await self.respond_and_idle("An error occurred, boss.", lang=lang)
                    return
                await self.respond_and_idle(tts_resp, display_text=display_resp, lang=lang)
            else:
                await self.respond(tts_resp, display_text=display_resp, lang=lang)
        except Exception as e:
            print(f"Pipeline error: {e}")
            self.speaking = False
            self.vad.reset()
            self.set_state("idle")
            self.send(caption_msg("An error occurred, boss."))
            await self.tts.speak("An error occurred, boss.", lang=self.detected_lang)

    async def respond(self, text, display_text=None, lang=None):
        disp = display_text or text
        spoken_lang = lang or self.detected_lang
        self.speaking = True
        self.set_state("speaking")
        self.send(caption_msg(disp))
        self.send(jarvis_speech_msg(disp))
        await self.tts.speak(text, lang=spoken_lang)
        self.speaking = False
        self.vad.reset()
        self.listen_start = time.monotonic()
        self.set_state("listening")
        self.send(caption_msg("Listening..."))

    async def respond_and_idle(self, text, display_text=None, lang=None):
        disp = display_text or text
        spoken_lang = lang or self.detected_lang
        self.speaking = True
        self.set_state("speaking")
        self.send(caption_msg(disp))
        self.send(jarvis_speech_msg(disp))
        await self.tts.speak(text, lang=spoken_lang)
        self.speaking = False
        self.vad.reset()
        self.conversation_start = time.monotonic()
        self.vad.set_silence_timeout(SILENCE_TIMEOUT_EXTENDED)
        self.set_state("conversation")
        self.send(caption_msg("Listening..."))

    async def handle_message(self, message):
        msg_type = message.get("type")
        if msg_type == "cancel":
            self.tts.stop()
            self.speaking = False
            self.pending_action = None
            self.pending_password = None
            self.pending_approval = None
            self.wake.reset(); self.vad.reset(); self.set_state("idle")
        elif msg_type == "mic-toggle":
            self.mic_muted = bool(message.get("value", False))
            # Muting silences both microphone input and TTS output.
            self.tts.set_muted(self.mic_muted)
            print(f"Microphone {'muted' if self.mic_muted else 'unmuted'}")
        elif msg_type == "gesture_control":
            action = message.get("value")
            if action == "start":
                self.start_gesture_tracking()
            elif action == "stop":
                self.stop_gesture_tracking()
        elif msg_type == "settings":
            key, value = message.get("key"), message.get("value")
            try:
                from user_profile import set as set_profile
                set_profile(key, value)
                self.send(caption_msg("Setting saved. Restart Jarvis to apply voice changes, boss."))
            except (KeyError, TypeError):
                self.send(caption_msg("That setting is not available, boss."))
        elif msg_type == "settings-get":
            from user_profile import all as profile_all
            from server.messages import settings_values_msg
            self.send(settings_values_msg(profile_all()))
        elif msg_type == "command":
            text = message.get("value", "")
            # The voice dispatcher owns typed commands too. All password gates,
            # approval gates, permission checks, chain/planner dispatch, and tool
            # handling run inside process_command via source="text".
            await self.process_command(text, lang="en", source="text")
