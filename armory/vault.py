"""Keeping the Nexus login: the desktop keyring (Secret Service, through secret-tool) when there is
one, otherwise ~/.config/armory/nexus.json readable only by you."""
import json
import os
import shutil
import subprocess

from . import config
from .config import SECRETS, read_json, write_json

ATTRS = ["application", "armory", "kind"]


def _tool():
    return shutil.which("secret-tool")


def _keyring_get(kind):
    if not _tool():
        return None
    try:
        r = subprocess.run([_tool(), "lookup", *ATTRS, kind], capture_output=True, text=True, timeout=5,
                           env=config.clean_env())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 and r.stdout else None


def _keyring_set(kind, value):
    if not _tool():
        return False
    try:
        r = subprocess.run([_tool(), "store", f"--label=Armory: Nexus Mods {kind}", *ATTRS, kind],
                           input=value, capture_output=True, text=True, timeout=10, env=config.clean_env())
    except (OSError, subprocess.TimeoutExpired):
        return False
    # read it back: some setups "succeed" without a keyring to store in
    return r.returncode == 0 and _keyring_get(kind) == value


def _keyring_clear(kind):
    if _tool():
        try:
            subprocess.run([_tool(), "clear", *ATTRS, kind], capture_output=True, timeout=5, env=config.clean_env())
        except (OSError, subprocess.TimeoutExpired):
            pass


_cache = {}


def get(kind):
    """kind: "apikey" or "oauth" -> str ("" if none); asked once, then remembered"""
    if kind not in _cache:
        v = _keyring_get(kind)
        _cache[kind] = v if v is not None else read_json(SECRETS, {}).get(kind, "")
    return _cache[kind]


def put(kind, value):
    """where it went: "keyring" or "file" """
    _cache.pop(kind, None)
    file_data = read_json(SECRETS, {})
    if not value:
        _keyring_clear(kind)
        file_data.pop(kind, None)
        where = "file"
    elif _keyring_set(kind, value):
        file_data.pop(kind, None)
        where = "keyring"
    else:
        file_data[kind] = value
        where = "file"
    _cache[kind] = value or ""
    if file_data:
        write_json(SECRETS, file_data, private=True)
    else:
        try:
            os.unlink(SECRETS)
        except OSError:
            pass
    return where


def get_json(kind):
    try:
        return json.loads(get(kind) or "{}")
    except ValueError:
        return {}


def put_json(kind, data):
    return put(kind, json.dumps(data) if data else "")


def migrate():
    """a key kept in the file by an older Armory moves to the keyring when there is one"""
    data = read_json(SECRETS, {})
    for kind, value in list(data.items()):
        if value and _keyring_set(kind, value):
            data.pop(kind)
    if data:
        write_json(SECRETS, data, private=True)
    elif os.path.exists(SECRETS):
        os.unlink(SECRETS)
