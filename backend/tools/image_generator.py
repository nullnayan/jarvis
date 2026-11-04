# FILE: backend/tools/image_generator.py
# Generates high-quality drawings and images using Google Gemini & FLUX.1.
# Saves JPGs to custom paths (Desktop, Downloads, Pictures) and integrates with MS Paint.

import os
import io
import re
import time
import urllib.request
import urllib.parse
import subprocess
import base64
import json
from PIL import Image
from config import (
    GEMINI_MODEL,
    IMAGE_GEN_FALLBACK_MODEL,
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN,
    CLOUDFLARE_IMAGE_MODEL,
)
from llm.gemini_client import gemini_client

def _resolve_destination(prompt: str, destination: str = "") -> str:
    """Resolves destination folder/path, ensuring a valid .jpg target file."""
    user_home = os.path.expanduser("~")
    dest_lower = (destination or "").strip().lower()

    if "desktop" in dest_lower:
        target_dir = os.path.join(user_home, "Desktop")
    elif "download" in dest_lower:
        target_dir = os.path.join(user_home, "Downloads")
    elif "picture" in dest_lower or "photo" in dest_lower:
        target_dir = os.path.join(user_home, "Pictures")
    elif destination and os.path.isabs(destination):
        if os.path.isdir(destination):
            target_dir = destination
        else:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            return destination if destination.lower().endswith((".jpg", ".jpeg")) else f"{destination}.jpg"
    else:
        target_dir = os.path.join(user_home, "Pictures", "Jarvis_Art")

    os.makedirs(target_dir, exist_ok=True)

    match = re.search(r'[\w\-]+\.(?:jpg|jpeg|png)', destination, re.IGNORECASE)
    if match:
        filename = match.group(0)
        if not filename.lower().endswith((".jpg", ".jpeg")):
            filename = f"{os.path.splitext(filename)[0]}.jpg"
    else:
        clean_name = re.sub(r'[^\w\s]', '', prompt)[:25].strip().replace(' ', '_')
        if not clean_name:
            clean_name = "artwork"
        filename = f"{clean_name}_{int(time.time())}.jpg"

    return os.path.join(target_dir, filename)

def _try_gemini_enhance(prompt: str) -> str:
    """Refines the user's prompt using Gemini 3.7 Flash across 7 keys into a grand, realistic, expansive description."""
    try:
        print(f"[ImageGenerator] Enriching prompt with Gemini 3.7 Flash across 7-key pool...")
        enriched = gemini_client.enrich_photo_prompt(prompt)
        if enriched and len(enriched) > len(prompt):
            print(f"[ImageGenerator] Enriched Realistic Prompt:\n{enriched}")
            return enriched
    except Exception as e:
        print(f"[ImageGenerator] Prompt enrichment error: {e}")
    return prompt

def _fetch_cloudflare_image(prompt: str) -> bytes:
    """Generates an uncompressed studio-grade photo using Cloudflare Workers AI (FLUX.1-schnell)."""
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        raise ValueError("Cloudflare credentials not configured in config.py")

    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{CLOUDFLARE_IMAGE_MODEL}"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Jarvis-Assistant/1.0"
    }
    payload = json.dumps({"prompt": prompt, "steps": 4}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    print(f"[ImageGenerator] Requesting Cloudflare Workers AI ({CLOUDFLARE_IMAGE_MODEL})...")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=35) as resp:
        res_data = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        if "result" in res_data and "image" in res_data["result"]:
            raw_b64 = res_data["result"]["image"]
            img_bytes = base64.b64decode(raw_b64)
            print(f"[ImageGenerator] Cloudflare generated {len(img_bytes):,} bytes in {elapsed:.2f}s!")
            return img_bytes
        raise ValueError(f"Unexpected Cloudflare response format: {list(res_data.keys())}")

def _fetch_flux_fallback(prompt: str) -> bytes:
    """Fallback generator using public FLUX.1 endpoint."""
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model=flux&nologo=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    print(f"[ImageGenerator] Falling back to public FLUX gateway...")
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read()

def generate_image(params: dict) -> str:
    """Tool entry point for drawing/generating images and opening in Paint or custom paths."""
    prompt = str(params.get("prompt", "")).strip()
    destination = str(params.get("destination", "")).strip()
    open_in_paint = bool(params.get("open_in_paint", False))
    open_after_save = bool(params.get("open_after_save", True))

    if not prompt:
        return "Please describe what you would like me to draw, boss."

    if any(k in prompt.lower() for k in ["on paint", "in paint", "paint pe", "paint par", "paint me"]):
        open_in_paint = True

    try:
        dest_path = _resolve_destination(prompt, destination)
        print(f"[ImageGenerator] Generating drawing for prompt: '{prompt}'")
        print(f"[ImageGenerator] Target destination: {dest_path}")

        enhanced_prompt = _try_gemini_enhance(prompt)

        # Primary engine: Cloudflare Workers AI FLUX.1-schnell (direct API, studio quality)
        img_bytes = None
        try:
            img_bytes = _fetch_cloudflare_image(enhanced_prompt)
        except Exception as cf_err:
            print(f"[ImageGenerator] Cloudflare generation failed: {cf_err}. Switching to fallback...")
            img_bytes = _fetch_flux_fallback(enhanced_prompt)

        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        image.save(dest_path, "JPEG", quality=95)
        print(f"[ImageGenerator] Image saved successfully to: {dest_path}")

        if open_in_paint:
            subprocess.Popen(["mspaint.exe", dest_path])
            return f"I have generated the realistic artwork and opened it in Paint for you, boss."
        else:
            # Auto-open generated photo so user immediately sees the result
            os.startfile(dest_path)
            return f"I have enriched your prompt with Gemini 3.7 Flash, generated the realistic photo, and displayed it on your screen, boss."
    except Exception as e:
        print(f"[ImageGenerator] Error generating image: {e}")
        return "An error occurred while generating the drawing, boss."
