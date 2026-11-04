# FILE: whatsapp.py
# Sends WhatsApp messages using the native WhatsApp Desktop App (zero mouse coordinates).
import json
import os
import subprocess
import time
import asyncio
import threading
import urllib.parse
import pyautogui
import pyperclip
from config import WHATSAPP_CONTACT_CACHE_FILE, WHATSAPP_SEARCH_POLL_INTERVAL, WHATSAPP_SEARCH_MAX_WAIT
from user_profile import get as profile_get
from tools.window_manager import focus_and_maximize_window
from tools.app_readiness import wait_for_app, wait_for_app_interactive, is_process_running
from server.messages import dodge_msg, undodge_msg

pyautogui.FAILSAFE = bool(profile_get("pyautogui_failsafe", True))
_pipeline_ref = None

def _load_contact_cache() -> dict:
    """Loads cached WhatsApp contact name variations."""
    if os.path.exists(WHATSAPP_CONTACT_CACHE_FILE):
        try:
            with open(WHATSAPP_CONTACT_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WhatsApp Cache] Error loading: {e}")
    return {}

def _save_contact_cache(contact: str, matched_variation: str) -> None:
    """Persists a verified contact name match to the local cache."""
    try:
        os.makedirs(os.path.dirname(WHATSAPP_CONTACT_CACHE_FILE), exist_ok=True)
        cache = _load_contact_cache()
        cache[contact.strip().lower()] = matched_variation
        with open(WHATSAPP_CONTACT_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        print(f"[WhatsApp Cache] Cached contact: '{contact}' -> '{matched_variation}'")
    except Exception as e:
        print(f"[WhatsApp Cache] Error saving: {e}")

def set_pipeline(pipeline):
    global _pipeline_ref
    _pipeline_ref = pipeline

def _speak(text: str):
    """Speaks a message to the user via TTS safely from background threads."""
    if _pipeline_ref:
        _pipeline_ref.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(_pipeline_ref.respond_and_idle(text))
        )

def _dodge(position="top-left"):
    """Moves Jarvis window out of the way before clicking screen areas."""
    try:
        if _pipeline_ref:
            _pipeline_ref.send(dodge_msg(position))
            time.sleep(0.4)
    except Exception as e:
        print(f"[WhatsApp] _dodge notice: {e}")

def _undodge():
    """Restores Jarvis window back to its previous position."""
    try:
        if _pipeline_ref:
            _pipeline_ref.send(undodge_msg())
            time.sleep(0.2)
    except Exception as e:
        print(f"[WhatsApp] _undodge notice: {e}")

def whatsapp_message(params: dict) -> str:
    """Entry point called by the LLM tool dispatcher for WhatsApp messages."""
    contact = params.get("contact", "").strip()
    message = params.get("message", "").strip()
    phone = params.get("phone", "").strip()

    if not message:
        return "No message provided, boss."
    if not contact and not phone:
        return "No contact name or phone number provided, boss."

    target = contact or phone
    threading.Thread(target=_send_via_desktop_app, args=(contact, message, phone), daemon=True).start()
    return f"Sending a WhatsApp message to {target}, boss."


_last_called_contact = ""

def whatsapp_call(params: dict) -> str:
    """Entry point called by the LLM tool dispatcher for WhatsApp voice/audio calls."""
    global _last_called_contact
    contact = params.get("contact", "").strip()
    phone = params.get("phone", "").strip()
    call_type = params.get("call_type", "voice").strip().lower()
    talk_on_behalf = bool(params.get("talk_on_behalf", False))

    if not contact and not phone:
        return "No contact name or phone number provided, boss."

    target = contact or phone
    _last_called_contact = target
    call_label = "video call" if "video" in call_type else "voice call"
    threading.Thread(target=_call_via_desktop_app, args=(contact, phone, call_type, talk_on_behalf), daemon=True).start()
    if talk_on_behalf:
        return f"Calling {target} on WhatsApp and standing by to speak on your behalf, boss."
    return f"Starting a WhatsApp {call_label} with {target}, boss."


def whatsapp_video_call(params: dict) -> str:
    """Convenience alias for WhatsApp video calls."""
    params["call_type"] = "video"
    return whatsapp_call(params)


def whatsapp_take_call(params: dict = None) -> str:
    """Activates CallAgent on the active WhatsApp call to speak on User's behalf."""
    contact = (params or {}).get("contact", "").strip() or _last_called_contact or "the caller"
    if _pipeline_ref and hasattr(_pipeline_ref, "call_agent"):
        _pipeline_ref.call_agent.start_call(contact)
        return f"Taking over the call with {contact} to speak on your behalf, boss."
    return "Call agent is not available, boss."


