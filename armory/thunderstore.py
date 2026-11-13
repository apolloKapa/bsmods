"""Thunderstore (thunderstore.io): the package list of a game, dependencies, and ror2mm:// links.

The list comes from the community's package-listing-index (gzip chunks). Only what Armory shows
is kept, in ~/.cache/armory/thunderstore/<community>.json, refreshed after an hour.
"""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from .config import CACHE, read_json, write_json
from .net import NetError, get_json, request

SITE = "https://thunderstore.io"
MAX_AGE = 3600


def package_url(community, owner, name):
    return f"{SITE}/c/{community}/p/{owner}/{name}/"


def download_url(owner, name, version):
    return f"{SITE}/package/download/{owner}/{name}/{version}/"


def parse_link(url):
    """ror2mm://v1/install/thunderstore.io/<owner>/<name>/<version>/ -> dict, or None"""
    m = re.match(r"^ror2mm://v1/install/[^/]+/([^/]+)/([^/]+)/([^/?]+)/?", url.strip(), re.IGNORECASE)
    if not m:
        return None
    return {"owner": m.group(1), "name": m.group(2), "version": m.group(3),
            "full": f"{m.group(1)}-{m.group(2)}"}


def split_dep(dep):
    """"Owner-Name-1.2.3" -> ("Owner-Name", "1.2.3")"""
    full, _, ver = dep.rpartition("-")
    return (full, ver) if full else (dep, "")


def vtuple(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-+]", str(v or "0")))


def _compact(p):
    vs = p.get("versions") or []
    if not vs:
        return None
    latest = vs[0]
    return {"full": p.get("full_name") or f"{p['owner']}-{p['name']}", "name": p["name"], "owner": p["owner"],
            "desc": latest.get("description", ""), "icon": latest.get("icon", ""),
            "version": latest.get("version_number", ""), "deps": latest.get("dependencies", []),
            "downloads": sum(v.get("downloads", 0) for v in vs), "rating": p.get("rating_score", 0),
            "nsfw": bool(p.get("has_nsfw_content")), "deprecated": bool(p.get("is_deprecated")),
            "pinned": bool(p.get("is_pinned")), "categories": p.get("categories", []),
            "updated": p.get("date_updated", ""), "created": p.get("date_created", ""),
            "url": p.get("package_url", ""), "size": latest.get("file_size", 0),
            "website": latest.get("website_url", "")}


def _fetch_chunk(url):
    raw, _ = request(url, timeout=90)
    return [c for c in (_compact(p) for p in json.loads(raw)) if c]


def listing(community, force=False, progress=None):
    """every package of a community, newest-updated info: [dict]"""
    path = os.path.join(CACHE, "thunderstore", f"{community}.json")
    cached = read_json(path, {})
    if not force and cached and time.time() - cached.get("time", 0) < MAX_AGE:
        return cached["packages"]
    try:
        raw, _ = request(f"{SITE}/c/{community}/api/v1/package-listing-index/", timeout=30)
        chunks = json.loads(raw)
        out = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            for i, part in enumerate(pool.map(_fetch_chunk, chunks)):
                out += part
                if progress:
                    progress(i + 1, len(chunks))
    except (NetError, ValueError) as e:
        if cached:
            return cached["packages"]
        raise NetError(f"Couldn't load Thunderstore: {e}") from None
    write_json(path, {"time": time.time(), "packages": out})
    return out


def index(packages):
    return {p["full"].lower(): p for p in packages}


def resolve(full, packages, have=None):
    """the packages to install for one, dependencies first: [package dict]
    have: {full lower: installed version}; ones already installed at that version or newer are left out"""
    idx = index(packages)
    have = have or {}
    out, seen = [], set()

    def visit(name, want=""):
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        p = idx.get(key)
        if not p:
            return
        for d in p.get("deps", []):
            dn, dv = split_dep(d)
            visit(dn, dv)
        if key in have and vtuple(have[key]) >= vtuple(want or p["version"]):
            return
        out.append(p)

    visit(full)
    return out


def package_info(owner, name):
    """one package, straight from the API (for links to packages not in the cached list)"""
    p = get_json(f"{SITE}/api/experimental/package/{owner}/{name}/")
    latest = p.get("latest") or {}
    return {"full": p.get("full_name") or f"{owner}-{name}", "name": p.get("name", name), "owner": owner,
            "desc": latest.get("description", ""), "icon": latest.get("icon", ""),
            "version": latest.get("version_number", ""), "deps": latest.get("dependencies", []),
            "downloads": latest.get("downloads", 0), "rating": p.get("rating_score", 0), "nsfw": False,
            "deprecated": p.get("is_deprecated", False), "categories": [], "url": p.get("package_url", ""),
            "updated": p.get("date_updated", ""), "created": p.get("date_created", ""), "size": 0}


def search(packages, text="", sort="popular", nsfw=True, deprecated=False):
    q = text.strip().lower()
    out = [p for p in packages
           if (nsfw or not p["nsfw"]) and (deprecated or not p["deprecated"])
           and (not q or q in p["name"].lower() or q in p["owner"].lower() or q in p["desc"].lower())]
    key = {"popular": lambda p: -p["downloads"], "rating": lambda p: -p["rating"],
           "updated": lambda p: p["updated"], "new": lambda p: p["created"],
           "name": lambda p: p["name"].lower()}.get(sort, lambda p: -p["downloads"])
    out.sort(key=key, reverse=sort in ("updated", "new"))
    if not q and sort == "popular":
        # pinned ones (the mod loader) first, like the website
        out.sort(key=lambda p: not p["pinned"])
    return out
