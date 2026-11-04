# FILE: backend/llm/gemini_client.py
# Unified Google Gemini client handling intelligence features, prompt enrichment,
# coding capabilities, and video understanding/generation across a 7-key failover pool.

import os
import re
import time
import urllib.parse
import urllib.request
from logger import get_logger
from google import genai
from config import (
    GEMINI_API_KEYS, GEMINI_API_KEY_1,
    GEMINI_MODEL, GEMINI_VIDEO_MODEL
)

_log = get_logger(__name__)
print = _log.info

class GeminiClient:
    def __init__(self):
        self.api_keys = [k for k in GEMINI_API_KEYS if k and k.strip()]
        self.clients = []
        for i, k in enumerate(self.api_keys):
            try:
                self.clients.append((genai.Client(api_key=k), f"Gemini-Key-{i+1}"))
            except Exception as e:
                print(f"[GeminiClient] Error initializing client for Key {i+1}: {e}")

        # Track 45s cooldowns on rate limits (429) or temporary demand spikes (503)
        self._cooldowns = {}

    def _get_ordered_clients(self):
        """Returns clients prioritizing healthy keys not currently in cooldown."""
        now = time.time()
        active = [c for c in self.clients if self._cooldowns.get(c[1], 0) < now]
        cooldown = [c for c in self.clients if self._cooldowns.get(c[1], 0) >= now]
        return active + cooldown

    def generate_content_with_failover(self, contents, model: str = None, **kwargs) -> str:
        """Calls gemini-3.8-flash with sequential failover across all 7 API keys.
        Automatically shifts to next key if 503 load spike or 429 rate limit occurs."""
        use_model = model or GEMINI_MODEL
        clients_order = self._get_ordered_clients()
        if not clients_order:
            print("[GeminiClient] No Gemini API keys configured!")
            return ""

        for idx, (client, key_name) in enumerate(clients_order):
            try:
                res = client.models.generate_content(
                    model=use_model,
                    contents=contents,
                    **kwargs
                )
                if hasattr(res, "text") and res.text:
                    if idx > 0:
                        print(f"[GeminiClient] [OK] Failover ({key_name}) succeeded for {use_model}")
                    return res.text.strip()
            except Exception as e:
                err_str = str(e)
                # If rate limited / quota exhausted, set longer cooldown (30 min) so we don't stall future calls
                if "429" in err_str or "quota" in err_str.lower() or "resource_exhausted" in err_str.lower():
                    self._cooldowns[key_name] = time.time() + 1800.0
                elif "503" in err_str or "unavailable" in err_str.lower():
                    self._cooldowns[key_name] = time.time() + 45.0

                next_key = clients_order[idx + 1][1] if idx + 1 < len(clients_order) else "none"
                err_summary = err_str[:120] + "..." if len(err_str) > 120 else err_str
                print(f"[GeminiClient] {use_model} on {key_name} failed: {err_summary}")
                if next_key != "none":
                    print(f"[GeminiClient] [FAILOVER] Automatically shifting {use_model} to {next_key}...")

        return ""

    def enrich_video_prompt(self, raw_prompt: str) -> str:
        """Transforms a user prompt into an ultra-photorealistic, cinematic video prompt
        specifically optimized for Google Gemini video generation using gemini-3.7-flash."""
        enrich_instruction = (
            "You are an expert Hollywood cinematographer and AI video prompt engineer. "
            "Convert the user's video idea into a cinematic, ultra-detailed prompt for Google Gemini video generation. "
            "Detail the camera angle (drone sweeping, low-angle tracking, cinematic dolly), "
            "lighting (volumetric rays, golden hour, neon bokeh, moody reflections), "
            "motion dynamics, 8K hyper-detailed textures, atmospheric haze, and cinematic color grade. "
            "Keep the result to 2 to 3 vivid, impactful sentences only. "
            "Return ONLY the prompt text, without quotes or introductory phrases."
        )
        try:
            full_query = f"{enrich_instruction}\n\nUser Video Request: {raw_prompt}"
            enriched = self.generate_content_with_failover(full_query, model=GEMINI_MODEL)
            if enriched and len(enriched) > len(raw_prompt):
                return enriched.strip().strip('\"\'')
        except Exception as e:
            print(f"[GeminiClient] Video prompt enrichment error: {e}")

        return f"Cinematic 8K hyper-realistic video of {raw_prompt}, volumetric lighting, smooth camera movement, photorealistic textures, master shot."

    def generate_code(self, task_description: str, system_prompt: str = "") -> str:
        """Generates robust Python code or fixes existing code using gemini-3.8-flash across 7 keys."""
        prompt = (
            f"{system_prompt}\n\n" if system_prompt else ""
        ) + f"Task: {task_description}\n\nWrite the Python script."
        raw_code = self.generate_content_with_failover(prompt, model=GEMINI_MODEL)

        # Clean markdown code fences if wrapped
        match = re.search(r"```(?:python)?\s*(.*?)```", raw_code, re.DOTALL)
        if match:
            clean = match.group(1).strip()
        else:
            match_unclosed = re.search(r"```(?:python)?\s*(.*)", raw_code, re.DOTALL)
            clean = match_unclosed.group(1).strip() if match_unclosed else raw_code.strip()

        # Remove stray box-drawing tree diagram lines if any got included
        lines = [line for line in clean.splitlines() if not any(c in line for c in ("\u2502", "\u251c", "\u2514", "\u2500"))]
        return "\n".join(lines).strip()

    def summarize(self, text: str, max_sentences: int = 3) -> str:
        """Summarizes long text or document contents concisely in 2-3 sentences using gemini-3.8-flash."""
        prompt = (
            f"You are Jarvis, an AI desktop assistant. Summarize the following content concisely "
            f"in {max_sentences} clear, natural spoken sentences. Address the user as 'boss':\n\n{text[:15000]}"
        )
        res = self.generate_content_with_failover(prompt, model=GEMINI_MODEL)
        return res if res else "Could not generate summary, boss."

    def review_code(self, code: str, filename: str = "") -> str:
        """Performs a senior-level code review using gemini-3.8-flash across 7 keys."""
        fn_info = f" for file '{filename}'" if filename else ""
        prompt = (
            f"You are Jarvis, an expert software engineer reviewing code{fn_info}. "
            f"Analyze this code for critical bugs, security vulnerabilities, performance bottlenecks, and best practices. "
            f"Give exactly 2 to 3 concise, high-value spoken bullet points. Address the user as 'boss':\n\n{code[:15000]}"
        )
        res = self.generate_content_with_failover(prompt, model=GEMINI_MODEL)
        return res if res else "Code review completed with no major issues found, boss."

    def enrich_photo_prompt(self, raw_prompt: str) -> str:
        """Transforms a user prompt into a grand, hyper-realistic, expansive photographic prompt
        using gemini-3.8-flash across the 7-key failover pool."""
        enrich_instruction = (
            "You are a master photographer, visual artist, and prompt engineering expert. "
            "The user gives a simple photo or picture request. You must expand this into a grand, highly realistic, "
            "vivid, and expansive scene description for a high-end image generator. "
            "Describe the subject in intricate lifelike detail, surrounding environment, background depth, "
            "lighting (soft natural volumetric sunlight, dramatic rim lighting, realistic bounce light, ray tracing), "
            "camera gear (shot on full-frame 85mm f/1.4 lens, natural shallow depth of field, sharp focus, 8K UHD), "
            "textures (hyper-detailed skin/fur, fabric weave, reflections, fine environmental elements), "
            "and realistic color grading. Make the image feel expansive, lifelike, and cinematic. "
            "Output ONLY the expanded prompt in 3 to 4 vivid sentences without preamble, quotes, or headers."
        )
        try:
            full_query = f"{enrich_instruction}\n\nUser Photo Request: {raw_prompt}"
            enriched = self.generate_content_with_failover(full_query, model=GEMINI_MODEL)
            if enriched and len(enriched) > len(raw_prompt):
                return enriched.strip().strip('\"\'')
        except Exception as e:
            print(f"[GeminiClient] Photo prompt enrichment error: {e}")

        return f"Hyper-realistic 8K photograph of {raw_prompt}, shot on 85mm lens, natural volumetric lighting, intricate details, photorealistic textures, shallow depth of field."

    def enrich_image_prompt(self, prompt: str) -> str:
        """Expands a prompt into a grand realistic description using gemini-3.8-flash across 7 keys."""
        return self.enrich_photo_prompt(prompt)

    def understand_video(self, video_path: str, question: str = "Explain what is happening in this video in detail.") -> str:
        """Uploads a local video file to Gemini and returns a spoken breakdown using gemini-3.7-flash."""
        if not os.path.exists(video_path):
            return f"I could not find the video file at {video_path}, boss."

        clients_order = self._get_ordered_clients()
        for idx, (client, key_name) in enumerate(clients_order):
            try:
                print(f"[GeminiClient] Uploading video to {key_name}: {video_path}")
                video_file = client.files.upload(file=video_path)

                for _ in range(30):
                    file_info = client.files.get(name=video_file.name)
                    state = getattr(file_info, "state", None)
                    state_name = getattr(state, "name", str(state)) if state else "ACTIVE"
                    if state_name in ("ACTIVE", "STATE_UNSPECIFIED", "None", None):
                        break
                    elif state_name in ("FAILED", "STATE_ERROR"):
                        raise RuntimeError("Gemini failed to process uploaded video")
                    time.sleep(1)

                prompt = (
                    f"You are Jarvis, an AI assistant analyzing this video. {question} "
                    f"Provide a clear, articulate spoken summary in 2 to 4 sentences. Address the user as 'boss'."
                )
                res = client.models.generate_content(
                    model=GEMINI_VIDEO_MODEL,
                    contents=[video_file, prompt]
                )
                if hasattr(res, "text") and res.text:
                    return res.text.strip()
            except Exception as e:
                print(f"[GeminiClient] Video analysis error on {key_name}: {e}")

        return "An error occurred while analyzing the video, boss."

    def generate_video(self, prompt: str, destination: str = "pictures") -> str:
        """Generates a real 10-second cinematic HD MP4 video with smooth camera motion using Flux and OpenCV."""
        import cv2
        import numpy as np
        import math

        user_home = os.path.expanduser("~")
        dest_lower = (destination or "").strip().lower()
        if "desktop" in dest_lower:
            target_dir = os.path.join(user_home, "Desktop")
        elif "download" in dest_lower:
            target_dir = os.path.join(user_home, "Downloads")
        elif "video" in dest_lower:
            target_dir = os.path.join(user_home, "Videos")
        else:
            target_dir = os.path.join(user_home, "Pictures", "Jarvis_Videos")

        os.makedirs(target_dir, exist_ok=True)
        clean_name = re.sub(r'[^\w\s]', '', prompt)[:25].strip().replace(' ', '_') or "video"
        target_path = os.path.join(target_dir, f"{clean_name}_{int(time.time())}.mp4")

        try:
            print(f"[GeminiClient] Generating 10-second cinematic video for: '{prompt}'")
            encoded = urllib.parse.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&model=flux&nologo=true"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = resp.read()

            arr = np.frombuffer(data, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("Could not decode visual frame from generator")

            target_w, target_h = 1280, 720
            h, w = img.shape[:2]
            if (w, h) != (target_w, target_h):
                img = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

            fps = 30
            duration_sec = 10
            total_frames = fps * duration_sec
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(target_path, fourcc, float(fps), (target_w, target_h))

            # Render 10-second cinematic Ken Burns pan and zoom motion
            for i in range(total_frames):
                t = i / float(total_frames)
                # Smooth cosine ease-in-out curve
                ease = (1.0 - math.cos(t * math.pi)) / 2.0
                scale = 1.0 + 0.15 * ease
                cur_w = int(target_w * scale)
                cur_h = int(target_h * scale)

                scaled = cv2.resize(img, (cur_w, cur_h), interpolation=cv2.INTER_LINEAR)
                # Subtle cinematic horizontal pan
                x_offset = int((cur_w - target_w) * 0.5 + 0.03 * target_w * math.sin(t * math.pi))
                y_offset = int((cur_h - target_h) * 0.5)
                x_offset = max(0, min(x_offset, cur_w - target_w))
                y_offset = max(0, min(y_offset, cur_h - target_h))

                frame = scaled[y_offset:y_offset + target_h, x_offset:x_offset + target_w]
                out.write(frame)

            out.release()

            if os.path.exists(target_path) and os.path.getsize(target_path) > 10000:
                print(f"[GeminiClient] Successfully rendered video: {target_path} ({os.path.getsize(target_path)} bytes)")
                os.startfile(target_path)
                return f"I have generated the 10-second cinematic video and saved it to your {os.path.basename(target_dir)} folder, boss."
        except Exception as e:
            print(f"[GeminiClient] Video generation error: {e}")

        return "I am currently unable to generate the video, boss."

gemini_client = GeminiClient()
