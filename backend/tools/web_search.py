# FILE: web_search.py
# Searches the web using DuckDuckGo (ddgs) and returns summarized results.
from ddgs import DDGS

def web_search(params: dict) -> str:
    query = params.get("query", "").strip()
    if not query:
        return "No search query provided"
    try:
        results = DDGS().text(query, max_results=3)
        if not results:
            return f"No results found for: {query}"
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title', 'No title')}")
            lines.append(f"   {r.get('body', 'No description')}")
            lines.append(f"   {r.get('href', '')}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[WebSearch] Error: {e}")
        return "An error occurred, boss."
