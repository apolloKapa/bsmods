"""Armory without the window, for scripts and terminals.

  armory games                         the games Armory lists
  armory mods GAME                     the mods of a game's profile, in order (* = on)
  armory profiles GAME                 its profiles (* = in use)
  armory use GAME PROFILE              switch profile (and put its mods in the game)
  armory enable|disable GAME MOD...    turn mods on or off (by id or name) and deploy
  armory deploy GAME                   put the mods that are on in the game
  armory purge GAME                    take every mod out of the game
  armory install GAME FILE...          install archives (mods with an installer wizard need the window)
  armory play GAME                     deploy, then start the game
  armory nexus                         whether you're logged in to Nexus Mods (and as whom)
  armory version                       Armory's version (and whether a newer one is out)
GAME is an id like lethalcompany or a name like "Lethal Company".
"""
import os
import shutil
import subprocess
import sys
import tempfile

from . import VERSION, config, games, install, layout, saves, updates
from .store import Store

COMMANDS = {"games", "mods", "profiles", "use", "enable", "disable", "deploy", "purge", "install", "play",
            "version", "nexus", "help", "--help", "-h"}


def find_game(q):
    gs = games.detect()
    ql = q.lower()
    for g in gs:
        if g.id == ql or g.name.lower() == ql:
            return g
    hits = [g for g in gs if ql in g.name.lower() or ql in g.id]
    if len(hits) == 1:
        return hits[0]
    raise SystemExit(f"armory: no single game matches “{q}” (see: armory games)")


def find_mod(st, q):
    if q in st.mods:
        return q
    hits = [mid for mid, m in st.mods.items() if (m.get("name") or "").lower() == q.lower()] or \
        [mid for mid, m in st.mods.items() if q.lower() in (m.get("name") or mid).lower()]
    if len(hits) != 1:
        raise SystemExit(f"armory: no single mod matches “{q}” (see: armory mods GAME)")
    return hits[0]


def report(stats):
    print(f"{stats['added']} files put in, {stats['removed']} taken out, {stats['kept']} unchanged"
          + (f", {len(stats['skipped'])} skipped" if stats["skipped"] else ""))


def main(argv):
    if not argv or argv[0] in ("help", "--help", "-h"):
        print(__doc__.strip())
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "version":
        print(f"Armory {VERSION}")
        try:
            new = updates.latest()
            if new:
                print(f"Armory {new['version']} is out: {new['url']}")
        except Exception as e:  # noqa: BLE001 - only informational
            print(f"(couldn't check for a newer one: {e})")
        return 0
    if cmd == "nexus":
        from . import nexus, oauth
        nx = nexus.Nexus()
        if not nx.logged_in:
            print("Not logged in to Nexus Mods (Settings → Nexus Mods in the window)")
            return 1
        u = nx.validate()
        how = "signed in through Nexus" if oauth.signed_in() else "API key"
        print(f"Logged in as {u.get('name')} ({'Premium' if nx.premium else 'free account'}, {how})")
        return 0
    if cmd == "games":
        for g in games.detect():
            st = Store(g)
            print(f"{g.id:24} {g.name:32} {len(st.mods):4} mods  {'' if g.found else '(not found)'}")
        return 0
    if not args:
        raise SystemExit(f"armory {cmd}: which game?")
    g = find_game(args[0])
    st = Store(g)
    if cmd == "mods":
        for m in st.ordered():
            print(f"{'*' if m['enabled'] else ' '} {m['priority'] + 1:3}  {m['id']:36} {m.get('name', '')}"
                  + (f"  v{m['version']}" if m.get("version") else ""))
        return 0
    if cmd == "profiles":
        for p in st.profiles:
            print(("* " if p == st.active else "  ") + p)
        return 0
    if cmd == "use":
        if len(args) < 2 or args[1] not in st.profiles:
            raise SystemExit("armory use: name one of: " + ", ".join(st.profiles))
        old = st.active
        st.switch_profile(args[1])
        if saves.per_profile(g):
            saves.swap(g, old, args[1])
        report(st.deploy())
        return 0
    if cmd in ("enable", "disable"):
        for q in args[1:]:
            st.set_enabled(find_mod(st, q), cmd == "enable")
        report(st.deploy())
        return 0
    if cmd == "deploy":
        report(st.deploy())
        return 0
    if cmd == "purge":
        report(st.purge())
        return 0
    if cmd == "install":
        for f in args[1:]:
            os.makedirs(os.path.join(config.DATA, "tmp"), exist_ok=True)
            tmp = tempfile.mkdtemp(prefix="install-", dir=os.path.join(config.DATA, "tmp"))
            try:
                root = install.unpack(os.path.abspath(f), tmp)
                if layout.find_fomod(root):
                    print(f"{f}: has an installer wizard (FOMOD); install it from the Armory window")
                    continue
                if config.get("scan_mods", False):
                    found = layout.scan(root)
                    if found:
                        print(f"{f}: ClamAV found {found[0][1]} in {found[0][0]}; not installed")
                        continue
                mid = install.stage(st, root, layout.mod_name_from_file(f),
                                    {"source": {"type": "local"}, "archive": os.path.abspath(f)})
                print(f"installed {st.mods[mid].get('name')} ({mid})")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        report(st.deploy())
        return 0
    if cmd == "play":
        report(st.deploy())
        if g.launch:
            subprocess.Popen(g.launch, shell=True, cwd=g.path, start_new_session=True, env=config.clean_env())
        elif g.appid:
            subprocess.Popen(["xdg-open", f"steam://rungameid/{g.appid}"], start_new_session=True,
                             env=config.clean_env())
        return 0
    raise SystemExit(f"armory: unknown command {cmd} (armory help)")


def run():
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # noqa: BLE001 - shown as one line
        if isinstance(e, SystemExit):
            raise
        print(f"armory: {e}", file=sys.stderr)
        sys.exit(1)
