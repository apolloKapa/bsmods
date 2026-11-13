"""Each game's mods, profiles and deployment.

Mods are never unpacked into the game. Each one is "staged" in
~/.local/share/armory/games/<game>/mods/<id>/, laid out like the game folder. Deploying puts the
files of the mods that are on in the game, in priority order (a mod lower in the list wins a
file both have), as hard links (or symlinks, or copies). Files of the game a mod replaces are
moved to backup/ first and put back when no mod needs that path any more. deployed.json records
every file that was put in the game, so turning a mod off removes exactly its files.

Profiles are named sets of on/off and order (and, for Bethesda games, the plugin load order).
"""
import os
import re
import shutil
import struct
import threading
import time

from . import config
from .config import DATA, read_json, write_json

NSFW_WORDS = re.compile(r"\b(nsfw|nude|nudes|nudity|naked|lewd|hentai|porn|porno|explicit|18\+|sexy|erotic|"
                        r"underwear|lingerie|bikini|topless)\b", re.IGNORECASE)
PLUGIN_EXTS = (".esp", ".esm", ".esl")


def resolve_case(base, rel):
    """base/rel, using the spelling of folders that already exist (Windows games ignore case)"""
    cur = base
    parts = [p for p in rel.split("/") if p]
    for i, part in enumerate(parts):
        exact = os.path.join(cur, part)
        if os.path.lexists(exact):
            cur = exact
            continue
        try:
            hit = next((n for n in os.listdir(cur) if n.lower() == part.lower()), None)
        except OSError:
            hit = None
        if hit is None:
            return os.path.join(cur, *parts[i:])
        cur = os.path.join(cur, hit)
    return cur


def tree_size(path):
    total = 0
    for d, _, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(d, f)).st_size
            except OSError:
                pass
    return total


def staged_files(folder):
    """{lowercase rel: rel} of a staged mod"""
    out = {}
    for d, _, files in os.walk(folder):
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), folder).replace(os.sep, "/")
            out[rel.lower()] = rel
    return out


class DeployError(Exception):
    pass