def whatsapp_open(params: dict) -> str:
    """Entry point to open a WhatsApp chat with a contact without sending any message."""
    contact = params.get("contact", "").strip()
    phone = params.get("phone", "").strip()

    if not contact and not phone:
        return "No contact name or phone number provided, boss."

    target = contact or phone
    threading.Thread(target=_open_via_desktop_app, args=(contact, phone), daemon=True).start()
    return f"Opening WhatsApp chat with {target}, boss."


def _open_via_desktop_app(contact: str, phone: str):
    """Opens a WhatsApp chat with a contact using smart search, without sending any text."""
    target = contact or phone
    print(f"[WhatsApp Desktop] Opening chat for {target}...")

    try:
        is_cold = not is_process_running("whatsapp")
        if phone:
            phone_clean = phone.replace(" ", "").replace("-", "").lstrip("+")
            if not phone_clean.startswith("91") and len(phone_clean) == 10:
                phone_clean = "91" + phone_clean
            os.startfile(f"whatsapp://send?phone={phone_clean}")
            wait_for_app("WhatsApp", "whatsapp", is_cold=is_cold)
            if is_cold:
                wait_for_app_interactive("WhatsApp", "whatsapp", max_wait=4.0)
            focus_and_maximize_window("whatsapp", max_wait=5.0)
            _speak(f"Opened chat with {target} on WhatsApp, boss.")
            return

        os.startfile("whatsapp:")
        wait_for_app("WhatsApp", "whatsapp", is_cold=is_cold)
        if is_cold:
            wait_for_app_interactive("WhatsApp", "whatsapp", max_wait=4.0)
        focus_and_maximize_window("whatsapp", max_wait=6.0)
        time.sleep(0.3 if not is_cold else 0.8)

        found = _search_and_open_contact(contact)
        if found:
            _speak(f"Opened chat with {target} on WhatsApp, boss.")

    except Exception as e:
        print(f"[WhatsApp Desktop] Open chat error: {e}")
        _speak("An error occurred, boss.")


def _generate_name_variations(name: str) -> list[str]:
    """
    Generates intelligent spelling and format variations for a contact name:
    - Cached variations first for instant repeat search
    - Exact name, lowercase, Title Case
    - With and without spaces (e.g. 'mata shri' vs 'matashri')
    - Splitting common compound words ('matashree' -> 'mata shree')
    - Common Indian phonetic substitutions (shri <-> shree, ee <-> i, oo <-> u, v <-> w)
    - Stripping honorifics ('ji', 'bhaiya', 'bhai', 'didi', 'sir')
    - First word alone (prefix search in WhatsApp)
    """
    import re
    raw = name.strip()
    if not raw:
        return []

    variations = []
    # 1. Fast Cache Check: If user previously contacted this name successfully, try that first!
    cache = _load_contact_cache()
    cached_var = cache.get(raw.lower())
    if cached_var:
        variations.append(cached_var)
        print(f"[WhatsApp Cache] Hit! Prioritizing cached variation: '{cached_var}'")

    if raw not in variations:
        variations.append(raw)

    # Casing variations
    for case_ver in (raw.lower(), raw.title()):
        if case_ver not in variations:
            variations.append(case_ver)

    # Spacing variations
    if " " in raw:
        no_space = raw.replace(" ", "")
        if no_space not in variations:
            variations.append(no_space)
    else:
        # If no spaces, check if common words can be split
        for pattern in (r'^(mata)(shri|shree|ji)?$', r'^(papa)(ji)?$', r'^(mummy|mom)(ji)?$'):
            m = re.match(pattern, raw, re.IGNORECASE)
            if m and m.group(2):
                spaced = f"{m.group(1)} {m.group(2)}"
                if spaced not in variations:
                    variations.append(spaced)

    # Strip honorifics: ' ji', ' bhaiya', ' bhai', ' didi', ' sir'
    clean_base = re.sub(r'(?i)\s+(ji|bhaiya|bhai|didi|sir)$', '', raw).strip()
    if clean_base and clean_base not in variations:
        variations.append(clean_base)

    # Vowel & consonant substitutions
    def apply_subs(s: str) -> list[str]:
        results = []
        # shri <-> shree
        if "shri" in s.lower():
            results.append(re.sub(r'(?i)shri', 'shree', s))
        if "shree" in s.lower():
            results.append(re.sub(r'(?i)shree', 'shri', s))
        # ee <-> i
        if "ee" in s.lower():
            results.append(re.sub(r'(?i)ee', 'i', s))
        elif "i" in s.lower():
            results.append(re.sub(r'(?i)i', 'ee', s))
        # oo <-> u
        if "oo" in s.lower():
            results.append(re.sub(r'(?i)oo', 'u', s))
        elif "u" in s.lower():
            results.append(re.sub(r'(?i)u', 'oo', s))
        # v <-> w
        if "v" in s.lower():
            results.append(re.sub(r'(?i)v', 'w', s))
        elif "w" in s.lower():
            results.append(re.sub(r'(?i)w', 'v', s))
        # nch <-> nsh (common Hindi / Whisper transliteration: Ravanch <-> Ravansh, Aryavanch <-> Aryavansh)
        if "nch" in s.lower():
            results.append(re.sub(r'(?i)nch', 'nsh', s))
        if "nsh" in s.lower():
            results.append(re.sub(r'(?i)nsh', 'nch', s))
        return results

    pool = list(variations)
    for item in pool:
        for sub in apply_subs(item):
            if sub not in variations:
                variations.append(sub)
                if " " in sub:
                    sub_ns = sub.replace(" ", "")
                    if sub_ns not in variations:
                        variations.append(sub_ns)

    # First word only (WhatsApp matches any contact starting with first name)
    words = raw.split()
    if len(words) > 1:
        first_word = words[0]
        if first_word not in variations:
            variations.append(first_word)
        for sub in apply_subs(first_word):
            if sub not in variations:
                variations.append(sub)

    # Deduplicate while strictly preserving order
    seen = set()
    deduped = []
    for v in variations:
        norm = v.strip()
        if norm and norm.lower() not in seen:
            seen.add(norm.lower())
            deduped.append(norm)

    return deduped


