"""Unpacking a downloaded mod and working out where its files go in the game.

plan() takes the unpacked folder and the game's layout (see games.py) and returns
[(source file, path relative to the game)], the "staged" layout. Nothing is written here.
"""
import fnmatch
import os
import re
import shutil
import subprocess

ARCHIVE_EXTS = (".zip", ".7z", ".rar", ".tar", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar.zst")
JUNK = {"__macosx", ".ds_store", "thumbs.db", "desktop.ini"}


class LayoutError(Exception):
    pass


def is_archive(path):
    p = path.lower()
    return any(p.endswith(e) for e in ARCHIVE_EXTS)


def strip_ext(name):
    return re.sub(r"(\.tar)?\.[A-Za-z0-9]{1,4}$", "", name)


def mod_name_from_file(filename):
    """"Cool Spell-1234-1-2-1700000000.zip" (a Nexus download) -> "Cool Spell" """
    base = strip_ext(os.path.basename(filename))
    m = re.match(r"^(.*?)-(\d+)(-[\dA-Za-z]+)*-(\d{9,11})$", base)
    if m:
        base = m.group(1)
    return base.replace("_", " ").strip() or "Mod"


def extract(src, dest):
    """unpack an archive into dest (bsdtar first, then 7z or unrar for what it can't read)"""
    os.makedirs(dest, exist_ok=True)
    tried = []
    for tool, cmd in (("bsdtar", ["bsdtar", "-xf", src, "-C", dest]),
                      ("7z", ["7z", "x", "-y", "-bd", f"-o{dest}", src]),
                      ("7zz", ["7zz", "x", "-y", "-bd", f"-o{dest}", src]),
                      ("unrar", ["unrar", "x", "-o+", "-idq", src, dest + "/"])):
        if not shutil.which(tool):
            continue
        if tool == "unrar" and not src.lower().endswith(".rar"):
            continue
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            fix_permissions(dest)
            return
        tried.append(f"{tool}: {(r.stderr or r.stdout).strip().splitlines()[-1:] or ['failed']}")
        # a partly unpacked archive: start again with the next tool
        for n in os.listdir(dest):
            p = os.path.join(dest, n)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) and not os.path.islink(p) else os.unlink(p)
    if not tried:
        raise LayoutError("Install bsdtar (libarchive) or 7-Zip to unpack mods")
    raise LayoutError(f"Couldn't unpack {os.path.basename(src)} ({'; '.join(map(str, tried))})")


def fix_permissions(root):
    """archives made on Windows sometimes unpack with folders we can't enter"""
    for d, dirs, files in os.walk(root):
        for n in dirs:
            p = os.path.join(d, n)
            try:
                os.chmod(p, os.stat(p).st_mode | 0o700)
            except OSError:
                pass
        for n in files:
            p = os.path.join(d, n)
            try:
                if not os.path.islink(p):
                    os.chmod(p, os.stat(p).st_mode | 0o600)
            except OSError:
                pass


def entries(folder):
    try:
        return [n for n in os.listdir(folder) if n.lower() not in JUNK]
    except OSError:
        return []


def matches(name, patterns):
    n = name.lower()
    return any(fnmatch.fnmatch(n, p.lower()) for p in patterns)


def files_under(folder, ignore_top=()):
    """every file below folder: [(abs, rel)]"""
    out = []
    for d, dirs, files in os.walk(folder):
        dirs[:] = [x for x in dirs if x.lower() not in JUNK]
        for f in files:
            if f.lower() in JUNK:
                continue
            p = os.path.join(d, f)
            rel = os.path.relpath(p, folder)
            if d == folder and matches(f, ignore_top):
                continue
            out.append((p, rel))
    return out


def levels(root, max_depth=5):
    """folders breadth first, shallowest first: [(path, depth)]"""
    out, queue = [], [(root, 0)]
    while queue:
        d, depth = queue.pop(0)
        out.append((d, depth))
        if depth < max_depth:
            for n in sorted(entries(d)):
                p = os.path.join(d, n)
                if os.path.isdir(p) and not os.path.islink(p):
                    queue.append((p, depth + 1))
    return out


