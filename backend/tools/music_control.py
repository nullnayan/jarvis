# FILE: backend/tools/music_control.py
# Smart mood-based and query-based music playback.

import urllib.parse
import webbrowser

MOOD_MAP = {
    "chill": "lo-fi hip hop chill beats live stream",
    "lofi": "lofi hip hop radio beats to relax study to",
    "lo-fi": "lofi hip hop radio beats to relax study to",
    "workout": "gym motivation workout music mix",
    "gym": "hardstyle gym workout motivation mix",
    "focus": "deep focus ambient study music",
    "study": "binaural beats deep focus study music",
    "party": "latest party dance hits playlist",
    "sleep": "relaxing sleep music rain sounds",
    "rock": "classic rock greatest hits playlist"
}

def music_control(params: dict) -> str:
    query = str(params.get("query", "")).strip()
    mood = str(params.get("mood", "")).strip().lower()

    target = query
    if not target and mood:
        target = MOOD_MAP.get(mood, f"{mood} music playlist")
    elif not target:
        target = "lo-fi hip hop chill beats"

    for k, v in MOOD_MAP.items():
        if k in target.lower():
            target = v
            break

    encoded = urllib.parse.quote(target)
    youtube_url = f"https://www.youtube.com/results?search_query={encoded}"

    print(f"[MusicControl] Playing: '{target}'")
    webbrowser.open(youtube_url)
    return f"Playing {target} for you, boss."