def _search_and_open_contact(contact: str) -> bool:
    """
    Searches WhatsApp Desktop using smart spelling variations.
    Verifies contact selection using UI focus and clipboard checks.
    Returns True if contact chat was opened, False if not found.
    """
    variations = _generate_name_variations(contact)
    print(f"[WhatsApp] Starting smart search for '{contact}' with variations: {variations}")

    for idx, name in enumerate(variations, 1):
        print(f"[WhatsApp] Trying variation {idx}/{len(variations)}: '{name}'")

        # Focus search bar
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(0.2)

        # Clear search box
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.08)
        pyautogui.press('backspace')
        time.sleep(0.08)

        # Paste variation
        pyperclip.copy(name)
        pyautogui.hotkey('ctrl', 'v')
        # Adaptive wait for WhatsApp search results indexer
        time.sleep(WHATSAPP_SEARCH_POLL_INTERVAL * 2)  # ~0.4s

        # Press down arrow to highlight first search result
        pyautogui.press('down')
        time.sleep(0.15)

        # Press enter to open the chat
        pyautogui.press('enter')
        time.sleep(0.35)

        # VERIFICATION CHECK:
        # If WhatsApp did NOT find the contact, pressing Down and Enter did nothing,
        # so focus is STILL trapped in the search box!
        # When focus is in the search box, Ctrl+A + Ctrl+C copies the searched text ('name').
        # When chat opened, focus is in the empty message input, so copying yields nothing.
        SENTINEL = "__JARVIS_EMPTY_CHECK__"
        pyperclip.copy(SENTINEL)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.08)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.1)
        copied = pyperclip.paste().strip()

        if copied.lower() == name.lower():
            # Focus never left the search bar: contact was not matched
            print(f"[WhatsApp] Variation '{name}' was not found in contacts.")
            continue

        # Focus moved away: contact was found and chat opened!
        print(f"[WhatsApp] [OK] Contact matched and chat opened with variation: '{name}'")
        _save_contact_cache(contact, name)
        return True

    # All variations exhausted without match
    print(f"[WhatsApp] All {len(variations)} variations failed for '{contact}'.")
    # Clean up search box so no lingering text remains
    pyautogui.hotkey('ctrl', 'f')
    time.sleep(0.2)
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.press('backspace')
    pyautogui.press('esc')
    _speak(f"I couldn't find {contact} in your WhatsApp contacts, boss. Please type the name or provide their phone number.")
    return False


