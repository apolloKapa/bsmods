"""Is there a newer Armory? (GitHub releases), and updating the AppImage in place.

Only GitHub is asked, at most once a day, and only when "Check for Armory updates" is on: nothing
about you or your mods is sent. A new AppImage is checked against the release's SHA256SUMS before it
replaces the running one.
"""
import hashlib
import os
import re
import time

from . import VERSION, config
from .net import NetError, download, get_json, request

REPO = "apolloKapa/armory"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET = "Armory-x86_64.AppImage"


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4])


def due():
    return config.get("check_updates", True) and time.time() - (config.get("update_checked_at", 0) or 0) > 86400


def latest():
    """{"version", "url", "notes", "asset", "sums"} of the newest release, or None if this is it"""
    rel = get_json(API, headers={"Accept": "application/vnd.github+json"})
    config.save_conf(update_checked_at=time.time())
    tag = rel.get("tag_name", "")
    if vtuple(tag) <= vtuple(VERSION):
        return None
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    return {"version": tag.lstrip("v"), "url": rel.get("html_url") or PAGE, "notes": rel.get("body") or "",
            "asset": assets.get(ASSET), "sums": assets.get("SHA256SUMS")}


def appimage():
    """the AppImage this Armory runs from, if it's one we may replace"""
    p = os.environ.get("APPIMAGE", "")
    return p if p and os.path.isfile(p) and os.access(os.path.dirname(p), os.W_OK) else ""


def install(info, progress=None):
    """download the new AppImage next to the running one, check it, and swap it in: its path"""
    target = appimage()
    if not target:
        raise NetError("Armory isn't running from an AppImage it can replace")
    if not info.get("asset") or not info.get("sums"):
        raise NetError("That release has no AppImage with a checksum")
    raw, _ = request(info["sums"])
    want = None
    for line in raw.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == ASSET:
            want = parts[0].lower()
    if not want:
        raise NetError("The release's SHA256SUMS doesn't list the AppImage")
    new = target + ".new"
    download(info["asset"], new, progress)
    h = hashlib.sha256()
    with open(new, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != want:
        os.unlink(new)
        raise NetError("The download doesn't match the release's checksum, so it wasn't used")
    os.chmod(new, 0o755)
    os.replace(new, target)
    return target