def unwrap(root):
    """go down through folders that only hold one folder"""
    d = root
    while True:
        e = entries(d)
        if len(e) == 1 and os.path.isdir(os.path.join(d, e[0])):
            d = os.path.join(d, e[0])
        else:
            return d


def fill(template, name):
    return template.replace("{name}", name).strip("/")


def join(base, rel):
    return f"{base}/{rel}" if base else rel


def plan(root, layout, name):
    """[(abs source, staged rel path)] for an unpacked mod; raises LayoutError if it's empty"""
    ignore = layout.get("ignore_top", [])
    safe = re.sub(r'[<>:"/\\|?*]+', "_", name).strip() or "Mod"
    out = []

    # 1. folders that are each a mod (Blade & Sorcery, Stardew, Celeste, BONELAB pallets...)
    fm = layout.get("folder_mod")
    if fm:
        found = []
        for d, _ in levels(root, 6):
            if any(d.startswith(f + os.sep) for f in found):
                continue
            if any(matches(n, [fm["marker"]]) for n in entries(d)):
                found.append(d)
        if found:
            prefix = fm.get("prefix", "")
            for d in found:
                folder = os.path.basename(d) if d != root else safe
                if prefix and not folder.lower().startswith(prefix.lower()):
                    folder = prefix + folder
                for src, rel in files_under(d):
                    out.append((src, join(fm["dir"], os.path.join(folder, rel))))
            return finish(out, name)

    # 2. an archive laid out like the game folder
    markers = layout.get("root_markers", [])
    data = layout.get("data")
    if markers or data:
        for d, depth in levels(root, 4):
            names = entries(d)
            if markers and any(matches(n, markers) for n in names):
                # a loader's own top folder is the root; "Data" at the top is the Data folder
                for src, rel in files_under(d, ignore):
                    out.append((src, rel))
                return finish(out, name)
            if data and any(matches(n, data["markers"]) for n in names):
                for src, rel in files_under(d, ignore):
                    out.append((src, join(data["dir"], rel)))
                return finish(out, name)

    # 3. known top-level folders (plugins/, config/, ...), loose files by extension
    base = unwrap(root)
    dmap = layout.get("dir_map", {})
    emap = layout.get("ext_map", {})
    default = fill(layout.get("default", ""), safe)
    if dmap:
        for d, _ in levels(root, 3):
            if any(n.lower() in dmap and os.path.isdir(os.path.join(d, n)) for n in entries(d)):
                base = d
                break
    for n in entries(base):
        p = os.path.join(base, n)
        if os.path.isdir(p):
            target = dmap.get(n.lower())
            if target is not None:
                for src, rel in files_under(p):
                    out.append((src, join(fill(target, safe), rel)))
            else:
                for src, rel in files_under(p):
                    out.append((src, join(default, os.path.join(n, rel))))
        else:
            if matches(n, ignore):
                continue
            ext = os.path.splitext(n)[1].lower()
            target = emap.get(ext)
            out.append((p, join(fill(target, safe) if target is not None else default, n)))
    return finish(out, name)


def finish(out, name):
    if not out:
        raise LayoutError(f"{name} has no files in it")
    seen, clean = set(), []
    for src, rel in out:
        rel = os.path.normpath(rel).replace(os.sep, "/")
        if rel.startswith("../") or rel.startswith("/") or rel == "..":
            continue
        if rel.lower() in seen:
            continue
        seen.add(rel.lower())
        clean.append((src, rel))
    return clean


def find_fomod(root):
    """the folder that holds fomod/ModuleConfig.xml, or None"""
    for d, _ in levels(root, 4):
        for n in entries(d):
            if n.lower() == "fomod":
                fd = os.path.join(d, n)
                for f in entries(fd):
                    if f.lower() == "moduleconfig.xml":
                        return d, os.path.join(fd, f)
    return None