def _trigger_call(call_type: str = "voice") -> bool:
    """Clicks the Voice or Video call button in the WhatsApp Desktop chat header."""
    is_video = "video" in call_type.lower()
    screen_w, screen_h = pyautogui.size()
    print(f"[WhatsApp Call] Initiating click for {call_type} call...")

    # Ensure WhatsApp is in foreground
    focus_and_maximize_window("whatsapp", max_wait=3.0)
    time.sleep(0.5)

    def do_click(x: int, y: int, label: str) -> bool:
        print(f"[WhatsApp Call] {label}: clicking at ({x}, {y})...")
        pyautogui.moveTo(x, y, duration=0.25)
        time.sleep(0.08)
        pyautogui.mouseDown()
        time.sleep(0.08)
        pyautogui.mouseUp()
        time.sleep(0.2)
        return True

    # Strategy 1: Targeted Top-Right Header Crop Vision (Gemini 2.5 Flash)
    # Crop the top-right header region: x from (screen_w - 450) to screen_w, y from 0 to 130
    try:
        from tools.screen_vision import find_element_coordinates
        crop_region = (screen_w - 450, 0, 450, 130)
        icon_name = "camera icon for video call" if is_video else "phone icon for voice call"
        desc = f"WhatsApp top-right chat header {icon_name}"
        coords = find_element_coordinates(desc, region=crop_region)
        if coords:
            # Sanity check: must be in the right half of header
            if (screen_w - 300) <= coords[0] <= (screen_w - 50) and 30 <= coords[1] <= 110:
                return do_click(coords[0], coords[1], f"Vision ({icon_name})")
            else:
                print(f"[WhatsApp Call] Vision returned out-of-range coordinates {coords}, falling back to calibrated position")
    except Exception as e:
        print(f"[WhatsApp Call] Vision notice: {e}")

    # Strategy 2: derive a target from the WhatsApp window's absolute rectangle.
    # Header icons from right-to-left:
    # 1. Menu (three dots): screen_w - 36
    # 2. Search (magnifying glass): screen_w - 82
    # 3. Video call (camera icon): screen_w - 128
    # 4. Voice call (phone handset): screen_w - 174
    # Header vertical center: y ≈ 62
    try:
        from tools.computer_use import find_window_rect, window_rect_to_header_button
        _hwnd, rect = find_window_rect("WhatsApp")
        if rect:
            click_x, click_y = window_rect_to_header_button(rect, "video" if is_video else "voice")
            if rect[0] <= click_x < rect[2] and rect[1] <= click_y < rect[3]:
                return do_click(click_x, click_y, f"Window-relative layout ({call_type})")
    except Exception as e:
        print(f"[WhatsApp Call] Window-relative fallback notice: {e}")
    return False


def _verify_message_sent(expected_message: str) -> bool:
    """Verifies that the message input box is empty after pressing Enter."""
    try:
        SENTINEL = "__SENT_CHECK__"
        pyperclip.copy(SENTINEL)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.08)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.1)
        current_input = pyperclip.paste().strip()
        # If input box is empty or unchanged from sentinel, the message cleared and was sent
        if not current_input or current_input == SENTINEL:
            return True
        if current_input.lower() == expected_message.strip().lower():
            print("[WhatsApp Desktop] Message still in input box, retrying Enter key...")
            pyautogui.press('enter')
            time.sleep(0.35)
            pyperclip.copy(SENTINEL)
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.08)
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.1)
            return pyperclip.paste().strip() != expected_message.strip()
    except Exception as e:
        print(f"[WhatsApp Desktop] Verification notice: {e}")
    return True


