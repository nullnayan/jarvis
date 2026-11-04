"""Read-only self-inspection tools for the Jarvis source tree."""

from self_dev.repo_map import list_source_files, project_summary, read_source, search_source


def self_code(params: dict) -> str:
    """List, read, search, or summarize Jarvis's own source code."""
    action = str(params.get("action", "")).strip().lower()

    if action == "list":
        files = list_source_files()
        if not files:
            return "I could not list the source files, boss."
        main_files = ", ".join(path[:40] for path in files[:8])
        return f"I have {len(files)} source files, boss. The main ones are: {main_files}."

    if action == "read":
        path = str(params.get("path", "")).strip()
        if not path:
            return "Which file should I read, boss?"
        content = read_source(path)
        return content if len(content) < 400 else content[:400] + "..."

    if action == "search":
        query = str(params.get("query", "")).strip()
        if not query:
            return "What should I search for, boss?"
        hits = search_source(query)
        if not hits:
            return "I found no matches, boss."
        return " | ".join(hits[:10])

    if action == "summary":
        return project_summary() + ", boss."

    if action == "last_changes":
        try:
            from security.audit_log import read_recent
            changes = [entry for entry in read_recent(20) if entry.get("tool") == "self_fix"][-3:]
            if not changes:
                return "I have no recorded self-changes yet, boss."
            summary = "; ".join(
                f"{', '.join(entry.get('files_changed', [])) or 'a source file'} at {entry.get('timestamp', '')[:16]}"
                for entry in changes
            )
            return f"My most recent changes were: {summary}, boss."
        except Exception:
            return "I could not read the change history, boss."

    return "Self-code action not recognized, boss."
