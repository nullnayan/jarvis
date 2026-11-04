# FILE: file_manager.py
# File and folder operations including deletion and instant Recycle Bin management.
import os
import shutil
import ctypes
from ctypes import wintypes

def empty_recycle_bin(params: dict = None) -> str:
    """Empties the Windows Recycle Bin across all drives instantly using Win32 API."""
    try:
        shell32 = ctypes.windll.shell32
        shell32.SHEmptyRecycleBinW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD]
        shell32.SHEmptyRecycleBinW.restype = ctypes.c_long
        # Flags: SHERB_NOCONFIRMATION=1, SHERB_NOPROGRESSUI=2, SHERB_NOSOUND=4 (1+2+4=7)
        hr = shell32.SHEmptyRecycleBinW(None, None, 7)
        # S_OK (0) or already empty status codes (0x8000ffff, 0x80070002)
        if hr in (0, -2147418113, -2147024894):
            return "The Recycle Bin has been emptied, boss."
        print(f"[FileManager] Recycle Bin HRESULT: {hr}")
        return "An error occurred, boss."
    except Exception as e:
        print(f"[FileManager] Error emptying Recycle Bin: {e}")
        return "An error occurred, boss."

def clean_target_candidates(target: str) -> list[str]:
    """Generates candidate target names by stripping common conversational qualifiers."""
    clean = target.strip(' "\'').replace('/', '\\')
    candidates = [clean]

    # Conversational prefixes to strip
    lower = clean.lower()
    prefixes = [
        "the folder called ", "the folder named ", "folder called ", "folder named ",
        "the file called ", "the file named ", "file called ", "file named ",
        "the folder ", "folder ", "the file ", "file ", "the "
    ]
    for p in prefixes:
        if lower.startswith(p):
            stripped = clean[len(p):].strip()
            if stripped:
                candidates.append(stripped)
            break

    # Conversational suffixes to strip
    suffixes = [
        " from my desktop", " from desktop", " on my desktop", " on desktop",
        " from my downloads", " from downloads", " on my downloads", " on downloads",
        " from my documents", " from documents", " on my documents", " on documents",
        " folder", " file"
    ]
    for c in list(candidates):
        c_lower = c.lower()
        for s in suffixes:
            if c_lower.endswith(s):
                stripped = c[:len(c) - len(s)].strip()
                if stripped:
                    candidates.append(stripped)

    # Space / underscore / hyphen variations (e.g. "test folder" -> "test_folder")
    for c in list(candidates):
        if " " in c:
            candidates.append(c.replace(" ", "_"))
            candidates.append(c.replace(" ", "-"))
            candidates.append(c.replace(" ", ""))
        if "_" in c:
            candidates.append(c.replace("_", " "))
            candidates.append(c.replace("_", "-"))
        if "-" in c:
            candidates.append(c.replace("-", " "))
            candidates.append(c.replace("-", "_"))

    # Unique candidates preserving order
    seen = set()
    result = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result

def resolve_file_path(target: str) -> str | None:
    """Finds the full absolute path of a target file or folder across common user directories."""
    candidates = clean_target_candidates(target)
    search_roots = [
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Documents"),
        os.getcwd(),
    ]

    for cand in candidates:
        # Check direct or expanded path
        expanded = os.path.expanduser(cand)
        if os.path.exists(expanded):
            return os.path.abspath(expanded)

        # Check in common directories
        for root in search_roots:
            candidate_path = os.path.join(root, cand)
            if os.path.exists(candidate_path):
                return os.path.abspath(candidate_path)

        # Fuzzy match by base name in Desktop, Downloads, Documents
        cand_lower = cand.lower()
        for root in search_roots:
            if os.path.exists(root):
                try:
                    for entry in os.listdir(root):
                        if entry.lower() == cand_lower:
                            return os.path.join(root, entry)
                except Exception:
                    pass

    return None

def delete_item(params: dict) -> str:
    """Deletes any file or folder by path or name safely with clean voice response."""
    target = params.get("target") or params.get("path") or params.get("name") or ""
    if not target:
        return "No file or folder was specified to delete, boss."

    try:
        resolved = resolve_file_path(target)
        if not resolved or not os.path.exists(resolved):
            print(f"[FileManager] Target not found: {target}")
            return "An error occurred, boss."

        # Never allow deleting critical system or user root folders
        lower_resolved = os.path.abspath(resolved).lower()
        critical_paths = [
            r"c:\\", r"c:", r"c:\windows", r"c:\windows\system32",
            os.path.expanduser("~").lower(),
        ]
        if lower_resolved in critical_paths or any(lower_resolved == cp.rstrip("\\") for cp in critical_paths):
            print(f"[FileManager] Blocked attempt to delete system path: {resolved}")
            return "Execution blocked: That is a critical system path and cannot be deleted, boss."

        item_name = os.path.basename(resolved)
        if os.path.isdir(resolved):
            def handle_remove_readonly(func, path, excinfo):
                import stat
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception as ex:
                    print(f"[FileManager] Failed to reset permissions on {path}: {ex}")

            shutil.rmtree(resolved, onerror=handle_remove_readonly)
            print(f"[FileManager] Successfully deleted directory: {resolved}")
            return f"Deleted the {item_name} folder, boss."
        else:
            try:
                os.remove(resolved)
            except PermissionError:
                import stat
                os.chmod(resolved, stat.S_IWRITE)
                os.remove(resolved)
            print(f"[FileManager] Successfully deleted file: {resolved}")
            return f"Deleted {item_name}, boss."

    except Exception as e:
        print(f"[FileManager] Delete error: {e}")
        return "An error occurred, boss."