def _send_via_desktop_app(contact: str, message: str, phone: str):
    """Automates messaging via the native WhatsApp Desktop app with smart verification."""
    target = contact or phone
    print(f"[WhatsApp Desktop] Starting message automation for {target}...")

    try:
        is_cold = not is_process_running("whatsapp")
        if is_cold:
            print("[WhatsApp Desktop] Cold launch detected. Giving WhatsApp initialization buffer.")

        # Path A: Direct phone number URI
        if phone:
            phone_clean = phone.replace(" ", "").replace("-", "").lstrip("+")
            if not phone_clean.startswith("91") and len(phone_clean) == 10:
                phone_clean = "91" + phone_clean
            encoded_msg = urllib.parse.quote(message)
            uri = f"whatsapp://send?phone={phone_clean}&text={encoded_msg}"
            print(f"[WhatsApp Desktop] Launching direct URI: {uri}")
            os.startfile(uri)
            wait_for_app("WhatsApp", "whatsapp", is_cold=is_cold)
            if is_cold:
                wait_for_app_interactive("WhatsApp", "whatsapp", max_wait=4.0)

            focus_and_maximize_window("whatsapp", max_wait=5.0)
            time.sleep(0.5 if not is_cold else 1.2)

            pyautogui.press('enter')
            time.sleep(0.3)
            sent = _verify_message_sent(message)
            if sent:
                print(f"[WhatsApp Desktop] Message sent to {phone_clean}")
                _speak(f"Message sent to {target} on WhatsApp, boss.")
            else:
                print(f"[WhatsApp Desktop] Warning: Message may not have dispatched")
                _speak(f"I tried sending the message to {target}, boss, but please check WhatsApp to confirm it went through.")
            return

        # Path B: Smart Contact Search
        print("[WhatsApp Desktop] Launching WhatsApp Desktop app...")
        os.startfile("whatsapp:")
        wait_for_app("WhatsApp", "whatsapp", is_cold=is_cold)
        if is_cold:
            wait_for_app_interactive("WhatsApp", "whatsapp", max_wait=4.0)

        focused = focus_and_maximize_window("whatsapp", max_wait=6.0)
        if not focused:
            print("[WhatsApp Desktop] Warning: WhatsApp window not focused, retrying...")
            time.sleep(0.5)
            focus_and_maximize_window("whatsapp", max_wait=3.0)

        time.sleep(0.3 if not is_cold else 0.8)

        # Smart search with variation fallbacks and verification
        found = _search_and_open_contact(contact)
        if not found:
            # Contact not found: user already notified, do NOT paste message into search bar!
            return

        # Contact is open! Paste and send message into the active chat box
        print(f"[WhatsApp Desktop] Typing message and sending: {message}")
        pyperclip.copy(message)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.3)
        pyautogui.press('enter')
        time.sleep(0.3)

        sent = _verify_message_sent(message)
        if sent:
            print(f"[WhatsApp Desktop] Message successfully sent to {contact}: {message}")
            _speak(f"Message sent to {target} on WhatsApp, boss.")
        else:
            print(f"[WhatsApp Desktop] Verification check: message did not dispatch cleanly")
            _speak(f"I pasted the message for {target}, boss, but please check WhatsApp to confirm it went through.")

    except Exception as e:
        print(f"[WhatsApp Desktop] Automation error: {e}")
        _speak("An error occurred, boss.")


def _call_via_desktop_app(contact: str, phone: str, call_type: str = "voice", talk_on_behalf: bool = False):
    """Automates WhatsApp voice or video calling with automatic Jarvis window dodging and CallAgent support."""
    target = contact or phone
    is_video = "video" in call_type.lower()
    call_label = "video call" if is_video else "voice call"
    print(f"[WhatsApp Desktop] Initiating {call_label} with {target} (talk_on_behalf={talk_on_behalf})...")

    try:
        is_cold = not is_process_running("whatsapp")
        # Move Jarvis orb away from the top-right corner so WhatsApp call buttons are never obstructed
        _dodge("top-left")

        # Path A: Direct phone number URI to open chat
        if phone:
            phone_clean = phone.replace(" ", "").replace("-", "").lstrip("+")
            if not phone_clean.startswith("91") and len(phone_clean) == 10:
                phone_clean = "91" + phone_clean
            cmd = f'whatsapp://send?phone={phone_clean}'
            print(f"[WhatsApp Desktop] Launching direct URI: {cmd}")
            os.startfile(f"whatsapp://send?phone={phone_clean}")
            wait_for_app("WhatsApp", "whatsapp", is_cold=is_cold)
            if is_cold:
                wait_for_app_interactive("WhatsApp", "whatsapp", max_wait=4.0)

            focus_and_maximize_window("whatsapp", max_wait=5.0)
            time.sleep(0.8)
            _trigger_call(call_type=call_type)
            if talk_on_behalf and _pipeline_ref and hasattr(_pipeline_ref, "call_agent"):
                _pipeline_ref.call_agent.start_call(target, call_type)
            else:
                _speak(f"Starting {call_label} with {target} on WhatsApp, boss.")
            return

        # Path B: Contact Name Search
        print("[WhatsApp Desktop] Launching WhatsApp Desktop app...")
        os.startfile("whatsapp:")
        wait_for_app("WhatsApp", "whatsapp", is_cold=is_cold)
        if is_cold:
            wait_for_app_interactive("WhatsApp", "whatsapp", max_wait=4.0)

        focused = focus_and_maximize_window("whatsapp", max_wait=6.0)
        if not focused:
            time.sleep(0.5)
            focus_and_maximize_window("whatsapp", max_wait=3.0)

        time.sleep(0.3 if not is_cold else 0.8)

        # Smart search contact
        found = _search_and_open_contact(contact)
        if not found:
            return

        time.sleep(0.8)

        # Trigger call
        _trigger_call(call_type=call_type)
        if talk_on_behalf and _pipeline_ref and hasattr(_pipeline_ref, "call_agent"):
            _pipeline_ref.call_agent.start_call(target, call_type)
        else:
            _speak(f"Starting {call_label} with {target} on WhatsApp, boss.")

    except Exception as e:
        print(f"[WhatsApp Desktop] Call automation error: {e}")
        _speak("An error occurred, boss.")
    finally:
        # Restore Jarvis orb back to home position
        time.sleep(1.5)
        _undodge()


