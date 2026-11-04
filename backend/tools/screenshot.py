# FILE: screenshot.py
# Takes a screenshot, optionally analyzes it with NVIDIA NIM Vision API.
import os
import time
import base64
from PIL import ImageGrab

SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")

def screenshot(params: dict) -> str:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    filename = f"screenshot_{int(time.time())}.png"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    try:
        img = ImageGrab.grab()
        img.save(filepath)
        analyze = params.get("analyze", False)
        if analyze:
            return _analyze_image(filepath, params.get("question", ""))
        return "Screenshot captured and saved, boss."
    except Exception as e:
        print(f"[Screenshot] Error: {e}")
        return "An error occurred, boss."

def _analyze_image(filepath: str, question: str = "") -> str:
    try:
        from openai import OpenAI
        from config import GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_BASE_URL, VISION_MODEL
        with open(filepath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        prompt = question if question else "Describe what you see on this screenshot in 2-3 sentences."
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]
        }]
        try:
            client = OpenAI(api_key=GROQ_API_KEY_1, base_url=GROQ_BASE_URL)
            response = client.chat.completions.create(
                model=VISION_MODEL,
                messages=messages,
                max_tokens=300, timeout=15
            )
            return response.choices[0].message.content or "Done, boss."
        except Exception as e1:
            print(f"[Screenshot] Vision Key 1 error: {e1}, trying Key 2...")
            client = OpenAI(api_key=GROQ_API_KEY_2, base_url=GROQ_BASE_URL)
            response = client.chat.completions.create(
                model=VISION_MODEL,
                messages=messages,
                max_tokens=300, timeout=15
            )
            return response.choices[0].message.content or "Done, boss."
    except Exception as e:
        print(f"[Screenshot] Vision error: {e}")
        return "An error occurred, boss."
