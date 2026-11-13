"""Save games: backups, restoring them, and keeping separate saves for each profile.

Where a game keeps its saves is known for the games below; for others you pick the folder once
(⋯ → Saves → Choose the save folder). Paths starting "@prefix/" are in the game's Proton prefix
user folder, "@home/" in your home folder; others are inside the game folder.

Backups are zips in ~/.local/share/armory/games/<game>/save-backups (the newest 30 are kept).
Separate saves per profile: switching profile backs up the saves, keeps them with the old profile
and puts the new profile's in place (a new profile starts with a copy of the current ones).
"""
import json
import os
import shutil
import time
import zipfile

from . import config
from .config import DATA

KNOWN = {
    "bladeandsorcery": ["@prefix/Documents/My Games/BladeAndSorcery/Saves"],
    "lethalcompany": ["@prefix/AppData/LocalLow/ZeekerssRBLX/Lethal Company"],
    "repo": ["@prefix/AppData/LocalLow/semiwork/Repo/saves"],
    "contentwarning": ["@prefix/AppData/LocalLow/Landfall Games/Content Warning"],
    "ultrakill": ["Saves"],
    "subnautica": ["SNAppData/SavedGames"],
    "subnauticabelowzero": ["SNAppData/SavedGames"],
    "valheim": ["@prefix/AppData/LocalLow/IronGate/Valheim"],
    "bonelab": ["@prefix/AppData/LocalLow/Stress Level Zero/BONELAB/Saves"],
    "reddeadredemption2": ["@prefix/Documents/Rockstar Games/Red Dead Redemption 2/Profiles"],
    "nomanssky": ["@prefix/AppData/Roaming/HelloGames/NMS"],
    "celeste": ["Saves"],
    "stardewvalley": ["@prefix/AppData/Roaming/StardewValley/Saves"],
    "skyrimspecialedition": ["@prefix/Documents/My Games/Skyrim Special Edition/Saves"],
    "skyrim": ["@prefix/Documents/My Games/Skyrim/Saves"],
    "fallout4": ["@prefix/Documents/My Games/Fallout4/Saves"],
    "newvegas": ["@prefix/Documents/My Games/FalloutNV/Saves"],
    "fallout3": ["@prefix/Documents/My Games/Fallout3/Saves"],
    "oblivion": ["@prefix/Documents/My Games/Oblivion/Saves"],
    "starfield": ["@prefix/Documents/My Games/Starfield/Saves"],
    "cyberpunk2077": ["@prefix/Saved Games/CD Projekt Red/Cyberpunk 2077"],
    "witcher3": ["@prefix/Documents/The Witcher 3/gamesaves"],
    "baldursgate3": ["@prefix/AppData/Local/Larian Studios/Baldur's Gate 3/PlayerProfiles/Public/Savegames"],
    "rimworld": ["@prefix/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Saves"],
    "projectzomboid": ["@home/Zomboid/Saves"],
    "eldenring": ["@prefix/AppData/Roaming/EldenRing"],
    "thesims4": ["@prefix/Documents/Electronic Arts/The Sims 4/saves"],
    "balatro": ["@prefix/AppData/Roaming/Balatro"],
}


def specs(game):
    custom = (config.get("save_dirs", {}) or {}).get(game.id)
    if custom:
        return list(custom)
    return list(KNOWN.get(game.id, []))


def resolve(game, spec):
    if os.path.isabs(spec):
        return spec
    if spec.startswith("@home/"):
        return os.path.join(config.HOME, spec[len("@home/"):])
    if spec.startswith("@prefix/"):
        return game.resolve(spec)
    return os.path.join(game.path, spec) if game.path else None


def folders(game):
    """[(spec, absolute path)] of the save folders that can be found (existing or not)"""
    out = []
    for s in specs(game):
        p = resolve(game, s)
        if p:
            out.append((s, p))
    return out


def set_folder(game, path):
    dirs = dict(config.get("save_dirs", {}) or {})
    if path:
        dirs[game.id] = [path]
    else:
        dirs.pop(game.id, None)
    config.save_conf(save_dirs=dirs)


def backup_dir(game):
    return os.path.join(DATA, "games", game.id, "save-backups")


def backup(game, label=""):
    """zip the saves: the zip's path (None if there are no saves to back up)"""
    found = [(s, p) for s, p in folders(game) if os.path.isdir(p) and os.listdir(p)]
    if not found:
        return None
    d = backup_dir(game)
    os.makedirs(d, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(d, f"{stamp}{'_' + label if label else ''}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("armory-saves.json", json.dumps({"folders": [s for s, _ in found], "time": time.time()}))
        for i, (_, p) in enumerate(found):
            for root, _, files in os.walk(p):
                for f in files:
                    full = os.path.join(root, f)
                    z.write(full, f"{i}/{os.path.relpath(full, p)}")
    # keep the newest 30
    for old in sorted(backups(game))[:-30]:
        try:
            os.unlink(old)
        except OSError:
            pass
    return path


def backups(game):
    d = backup_dir(game)
    try:
        return sorted(os.path.join(d, n) for n in os.listdir(d) if n.endswith(".zip"))
    except OSError:
        return []


def restore(game, path):
    """put a backup's saves back (the current ones are backed up first)"""
    backup(game, "before-restore")
    with zipfile.ZipFile(path) as z:
        meta = json.loads(z.read("armory-saves.json"))
        targets = [resolve(game, s) for s in meta["folders"]]
        for t in targets:
            if t and os.path.isdir(t):
                shutil.rmtree(t)
        for n in z.namelist():
            if n == "armory-saves.json" or n.endswith("/"):
                continue
            i, _, rel = n.partition("/")
            if not i.isdigit() or int(i) >= len(targets) or not targets[int(i)]:
                continue
            dest = os.path.normpath(os.path.join(targets[int(i)], rel))
            if not dest.startswith(os.path.normpath(targets[int(i)]) + os.sep):
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(n) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)


# ---- separate saves for each profile ----

def per_profile(game):
    return game.id in (config.get("profile_saves", []) or [])


def set_per_profile(game, on):
    ids = [g for g in config.get("profile_saves", []) or [] if g != game.id]
    if on:
        ids.append(game.id)
    config.save_conf(profile_saves=ids)


def _store(game, profile):
    return os.path.join(DATA, "games", game.id, "profile-saves", profile)


def swap(game, old, new):
    """keep the saves with profile `old` and put profile `new`'s in place"""
    if old == new:
        return
    backup(game, f"switch-{old}")
    for i, (_, p) in enumerate(folders(game)):
        keep = os.path.join(_store(game, old), str(i))
        shutil.rmtree(keep, ignore_errors=True)
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        if os.path.isdir(p):
            shutil.copytree(p, keep, symlinks=True)
        theirs = os.path.join(_store(game, new), str(i))
        if os.path.isdir(theirs):
            if os.path.isdir(p):
                shutil.rmtree(p)
            shutil.copytree(theirs, p, symlinks=True)
        # a profile without saves of its own yet starts with the current ones
