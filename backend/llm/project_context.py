"""Provider-independent project context and plan parsing."""
import json
import re


def get_sanitized_package_inventory() -> list[str]:
    """Returns a sanitized list of installed Python package names ONLY.
    No paths, versions, environments, or file structures are exposed."""
    try:
        import importlib.metadata
        names = set()
        for dist in importlib.metadata.distributions():
            if dist.metadata and "Name" in dist.metadata:
                name = dist.metadata["Name"].strip().lower()
                if name and not name.startswith("_"):
                    names.add(name)
        return sorted(list(names))[:150]
    except Exception:
        return [
            "flask", "requests", "jinja2", "urllib3", "websockets",
            "pytest", "pillow", "numpy", "opencv-python", "openai"
        ]


def _clean_json_plan(text: str) -> dict:
    """Safely extracts JSON steps and required_installs from raw model output."""
    if not text:
        return {"steps": [], "required_installs": []}

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        candidate = cleaned[start:end + 1] if start != -1 and end > start else cleaned

    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            steps = data.get("steps")
            if not steps and isinstance(data.get("plan"), dict):
                steps = data["plan"].get("steps")
            elif not steps and isinstance(data.get("plan"), list):
                steps = data.get("plan")
            reqs = data.get("required_installs") or (data.get("plan", {}).get("required_installs") if isinstance(data.get("plan"), dict) else [])
            return {
                "steps": steps if isinstance(steps, list) else [],
                "required_installs": [str(p).strip().lower() for p in reqs if p] if isinstance(reqs, list) else [],
            }
        elif isinstance(data, list):
            return {"steps": data, "required_installs": []}
    except Exception:
        start_arr = cleaned.find("[")
        end_arr = cleaned.rfind("]")
        if start_arr != -1 and end_arr > start_arr:
            try:
                arr = json.loads(cleaned[start_arr:end_arr + 1])
                if isinstance(arr, list):
                    return {"steps": arr, "required_installs": []}
            except Exception:
                pass

    return {"steps": [], "required_installs": []}
