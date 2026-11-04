# FILE: backend/tools/youtube_intel.py
# Fetches YouTube transcripts and summarizes video content using Gemini Flash.

import re
from youtube_transcript_api import YouTubeTranscriptApi
from llm.gemini_client import gemini_client
from tools.context import get_active_window

def _extract_video_id(url: str) -> str | None:
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
        r'embed\/([0-9A-Za-z_-]{11})',
        r'shorts\/([0-9A-Za-z_-]{11})'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def youtube_intel(params: dict) -> str:
    url = str(params.get("url", "")).strip()

    if not url:
        # Check active window title for youtube URL / video ID
        win = get_active_window()
        title = win.get("title", "")
        extracted = _extract_video_id(title)
        if extracted:
            vid = extracted
        else:
            return "Please provide the YouTube video link you want me to summarize, boss."
    else:
        vid = _extract_video_id(url)
        if not vid:
            return "That does not appear to be a valid YouTube URL, boss."

    try:
        print(f"[YouTubeIntel] Fetching transcript for video ID: {vid}")
        # Try fetching transcript
        ytt = YouTubeTranscriptApi()
        # Newer youtube_transcript_api versions support get_transcript directly or via instance
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(vid)
        except AttributeError:
            transcript_list = ytt.get_transcript(vid)

        full_text = " ".join([entry.get("text", "") for entry in transcript_list])
        if not full_text.strip():
            return "I could not find an English transcript for this video, boss."

        summary = gemini_client.summarize(full_text, max_sentences=3)
        return f"Here is the video summary, boss: {summary}"
    except Exception as e:
        print(f"[YouTubeIntel] Transcript error: {e}")
        return "Could not retrieve the transcript for this video. Captions might be disabled, boss."
