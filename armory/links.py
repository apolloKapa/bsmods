"""nxm:// and ror2mm:// links: making Armory the app that opens them, and sending a link (or
files) to the Armory that's already running instead of starting a second one."""
import os
import shutil
import subprocess
import sys

from .config import HOME

APPS = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local/share"), "applications")
DESKTOP = "armory-links.desktop"
SCHEMES = {"nxm": "Nexus Mods (Mod Manager Download)", "ror2mm": "Thunderstore (Install with Mod Manager)"}
SOCKET = f"armory-{os.getuid()}"


def quote(arg):
    """an argument for a .desktop Exec line (its own rules, not the shell's): plain when it can be,
    since some tools (xdg-mime) skip quoted programs"""
    if arg and all(c.isalnum() or c in "/._-+~:@" for c in arg):
        return arg
    return '"' + "".join("\\" + c if c in '"`$\\' else c for c in arg) + '"'


def command():
    """how to start this Armory from a .desktop file"""
    if os.environ.get("APPIMAGE"):
        return quote(os.environ["APPIMAGE"])
    if getattr(sys, "frozen", False):
        return quote(sys.executable)
    launcher = os.path.join(HOME, ".local/bin/armory")
    if os.path.exists(launcher):
        return quote(launcher)
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return f"env PYTHONPATH={quote(pkg_parent)} {quote(sys.executable)} -m armory"


def handler(scheme):
    """the .desktop file that opens these links now ("" if none)"""
    if not shutil.which("xdg-mime"):
        return ""
    r = subprocess.run(["xdg-mime", "query", "default", f"x-scheme-handler/{scheme}"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def is_ours(scheme):
    return handler(scheme) == DESKTOP


def handler_name(scheme):
    h = handler(scheme)
    if not h:
        return "nothing"
    if h == DESKTOP:
        return "Armory"
    for d in (APPS, "/usr/share/applications", "/usr/local/share/applications"):
        try:
            for line in open(os.path.join(d, h), encoding="utf-8"):
                if line.startswith("Name="):
                    return line[5:].strip()
        except OSError:
            continue
    return h.removesuffix(".desktop")


def register(schemes):
    """make Armory open these link types (only the ones asked for)"""
    os.makedirs(APPS, exist_ok=True)
    mine = [s for s in SCHEMES if s in schemes or is_ours(s)]
    with open(os.path.join(APPS, DESKTOP), "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\nType=Application\nName=Armory (mod links)\n"
                "Comment=Opens Nexus Mods and Thunderstore mod manager links in Armory\n"
                f"Exec={command()} %u\nIcon=armory\nTerminal=false\nNoDisplay=true\n"
                f"MimeType={''.join(f'x-scheme-handler/{s};' for s in mine)}\nCategories=Game;\n")
    if shutil.which("xdg-mime"):
        for s in schemes:
            subprocess.run(["xdg-mime", "default", DESKTOP, f"x-scheme-handler/{s}"], capture_output=True)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", APPS], capture_output=True)


def unregister(scheme):
    """stop opening one link type; the previous app isn't known, so nothing is set instead"""
    path = os.path.join(APPS, DESKTOP)
    keep = [s for s in SCHEMES if s != scheme and is_ours(s)]
    mimeapps = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "mimeapps.list")
    try:
        lines = open(mimeapps, encoding="utf-8").read().splitlines()
        out = [ln for ln in lines if not (ln.startswith(f"x-scheme-handler/{scheme}=") and DESKTOP in ln)]
        if out != lines:
            with open(mimeapps, "w", encoding="utf-8") as f:
                f.write("\n".join(out) + "\n")
    except OSError:
        pass
    if keep:
        register(keep)
    else:
        try:
            os.unlink(path)
        except OSError:
            pass
