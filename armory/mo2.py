"""Importing a Mod Organizer 2 instance: its mods, profiles (on/off and order) and plugin order.

An MO2 instance folder has mods/<name>/ (each laid out like the game's Data folder for Bethesda
games, the game folder otherwise), mods/<name>/meta.ini (Nexus ids, version), overwrite/, and
profiles/<name>/modlist.txt ("+name" on, "-name" off, top line = highest priority) and plugins.txt.
Files are hard-linked when they're on the same drive (no extra space), copied otherwise.
"""
import configparser
import os


def is_instance(folder):
    return os.path.isdir(os.path.join(folder, "mods")) and os.path.isdir(os.path.join(folder, "profiles"))


def read_meta(folder):
    p = os.path.join(folder, "meta.ini")
    c = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        c.read(p, encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        return {}
    g = c["General"] if c.has_section("General") else {}
    meta = {}
    try:
        mod_id = int(str(g.get("modid", "0")).strip() or 0)
    except ValueError:
        mod_id = 0
    if g.get("version"):
        meta["version"] = str(g.get("version")).strip().lstrip("d").split("+")[0]
    if mod_id > 0:
        file_id = 0
        if c.has_section("installedFiles"):
            for k, v in c["installedFiles"].items():
                if k.endswith("fileid"):
                    try:
                        file_id = int(v)
                    except ValueError:
                        pass
        meta["source"] = {"type": "nexus", "mod_id": mod_id, "file_id": file_id or None}
    return meta


def modlist(folder, profile):
    """[(mod name, on)] highest priority first, separators and unmanaged entries left out"""
    out = []
    try:
        lines = open(os.path.join(folder, "profiles", profile, "modlist.txt"), encoding="utf-8").read().splitlines()
    except OSError:
        return out
    for line in lines:
        if not line or line.startswith("#") or line[0] not in "+-":
            continue
        name = line[1:]
        if name.endswith("_separator"):
            continue
        out.append((name, line[0] == "+"))
    return out


def plugins(folder, profile):
    """[(plugin, on)] in load order, from the profile's plugins.txt (+ loadorder.txt)"""
    try:
        lines = open(os.path.join(folder, "profiles", profile, "plugins.txt"), encoding="utf-8-sig").read().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append((line.lstrip("*"), line.startswith("*")))
    return out


def import_instance(store, folder, progress=None):
    """bring an MO2 instance into a game's store: {"mods": n, "profiles": [names]}"""
    game = store.game
    data = game.layout.get("data")
    base = data["dir"] if data else ""
    mods_dir = os.path.join(folder, "mods")
    names = sorted(n for n in os.listdir(mods_dir) if os.path.isdir(os.path.join(mods_dir, n))
                   and not n.endswith("_separator"))
    overwrite = os.path.join(folder, "overwrite")
    if os.path.isdir(overwrite) and any(fs for _, _, fs in os.walk(overwrite)):
        names.append("\0overwrite")
    ids = {}
    for i, n in enumerate(names):
        src = overwrite if n == "\0overwrite" else os.path.join(mods_dir, n)
        title = "MO2 Overwrite" if n == "\0overwrite" else n
        files = []
        for d, _, fs in os.walk(src):
            for f in fs:
                if d == src and f.lower() == "meta.ini":
                    continue
                full = os.path.join(d, f)
                rel = os.path.relpath(full, src).replace(os.sep, "/")
                files.append((full, f"{base}/{rel}" if base else rel))
        if not files:
            continue
        meta = {"name": title, "source": {"type": "local"}, "summary": "Imported from Mod Organizer 2"}
        meta.update(read_meta(src))
        if meta["source"].get("type") == "nexus":
            meta["source"]["domain"] = game.nexus
        mid = store.add(title, files, meta, enable=False, link=True)
        ids[n] = mid
        if progress:
            progress(i + 1, len(names))
    made = []
    profiles_dir = os.path.join(folder, "profiles")
    for prof in sorted(os.listdir(profiles_dir)):
        if not os.path.isdir(os.path.join(profiles_dir, prof)):
            continue
        entries = modlist(folder, prof)
        name, k = f"MO2 {prof}", 2
        while name in store.profiles:
            name = f"MO2 {prof} ({k})"
            k += 1
        store.new_profile(name, copy=False)
        # MO2's top line wins; here the last one does
        order = [ids[n] for n, _ in reversed(entries) if n in ids]
        if "\0overwrite" in ids:
            order.append(ids["\0overwrite"])
        store.set_order(order)
        for n, on in entries:
            if n in ids:
                store.set_enabled(ids[n], on)
        if "\0overwrite" in ids:
            store.set_enabled(ids["\0overwrite"], True)
        if game.plugins:
            pl = plugins(folder, prof)
            if pl:
                store.set_plugins(pl)
        made.append(name)
    return {"mods": len(ids), "profiles": made}
