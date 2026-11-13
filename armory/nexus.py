"""Nexus Mods: the account (personal API key), mod info, files, downloads, updates, endorsing,
and search (the public v2 GraphQL API, which needs no key).

Logging in uses the personal API key from https://next.nexusmods.com/settings/api-keys: Nexus only
lets registered apps use its one-click sign-in. Free accounts download through the website's
"Mod Manager Download" button, which opens an nxm:// link that Armory handles; Premium accounts can
also download from inside Armory.
"""
import json
import re
import time
import urllib.parse

from . import VERSION, config, oauth
from .net import NetError, get_json, request

API = "https://api.nexusmods.com"
GQL = "https://api.nexusmods.com/v2/graphql"
SITE = "https://www.nexusmods.com"
KEY_PAGE = "https://next.nexusmods.com/settings/api-keys"


def mod_url(domain, mod_id, tab=None):
    return f"{SITE}/{domain}/mods/{mod_id}" + (f"?tab={tab}" if tab else "")


def game_url(domain):
    return f"{SITE}/games/{domain}/mods"


def parse_nxm(url):
    """nxm://<game>/mods/<mod>/files/<file>?key=..&expires=..&user_id=.. -> dict, or None"""
    m = re.match(r"^nxm://([^/]+)/mods/(\d+)/files/(\d+)/?(\?.*)?$", url.strip(), re.IGNORECASE)
    if not m:
        return None
    q = urllib.parse.parse_qs((m.group(4) or "?")[1:])
    return {"domain": m.group(1).lower(), "mod_id": int(m.group(2)), "file_id": int(m.group(3)),
            "key": (q.get("key") or [""])[0], "expires": (q.get("expires") or [""])[0],
            "user_id": (q.get("user_id") or [""])[0]}


class Nexus:
    def __init__(self, key=None):
        self.key = key if key is not None else config.nexus_key()
        self.user = None
        self.remaining = None

    @property
    def logged_in(self):
        return bool(self.key) or oauth.signed_in()

    @property
    def premium(self):
        return bool(self.user and (self.user.get("is_premium") or self.user.get("is_premium?")))

    def _headers(self):
        h = {"Application-Name": "Armory", "Application-Version": VERSION, "Accept": "application/json"}
        token = oauth.access_token() if oauth.signed_in() else ""
        if token:
            h["Authorization"] = f"Bearer {token}"
        else:
            h["apikey"] = self.key
        return h

    def get(self, path, **params):
        if not self.logged_in:
            raise NetError("Log in to Nexus Mods first (Settings → Nexus Mods)", 401)
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        for attempt in range(3):
            try:
                raw, headers = request(url, headers=self._headers())
                break
            except NetError as e:
                # rate limited: wait a little (longer each time) and try again, then give up
                if e.status != 429 or attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        rem = headers.get("x-rl-daily-remaining") or headers.get("X-RL-Daily-Remaining")
        if rem:
            self.remaining = int(rem)
        return json.loads(raw)

    def post(self, path, data):
        if not self.logged_in:
            raise NetError("Log in to Nexus Mods first", 401)
        raw, _ = request(API + path, data=urllib.parse.urlencode(data), method="POST",
                         headers=dict(self._headers(), **{"Content-Type": "application/x-www-form-urlencoded"}))
        try:
            return json.loads(raw)
        except ValueError:
            return {}

    # -- account --
    def validate(self):
        self.user = self.get("/v1/users/validate.json")
        return self.user

    # -- mods --
    def mod(self, domain, mod_id):
        return self.get(f"/v1/games/{domain}/mods/{mod_id}.json")

    def files(self, domain, mod_id):
        return self.get(f"/v1/games/{domain}/mods/{mod_id}/files.json")

    def download_links(self, domain, mod_id, file_id, key=None, expires=None):
        params = {"key": key, "expires": expires} if key else {}
        return self.get(f"/v1/games/{domain}/mods/{mod_id}/files/{file_id}/download_link.json", **params)

    def md5_search(self, domain, md5):
        try:
            return self.get(f"/v1/games/{domain}/mods/md5_search/{md5}.json")
        except NetError as e:
            if e.status == 404:
                return []
            raise

    def endorse(self, domain, mod_id, version, on=True):
        return self.post(f"/v1/games/{domain}/mods/{mod_id}/{'endorse' if on else 'abstain'}.json",
                         {"Version": version or ""})

    def endorsements(self):
        return self.get("/v1/user/endorsements.json")

    def track(self, domain, mod_id):
        return self.post(f"/v1/user/tracked_mods.json?domain_name={domain}", {"mod_id": mod_id})

    def update_for(self, domain, mod_id, file_id, version):
        """{"file_id", "version", "name"} of a newer file for an installed one, or None"""
        data = self.files(domain, mod_id)
        files = {f["file_id"]: f for f in data.get("files", [])}
        cur = file_id
        if cur:
            nxt = {u["old_file_id"]: u["new_file_id"] for u in data.get("file_updates", [])}
            seen = set()
            while cur in nxt and cur not in seen:
                seen.add(cur)
                cur = nxt[cur]
            if cur != file_id and cur in files:
                f = files[cur]
                return {"file_id": cur, "version": f.get("version") or f.get("mod_version") or "",
                        "name": f.get("name", "")}
            if file_id in files and files[file_id].get("category_name") not in ("OLD_VERSION", "ARCHIVED"):
                return None
        # no file chain: the newest main file, if its version differs
        mains = [f for f in files.values() if f.get("category_name") == "MAIN"]
        if mains:
            f = max(mains, key=lambda f: f.get("uploaded_timestamp", 0))
            if f["file_id"] != file_id and str(f.get("version") or "") != str(version or ""):
                return {"file_id": f["file_id"], "version": f.get("version", ""), "name": f.get("name", "")}
        return None


