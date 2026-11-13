"""Where Armory keeps things, and small JSON helpers.

~/.config/armory/config.json     settings (window, view, deploy method, which games are listed)
~/.config/armory/nexus.json      the Nexus Mods API key (mode 600)
~/.local/share/armory/games/<id>  per game: staged mods, profiles, what is deployed, backups
~/.local/share/armory/downloads   downloaded archives (kept so a mod can be reinstalled)
~/.cache/armory                   images and Thunderstore listings
"""
import json
import os
import re
import tempfile

HOME = os.path.expanduser("~")
DATA = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local/share"), "armory")
CONF_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "armory")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"), "armory")
DOWNLOADS = os.path.join(DATA, "downloads")
CONF = os.path.join(CONF_DIR, "config.json")
SECRETS = os.path.join(CONF_DIR, "nexus.json")


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            v = json.load(f)
        if default is not None and not isinstance(v, type(default)):
            return default
        return v
    except (OSError, ValueError):
        return default


def write_json(path, data, private=False):
    """written to a temporary file first, so a crash never leaves half a file"""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        if private:
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_conf():
    return read_json(CONF, {})


def get(key, default=None):
    return load_conf().get(key, default)


def save_conf(**changes):
    c = load_conf()
    c.update(changes)
    write_json(CONF, c)


def nexus_key():
    return read_json(SECRETS, {}).get("apikey", "")


def set_nexus_key(key):
    if key:
        write_json(SECRETS, {"apikey": key}, private=True)
    else:
        try:
            os.unlink(SECRETS)
        except OSError:
            pass


def slug(text, fallback="mod"):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    return s[:60] or fallback


def human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def short_count(n):
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)