class Store:
    def __init__(self, game):
        self.game = game
        self.dir = os.path.join(DATA, "games", game.id)
        self.mods_dir = os.path.join(self.dir, "mods")
        self.backup_dir = os.path.join(self.dir, "backup")
        self.lock = threading.RLock()
        self.mods = read_json(os.path.join(self.dir, "mods.json"), {})
        p = read_json(os.path.join(self.dir, "profiles.json"), {})
        self.profiles = p.get("profiles") or {}
        self.active = p.get("active") or "Default"
        if self.active not in self.profiles:
            self.profiles[self.active] = {"order": list(self.mods), "enabled": []}
        self._sync_profiles()

    # -- saving --
    def save(self):
        with self.lock:
            write_json(os.path.join(self.dir, "mods.json"), self.mods)
            write_json(os.path.join(self.dir, "profiles.json"), {"active": self.active, "profiles": self.profiles})

    def _sync_profiles(self):
        """every mod is in every profile's order; gone mods are dropped"""
        for prof in self.profiles.values():
            order = [m for m in prof.get("order", []) if m in self.mods]
            order += [m for m in self.mods if m not in order]
            # an imported profile's config files stay last, so they win over mods added after them
            order.sort(key=lambda m: bool(self.mods[m].get("pin_bottom")))
            prof["order"] = order
            prof["enabled"] = [m for m in prof.get("enabled", []) if m in self.mods]

    @property
    def profile(self):
        return self.profiles[self.active]

    # -- mods --
    def mod_path(self, mid):
        return os.path.join(self.mods_dir, mid)

    def new_id(self, name):
        base = config.slug(name)
        mid, n = base, 2
        while mid in self.mods or os.path.exists(self.mod_path(mid)):
            mid = f"{base}-{n}"
            n += 1
        return mid

    def find(self, **source):
        """the mod installed from this source ({"nexus": mod id} / {"thunderstore": full name}), or None"""
        for mid, m in self.mods.items():
            s = m.get("source") or {}
            if "nexus" in source and s.get("type") == "nexus" and int(s.get("mod_id") or 0) == int(source["nexus"]):
                return mid
            if "thunderstore" in source and s.get("type") == "thunderstore" \
                    and s.get("full_name", "").lower() == source["thunderstore"].lower():
                return mid
        return None

    def add(self, name, files, meta, replace=None, enable=True, move=False):
        """stage a mod: files is [(abs source, rel)]. Replacing keeps its place, profiles and marks"""
        with self.lock:
            mid = replace if replace in self.mods else self.new_id(name)
            dest = self.mod_path(mid)
            tmp = dest + ".new"
            shutil.rmtree(tmp, ignore_errors=True)
            for src, rel in files:
                target = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if move:
                    shutil.move(src, target)
                else:
                    shutil.copy2(src, target, follow_symlinks=True)
            old = self.mods.get(mid, {})
            # files of the old version that are deployed are hard links to the old staged copy:
            # deploy() sees the new inodes and relinks them
            shutil.rmtree(dest, ignore_errors=True)
            os.rename(tmp, dest)
            keep = {k: old[k] for k in ("nsfw", "hidden", "notes", "endorsed") if k in old}
            meta = dict(meta, **keep)
            meta["name"] = meta.get("name") or name
            meta["installed"] = time.time()
            meta["size"] = tree_size(dest)
            meta["files"] = len(files)
            meta.pop("update", None)
            self.mods[mid] = meta
            self._sync_profiles()
            if enable and mid not in self.profile["enabled"]:
                self.profile["enabled"].append(mid)
            self.save()
            return mid

    def remove(self, mid):
        """forget a mod and delete its staged files (call deploy() first so it's out of the game)"""
        with self.lock:
            shutil.rmtree(self.mod_path(mid), ignore_errors=True)
            self.mods.pop(mid, None)
            self._sync_profiles()
            self.save()

    def update_meta(self, mid, **changes):
        with self.lock:
            if mid in self.mods:
                for k, v in changes.items():
                    if v is None:
                        self.mods[mid].pop(k, None)
                    else:
                        self.mods[mid][k] = v
                self.save()

    def enabled(self, mid):
        return mid in self.profile["enabled"]

    def set_enabled(self, mid, on):
        with self.lock:
            en = [m for m in self.profile["enabled"] if m != mid]
            if on:
                en.append(mid)
            self.profile["enabled"] = en
            self.save()

    def set_order(self, order):
        with self.lock:
            self.profile["order"] = [m for m in order if m in self.mods] + \
                [m for m in self.profile["order"] if m not in order]
            self.save()

    def move(self, mid, where):
        """where: "top", "bottom", "up", "down" (bottom = highest priority)"""
        order = [m for m in self.profile["order"] if m != mid]
        i = self.profile["order"].index(mid)
        pos = {"top": 0, "bottom": len(order), "up": max(0, i - 1), "down": min(len(order), i + 1)}[where]
        order.insert(pos, mid)
        self.set_order(order)

    def ordered(self):
        """the mods in priority order, each with its id, on/off and place"""
        out = []
        for i, mid in enumerate(self.profile["order"]):
            m = dict(self.mods[mid])
            m["id"] = mid
            m["enabled"] = mid in self.profile["enabled"]
            m["priority"] = i
            out.append(m)
        return out

    # -- NSFW and hidden --
    @staticmethod
    def looks_nsfw(m):
        if m.get("adult"):
            return True
        return bool(NSFW_WORDS.search(" ".join(str(m.get(k) or "") for k in ("name", "summary", "id"))))

    def is_nsfw(self, m):
        mark = m.get("nsfw")
        return mark if isinstance(mark, bool) else self.looks_nsfw(m)

    def set_nsfw(self, mid, on):
        m = dict(self.mods[mid], id=mid)
        m.pop("nsfw", None)
        self.update_meta(mid, nsfw=None if on == self.looks_nsfw(m) else on)

    # -- profiles --
    def switch_profile(self, name):
        with self.lock:
            if name in self.profiles:
                self.active = name
                self.save()

    def new_profile(self, name, copy=True):
        with self.lock:
            src = self.profile
            self.profiles[name] = {"order": list(src["order"]), "enabled": list(src["enabled"]) if copy else [],
                                   "plugins": [list(p) for p in src.get("plugins", [])] if copy else []}
            self.active = name
            self._sync_profiles()
            self.save()

    def rename_profile(self, old, new):
        with self.lock:
            if old in self.profiles and new not in self.profiles:
                self.profiles = {(new if k == old else k): v for k, v in self.profiles.items()}
                if self.active == old:
                    self.active = new
                self.save()

    def delete_profile(self, name):
        with self.lock:
            if name in self.profiles and len(self.profiles) > 1:
                del self.profiles[name]
                if self.active == name:
                    self.active = next(iter(self.profiles))
                self.save()

    # -- files and conflicts --
    def file_map(self, only_enabled=True):
        """{lowercase rel: [(mod id, rel)]} lowest priority first"""
        out = {}
        for mid in self.profile["order"]:
            if only_enabled and mid not in self.profile["enabled"]:
                continue
            for key, rel in staged_files(self.mod_path(mid)).items():
                out.setdefault(key, []).append((mid, rel))
        return out

    def conflicts(self):
        """{mod id: {"wins": {other: n}, "loses": {other: n}}} among the mods that are on"""
        out = {}
        for key, owners in self.file_map().items():
            if len(owners) < 2:
                continue
            winner = owners[-1][0]
            for mid, _ in owners[:-1]:
                if mid == winner:
                    continue
                w = out.setdefault(winner, {"wins": {}, "loses": {}})
                w["wins"][mid] = w["wins"].get(mid, 0) + 1
                l_ = out.setdefault(mid, {"wins": {}, "loses": {}})
                l_["loses"][winner] = l_["loses"].get(winner, 0) + 1
        return out

    # -- deploying --
    def _deployed_path(self):
        return os.path.join(self.dir, "deployed.json")

    def deployed(self):
        return read_json(self._deployed_path(), {"files": {}, "dirs": [], "backups": {}})

    @staticmethod
    def _is_ours(dest, rec, src):
        try:
            st = os.lstat(dest)
        except OSError:
            return False
        method = rec.get("method")
        if method == "symlink":
            return os.path.islink(dest) and os.readlink(dest) == rec.get("src")
        if method == "hardlink":
            return st.st_ino == rec.get("ino") and st.st_dev == rec.get("dev")
        return st.st_size == rec.get("size") and abs(st.st_mtime - rec.get("mtime", 0)) < 2

    def _place(self, src, dest, method):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if method == "symlink":
            os.symlink(src, dest)
            return "symlink"
        if method == "hardlink":
            try:
                os.link(src, dest)
                return "hardlink"
            except OSError:
                pass
        shutil.copy2(src, dest)
        return "copy"

    def _record(self, dest, src, used):
        st = os.lstat(dest)
        return {"method": used, "ino": st.st_ino, "dev": st.st_dev, "size": st.st_size,
                "mtime": st.st_mtime, "src": src}

    def deploy(self, progress=None, purge=False):
        """make the game match the profile: {"added", "removed", "kept", "backed_up", "skipped"}"""
        g = self.game
        if not g.found:
            raise DeployError(f"{g.name} isn't installed (or its folder isn't set)")
        with self.lock:
            method = config.get("deploy_method", "hardlink")
            state = self.deployed()
            files, dirs, backups = state["files"], set(state.get("dirs", [])), state.get("backups", {})
            want = {}
            if not purge:
                for key, owners in self.file_map().items():
                    mid, rel = owners[-1]
                    want[key] = (mid, rel, os.path.join(self.mod_path(mid), rel))
            stats = {"added": 0, "removed": 0, "kept": 0, "backed_up": 0, "skipped": []}
            total = len(files) + len(want)
            done = 0

            def tick():
                nonlocal done
                done += 1
                if progress and done % 200 == 0:
                    progress(done, total)

            try:
                # what no longer belongs (or now comes from another mod)
                for key in list(files):
                    rec = files[key]
                    w = want.get(key)
                    dest = rec["dest"]
                    if w and w[0] == rec["mod"] and rec.get("src") == w[2] and self._is_ours(dest, rec, w[2]):
                        if rec.get("method") == "symlink" or self._same_file(dest, w[2], rec.get("method")):
                            stats["kept"] += 1
                            tick()
                            continue
                    if self._is_ours(dest, rec, rec.get("src")):
                        try:
                            os.unlink(dest)
                        except OSError:
                            pass
                    del files[key]
                    stats["removed"] += 1
                    if key in backups and not w:
                        self._restore(backups.pop(key), dest)
                    tick()
                # what is missing
                for key, (mid, rel, src) in want.items():
                    if key in files:
                        continue
                    base = g.resolve(rel)
                    if base is None:
                        stats["skipped"].append(rel)
                        continue
                    root = g.prefix_user if rel.startswith("@prefix/") else g.path
                    sub = rel[len("@prefix/"):] if rel.startswith("@prefix/") else rel
                    dest = resolve_case(root, sub)
                    if os.path.lexists(dest):
                        if os.path.isdir(dest) and not os.path.islink(dest):
                            stats["skipped"].append(rel)
                            continue
                        # a file of the game (or one we don't know): keep it to put back later
                        if key not in backups:
                            bk = os.path.join(self.backup_dir, key)
                            os.makedirs(os.path.dirname(bk), exist_ok=True)
                            shutil.move(dest, bk)
                            backups[key] = {"backup": bk, "dest": dest}
                            stats["backed_up"] += 1
                        else:
                            os.unlink(dest)
                    for d in self._new_dirs(root, dest):
                        dirs.add(d)
                    used = self._place(src, dest, method)
                    files[key] = dict(self._record(dest, src, used), mod=mid, dest=dest)
                    stats["added"] += 1
                    tick()
                # folders we made that are empty now
                for d in sorted(dirs, key=len, reverse=True):
                    try:
                        if os.path.isdir(d) and not os.listdir(d):
                            os.rmdir(d)
                    except OSError:
                        pass
                dirs = {d for d in dirs if os.path.isdir(d)}
            finally:
                write_json(self._deployed_path(), {"files": files, "dirs": sorted(dirs), "backups": backups,
                                                   "profile": self.active, "time": time.time()})
            if self.game.plugins and not purge:
                try:
                    self.write_plugins()
                except OSError as e:
                    stats["skipped"].append(f"Plugins.txt: {e}")
            return stats

    @staticmethod
    def _same_file(dest, src, method):
        """is the deployed file still the staged one (a reinstall stages new files)"""
        try:
            sa, sb = os.stat(dest), os.stat(src)
        except OSError:
            return False
        if method == "hardlink":
            return sa.st_ino == sb.st_ino and sa.st_dev == sb.st_dev
        return sa.st_size == sb.st_size and abs(sa.st_mtime - sb.st_mtime) < 2

    @staticmethod
    def _new_dirs(root, dest):
        """the folders between root and dest that don't exist yet"""
        out = []
        d = os.path.dirname(dest)
        while d and d != root and len(d) > len(root) and not os.path.exists(d):
            out.append(d)
            d = os.path.dirname(d)
        return out

    @staticmethod
    def _restore(bk, dest):
        src = bk["backup"] if isinstance(bk, dict) else bk
        if os.path.lexists(src) and not os.path.lexists(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)

    def purge(self, progress=None):
        """take every mod out of the game (the staged mods stay)"""
        return self.deploy(progress, purge=True)

    def deployed_count(self):
        return len(self.deployed().get("files", {}))

    # -- adopting mods that are already in the game --
    def adopt(self, folder_rel, sources=()):
        """move mod folders already in the game (or an old manager's storage) under Armory: names"""
        g = self.game
        names = []
        if not g.found:
            return names
        mine = {os.path.normcase(r["dest"]) for r in self.deployed()["files"].values()}
        places = [(resolve_case(g.path, folder_rel), True)] + [(s, False) for s in sources]
        for base, on in places:
            if not os.path.isdir(base):
                continue
            for n in sorted(os.listdir(base)):
                p = os.path.join(base, n)
                if not os.path.isdir(p) or os.path.islink(p):
                    continue
                inner = [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs]
                if not inner or any(os.path.normcase(f) in mine for f in inner):
                    continue
                files = [(f, f"{folder_rel}/{n}/{os.path.relpath(f, p)}") for f in inner]
                meta = {"name": n, "source": {"type": "local"}}
                man = read_json(os.path.join(p, "manifest.json"), {})
                if man:
                    meta.update(name=str(man.get("Name") or n), version=str(man.get("ModVersion") or ""),
                                author=str(man.get("Author") or ""), summary=str(man.get("Description") or ""),
                                game_version=str(man.get("GameVersion") or ""))
                    thumb = man.get("Thumbnail")
                    if thumb:
                        meta["thumb_rel"] = f"{folder_rel}/{n}/{thumb}"
                self.add(n, files, meta, enable=on, move=True)
                shutil.rmtree(p, ignore_errors=True)
                names.append(meta["name"])
        return names

    # -- Bethesda plugins --
    def data_dir(self):
        return resolve_case(self.game.path, "Data") if self.game.found else None

    def available_plugins(self):
        """{lowercase name: (name, path)} of plugins in the game's Data and in the mods that are on"""
        out = {}
        d = self.data_dir()
        if d and os.path.isdir(d):
            deployed = {os.path.normcase(r["dest"]) for r in self.deployed()["files"].values()}
            for n in os.listdir(d):
                if n.lower().endswith(PLUGIN_EXTS) and os.path.normcase(os.path.join(d, n)) not in deployed:
                    out[n.lower()] = (n, os.path.join(d, n))
        for key, owners in self.file_map().items():
            parts = key.split("/")
            if len(parts) == 2 and parts[0] == "data" and key.endswith(PLUGIN_EXTS):
                mid, rel = owners[-1]
                out[key.split("/")[1]] = (rel.split("/")[1], os.path.join(self.mod_path(mid), rel))
        return out

    def plugins(self):
        """[(name, on, path, is master)] in load order; the game's own masters come first, always on"""
        info = self.game.plugins or {}
        avail = self.available_plugins()
        masters = [m for m in info.get("masters", []) if m.lower() in avail]
        saved = self.profile.get("plugins", [])
        order = [(n, on) for n, on in saved if n.lower() in avail and n not in masters]
        known = {n.lower() for n, _ in order} | {m.lower() for m in masters}
        new = sorted((v[0] for k, v in avail.items() if k not in known),
                     key=lambda n: (not n.lower().endswith(".esm"), not n.lower().endswith(".esl"), n.lower()))
        order += [(n, True) for n in new]
        out = [(m, True, avail[m.lower()][1], True) for m in masters]
        for n, on in order:
            path = avail[n.lower()][1]
            out.append((n, bool(on), path, plugin_header(path)["master"]))
        return out

    def set_plugins(self, items):
        """items: [(name, on)] (the game's masters are left out)"""
        masters = {m.lower() for m in (self.game.plugins or {}).get("masters", [])}
        with self.lock:
            self.profile["plugins"] = [[n, bool(on)] for n, on in items if n.lower() not in masters]
            self.save()

    def sort_plugins(self):
        """masters first, then every plugin after the masters it needs (current order otherwise)"""
        items = [(n, on, p, m) for n, on, p, m in self.plugins()]
        implicit = {m.lower() for m in (self.game.plugins or {}).get("masters", [])}
        rest = [i for i in items if i[0].lower() not in implicit]
        rest.sort(key=lambda i: 0 if i[3] else 1)
        by = {i[0].lower(): i for i in rest}
        out, seen = [], set()

        def visit(item, stack=()):
            k = item[0].lower()
            if k in seen or k in stack:
                return
            for m in plugin_header(item[2])["masters"]:
                dep = by.get(m.lower())
                if dep:
                    visit(dep, stack + (k,))
            seen.add(k)
            out.append(item)

        for i in rest:
            visit(i)
        self.set_plugins([(n, on) for n, on, _, _ in out])

    def plugins_txt(self):
        info = self.game.plugins
        user = self.game.prefix_user
        if not info or not user:
            return None
        return resolve_case(user, f"AppData/Local/{info['appdata']}/Plugins.txt")

    def write_plugins(self):
        info = self.game.plugins
        path = self.plugins_txt()
        if not info or not path:
            return False
        items = self.plugins()
        implicit = {m.lower() for m in info.get("masters", [])}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lines = ["# Written by Armory"]
        if info.get("star", True):
            for n, on, _, _ in items:
                if n.lower() in implicit:
                    continue
                lines.append(("*" if on else "") + n)
        else:
            lines += [n for n, on, _, _ in items if on]
            # these games load by file date: set them in order
            stamp = time.mktime((2008, 1, 1, 0, 0, 0, 0, 0, -1))
            for i, (_, _, p, _) in enumerate(items):
                try:
                    os.utime(p, (stamp + i * 60, stamp + i * 60))
                except OSError:
                    pass
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
        with open(os.path.join(os.path.dirname(path), "loadorder.txt"), "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(n for n, _, _, _ in items) + "\n")
        return True


_headers = {}


def plugin_header(path):
    """{"master": bool, "light": bool, "masters": [names]} from a plugin's TES4 record"""
    try:
        st = os.stat(path)
    except OSError:
        return {"master": path.lower().endswith(".esm"), "light": False, "masters": []}
    key = (path, st.st_mtime, st.st_size)
    if key in _headers:
        return _headers[key]
    res = {"master": path.lower().endswith(".esm"), "light": path.lower().endswith(".esl"), "masters": []}
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
        if head[:4] == b"TES4":
            size, flags = struct.unpack_from("<II", head, 4)
            start = 24 if head[24:28] == b"HEDR" else 20
            res["master"] = res["master"] or bool(flags & 0x1)
            res["light"] = res["light"] or bool(flags & 0x200)
            i, end = start, min(len(head), start + size)
            while i + 6 <= end:
                typ = head[i:i + 4]
                ln = struct.unpack_from("<H", head, i + 4)[0]
                data = head[i + 6:i + 6 + ln]
                if typ == b"MAST":
                    res["masters"].append(data.split(b"\0", 1)[0].decode("cp1252", "replace"))
                i += 6 + ln
    except (OSError, struct.error):
        pass
    _headers[key] = res
    return res
