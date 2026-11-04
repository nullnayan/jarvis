# FILE: screen_vision.py
# Gives Jarvis the ability to see the screen and locate UI elements via NVIDIA NIM Vision AI.
import base64
import io
import json
import re
from PIL import ImageGrab
import pyautogui
from openai import OpenAI
from config import GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_BASE_URL, VISION_MODEL

def _call_vision(messages, max_tokens=60, temperature=0.1, timeout=12):
    """Calls Groq vision model using Key 1 with automatic failover to Key 2."""
    try:
        client = OpenAI(api_key=GROQ_API_KEY_1, base_url=GROQ_BASE_URL)
        return client.chat.completions.create(
            model=VISION_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout
        )
    except Exception as e1:
        print(f"[ScreenVision] Key 1 failed: {e1}, failing over to Key 2...")
        client = OpenAI(api_key=GROQ_API_KEY_2, base_url=GROQ_BASE_URL)
        return client.chat.completions.create(
            model=VISION_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout
        )

def capture_screen_b64(quality=85, max_width=None, region=None):
    """Takes a screenshot (optionally cropped to region=(x, y, w, h)).
    Returns (b64_str, scale_x, scale_y, offset_x, offset_y).
    """
    if region:
        rx, ry, rw, rh = region
        img = ImageGrab.grab(bbox=(rx, ry, rx + rw, ry + rh))
        offset_x, offset_y = rx, ry
    else:
        img = ImageGrab.grab()
        offset_x, offset_y = 0, 0

    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    orig_w, orig_h = img.width, img.height
    if max_width and img.width > max_width:
        ratio = max_width / float(img.width)
        new_height = int(float(img.height) * ratio)
        img = img.resize((max_width, new_height))
        scale_x = orig_w / float(max_width)
        scale_y = orig_h / float(new_height)
    else:
        scale_x, scale_y = 1.0, 1.0

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return b64, scale_x, scale_y, offset_x, offset_y

def check_whatsapp_state() -> str:
    """
    Analyzes the current screen to detect WhatsApp Web status.
    Returns: 'qr_code', 'loading', 'chats_ready', or 'not_open'.
    """
    b64, *_ = capture_screen_b64(max_width=1280)
    prompt = """Analyze this desktop screenshot and identify the state of WhatsApp Web.
Choose one of these exact states:
- 'qr_code': WhatsApp Web is displayed with a large square QR code asking to scan from phone.
- 'loading': WhatsApp Web is showing 'Loading your chats', 'Connecting...', or a green progress bar.
- 'chats_ready': WhatsApp Web is logged in and ready. You clearly see the chat list with contact names and a search bar on the left pane.
- 'not_open': WhatsApp Web is NOT the active window on screen (another app like VSCode, desktop, or a non-WhatsApp tab is in front).

Respond ONLY with a JSON object: {"state": "<qr_code|loading|chats_ready|not_open>"}"""

    try:
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]
        }]
        resp = _call_vision(messages, max_tokens=40, temperature=0.1, timeout=10)
        content = resp.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            state = data.get("state", "not_open")
            print(f"[ScreenVision] WhatsApp state: {state}")
            return state
    except Exception as e:
        print(f"[ScreenVision] State check error: {e}")

    return "not_open"

def find_element_coordinates(description: str, region: tuple = None) -> tuple | None:
    """
    Uses NVIDIA NIM Vision AI to locate a specific UI element on the screen.
    If region=(x, y, w, h) is provided, inspects that specific crop for 1:1 pixel accuracy.
    Returns (x, y) coordinates relative to the full screen display.
    Never guesses or returns blind fallbacks.
    """
    screen_w, screen_h = pyautogui.size()
    b64, scale_x, scale_y, offset_x, offset_y = capture_screen_b64(max_width=None if region else 1280, region=region)

    if region:
        rw, rh = region[2], region[3]
        prompt = f"""This image is a {rw}x{rh} pixel crop of the screen at offset ({offset_x}, {offset_y}).
Find this UI element: "{description}".

If found, return JSON with its center pixel coordinates relative to this image:
{{"found": true, "x": <integer>, "y": <integer>}}

If the element is NOT visible in this image, return:
{{"found": false}}"""
    else:
        prompt = f"""Look at this desktop screenshot.
Find this UI element: "{description}".

Return JSON with its center pixel coordinates:
{{"found": true, "x": <integer>, "y": <integer>}}

If the element is NOT visible on screen, return:
{{"found": false}}"""

    try:
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]
        }]
        resp = _call_vision(messages, max_tokens=60, temperature=0.1, timeout=10)
        content = resp.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            if data.get("found"):
                raw_x = float(data.get("x", 0))
                raw_y = float(data.get("y", 0))
                # Rescale back to real display coordinates
                real_x = int(offset_x + (raw_x * scale_x))
                real_y = int(offset_y + (raw_y * scale_y))
                if 0 < real_x < screen_w and 0 < real_y < screen_h:
                    print(f"[ScreenVision] Located '{description}' at ({real_x}, {real_y}) [raw=({raw_x}, {raw_y}), scale=({scale_x:.2f}, {scale_y:.2f})]")
                    return (real_x, real_y)
    except Exception as e:
        print(f"[ScreenVision] Vision coordinate error for '{description}': {e}")

    # NEVER guess fallback coordinates! If not seen, return None for safety.
    print(f"[ScreenVision] Element '{description}' not found on screen.")
    return None
