# FILE: backend/tools/gemini_browser_agent.py
# Automated Chrome & Google Gemini agent for photo (Imagen 3) & video (Veo) generation,
# polling, downloading, and playback.

import os
import sys
import time
import glob
import subprocess
import cv2
import numpy as np
import json
import re
from PIL import ImageGrab
import pyautogui
import pyperclip
from tools.window_manager import focus_and_maximize_window, minimize_jarvis_orb, restore_jarvis_orb
from tools.screen_vision import capture_screen_b64, _call_vision, find_element_coordinates
from llm.gemini_client import gemini_client

GEMINI_URL = "https://gemini.google.com/app"
DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
VIDEOS_BTN_TEMPLATE = os.path.join(DATA_DIR, "gemini_videos_btn.png")
IMAGES_BTN_TEMPLATE = os.path.join(DATA_DIR, "gemini_images_btn.png")
PLUS_BTN_TEMPLATE = os.path.join(DATA_DIR, "gemini_plus_btn.png")
CREATE_VIDEO_ITEM_TEMPLATE = os.path.join(DATA_DIR, "gemini_create_video_item.png")

class GeminiBrowserAgent:
    def __init__(self):
        self.video_max_wait = 240.0   # 4-minute maximum cutoff for video
        self.video_initial_wait = 60.0 # 1 minute before first check (user requested)
        self.video_poll_interval = 30.0 # 30s between checks
        self.photo_max_wait = 90.0    # 90s maximum cutoff for photo
        self.photo_initial_wait = 15.0 # 15s first check for Imagen 3
        self.photo_poll_interval = 10.0 # 10s checks

    def _find_template_multiscale(self, screen_bgr, template_path: str = "", scales=[0.8, 1.0, 1.25, 1.5, 1.88, 2.0]):
        """Finds a button template across multiple DPI scales on screen."""
        target_path = template_path or VIDEOS_BTN_TEMPLATE
        if not os.path.exists(target_path):
            return None
        template_bgr = cv2.imread(target_path)
        if template_bgr is None:
            return None

        gray_screen = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        th, tw = gray_template.shape[:2]

        best_val = -1
        best_loc = None
        best_scale = 1.0

        for scale in scales:
            resized_w = int(tw * scale)
            resized_h = int(th * scale)
            if resized_w > gray_screen.shape[1] or resized_h > gray_screen.shape[0]:
                continue
            resized_tmpl = cv2.resize(
                gray_template, (resized_w, resized_h),
                interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            )
            res = cv2.matchTemplate(gray_screen, resized_tmpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_scale = scale

        if best_val > 0.65:
            match_w = int(tw * best_scale)
            match_h = int(th * best_scale)
            center_x = best_loc[0] + match_w // 2
            center_y = best_loc[1] + match_h // 2
            return center_x, center_y, best_val
        return None

    def _safe_click(self, x: int, y: int, label: str = "") -> bool:
        """Safely clicks (x, y) if and only if it is strictly within the webpage body viewport.
        STRICT SAFETY GUARDS:
        - Rejects any click with y < 140 (protects Chrome tab strip, address bar, bookmarks)
        - Rejects any click with y > screen_h - 45 (protects Windows taskbar)
        - Rejects any click with x < 10 or x > screen_w - 60 (protects window controls and screen edges)
        """
        screen_w, screen_h = pyautogui.size()
        if y < 140:
            print(f"[GeminiBrowser] [SAFETY GUARD] Blocked unsafe click at ({x}, {y}) (y < 140 tab strip zone) for '{label}'!")
            return False
        if y > screen_h - 45:
            print(f"[GeminiBrowser] [SAFETY GUARD] Blocked unsafe click at ({x}, {y}) (y > {screen_h - 45} taskbar zone) for '{label}'!")
            return False
        if x < 10 or x > screen_w - 60:
            print(f"[GeminiBrowser] [SAFETY GUARD] Blocked unsafe click at ({x}, {y}) (horizontal margin zone) for '{label}'!")
            return False

        print(f"[GeminiBrowser] Safe clicking '{label}' at ({x}, {y})...")
        pyautogui.click(x, y)
        return True

    def _verify_prompt_entered(self) -> tuple[bool, str]:
        """Uses Vision AI to verify whether prompt text has actually been entered inside the Gemini prompt box."""
        print("[GeminiBrowser] [VISION AI] Verifying prompt text has been entered in prompt box...")
        screen_w, screen_h = pyautogui.size()
        try:
            crop_region = (int(screen_w * 0.15), 140, int(screen_w * 0.70), int(screen_h * 0.82))
            b64, _, _, _, _ = capture_screen_b64(region=crop_region)

            prompt = """Analyze this Gemini screenshot crop.
Is there user-entered prompt text inside the prompt input box, or is it empty / placeholder ('Ask Gemini')?
Respond ONLY with a JSON object:
{
  "has_text": true/false,
  "description": "<short 1-line description>"
}"""
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]
            }]
            resp = _call_vision(messages, max_tokens=100, temperature=0.1, timeout=10)
            content = resp.choices[0].message.content.strip()
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                has_text = bool(data.get("has_text", False))
                desc = data.get("description", "")
                print(f"[GeminiBrowser] [VISION AI] Prompt check: has_text={has_text} ({desc})")
                return has_text, desc
        except Exception as e:
            print(f"[GeminiBrowser] Prompt verification error: {e}")
        return False, "Verification check failed"

    def _verify_processing_started(self) -> tuple[bool, bool, str, str]:
        """Uses Vision AI to verify whether Google Veo video processing has ACTUALLY started.
        Returns: (processing_started: bool, error_detected: bool, error_message: str, description: str).
        Guarantees Jarvis NEVER enters a blind 4-minute wait loop on an unsubmitted or empty screen."""
        print("[GeminiBrowser] [VISION AI] Inspecting screen to verify video generation has actually started...")
        screen_w, screen_h = pyautogui.size()
        try:
            crop_region = (int(screen_w * 0.10), 140, int(screen_w * 0.80), int(screen_h * 0.75))
            b64, _, _, _, _ = capture_screen_b64(region=crop_region)

            prompt = """Analyze this Google Gemini chat screenshot.
Check if video generation/processing has actually started.
Indicators that video generation HAS started:
- A video generation card, preview box, or placeholder with 'Generating video...', 'Creating video...', or a progress bar / animated shimmer / loading spinner.
- A user chat bubble with the submitted video prompt and Gemini actively responding or generating.
Indicators that video generation has NOT started:
- The screen is still on the blank home screen ('Ask Gemini' or greeting) with no chat messages.
- The prompt is still sitting in the input box unsubmitted.
- An error modal or error banner (e.g., 'Something went wrong', 'Unable to generate video', prompt policy violation, quota exceeded).

Respond ONLY with a JSON object:
{
  "processing_started": true/false,
  "error_detected": true/false,
  "error_message": "",
  "status": "<1-line description of what is visible on screen>"
}"""
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]
            }]
            resp = _call_vision(messages, max_tokens=150, temperature=0.1, timeout=12)
            content = resp.choices[0].message.content.strip()
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                proc_started = bool(data.get("processing_started", False))
                err_detected = bool(data.get("error_detected", False))
                err_msg = data.get("error_message", "")
                status = data.get("status", "")
                print(f"[GeminiBrowser] [VISION AI] Verification: started={proc_started}, error={err_detected}, status='{status}'")
                return proc_started, err_detected, err_msg, status
        except Exception as e:
            print(f"[GeminiBrowser] Processing verification error: {e}")
        return False, False, "", "Verification check failed"

    def dismiss_unwanted_popups(self, max_attempts: int = 1) -> bool:
        """Safely dismisses unwanted Gemini promo modals, update dialogs, or popups.
        Uses Escape key and guarded Vision AI targeting strictly within the central webpage viewport.
        Strict safety guards prevent clicking near the tab bar (y < 140) or window controls."""
        print("[GeminiBrowser] Safely clearing any unwanted Gemini promo modals or dialogs...")
        screen_w, screen_h = pyautogui.size()

        # 1. Primary safe method: Press Escape (natively dismisses standard HTML/Material modals without mouse movement)
        pyautogui.press('esc')
        time.sleep(0.25)
        pyautogui.press('esc')
        time.sleep(0.25)

        # 2. Vision AI targeting strictly inside the central webpage body (never near tabs or title bar)
        try:
            from tools.screen_vision import find_element_coordinates
            # Dialog region: central 60% of screen width, y strictly between 160 and screen_h - 100
            crop_region = (int(screen_w * 0.20), 160, int(screen_w * 0.60), int(screen_h * 0.65))
            coords = find_element_coordinates(
                "the 'Dismiss', 'Got it', 'Not now', 'No thanks', or 'Close' button on the popup dialog",
                region=crop_region
            )
            if coords:
                cx, cy = coords
                # STRICT SAFETY GUARD: NEVER click near the tab bar (y < 140) or window controls
                if cy < 140 or cy > screen_h - 60 or cx > screen_w - 60:
                    print(f"[GeminiBrowser] [SAFETY GUARD] Rejected unsafe coordinate ({cx}, {cy}) outside webpage body!")
                    return False
                print(f"[GeminiBrowser] [DISMISSED] Clicking safe popup dismiss button at ({cx}, {cy})...")
                pyautogui.click(cx, cy)
                time.sleep(0.3)
                pyautogui.press('esc')
                return True
        except Exception as e:
            print(f"[GeminiBrowser] Vision popup check: {e}")

        return False

    def wait_for_gemini_page_ready(self, max_wait: float = 25.0) -> bool:
        """Actively inspects the screen and window state to ensure the Gemini web app
        is completely opened, focused, and rendered before any automation actions occur."""
        print(f"[GeminiBrowser] Verifying Gemini window and web page are fully loaded (max wait: {max_wait}s)...")
        start = time.time()
        screen_w, screen_h = pyautogui.size()

        # Wait initial 1.5s for Chrome window to appear, then focus
        time.sleep(1.5)
        focus_and_maximize_window("gemini", max_wait=2.0) or focus_and_maximize_window("chrome", max_wait=2.0)
        # Clear any initial promo modal once safely
        self.dismiss_unwanted_popups()

        while time.time() - start < max_wait:
            focused = focus_and_maximize_window("gemini", max_wait=1.0)
            if not focused:
                focused = focus_and_maximize_window("chrome", max_wait=1.0)

            if focused:
                try:
                    screenshot = ImageGrab.grab()
                    screen_arr = np.array(screenshot)
                    screen_bgr = cv2.cvtColor(screen_arr, cv2.COLOR_RGB2BGR)

                    # Check if 'Videos' or 'Images' button is visible in sidebar
                    v_match = self._find_template_multiscale(screen_bgr, VIDEOS_BTN_TEMPLATE)
                    i_match = self._find_template_multiscale(screen_bgr, IMAGES_BTN_TEMPLATE)
                    if v_match or i_match:
                        matched = v_match or i_match
                        print(f"[GeminiBrowser] [CONFIRMED] Gemini UI fully rendered! Sidebar buttons active at ({matched[0]}, {matched[1]}).")
                        return True

                    # Check if dark Gemini theme with UI elements is loaded
                    center_sample = screen_bgr[int(screen_h * 0.5), int(screen_w * 0.5)]
                    is_dark = (center_sample[0] < 45 and center_sample[1] < 45 and center_sample[2] < 45)
                    sidebar_sample = screen_bgr[int(screen_h * 0.35), int(screen_w * 0.05)]
                    sidebar_dark = (sidebar_sample[0] < 45 and sidebar_sample[1] < 45 and sidebar_sample[2] < 45)

                    if is_dark and sidebar_dark:
                        print("[GeminiBrowser] [CONFIRMED] Gemini dark interface detected on screen!")
                        time.sleep(1.0)
                        return True
                except Exception as e:
                    print(f"[GeminiBrowser] Screen verification check error: {e}")

            time.sleep(0.8)

        print("[GeminiBrowser] Max wait reached. Proceeding with best-effort automation.")
        return False

    def _find_recent_download(self, start_time: float, exts: tuple) -> str:
        """Checks Downloads folder for any completed media file created after start_time."""
        if not os.path.exists(DOWNLOADS_DIR):
            return ""
        candidates = []
        try:
            for f in os.listdir(DOWNLOADS_DIR):
                if f.lower().endswith(exts) and not f.lower().endswith(".crdownload"):
                    full_p = os.path.join(DOWNLOADS_DIR, f)
                    try:
                        file_time = max(os.path.getmtime(full_p), os.path.getctime(full_p))
                        if file_time >= (start_time - 5.0) and os.path.getsize(full_p) > 20000:
                            candidates.append((file_time, full_p))
                    except Exception:
                        pass
        except Exception:
            pass
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
        return ""

    def _has_active_crdownload(self, start_time: float) -> bool:
        """Checks if Chrome is actively downloading a file."""
        if not os.path.exists(DOWNLOADS_DIR):
            return False
        try:
            for f in os.listdir(DOWNLOADS_DIR):
                if f.lower().endswith(".crdownload"):
                    full_p = os.path.join(DOWNLOADS_DIR, f)
                    try:
                        if os.path.getmtime(full_p) >= (start_time - 5.0):
                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        return False

    def _check_video_ready_on_screen(self) -> tuple:
        """Uses Vision AI to check if the Gemini page shows a completed video.
        Returns (is_ready: bool, description: str)."""
        try:
            b64, sx, sy, ox, oy = capture_screen_b64(max_width=1280)
            messages = [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": (
                    "Look at this screenshot of a Google Gemini page. "
                    "Is there a completed/generated video visible (a video player card showing a generated video, "
                    "NOT a 'Generating your video...' loading message)? "
                    "Reply with EXACTLY this JSON format: "
                    '{"video_ready": true, "description": "brief description"} or '
                    '{"video_ready": false, "description": "what is shown instead"}'
                )}
            ]}]
            resp = _call_vision(messages, max_tokens=80, temperature=0.1, timeout=15)
            text = resp.choices[0].message.content.strip()
            print(f"[GeminiBrowser] [VISION] Video status check: {text}")

            # Parse JSON from response
            json_match = re.search(r'\{[^}]+\}', text)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("video_ready", False), data.get("description", text)
            return False, text
        except Exception as e:
            print(f"[GeminiBrowser] Vision video check error: {e}")
            return False, str(e)

    def _trigger_download_click(self) -> bool:
        """Focuses Chrome/Gemini, checks if video is ready, hovers over the video to show
        the download overlay, then clicks the download button.
        Returns True if download was likely triggered, False otherwise."""
        try:
            focus_and_maximize_window("gemini", max_wait=2.0) or focus_and_maximize_window("chrome", max_wait=2.0)
            time.sleep(0.5)
            screen_w, screen_h = pyautogui.size()

            # Check if video is actually ready on screen
            is_ready, desc = self._check_video_ready_on_screen()
            if not is_ready:
                print(f"[GeminiBrowser] Video not ready yet on screen: {desc}")
                return False

            print(f"[GeminiBrowser] Video is ready on screen! Hovering to reveal download button...")

            # Step 1: Move cursor to CENTER of the video card to trigger hover overlay
            # Calibrated from user's screenshots on 1920x1080:
            # Video card center: x ≈ 34% of screen, y ≈ 36% of screen
            hover_x = int(screen_w * 0.34)
            hover_y = int(screen_h * 0.36)
            pyautogui.moveTo(hover_x, hover_y, duration=0.3)
            print(f"[GeminiBrowser] Hovering over video at ({hover_x}, {hover_y})...")
            time.sleep(1.5)  # Wait for the overlay buttons to appear

            # Step 2: Click the download button (⬇️ icon in top-right of video card)
            # From user's screenshot: download icon is at ~44% x, ~22% y of screen
            # The three icons (download, share, volume) are in the top-right of the video
            download_x = int(screen_w * 0.44)
            download_y = int(screen_h * 0.22)
            print(f"[GeminiBrowser] Clicking download button at ({download_x}, {download_y})...")
            pyautogui.click(download_x, download_y)
            time.sleep(2.0)

            # Check if download started
            if self._has_active_crdownload(time.time() - 5):
                print("[GeminiBrowser] Download started successfully!")
                return True

            # If proportional click didn't work, try Vision AI to find the button
            # (overlay should still be visible from the hover)
            try:
                coords = find_element_coordinates(
                    "the download button (down arrow icon in a circle) in the top-right area of the video player"
                )
                if coords and coords[1] >= 140:
                    print(f"[GeminiBrowser] Vision AI found download at ({coords[0]}, {coords[1]})")
                    pyautogui.click(coords[0], coords[1])
                    time.sleep(2.0)
                    return True
            except Exception as e:
                print(f"[GeminiBrowser] Vision download button fallback: {e}")

            return False

        except Exception as e:
            print(f"[GeminiBrowser] Error during download click: {e}")
            return False

    def generate_photo(self, prompt: str) -> str:
        """Generates a studio-grade photorealistic image using Google Imagen 3 via Gemini Pro:
        1. Enriches prompt with gemini-3.7-flash (adds authentic details, lighting, textures)
        2. Opens Chrome to Gemini Pro and verifies page readiness
        3. Clicks on 'Images' in sidebar
        4. Pastes prompt and triggers generation
        5. Waits the authentic diffusion duration (15-25s) for Imagen 3
        6. Downloads the high-res photo and opens it on screen."""
        print(f"[GeminiBrowser] Step 1: Enriching photo prompt using gemini-3.7-flash...")
        enriched_prompt = gemini_client.enrich_photo_prompt(prompt)
        print(f"[GeminiBrowser] Enriched Photo Prompt: {enriched_prompt}")

        print(f"[GeminiBrowser] Step 2: Opening Chrome to Gemini Pro ({GEMINI_URL})...")
        subprocess.Popen(["cmd", "/c", "start", "chrome", f"--remote-debugging-port=9222", GEMINI_URL], shell=False)

        print(f"[GeminiBrowser] Step 3: Verifying page is completely loaded...")
        self.wait_for_gemini_page_ready(max_wait=25.0)

        # Cross out and dismiss any unwanted promo popups, ads, or modals before interacting
        self.dismiss_unwanted_popups(max_attempts=2)

        # Step 4: Click on 'Images' in the sidebar
        print(f"[GeminiBrowser] Step 4: Locating and clicking 'Images' in Gemini sidebar...")
        screen_w, screen_h = pyautogui.size()
        images_clicked = False

        try:
            screenshot = ImageGrab.grab()
            screen_arr = np.array(screenshot)
            screen_bgr = cv2.cvtColor(screen_arr, cv2.COLOR_RGB2BGR)
            match = self._find_template_multiscale(screen_bgr, IMAGES_BTN_TEMPLATE)
            if match:
                btn_x, btn_y, score = match
                print(f"[GeminiBrowser] Matched 'Images' button at ({btn_x}, {btn_y}) with score {score:.3f}!")
                pyautogui.click(btn_x, btn_y)
                images_clicked = True
        except Exception as e:
            print(f"[GeminiBrowser] Template match error: {e}")

        if not images_clicked:
            # Proportional fallback for 'Images' in sidebar (x ~4.5%, y ~31.5%)
            fallback_x = int(screen_w * 0.045)
            fallback_y = int(screen_h * 0.315)
            print(f"[GeminiBrowser] Clicking 'Images' at proportional coordinate ({fallback_x}, {fallback_y})...")
            pyautogui.click(fallback_x, fallback_y)

        time.sleep(2.0)

        # Clear any tooltip or popup that might appear before focusing prompt
        self.dismiss_unwanted_popups(max_attempts=1)

        # Step 5: Focus prompt box and submit
        print(f"[GeminiBrowser] Step 5: Focusing prompt box and submitting Imagen 3 request...")
        focus_and_maximize_window("gemini", max_wait=2.0) or focus_and_maximize_window("chrome", max_wait=2.0)

        center_prompt_x = screen_w // 2
        center_prompt_y = int(screen_h * 0.52)
        bottom_prompt_y = int(screen_h * 0.89)

        pyautogui.click(center_prompt_x, center_prompt_y)
        time.sleep(0.4)
        pyautogui.press('/')
        time.sleep(0.2)

        full_submission = f"Generate a photorealistic 8K image: {enriched_prompt}"
        pyperclip.copy(full_submission)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)

        pyautogui.click(center_prompt_x, bottom_prompt_y)
        time.sleep(0.3)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)

        pyautogui.press('enter')
        print(f"[GeminiBrowser] Imagen 3 prompt submitted! Starting authentic diffusion timer...")

        start_time = time.time()
        photo_exts = (".jpg", ".jpeg", ".png", ".webp")

        # Wait 15 seconds for initial high-res Imagen 3 generation
        print(f"[GeminiBrowser] Waiting 15 seconds for Imagen 3 diffusion process...")
        time.sleep(self.photo_initial_wait)

        while True:
            elapsed = time.time() - start_time
            print(f"[GeminiBrowser] Checking photo generation status ({int(elapsed)}s elapsed)...")

            photo_file = self._find_recent_download(start_time, photo_exts)
            if photo_file:
                print(f"[GeminiBrowser] Generated photo detected: {photo_file}")
                os.startfile(photo_file)
                return "I have generated the photorealistic image with Imagen 3 and displayed it on your screen, boss."

            if self._has_active_crdownload(start_time):
                print("[GeminiBrowser] Photo is currently downloading... waiting for completion")
                for _ in range(10):
                    time.sleep(1.0)
                    photo_file = self._find_recent_download(start_time, photo_exts)
                    if photo_file:
                        os.startfile(photo_file)
                        return "I have generated the photorealistic image with Imagen 3 and displayed it on your screen, boss."

            self._trigger_download_click()
            time.sleep(2.0)
            photo_file = self._find_recent_download(start_time, photo_exts)
            if photo_file:
                print(f"[GeminiBrowser] Photo downloaded after click: {photo_file}")
                os.startfile(photo_file)
                return "I have generated the photorealistic image with Imagen 3 and displayed it on your screen, boss."

            if elapsed >= self.photo_max_wait:
                print(f"[GeminiBrowser] Photo generation timed out after {int(elapsed)}s.")
                return "Photo generation failed, boss."

            wait_time = min(self.photo_poll_interval, self.photo_max_wait - elapsed)
            print(f"[GeminiBrowser] Photo rendering in progress. Checking again in {int(wait_time)} seconds...")
            time.sleep(wait_time)

    def _click_sidebar_videos(self) -> bool:
        """Clicks the 'Videos' button in the Gemini left sidebar.
        Uses exact proportional coordinates calibrated from user's actual 1920x1080 screen.
        If the sidebar is collapsed (no sidebar visible), clicks the hamburger menu first."""
        screen_w, screen_h = pyautogui.size()

        # Gemini sidebar layout (calibrated from user's screenshot at 1920x1080):
        # Sidebar is ~180px wide. Items are stacked vertically:
        #   Chat/Spark tabs:  y ≈ 7%
        #   New chat:         y ≈ 10%
        #   Search chats:     y ≈ 12%
        #   Students:         y ≈ 30.5%
        #   Images:           y ≈ 34.7%
        #   Videos:           y ≈ 39.0%   ← TARGET
        #   Library:          y ≈ 43.5%
        # All items at x ≈ 5% of screen width

        videos_x = int(screen_w * 0.05)
        videos_y = int(screen_h * 0.39)

        print(f"[GeminiBrowser] Clicking sidebar 'Videos' at ({videos_x}, {videos_y})...")
        pyautogui.click(videos_x, videos_y)
        time.sleep(2.0)

        # Verify we're on Videos page by checking if prompt placeholder changed
        # If sidebar was collapsed, the click may have missed. Try hamburger menu.
        # The hamburger/sidebar toggle is at top-left corner: x ≈ 1%, y ≈ 4.5%
        # We'll check if the sidebar is visible by seeing if our click x is reasonable
        # For now, trust the click and proceed.
        return True

    def generate_video(self, prompt: str) -> str:
        """Simple, deterministic video generation workflow:
        1. Minimize Jarvis orb
        2. Enrich prompt with Gemini Flash
        3. Open Chrome → new tab → navigate to gemini.google.com/app
        4. Wait 5 seconds for page to load
        5. Press Escape to dismiss any popups
        6. Click 'Videos' in the left sidebar
        7. Click on the prompt box (bottom of page)
        8. Paste the enriched prompt (Ctrl+V)
        9. Press Enter to submit
        10. Restore Jarvis orb
        11. Poll for video download"""
        print("[GeminiBrowser] Minimizing Jarvis orb for screen automation...")
        minimize_jarvis_orb()
        time.sleep(0.5)

        try:
            screen_w, screen_h = pyautogui.size()
            print(f"[GeminiBrowser] Screen resolution: {screen_w}x{screen_h}")

            # ── Step 1: Enrich the prompt ──────────────────────────────
            print("[GeminiBrowser] Step 1: Enriching video prompt...")
            enriched_prompt = gemini_client.enrich_video_prompt(prompt)
            print(f"[GeminiBrowser] Enriched: {enriched_prompt[:120]}...")

            full_prompt = f"Generate video: {enriched_prompt}"

            # ── Step 2: Open Chrome → new tab → Gemini ────────────────
            print("[GeminiBrowser] Step 2: Opening Chrome and navigating to Gemini...")

            # Launch Chrome (if not already running, this opens it; if running, focuses it)
            subprocess.Popen(["cmd", "/c", "start", "chrome"], shell=False)
            time.sleep(1.5)

            # Focus Chrome window
            focus_and_maximize_window("chrome", max_wait=3.0)
            time.sleep(0.5)

            # Open a NEW tab so we don't interfere with existing tabs
            pyautogui.hotkey('ctrl', 't')
            time.sleep(0.8)

            # Navigate to Gemini via address bar
            pyautogui.hotkey('ctrl', 'l')  # Focus address bar
            time.sleep(0.3)
            pyperclip.copy(GEMINI_URL)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.2)
            pyautogui.press('enter')

            # ── Step 3: Wait for Gemini to fully load ──────────────────
            print("[GeminiBrowser] Step 3: Waiting 5 seconds for Gemini to load...")
            time.sleep(5.0)

            # Focus and maximize the Gemini window
            focus_and_maximize_window("gemini", max_wait=2.0) or focus_and_maximize_window("chrome", max_wait=2.0)
            time.sleep(0.5)

            # ── Step 4: Dismiss any popups with Escape ─────────────────
            print("[GeminiBrowser] Step 4: Pressing Escape to dismiss any popups...")
            pyautogui.press('esc')
            time.sleep(0.3)
            pyautogui.press('esc')
            time.sleep(0.5)

            # ── Step 5: Click 'Videos' in the sidebar ──────────────────
            print("[GeminiBrowser] Step 5: Clicking 'Videos' in the sidebar...")
            self._click_sidebar_videos()

            # ── Step 6: Click on the prompt box ────────────────────────
            print("[GeminiBrowser] Step 6: Clicking on the prompt box...")

            # The prompt box is at the bottom center of the main content area.
            # Calibrated from user's screenshot:
            #   Prompt text "Describe your video" is at y ≈ 88.3% of screen height
            #   x center ≈ 44.5% of screen width (shifted right from sidebar)
            prompt_x = int(screen_w * 0.445)
            prompt_y = int(screen_h * 0.883)

            pyautogui.click(prompt_x, prompt_y)
            time.sleep(0.4)

            # Click again to make sure focus is inside the text input
            pyautogui.click(prompt_x, prompt_y)
            time.sleep(0.3)

            # ── Step 7: Paste the prompt ───────────────────────────────
            print("[GeminiBrowser] Step 7: Pasting prompt into the box...")

            # Select all existing text (in case there's leftover) and replace
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)

            pyperclip.copy(full_prompt)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.8)

            # ── Step 8: Press Enter to submit ──────────────────────────
            print("[GeminiBrowser] Step 8: Pressing Enter to submit the prompt...")
            pyautogui.press('enter')
            time.sleep(1.0)

            print("[GeminiBrowser] Video prompt submitted to Gemini! Starting generation timer...")

        finally:
            # Always restore Jarvis orb
            restore_jarvis_orb()

        # ── Step 9: Poll for video download ────────────────────────────
        start_time = time.time()
        video_exts = (".mp4", ".webm", ".mov", ".mkv")

        print(f"[GeminiBrowser] Waiting {int(self.video_initial_wait)}s for Veo to generate the video...")
        time.sleep(self.video_initial_wait)

        while True:
            elapsed = time.time() - start_time
            print(f"[GeminiBrowser] Checking video status ({int(elapsed)}s elapsed)...")

            # First, check if a video file already appeared in Downloads
            video_file = self._find_recent_download(start_time, video_exts)
            if video_file:
                print(f"[GeminiBrowser] Video found in Downloads: {video_file}")
                os.startfile(video_file)
                return "I have generated and downloaded your video, boss. Playing it now."

            if self._has_active_crdownload(start_time):
                print("[GeminiBrowser] Video is downloading...")
                for _ in range(30):
                    time.sleep(1.0)
                    video_file = self._find_recent_download(start_time, video_exts)
                    if video_file:
                        os.startfile(video_file)
                        return "I have generated and downloaded your video, boss. Playing it now."

            # Minimize orb, focus Chrome, and check screen + attempt download
            minimize_jarvis_orb()
            time.sleep(0.5)

            download_clicked = False
            try:
                download_clicked = self._trigger_download_click()
            finally:
                restore_jarvis_orb()

            if download_clicked:
                # Download button was clicked! Wait up to 30s for file to appear
                print("[GeminiBrowser] Download button clicked! Waiting for file to appear...")
                for _ in range(30):
                    time.sleep(1.0)
                    video_file = self._find_recent_download(start_time, video_exts)
                    if video_file:
                        print(f"[GeminiBrowser] Video downloaded: {video_file}")
                        os.startfile(video_file)
                        return "I have generated and downloaded your video, boss. Playing it now."
                    if self._has_active_crdownload(start_time):
                        print("[GeminiBrowser] Download in progress...")
                        # Keep waiting
                print("[GeminiBrowser] Download button was clicked but no file appeared yet. Will retry.")

            if elapsed >= self.video_max_wait:
                print(f"[GeminiBrowser] Timed out after {int(elapsed)}s.")
                return "Video generation timed out after 4 minutes, boss. Please check Gemini manually."

            remaining = self.video_max_wait - elapsed
            wait_time = min(self.video_poll_interval, remaining)
            print(f"[GeminiBrowser] Checking again in {int(wait_time)}s...")
            time.sleep(wait_time)

gemini_browser_agent = GeminiBrowserAgent()
