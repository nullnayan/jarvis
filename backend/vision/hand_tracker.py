# FILE: backend/vision/hand_tracker.py
# Real-time hand tracking module using OpenCV and MediaPipe Hands / HandLandmarker.
# Computes palm centroid, wrist orientation (yaw/pitch/roll), hand depth/scale,
# pinch ratio, and finger spread ratio for 3D globe gesture control.

import os
import time
import math
import threading
import urllib.request
from typing import Callable, Optional

try:
    import cv2
    import numpy as np
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False


def _euclidean_dist_3d(p1, p2) -> float:
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2 + (p1.z - p2.z) ** 2)


class HandTracker:
    TASK_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

    def __init__(
        self,
        on_gesture_callback: Optional[Callable[[dict], None]] = None,
        camera_index: int = 0,
        fps: int = 30,
        min_detection_confidence: float = 0.65,
        min_tracking_confidence: float = 0.55
    ):
        self.on_gesture = on_gesture_callback
        self.camera_index = camera_index
        self.target_fps = fps
        self.frame_interval = 1.0 / max(1, fps)
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._last_detected = False

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True

        self._thread = threading.Thread(target=self._run_loop, name="HandTrackerThread", daemon=True)
        self._thread.start()
        print(f"[HandTracker] Started webcam tracking on camera index {self.camera_index}")

    def stop(self):
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._last_detected = False
        print("[HandTracker] Stopped hand tracking")

    def _ensure_task_model(self) -> str:
        model_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(model_dir, "hand_landmarker.task")
        if not os.path.exists(model_path) or os.path.getsize(model_path) < 1000000:
            print("[HandTracker] Downloading hand_landmarker.task model...")
            urllib.request.urlretrieve(self.TASK_MODEL_URL, model_path)
            print("[HandTracker] Model downloaded successfully.")
        return model_path

    def _run_loop(self):
        if not MEDIAPIPE_AVAILABLE:
            print("[HandTracker] MediaPipe or OpenCV not installed; hand tracking disabled.")
            with self._lock:
                self._running = False
            return

        cap = None
        detector = None
        use_tasks_api = False

        try:
            # 1. Initialize MediaPipe Detector
            if hasattr(mp, 'tasks') and hasattr(mp.tasks, 'vision'):
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision as mp_vision
                model_path = self._ensure_task_model()
                base_options = mp_python.BaseOptions(model_asset_path=model_path)
                options = mp_vision.HandLandmarkerOptions(
                    base_options=base_options,
                    running_mode=mp_vision.RunningMode.IMAGE,
                    num_hands=1,
                    min_hand_detection_confidence=self.min_detection_confidence,
                    min_hand_presence_confidence=self.min_tracking_confidence,
                    min_tracking_confidence=self.min_tracking_confidence
                )
                detector = mp_vision.HandLandmarker.create_from_options(options)
                use_tasks_api = True
            elif hasattr(mp, 'solutions') and hasattr(mp.solutions, 'hands'):
                detector = mp.solutions.hands.Hands(
                    static_image_mode=False,
                    max_num_hands=1,
                    min_detection_confidence=self.min_detection_confidence,
                    min_tracking_confidence=self.min_tracking_confidence
                )
                use_tasks_api = False
            else:
                print("[HandTracker] No compatible MediaPipe Hands API found.")
                with self._lock:
                    self._running = False
                return

            # 2. Open Webcam
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.camera_index)

            if not cap.isOpened():
                print(f"[HandTracker] Failed to open webcam at index {self.camera_index}")
                with self._lock:
                    self._running = False
                return

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, self.target_fps)

            print("[HandTracker] Camera and MediaPipe Hands pipeline initialized successfully.")

            while True:
                with self._lock:
                    if not self._running:
                        break

                start_time = time.monotonic()
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.02)
                    continue

                # Flip horizontally for natural mirror behavior
                frame = cv2.flip(frame, 1)

                # MediaPipe expects RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                landmarks_list = None
                if use_tasks_api:
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    results = detector.detect(mp_image)
                    if results.hand_landmarks and len(results.hand_landmarks) > 0:
                        landmarks_list = results.hand_landmarks[0]
                else:
                    rgb_frame.flags.writeable = False
                    results = detector.process(rgb_frame)
                    if results.multi_hand_landmarks:
                        landmarks_list = results.multi_hand_landmarks[0].landmark

                if landmarks_list:
                    gesture_data = self._compute_gesture_metrics(landmarks_list)
                    gesture_data["detected"] = True
                    self._last_detected = True

                    if self.on_gesture:
                        try:
                            self.on_gesture(gesture_data)
                        except Exception as cb_err:
                            print(f"[HandTracker] Callback error: {cb_err}")
                else:
                    if self._last_detected:
                        self._last_detected = False
                        if self.on_gesture:
                            try:
                                self.on_gesture({
                                    "detected": False,
                                    "palm_x": 0.0,
                                    "palm_y": 0.0,
                                    "yaw": 0.0,
                                    "pitch": 0.0,
                                    "roll": 0.0,
                                    "scale": 1.0,
                                    "pinch": 1.0,
                                    "spread": 0.0
                                })
                            except Exception as cb_err:
                                print(f"[HandTracker] Undetected callback error: {cb_err}")

                elapsed = time.monotonic() - start_time
                sleep_time = self.frame_interval - elapsed
                if sleep_time > 0.001:
                    time.sleep(sleep_time)

        except Exception as e:
            print(f"[HandTracker] Exception in tracking loop: {e}")
        finally:
            if detector and hasattr(detector, 'close'):
                try:
                    detector.close()
                except Exception:
                    pass
            if cap:
                try:
                    cap.release()
                except Exception:
                    pass
            print("[HandTracker] Webcam and MediaPipe resources released.")

    def _compute_gesture_metrics(self, lm) -> dict:
        """
        Computes normalized coordinates and metrics from 21 MediaPipe hand landmarks.
        Landmark indices:
          0: Wrist
          5: Index MCP, 9: Middle MCP, 13: Ring MCP, 17: Pinky MCP
          4: Thumb TIP, 8: Index TIP, 12: Middle TIP, 16: Ring TIP, 20: Pinky TIP
        """
        # 1. Palm Centroid: average of wrist and the 4 finger MCP joints
        palm_raw_x = (lm[0].x + lm[5].x + lm[9].x + lm[13].x + lm[17].x) / 5.0
        palm_raw_y = (lm[0].y + lm[5].y + lm[9].y + lm[13].y + lm[17].y) / 5.0

        # Map from [0, 1] camera image to Three.js normalized [-1.0, 1.0]
        # In mirrored camera frame: X=0 is left, X=1 is right. Center is 0.5.
        palm_x = (palm_raw_x - 0.5) * 2.0
        # In image coords, Y increases downward. In 3D space, +Y is UP. So negate:
        palm_y = -(palm_raw_y - 0.5) * 2.0

        # 2. Hand Orientation / Wrist Angles
        # Vector up: wrist (0) to middle MCP (9)
        up_x = lm[9].x - lm[0].x
        up_y = -(lm[9].y - lm[0].y)  # invert Y for 3D coordinate system
        up_z = -(lm[9].z - lm[0].z)  # MediaPipe Z is closer to camera for negative

        # Vector right: index MCP (5) to pinky MCP (17)
        right_x = lm[17].x - lm[5].x
        right_y = -(lm[17].y - lm[5].y)
        right_z = -(lm[17].z - lm[5].z)

        # Roll: rotation around camera forward axis (Z) - tilting wrist left/right
        roll = math.atan2(up_x, up_y)

        # Pitch: forward/backward tilt of hand
        pitch = math.atan2(up_z, math.hypot(up_x, up_y))

        # Yaw: side-to-side rotation around vertical axis (Y)
        yaw = math.atan2(right_z, math.hypot(right_x, right_y))

        # 3. Hand Depth / Scale
        # Distance from wrist (0) to middle fingertip (12)
        hand_span = _euclidean_dist_3d(lm[0], lm[12])
        # Baseline span at comfortable webcam distance (~50-60cm) is approx 0.35
        raw_scale = hand_span / 0.35
        scale = max(0.4, min(2.5, raw_scale))

        # 4. Pinch Ratio
        # Distance between thumb tip (4) and index tip (8)
        pinch_dist = _euclidean_dist_3d(lm[4], lm[8])
        # When pinched, pinch_dist is typically < 0.045; when open, > 0.18
        pinch = max(0.0, min(1.0, (pinch_dist - 0.04) / 0.16))

        # 5. Spread Ratio
        # Average distance between consecutive fingertips: (4-8, 8-12, 12-16, 16-20)
        d_01 = _euclidean_dist_3d(lm[4], lm[8])
        d_12 = _euclidean_dist_3d(lm[8], lm[12])
        d_23 = _euclidean_dist_3d(lm[12], lm[16])
        d_34 = _euclidean_dist_3d(lm[16], lm[20])
        avg_spread = (d_01 + d_12 + d_23 + d_34) / 4.0
        # Closed fingers avg ~0.055, fully spread fingers avg ~0.16
        spread = max(0.0, min(1.0, (avg_spread - 0.055) / 0.11))

        return {
            "palm_x": round(palm_x, 4),
            "palm_y": round(palm_y, 4),
            "yaw": round(yaw, 4),
            "pitch": round(pitch, 4),
            "roll": round(roll, 4),
            "scale": round(scale, 4),
            "pinch": round(pinch, 4),
            "spread": round(spread, 4),
        }
