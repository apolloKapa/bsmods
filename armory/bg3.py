"""Baldur's Gate 3: the game loads .pak mods listed in PlayerProfiles/Public/modsettings.lsx.

Most BG3 mods ship an info.json (made by the mod packaging tools) with each mod's UUID, folder,
name and version. After deploying, the mods that are on are added to modsettings.lsx in their order
and the ones Armory added before but are off now are taken out; entries you or the game added (the
base game's own) are left alone. The file is the game's: run BG3 once so it exists.
"""
import json
import os
import xml.etree.ElementTree as ET

from .config import DATA, read_json, write_json

SETTINGS = "AppData/Local/Larian Studios/Baldur's Gate 3/PlayerProfiles/Public/modsettings.lsx"


def info_entries(folder):
    """the mods an unpacked/staged mod's info.json describes"""
    out = []
    for d, _, files in os.walk(folder):
        for f in files:
            if f.lower() != "info.json":
                continue
            data = read_json(os.path.join(d, f), {})
            for m in data.get("Mods") or ([data] if data.get("UUID") else []):
                if m.get("UUID") and m.get("Folder"):
                    out.append({"UUID": m["UUID"], "Folder": m["Folder"], "Name": m.get("Name") or m["Folder"],
                                "Version64": str(m.get("Version64") or m.get("Version") or "36028797018963968"),
                                "MD5": data.get("MD5", "")})
    return out


def _attr(node, key):
    for a in node.findall("attribute"):
        if a.get("id") == key:
            return a.get("value")
    return None


def _desc(m):
    n = ET.Element("node", id="ModuleShortDesc")
    for key, typ in (("Folder", "LSString"), ("MD5", "LSString"), ("Name", "LSString"),
                     ("PublishHandle", "uint64"), ("UUID", "guid"), ("Version64", "int64")):
        ET.SubElement(n, "attribute", id=key, type=typ, value=str(m.get(key, "0" if typ == "uint64" else "")))
    return n


def write(store):
    """update modsettings.lsx for the mods that are on: (number of mods listed, a note or "")"""
    user = store.game.prefix_user
    if not user:
        return 0, "Run Baldur's Gate 3 once from Steam (its Proton prefix doesn't exist yet)"
    from .store import resolve_case
    path = resolve_case(user, SETTINGS)
    if not os.path.isfile(path):
        return 0, "Run Baldur's Gate 3 once so it makes modsettings.lsx, then turn a mod on or off"
    wanted = []
    for mid in store.profile["order"]:
        if mid in store.profile["enabled"]:
            wanted += info_entries(store.mod_path(mid))
    no_info = [store.mods[mid].get("name", mid) for mid in store.profile["enabled"]
               if not info_entries(store.mod_path(mid))
               and any(f.lower().endswith(".pak") for _, _, fs in os.walk(store.mod_path(mid)) for f in fs)]
    track = os.path.join(DATA, "games", store.game.id, "bg3-modsettings.json")
    before = set(read_json(track, {}).get("uuids", []))
    tree = ET.parse(path)
    root = tree.getroot()
    mods = next((n for n in root.iter("node") if n.get("id") == "Mods"), None)
    if mods is None:
        return 0, "modsettings.lsx doesn't look like BG3's; left alone"
    kids = mods.find("children")
    if kids is None:
        kids = ET.SubElement(mods, "children")
    order = next((n for n in root.iter("node") if n.get("id") == "ModOrder"), None)
    order_kids = order.find("children") if order is not None else None
    want_ids = [m["UUID"] for m in wanted]
    # take out what Armory listed before (it's added again below if it's still on)
    for n in list(kids):
        if _attr(n, "UUID") in before:
            kids.remove(n)
    if order_kids is not None:
        for n in list(order_kids):
            if _attr(n, "UUID") in before:
                order_kids.remove(n)
    present = {_attr(n, "UUID") for n in kids}
    added = []
    for m in wanted:
        if m["UUID"] in present:
            continue
        kids.append(_desc(m))
        if order_kids is not None:
            o = ET.SubElement(order_kids, "node", id="Module")
            ET.SubElement(o, "attribute", id="UUID", type="FixedString", value=m["UUID"])
        added.append(m["UUID"])
    tmp = path + ".armory-tmp"
    tree.write(tmp, encoding="UTF-8", xml_declaration=True)
    os.replace(tmp, path)
    write_json(track, {"uuids": added})
    note = ""
    if no_info:
        note = "These have no info.json, so BG3 may not list them: " + ", ".join(no_info[:4])
    return len(want_ids), note


def dump(path):
    return json.dumps([(_attr(n, "Folder"), _attr(n, "UUID")) for n in ET.parse(path).getroot().iter("node")
                       if n.get("id") == "ModuleShortDesc"])
