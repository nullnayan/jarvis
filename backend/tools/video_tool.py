# FILE: backend/tools/video_tool.py
# Understands and generates video content using Gemini and video synthesis endpoints.

import os
from llm.gemini_client import gemini_client
from tools.gemini_browser_agent import gemini_browser_agent

def video_tool(params: dict) -> str:
    action = params.get("action", "understand").lower().strip()
    path = params.get("path", "").strip()
    prompt = params.get("prompt", "").strip()
    question = params.get("question", "Explain what is happening in this video in detail.")
    destination = params.get("destination", "pictures")

    if action in ("understand", "analyze", "explain", "read"):
        if not path:
            # Check Desktop/Downloads/Videos for the most recent video file
            user_home = os.path.expanduser("~")
            candidate_dirs = [
                os.path.join(user_home, "Videos"),
                os.path.join(user_home, "Downloads"),
                os.path.join(user_home, "Desktop")
            ]
            recent_file = None
            recent_mtime = 0
            for d in candidate_dirs:
                if os.path.exists(d):
                    for f in os.listdir(d):
                        if f.lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".webm")):
                            full_p = os.path.join(d, f)
                            mt = os.path.getmtime(full_p)
                            if mt > recent_mtime:
                                recent_mtime = mt
                                recent_file = full_p
            if recent_file:
                path = recent_file
            else:
                return "Please specify the video file path you want me to analyze, boss."

        return gemini_client.understand_video(path, question=question)

    elif action in ("generate", "create", "make"):
        if not prompt:
            return "Please describe the video you would like me to generate, boss."
        return gemini_browser_agent.generate_video(prompt=prompt)

    return "Please specify whether to understand or generate a video, boss."
