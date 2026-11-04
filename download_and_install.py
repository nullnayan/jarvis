"""Download a GitHub Actions APK and install it on an explicitly selected device."""
import io
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import httpx


def select_device(output: str, requested: str = "") -> str:
    devices = [line.split()[0] for line in output.splitlines()
               if len(line.split()) == 2 and line.split()[1] == "device"]
    if requested:
        if requested not in devices:
            raise ValueError("The configured ADB_DEVICE_SERIAL is not connected or authorized.")
        return requested
    if len(devices) != 1:
        raise ValueError("Connect one authorized device or set ADB_DEVICE_SERIAL.")
    return devices[0]


def extract_apk(content: bytes, destination: Path) -> Path:
    # Extract only the expected file; never trust archive paths from a download.
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        candidates = [item for item in archive.infolist()
                      if item.filename.rsplit("/", 1)[-1] == "app-debug.apk" and not item.is_dir()]
        if len(candidates) != 1 or candidates[0].file_size > 200 * 1024 * 1024:
            raise ValueError("Artifact must contain exactly one supported app-debug.apk.")
        path = destination / "app-debug.apk"
        path.write_bytes(archive.read(candidates[0]))
    return path


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if not token:
        print("Set GITHUB_TOKEN or GH_TOKEN with access to this repository's Actions artifacts.")
        return 1
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repo:
        print("Set GITHUB_REPOSITORY to the owner/repository you want to install.")
        return 1
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "User-Agent": "Jarvis-Installer"}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        response = client.get(f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100")
        response.raise_for_status()
        artifacts = [item for item in response.json().get("artifacts", [])
                     if item.get("name") == "jarvis-companion-debug-apk" and not item.get("expired")]
        if not artifacts:
            print("No active Jarvis APK artifacts found. Run the Android build workflow first.")
            return 1
        response = client.get(artifacts[0]["archive_download_url"], follow_redirects=True)
        response.raise_for_status()
    apk = extract_apk(response.content, Path.cwd())
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=True, timeout=15)
    serial = select_device(result.stdout, os.environ.get("ADB_DEVICE_SERIAL", "").strip())
    subprocess.run(["adb", "-s", serial, "install", "-r", str(apk)], check=True, timeout=60)
    subprocess.run(["adb", "-s", serial, "shell", "monkey", "-p", "com.jarvis.companion",
                    "-c", "android.intent.category.LAUNCHER", "1"], check=True, timeout=15)
    print("Jarvis installed. Configure the server address and your new token in the app.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (httpx.HTTPError, subprocess.SubprocessError, OSError, ValueError, zipfile.BadZipFile) as exc:
        # Exception URLs can contain credentials; print only the error type.
        print(f"Installation failed ({type(exc).__name__}). Check credentials, artifact access, and ADB.")
        sys.exit(1)