# =========================================================================
# CHROME WHATSAPP WEB IMPLEMENTATION (PRESERVED / COMMENTED AS REQUESTED)
# =========================================================================
#
# from tools.screen_vision import check_whatsapp_state, find_element_coordinates
# CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
#
# def get_whatsapp_chrome_profile() -> str:
#     user_data = os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data")
#     if os.path.exists(user_data):
#         for entry in os.listdir(user_data):
#             idb = os.path.join(user_data, entry, "IndexedDB")
#             if os.path.exists(idb):
#                 for db in os.listdir(idb):
#                     if "whatsapp" in db.lower():
#                         return entry
#     return "Profile 9"
#
# def _visual_send_flow_chrome(contact: str, message: str, phone: str):
#     target = contact or phone
#     try:
#         profile_dir = get_whatsapp_chrome_profile()
#         if phone:
#             phone_clean = phone.replace(" ", "").replace("-", "").lstrip("+")
#             if not phone_clean.startswith("91") and len(phone_clean) == 10:
#                 phone_clean = "91" + phone_clean
#             url = f"https://web.whatsapp.com/send?phone={phone_clean}"
#         else:
#             url = "https://web.whatsapp.com"
#
#         cmd = f'"{CHROME_PATH}" --profile-directory="{profile_dir}" "{url}"'
#         subprocess.Popen(cmd, shell=True)
#         time.sleep(2)
#         focus_and_maximize_window("chrome")
#
#         max_wait = 24
#         poll_interval = 2.0
#         elapsed = 0
#         logged_in = False
#         while elapsed < max_wait:
#             time.sleep(poll_interval)
#             elapsed += poll_interval
#             focus_and_maximize_window("chrome")
#             state = check_whatsapp_state()
#             if state == "chats_ready":
#                 logged_in = True
#                 break
#             elif state == "qr_code" and elapsed >= 10:
#                 _speak("Sir, WhatsApp is displaying a QR code. Please scan it.")
#                 return
#
#         if not logged_in:
#             _speak("Sir, I could not bring your WhatsApp window forward.")
#             return
#
#         if not phone and contact:
#             search_coords = find_element_coordinates("WhatsApp search bar at top left")
#             if search_coords:
#                 pyautogui.click(search_coords[0], search_coords[1])
#             else:
#                 pyautogui.hotkey('ctrl', 'alt', '/')
#             time.sleep(0.5)
#             pyautogui.hotkey('ctrl', 'a')
#             pyautogui.press('backspace')
#             pyperclip.copy(contact)
#             pyautogui.hotkey('ctrl', 'v')
#             time.sleep(2.0)
#             contact_coords = find_element_coordinates(f"search result item for contact {contact}")
#             if contact_coords:
#                 pyautogui.click(contact_coords[0], contact_coords[1])
#             else:
#                 pyautogui.press('down')
#                 time.sleep(0.3)
#                 pyautogui.press('enter')
#             time.sleep(2.0)
#
#         msg_coords = find_element_coordinates("Type a message text box at bottom right of chat")
#         if msg_coords:
#             pyautogui.click(msg_coords[0], msg_coords[1])
#         time.sleep(0.3)
#         pyperclip.copy(message)
#         pyautogui.hotkey('ctrl', 'v')
#         time.sleep(0.4)
#         pyautogui.press('enter')
#         _speak(f"Message sent to {target}, boss.")
#     except Exception as e:
#         print(f"[WhatsApp Chrome] Error: {e}")
