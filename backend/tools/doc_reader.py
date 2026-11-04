# FILE: backend/tools/doc_reader.py
# Reads and summarizes documents (PDF, DOCX, TXT, code) using Gemini Flash.

import os
from llm.gemini_client import gemini_client

def _find_recent_doc(directory: str, extensions: tuple) -> str | None:
    if not os.path.exists(directory):
        return None
    recent_file, recent_mtime = None, 0
    for f in os.listdir(directory):
        if f.lower().endswith(extensions):
            full_p = os.path.join(directory, f)
            mt = os.path.getmtime(full_p)
            if mt > recent_mtime:
                recent_mtime = mt
                recent_file = full_p
    return recent_file

def _extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    if ext in (".txt", ".py", ".js", ".html", ".css", ".json", ".md", ".csv"):
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    elif ext == ".pdf":
        try:
            import PyPDF2
            text = []
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages[:15]:
                    text.append(page.extract_text() or "")
            return "\n".join(text)
        except Exception as e:
            return f"Error reading PDF: {e}"

    elif ext in (".docx", ".doc"):
        try:
            import docx
            doc = docx.Document(file_path)
            return "\n".join([p.text for p in doc.paragraphs])
        except Exception as e:
            return f"Error reading Word document: {e}"

    return ""

def _is_restricted_file(file_path: str) -> bool:
    norm = os.path.normpath(file_path).lower()
    base = os.path.basename(norm)
    if any(k in norm for k in (".secrets", ".env", "vault", "credential", "id_rsa", "token")):
        return True
    if base in ("config.py", ".secrets.enc", ".env", ".env.local", "vault.py"):
        return True
    return False

def doc_reader(params: dict) -> str:
    file_path = str(params.get("path", "")).strip()
    user_home = os.path.expanduser("~")

    if file_path and _is_restricted_file(file_path):
        print(f"[DocReader] BLOCKED access to restricted file: {file_path}")
        return "Access to security-critical configuration files is restricted, boss."

    if not file_path or not os.path.exists(file_path):
        # Auto-detect latest document in Desktop or Downloads
        doc_exts = (".pdf", ".docx", ".txt", ".md")
        candidate = _find_recent_doc(os.path.join(user_home, "Desktop"), doc_exts) or \
                    _find_recent_doc(os.path.join(user_home, "Downloads"), doc_exts)
        if candidate:
            file_path = candidate
        else:
            return "Please provide the path of the document you would like me to read, boss."

    text = _extract_text(file_path)
    if not text or not text.strip():
        return f"I could not extract any readable text from {os.path.basename(file_path)}, boss."

    fname = os.path.basename(file_path)
    summary = gemini_client.summarize(text)
    return f"Here is the summary of {fname}, boss: {summary}"