SORTS = {"popular": {"downloads": {"direction": "DESC"}},
         "endorsed": {"endorsements": {"direction": "DESC"}},
         "updated": {"updatedAt": {"direction": "DESC"}},
         "new": {"createdAt": {"direction": "DESC"}}}

SEARCH_QUERY = """query($f: ModsFilter, $s: [ModsSort!], $n: Int, $o: Int) {
  mods(filter: $f, sort: $s, count: $n, offset: $o) {
    totalCount
    nodes { modId name summary version author pictureUrl thumbnailUrl endorsements downloads
            adultContent updatedAt createdAt uploader { name } modCategory { name } }
  }
}"""


def search(domain, text="", sort="popular", offset=0, count=30, adult=True):
    f = {"gameDomainName": [{"value": domain, "op": "EQUALS"}]}
    if text.strip():
        f["name"] = [{"value": text.strip(), "op": "WILDCARD"}]
    if not adult:
        f["adultContent"] = [{"value": False, "op": "EQUALS"}]
    res = get_json(GQL, data={"query": SEARCH_QUERY,
                              "variables": {"f": f, "s": [SORTS.get(sort, SORTS["popular"])], "n": count, "o": offset}},
                   headers={"Application-Name": "Armory", "Application-Version": VERSION})
    if res.get("errors"):
        raise NetError(res["errors"][0].get("message", "Search failed"))
    mods = res["data"]["mods"]
    return mods["totalCount"], mods["nodes"]


REQ_QUERY = """query($ids: [CompositeDomainWithIdInput!]!) {
  legacyModsByDomain(ids: $ids) {
    nodes { modId modRequirements { nexusRequirements { nodes { modId modName url notes externalRequirement } } } }
  }
}"""


def requirements(domain, mod_ids):
    """{mod id: [{"mod_id", "name", "url", "notes", "external"}]} from the mods' pages (public API, no key)"""
    out = {}
    ids = sorted({int(i) for i in mod_ids if i})
    for i in range(0, len(ids), 40):
        chunk = [{"gameDomain": domain, "modId": m} for m in ids[i:i + 40]]
        res = get_json(GQL, data={"query": REQ_QUERY, "variables": {"ids": chunk}},
                       headers={"Application-Name": "Armory", "Application-Version": VERSION})
        if res.get("errors"):
            raise NetError(res["errors"][0].get("message", "Couldn't read requirements"))
        for node in res["data"]["legacyModsByDomain"]["nodes"]:
            reqs = []
            for r in ((node.get("modRequirements") or {}).get("nexusRequirements") or {}).get("nodes") or []:
                reqs.append({"mod_id": int(r["modId"]) if str(r.get("modId") or "").isdigit() else 0,
                             "name": r.get("modName") or "", "url": r.get("url") or "", "notes": r.get("notes") or "",
                             "external": bool(r.get("externalRequirement"))})
            out[int(node["modId"])] = reqs
    return out
