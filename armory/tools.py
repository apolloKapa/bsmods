"""Tools: programs you run inside a game's Proton prefix (script extenders, config editors, xEdit...),
and starting the game through one of them instead of Steam.

Windows programs run with the Proton the game uses in Steam (its compatibility setting, else your
default, else the newest installed), with the game's own prefix, the way Steam runs them.
"""
import os
import re
import subprocess

from . import config, games


def tools(game):
    return list((config.get("tools", {}) or {}).get(game.id, []))


def save_tools(game, items):
    all_ = dict(config.get("tools", {}) or {})
    all_[game.id] = items
    config.save_conf(tools=all_)


def play_with(game):
    """the tool Play starts the game with ("" = Steam)"""
    name = (config.get("play_with", {}) or {}).get(game.id, "")
    return name if any(t["name"] == name for t in tools(game)) else ""


def set_play_with(game, name):
    d = dict(config.get("play_with", {}) or {})
    if name:
        d[game.id] = name
    else:
        d.pop(game.id, None)
    config.save_conf(play_with=d)


def _compat_tool(appid):
    """the compatibility tool Steam is set to use for a game (or the default one)"""
    root = games.steam_root()
    if not root:
        return ""
    try:
        text = open(os.path.join(root, "config", "config.vdf"), encoding="utf-8", errors="replace").read()
    except OSError:
        return ""
    m = re.search(r'"CompatToolMapping"\s*\{', text)
    if not m:
        return ""
    block = text[m.end():]
    names = {}
    for am in re.finditer(r'"(\d+)"\s*\{\s*"name"\s*"([^"]*)"', block):
        names[am.group(1)] = am.group(2)
    return names.get(str(appid)) or names.get("0") or ""


def proton_for(appid):
    """the proton script to run a game's tools with, or None"""
    root = games.steam_root()
    if not root:
        return None
    custom = [os.path.join(r, "compatibilitytools.d") for r in games.STEAM_ROOTS] + \
        ["/usr/share/steam/compatibilitytools.d"]
    commons = [os.path.join(lib, "steamapps", "common") for lib in games.steam_libraries()]
    want = _compat_tool(appid)
    cands = []
    if want:
        for d in custom:
            cands.append(os.path.join(d, want, "proton"))
        pretty = {"proton_experimental": "Proton - Experimental", "proton_hotfix": "Proton Hotfix"}.get(want)
        n = re.match(r"proton_(\d+)", want)
        for c in commons:
            try:
                for name in os.listdir(c):
                    if name == pretty or (n and name.startswith(f"Proton {n.group(1)}")):
                        cands.append(os.path.join(c, name, "proton"))
            except OSError:
                pass
    # no setting for the game: what Steam uses then (its own Proton, Experimental first), then the
    # newest GE-Proton, then anything else
    def natural(n):
        return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", n)]

    for c in commons:
        try:
            names = os.listdir(c)
        except OSError:
            continue
        steam = [n for n in names if n.startswith("Proton") and "Runtime" not in n]
        steam.sort(key=lambda n: (n != "Proton - Experimental", [-x if isinstance(x, int) else 0 for x in natural(n)]))
        cands += [os.path.join(c, n, "proton") for n in steam]
    for d in custom:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        ge = sorted((n for n in names if n.lower().startswith("ge-proton")), key=natural, reverse=True)
        rest = sorted((n for n in names if n not in ge), key=natural, reverse=True)
        cands += [os.path.join(d, n, "proton") for n in ge + rest]
    return next((p for p in cands if os.path.isfile(p)), None)


def run(game, tool):
    """start a tool for a game: the process"""
    exe = tool["exe"]
    args = tool.get("args", "").split() if tool.get("args") else []
    cwd = os.path.dirname(exe)
    env = config.clean_env()
    if exe.lower().endswith((".exe", ".bat", ".msi")):
        if not game.appid:
            raise OSError("Windows tools need a Steam game (its Proton prefix)")
        proton = proton_for(game.appid)
        if not proton:
            raise OSError("No Proton found: install one in Steam")
        lib = game.library or (games.steam_install(game.appid)[0])
        compat = os.path.join(lib, "steamapps", "compatdata", str(game.appid)) if lib else ""
        if not compat or not os.path.isdir(compat):
            raise OSError("Run the game once from Steam first, so its Proton prefix exists")
        env.update(STEAM_COMPAT_DATA_PATH=compat, STEAM_COMPAT_CLIENT_INSTALL_PATH=games.steam_root() or "",
                   SteamAppId=str(game.appid), SteamGameId=str(game.appid))
        # the same DLL overrides the game's launch options set (mod loaders)
        opts = games.steam_launch_options(game.appid) or ""
        m = re.search(r'WINEDLLOVERRIDES="?([^"\s]+)', opts)
        if m:
            env["WINEDLLOVERRIDES"] = m.group(1)
        cmd = [proton, "run", exe] + args
    else:
        cmd = [exe] + args
    return subprocess.Popen(cmd, cwd=cwd, env=env, start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
