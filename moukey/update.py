import hashlib
import json
import logging
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from moukey import __version__

log = logging.getLogger("moukey")

REPO = "Nando1N/moukey"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"
# where a release download can come from. github redirects the asset link to its storage
HOSTS = {
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
MAX_EXE = 200 * 1024 * 1024
# written by installer/moukey.iss (AppId + "_is1"), it's how we know we were installed
APP_ID = "{CDE3B5F3-0832-4094-88CA-9C9D7E11FF0C}"
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"
# the new copy is started with this, so it waits for the old one to let go of the door
AFTER_UPDATE = "--depois-de-atualizar"


def version_tuple(text: str) -> tuple[int, ...] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(int(n) for n in m.groups()) if m else None


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = version_tuple(latest), version_tuple(current)
    return a is not None and b is not None and a > b


def _get(url: str, limit: int) -> bytes:
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in HOSTS:
        raise ValueError("not a github address")
    req = urllib.request.Request(url, headers={"User-Agent": f"MouKey/{__version__}"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        # the redirect has to land on github too
        final = urlparse(resp.geturl())
        if final.scheme != "https" or final.hostname not in HOSTS:
            raise ValueError("redirected away from github")
        data = resp.read(limit + 1)
    if len(data) > limit:
        raise ValueError("bigger than expected")
    return data


def check() -> dict | None:
    """the newest release on github, or None if there's nothing newer (or no internet)"""
    try:
        info = json.loads(_get(LATEST, 1024 * 1024))
    except (OSError, ValueError) as e:
        log.info("update check failed: %s", type(e).__name__)
        return None
    tag = info.get("tag_name") if isinstance(info, dict) else None
    if not isinstance(tag, str) or not is_newer(tag):
        return None
    assets = {a.get("name"): a.get("browser_download_url") for a in info.get("assets", [])}
    return {
        "version": tag.lstrip("v"),
        "exe": assets.get("MouKey.exe"),
        "sha": assets.get("MouKey.exe.sha256"),
        "setup": assets.get("MouKey-Setup.exe"),
        "setup_sha": assets.get("MouKey-Setup.exe.sha256"),
    }


def can_install() -> bool:
    # replacing itself only makes sense for the windows exe. from source, git pull does it
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def installed() -> bool:
    """true when this exe came from MouKey-Setup.exe (start menu, apps list and all)"""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            where, _ = winreg.QueryValueEx(key, "InstallLocation")
    except OSError:
        return False
    # a portable copy somewhere else on the same pc still updates itself in place
    return Path(where).resolve() == Path(sys.executable).parent.resolve()


def download(found: dict, folder: Path) -> Path:
    """downloads the new version and checks it against the sha256 published with the release.
    the installer when the app was installed, the bare exe when it's the portable one"""
    use_setup = installed()
    url, sha = (
        (found.get("setup"), found.get("setup_sha"))
        if use_setup
        else (found.get("exe"), found.get("sha"))
    )
    if not url or not sha:
        raise ValueError("release without the file or its hash")
    line = _get(sha, 1024).decode("ascii", "replace")
    m = re.match(r"\s*([0-9a-fA-F]{64})\b", line)
    if not m:
        raise ValueError("hash file doesn't look like a hash")
    data = _get(url, MAX_EXE)
    if hashlib.sha256(data).hexdigest() != m.group(1).lower():
        raise ValueError("download doesn't match the published hash")
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / ("MouKey-Setup.exe" if use_setup else "MouKey-novo.exe")
    out.write_bytes(data)
    return out


def install(new_exe: Path) -> None:
    """swaps the running exe for the new one and starts it. the caller quits right after"""
    if new_exe.name == "MouKey-Setup.exe":
        # the installer closes us, puts the new version in place (keeping the shortcuts and
        # options picked the first time) and opens it again. nothing shows on screen
        subprocess.Popen(
            [str(new_exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LANG=pt"],
            close_fds=True,
        )
        return
    current = Path(sys.executable)
    old = current.with_name(current.stem + ".antigo.exe")
    old.unlink(missing_ok=True)
    # windows won't let us overwrite a running exe, but renaming it is fine
    current.rename(old)
    try:
        new_exe.replace(current)
    except OSError:
        old.rename(current)
        raise
    subprocess.Popen([str(current), AFTER_UPDATE], close_fds=True)


def clean_old() -> None:
    """the previous exe is left next to the new one until the old process is gone"""
    if not can_install():
        return
    old = Path(sys.executable).with_name(Path(sys.executable).stem + ".antigo.exe")
    for _ in range(30):
        try:
            old.unlink(missing_ok=True)
            return
        except OSError:
            time.sleep(1)
