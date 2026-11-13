"""Installing a mod: unpack, read what it says about itself, lay it out for the game, stage it."""
import os
import shutil

from . import config, layout
from .config import read_json


def unpack(src, tmp):
    """the folder to read the mod from: src itself if it's a folder, else unpacked into tmp"""
    if os.path.isdir(src):
        return src
    if not layout.is_archive(src):
        # a single loose file (a .dll, .esp, .pak...): a folder with just that
        d = os.path.join(tmp, "file")
        os.makedirs(d, exist_ok=True)
        shutil.copy2(src, d)
        return d
    d = os.path.join(tmp, "unpacked")
    layout.extract(src, d, int(config.get("max_unpack_gb", 100) or 100))
    return d


def read_meta(root):
    """name, version, author, summary and a thumbnail from a manifest in the mod, if it has one
    (a pack of several mods keeps the archive's name)"""
    meta = {}
    found = [os.path.join(d, n) for d, _ in layout.levels(root, 3) for n in layout.entries(d)
             if n.lower() == "manifest.json"]
    if len(found) == 1:
        for path in found:
            d = os.path.dirname(path)
            m = read_json(path, {})
            if not m:
                continue
            field = lambda *ks: next((str(m[k]) for k in ks if m.get(k) not in (None, "")), "")
            # Blade & Sorcery
            if "GameVersion" in m or "ModVersion" in m:
                meta.update(name=field("Name"), version=field("ModVersion"), author=field("Author"),
                            summary=field("Description"), game_version=field("GameVersion"))
                if m.get("Thumbnail"):
                    meta["thumb_src"] = os.path.join(d, str(m["Thumbnail"]))
            # Thunderstore / SMAPI
            elif "version_number" in m or "Version" in m:
                meta.update(name=field("name", "Name"), version=field("version_number", "Version"),
                            author=field("author", "Author"), summary=field("description", "Description"))
            meta = {k: v for k, v in meta.items() if v}
            if meta:
                return meta
    return meta


def files_for(root, game, name, fomod_files=None):
    if fomod_files is not None:
        data = game.layout.get("data")
        base = data["dir"] if data else ""
        return layout.finish([(src, f"{base}/{rel}" if base else rel) for src, rel in fomod_files], name)
    return layout.plan(root, game.layout, name)


def stage(store, root, name, meta, fomod_files=None, replace=None, enable=True):
    """put a mod in the store: its id"""
    found = read_meta(root)
    meta = dict(meta)
    for k, v in found.items():
        if k != "thumb_src" and not meta.get(k):
            meta[k] = v
    files = files_for(root, store.game, name, fomod_files)
    thumb = found.get("thumb_src")
    if thumb:
        for src, rel in files:
            if os.path.normcase(src) == os.path.normcase(thumb):
                meta["thumb_rel"] = rel
                break
    if not meta.get("picture"):
        # the first picture in the mod, if it ships one at its top
        for src, rel in files:
            if rel.count("/") <= 4 and src.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) \
                    and os.path.getsize(src) > 8000 and "icon" not in rel.lower():
                meta.setdefault("thumb_rel", rel)
                break
    return store.add(meta.get("name") or name, files, meta, replace=replace, enable=enable)
