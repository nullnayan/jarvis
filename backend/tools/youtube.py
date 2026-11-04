# FILE: youtube.py
# Searches YouTube, finds the first video, and opens it in specified or default browser.
import urllib.parse
import re
import httpx
from tools.app_launcher import open_url_in_browser

def youtube_play(params: dict) -> str:
    query = params.get("query", "").strip()
    browser = params.get("browser", "").strip()
    target_browser = f" on {browser.title()}" if browser else ""

    if not query:
        open_url_in_browser("https://www.youtube.com", browser=browser)
        return f"Opened YouTube{target_browser}, boss."

    try:
        # Fetch YouTube search page and extract first video ID
        search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
        resp = httpx.get(search_url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        match = re.search(r'/watch\?v=([a-zA-Z0-9_-]{11})', resp.text)
        if match:
            video_url = f"https://www.youtube.com/watch?v={match.group(1)}"
            open_url_in_browser(video_url, browser=browser)
            return f"Playing {query} on YouTube{target_browser}, boss."
    except Exception as e:
        print(f"[YouTube] Direct video link failed, opening search: {e}")

    # Fallback: open search results page
    fallback_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    open_url_in_browser(fallback_url, browser=browser)
    return f"Searching YouTube for {query}{target_browser}, boss."
