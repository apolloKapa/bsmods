"""The games Armory knows, finding them in Steam, and the Proton prefix of each.

A game's "layout" says where the files of a downloaded mod go (see layout.py):
  root_markers  names (files or folders) that, when an archive has them, mean "this is the game
                folder": the archive is laid over the game as it is
  data          {"dir": ..., "markers": [...]}: archives with these (folders or *.ext) go in that
                folder (Bethesda's Data)
  folder_mod    {"marker": name or glob, "dir": ..., "prefix": ""}: every folder with that file (or
                folder) in it is one mod, put in dir/<prefix><folder> (Blade & Sorcery, Stardew Valley)
  dir_map       top-level folders of an archive and where they go ({name} is the mod's name)
  ext_map       loose files by extension
  default       where everything else goes ("" is the game folder)
  ignore_top    files at the top of a package that are only the package's own (Thunderstore)
A path that starts with "@prefix/" is in the Proton prefix's user folder
(compatdata/<appid>/pfx/drive_c/users/steamuser), "@home/" in your home folder (native Linux games).
"""
import os
import re

from .config import HOME, get, save_conf

STEAM_ROOTS = [os.path.join(HOME, ".local/share/Steam"), os.path.join(HOME, ".steam/steam"),
               os.path.join(HOME, ".steam/root"),
               os.path.join(HOME, ".var/app/com.valvesoftware.Steam/.local/share/Steam")]

THUNDERSTORE_TOP = ["manifest.json", "icon.png", "readme.md", "changelog.md", "license", "license.md",
                    "license.txt"]

BEPINEX = {
    "loader": "bepinex",
    "root_markers": ["bepinex", "doorstop_config.ini", "winhttp.dll", "run_bepinex.sh", ".doorstop_version"],
    "dir_map": {"plugins": "BepInEx/plugins/{name}", "patchers": "BepInEx/patchers/{name}",
                "config": "BepInEx/config", "core": "BepInEx/core", "monomod": "BepInEx/monomod/{name}"},
    "ext_map": {".dll": "BepInEx/plugins/{name}"},
    "default": "BepInEx/plugins/{name}",
    "ignore_top": THUNDERSTORE_TOP,
}

MELONLOADER = {
    "loader": "melonloader",
    "root_markers": ["melonloader", "version.dll", "userlibs", "userdata", "mods", "plugins"],
    "ext_map": {".dll": "Mods"},
    "default": "Mods",
    "ignore_top": THUNDERSTORE_TOP,
}

ROOT = {"root_markers": [], "default": ""}


def bethesda(data_markers_extra=()):
    return {
        "root_markers": ["data", "skse64_loader.exe", "skse_loader.exe", "f4se_loader.exe", "nvse_loader.exe",
                         "fose_loader.exe", "obse_loader.exe", "sfse_loader.exe", "d3d11.dll", "dxgi.dll",
                         "enblocal.ini"],
        "data": {"dir": "Data", "markers": ["meshes", "textures", "scripts", "interface", "sound", "music", "skse",
                                            "f4se", "nvse", "obse", "sfse", "seq", "strings", "video", "materials",
                                            "lodsettings", "grass", "shadersfx", "menus", "fonts", "mcm", "nemesis_engine",
                                            "*.esp", "*.esm", "*.esl", "*.bsa", "*.ba2", *data_markers_extra]},
        "default": "Data",
    }


def plugins(appdata, masters, star=True):
    """Bethesda load order: Plugins.txt in the prefix's AppData/Local/<appdata>"""
    return {"appdata": appdata, "masters": masters, "star": star}


BG3_MODS = "@prefix/AppData/Local/Larian Studios/Baldur's Gate 3/Mods"
OBR_PAKS = "OblivionRemastered/Content/Paks/~mods"
OBR_DATA = "OblivionRemastered/Content/Dev/ObvData/Data"
SKYRIM_MASTERS = ["Skyrim.esm", "Update.esm", "Dawnguard.esm", "HearthFires.esm", "Dragonborn.esm"]

# id: (name, steam appid, nexus domain, thunderstore community, folder that proves it, layout, extra)
GAMES = {
    "bladeandsorcery": dict(name="Blade & Sorcery", appid=629730, nexus="bladeandsorcery", proof="BladeAndSorcery_Data",
                            layout={"folder_mod": {"marker": "manifest.json",
                                                   "dir": "BladeAndSorcery_Data/StreamingAssets/Mods"},
                                    "root_markers": ["bladeandsorcery_data"],
                                    "default": "BladeAndSorcery_Data/StreamingAssets/Mods/{name}"},
                            adopt="BladeAndSorcery_Data/StreamingAssets/Mods"),
    "lethalcompany": dict(name="Lethal Company", appid=1966720, nexus="lethalcompany", thunderstore="lethal-company",
                          proof="Lethal Company_Data", layout=BEPINEX),
    "repo": dict(name="R.E.P.O.", appid=3241660, nexus="repo", thunderstore="repo", proof="REPO_Data", layout=BEPINEX),
    "contentwarning": dict(name="Content Warning", appid=2881650, nexus="contentwarning",
                           thunderstore="content-warning", proof="Content Warning_Data", layout=BEPINEX),
    "peak": dict(name="PEAK", appid=3527290, nexus="peak", thunderstore="peak", proof="PEAK_Data", layout=BEPINEX),
    "ultrakill": dict(name="ULTRAKILL", appid=1229490, nexus="ultrakill", thunderstore="ultrakill",
                      proof="ULTRAKILL_Data", layout=BEPINEX),
    "gorillatag": dict(name="Gorilla Tag", appid=1533390, nexus="gorillatag", thunderstore="gorilla-tag",
                       proof="Gorilla Tag_Data", layout=BEPINEX),
    "trombonechamp": dict(name="Trombone Champ", appid=1059990, thunderstore="trombone-champ",
                          proof="TromboneChamp_Data", layout=BEPINEX),
    "subnautica": dict(name="Subnautica", appid=264710, nexus="subnautica", thunderstore="subnautica",
                       proof="Subnautica_Data", layout=BEPINEX),
    "subnauticabelowzero": dict(name="Subnautica: Below Zero", appid=848450, nexus="subnauticabelowzero",
                                proof="SubnauticaZero_Data", layout=BEPINEX),
    "slimerancher": dict(name="Slime Rancher", appid=433340, nexus="slimerancher", proof="SlimeRancher_Data",
                         layout=BEPINEX),
    "slimerancher2": dict(name="Slime Rancher 2", appid=1657630, nexus="slimerancher2", proof="SlimeRancher2_Data",
                          layout=MELONLOADER),
    "sonsoftheforest": dict(name="Sons Of The Forest", appid=1326470, nexus="sonsoftheforest",
                            thunderstore="sons-of-the-forest", proof="SonsOfTheForest_Data",
                            layout={"root_markers": ["_redloader", "dotnet", "winhttp.dll", "mods",
                                                     "userlibs"],
                                    "ext_map": {".dll": "Mods"}, "default": "Mods", "ignore_top": THUNDERSTORE_TOP}),
    "bonelab": dict(name="BONELAB", appid=1592190, nexus="bonelab", thunderstore="bonelab", proof="BONELAB_Steam_Windows64_Data",
                    layout=dict(MELONLOADER, folder_mod={"marker": "*.pallet.json",
                                                         "dir": "@prefix/AppData/LocalLow/Stress Level Zero/BONELAB/Mods"})),
    "valheim": dict(name="Valheim", appid=892970, nexus="valheim", thunderstore="valheim", proof="valheim_Data",
                    layout=BEPINEX),
    "reddeadredemption2": dict(name="Red Dead Redemption 2", appid=1174180, nexus="reddeadredemption2",
                               proof="RDR2.exe",
                               layout={"root_markers": ["lml", "scripts", "dinput8.dll", "scripthookrdr2.dll",
                                                        "vfs.asi", "version.dll", "*.asi"],
                                       "ext_map": {".asi": ""}, "default": "lml/{name}"}),
    "nomanssky": dict(name="No Man's Sky", appid=275850, nexus="nomanssky", proof="GAMEDATA",
                      layout={"root_markers": ["gamedata", "binaries"], "dir_map": {"mods": "GAMEDATA/MODS"},
                              "default": "GAMEDATA/MODS/{name}"}),
    "doometernal": dict(name="DOOM Eternal", appid=782330, nexus="doometernal", proof="base",
                        layout={"root_markers": ["base", "mods", "eternalmodinjector.bat", "eternalmodinjectorshell.sh"],
                                "ext_map": {".zip": "Mods"}, "default": "Mods/{name}"}),
    "celeste": dict(name="Celeste", appid=504230, nexus="celeste", proof="Celeste.exe",
                    layout={"folder_mod": {"marker": "everest.yaml", "dir": "Mods"}, "root_markers": ["mods"],
                            "default": "Mods/{name}"}),
    "beatsaber": dict(name="Beat Saber", appid=620980, nexus="beatsaber", proof="Beat Saber_Data",
                      layout={"root_markers": ["plugins", "libs", "ipa", "beat saber_data", "userdata",
                                               "customsongs"],
                              "ext_map": {".dll": "Plugins"}, "default": "Plugins"}),
    "garrysmod": dict(name="Garry's Mod", appid=4000, nexus="garrysmod", proof="garrysmod",
                      layout={"root_markers": ["garrysmod"], "dir_map": {"addons": "garrysmod/addons"},
                              "ext_map": {".gma": "garrysmod/addons"}, "default": "garrysmod/addons/{name}"}),
    # well-known games people mod a lot
    "skyrimspecialedition": dict(name="Skyrim Special Edition", appid=489830, nexus="skyrimspecialedition",
                                 proof="SkyrimSE.exe", layout=bethesda(),
                                 plugins=plugins("Skyrim Special Edition", SKYRIM_MASTERS +
                                                 ["ccBGSSSE001-Fish.esm", "ccQDRSSE001-SurvivalMode.esl",
                                                  "ccBGSSSE037-Curios.esl", "ccBGSSSE025-AdvDSGS.esm",
                                                  "_ResourcePack.esl"])),
    "skyrim": dict(name="Skyrim", appid=72850, nexus="skyrim", proof="TESV.exe", layout=bethesda(),
                   plugins=plugins("Skyrim", SKYRIM_MASTERS, star=False)),
    "fallout4": dict(name="Fallout 4", appid=377160, nexus="fallout4", proof="Fallout4.exe", layout=bethesda(),
                     plugins=plugins("Fallout4", ["Fallout4.esm", "DLCRobot.esm", "DLCworkshop01.esm", "DLCCoast.esm",
                                                  "DLCworkshop02.esm", "DLCworkshop03.esm", "DLCNukaWorld.esm",
                                                  "DLCUltraHighResolution.esm"])),
    "newvegas": dict(name="Fallout New Vegas", appid=22380, nexus="newvegas", proof="FalloutNV.exe", layout=bethesda(),
                     plugins=plugins("FalloutNV", ["FalloutNV.esm", "DeadMoney.esm", "HonestHearts.esm",
                                                   "OldWorldBlues.esm", "LonesomeRoad.esm", "GunRunnersArsenal.esm",
                                                   "ClassicPack.esm", "MercenaryPack.esm", "TribalPack.esm",
                                                   "CaravanPack.esm"], star=False)),
    "fallout3": dict(name="Fallout 3", appid=22370, nexus="fallout3", proof="Fallout3.exe", layout=bethesda(),
                     plugins=plugins("Fallout3", ["Fallout3.esm", "Anchorage.esm", "ThePitt.esm", "BrokenSteel.esm",
                                                  "PointLookout.esm", "Zeta.esm"], star=False)),
    "oblivion": dict(name="Oblivion", appid=22330, nexus="oblivion", proof="Oblivion.exe", layout=bethesda(),
                     plugins=plugins("Oblivion", ["Oblivion.esm"], star=False)),
    "starfield": dict(name="Starfield", appid=1716740, nexus="starfield", proof="Starfield.exe", layout=bethesda(),
                      plugins=plugins("Starfield", ["Starfield.esm", "Constellation.esm", "OldMars.esm",
                                                    "BlueprintShips-Starfield.esm", "SFBGS003.esm", "SFBGS004.esm",
                                                    "SFBGS006.esm", "SFBGS007.esm", "SFBGS008.esm"])),
    "cyberpunk2077": dict(name="Cyberpunk 2077", appid=1091500, nexus="cyberpunk2077", proof="REDprelauncher.exe",
                          layout={"root_markers": ["archive", "bin", "r6", "red4ext", "engine", "mods"],
                                  "ext_map": {".archive": "archive/pc/mod", ".xl": "archive/pc/mod"},
                                  "default": "archive/pc/mod"}),
    "stardewvalley": dict(name="Stardew Valley", appid=413150, nexus="stardewvalley", proof="Content",
                          layout={"folder_mod": {"marker": "manifest.json", "dir": "Mods"},
                                  "root_markers": ["smapi-internal", "stardewmodding*"], "default": "Mods/{name}"}),
    "witcher3": dict(name="The Witcher 3", appid=292030, nexus="witcher3", proof="bin",
                     layout={"root_markers": ["mods", "dlc", "bin"],
                             "folder_mod": {"marker": "content", "dir": "Mods", "prefix": "mod"},
                             "default": "Mods/mod{name}"}),
    # more games people mod a lot
    "baldursgate3": dict(name="Baldur's Gate 3", appid=1086940, nexus="baldursgate3", proof="bin",
                         layout={"root_markers": ["bin", "data"],
                                 "ext_map": {".pak": BG3_MODS, ".dll": "bin"},
                                 "default": BG3_MODS, "keep_out": ["info.json"]}, bg3=True),
    "rimworld": dict(name="RimWorld", appid=294100, nexus="rimworld", proof="Data",
                     layout={"folder_mod": {"marker": "about", "dir": "Mods"}, "root_markers": ["mods"],
                             "default": "Mods/{name}"}),
    "bannerlord": dict(name="Mount & Blade II: Bannerlord", appid=261550, nexus="mountandblade2bannerlord",
                       proof="Modules",
                       layout={"folder_mod": {"marker": "submodule.xml", "dir": "Modules"}, "root_markers": ["modules"],
                               "default": "Modules/{name}"}),
    "7daystodie": dict(name="7 Days to Die", appid=251570, nexus="7daystodie", proof="7DaysToDie_Data",
                       layout={"folder_mod": {"marker": "modinfo.xml", "dir": "Mods"}, "root_markers": ["mods"],
                               "default": "Mods/{name}"}),
    "projectzomboid": dict(name="Project Zomboid", appid=108600, nexus="projectzomboid", proof="media",
                           layout={"folder_mod": {"marker": "mod.info", "dir": "@home/Zomboid/mods"},
                                   "default": "@home/Zomboid/mods/{name}"}),
    "kcd2": dict(name="Kingdom Come: Deliverance II", appid=1771300, nexus="kingdomcomedeliverance2", proof="Data",
                 layout={"folder_mod": {"marker": "mod.manifest", "dir": "Mods"}, "root_markers": ["mods"],
                         "default": "Mods/{name}"}),
    "thesims4": dict(name="The Sims 4", appid=1222670, nexus="thesims4", proof="Game",
                     layout={"default": "@prefix/Documents/Electronic Arts/The Sims 4/Mods/{name}"}),
    "balatro": dict(name="Balatro", appid=2379780, nexus="balatro", thunderstore="balatro", proof="Balatro.exe",
                    layout={"root_markers": ["version.dll"], "dir_map": {"mods": "@prefix/AppData/Roaming/Balatro/Mods"},
                            "default": "@prefix/AppData/Roaming/Balatro/Mods/{name}", "ignore_top": THUNDERSTORE_TOP}),
    "marvelrivals": dict(name="Marvel Rivals", appid=2767030, nexus="marvelrivals", proof="MarvelGame",
                         layout={"root_markers": ["marvelgame"],
                                 "default": "MarvelGame/Marvel/Content/Paks/~mods"}),
    "eldenring": dict(name="Elden Ring", appid=1245620, nexus="eldenring", proof="Game",
                      layout={"root_markers": ["game", "modengine2", "mod", "config_eldenring.toml",
                                               "modengine2_launcher.exe", "launchmod_eldenring.bat", "dinput8.dll"],
                              "default": "Game"}),
    "oblivionremastered": dict(name="Oblivion Remastered", appid=2623190, nexus="oblivionremastered",
                               proof="OblivionRemastered",
                               layout={"root_markers": ["oblivionremastered", "engine"],
                                       "ext_map": {".pak": OBR_PAKS, ".utoc": OBR_PAKS, ".ucas": OBR_PAKS,
                                                   ".esp": OBR_DATA, ".esm": OBR_DATA, ".bsa": OBR_DATA},
                                       "default": OBR_DATA}),
    "hades2": dict(name="Hades II", appid=1145350, nexus="hades2", thunderstore="hades-ii", proof="Ship",
                   layout={"root_markers": ["ship"],
                           "dir_map": {"plugins": "Ship/ReturnOfModding/plugins/{name}",
                                       "plugins_data": "Ship/ReturnOfModding/plugins_data/{name}",
                                       "config": "Ship/ReturnOfModding/config", "returnofmodding": "Ship/ReturnOfModding"},
                           "ext_map": {".lua": "Ship/ReturnOfModding/plugins/{name}", ".dll": "Ship"},
                           "default": "Ship/ReturnOfModding/plugins/{name}", "ignore_top": THUNDERSTORE_TOP}),
    "hollowknight": dict(name="Hollow Knight", appid=367520, nexus="hollowknight", proof="hollow_knight_Data",
                         layout={"root_markers": ["hollow_knight_data"],
                                 "default": "hollow_knight_Data/Managed/Mods/{name}"}),
}

LAYOUT_PRESETS = {
    "bepinex": ("BepInEx (Unity games)", BEPINEX),
    "melonloader": ("MelonLoader (Unity games)", MELONLOADER),
    "root": ("Into the game folder as they are", ROOT),
    "bethesda": ("Bethesda (Data folder and plugins)", bethesda()),
}


# ---- Steam --------------------------------------------------------------------------------------

def steam_libraries():
    libs = []
    for root in STEAM_ROOTS:
        try:
            text = open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8").read()
        except OSError:
            continue
        for p in re.findall(r'"path"\s*"([^"]+)"', text):
            p = os.path.realpath(p.replace("\\\\", "\\"))
            if p not in libs:
                libs.append(p)
    return libs


def steam_install(appid):
    """(library, game folder) of a Steam game, or (None, None)"""
    for lib in steam_libraries():
        try:
            text = open(os.path.join(lib, "steamapps", f"appmanifest_{appid}.acf"), encoding="utf-8").read()
        except OSError:
            continue
        m = re.search(r'"installdir"\s*"([^"]+)"', text)
        if m:
            d = os.path.join(lib, "steamapps", "common", m.group(1))
            if os.path.isdir(d):
                return lib, d
    return None, None


def steam_root():
    for r in STEAM_ROOTS:
        if os.path.isdir(os.path.join(r, "steamapps")):
            return os.path.realpath(r)
    return None


def steam_image(appid, kind="capsule"):
    """a picture Steam already has of the game: capsule (portrait), hero (wide) or header"""
    root = steam_root()
    if not root or not appid:
        return None
    names = {"capsule": ["library_600x900.jpg", "library_600x900_2x.jpg", "library_capsule.jpg"],
             "hero": ["library_hero.jpg", "library_hero_2x.jpg"],
             "header": ["header.jpg", "library_header.jpg"],
             "logo": ["logo.png", "logo_2x.png"]}[kind]
    base = os.path.join(root, "appcache", "librarycache")
    for folder in (os.path.join(base, str(appid)), base):
        if not os.path.isdir(folder):
            continue
        for n in names:
            for cand in (os.path.join(folder, n), os.path.join(folder, f"{appid}_{n}")):
                if os.path.isfile(cand):
                    return cand
        if folder != base:
            # newer Steam keeps them under hashed subfolders
            for sub, _, files in os.walk(folder):
                for n in names:
                    if n in files:
                        return os.path.join(sub, n)
    return None


def steam_launch_options(appid):
    """the launch options set for a game in Steam (any user), or None if none are set"""
    root = steam_root()
    if not root:
        return None
    ud = os.path.join(root, "userdata")
    try:
        users = os.listdir(ud)
    except OSError:
        return None
    for u in users:
        try:
            text = open(os.path.join(ud, u, "config", "localconfig.vdf"), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        m = re.search(r'\n\s*"%d"\s*\{' % appid, text)
        if not m:
            continue
        # the app's block: up to its closing brace at the same depth
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        lo = re.search(r'"LaunchOptions"\s*"((?:[^"\\]|\\.)*)"', text[m.end():i])
        if lo:
            return lo.group(1).replace('\\"', '"')
    return None


# ---- the game list ------------------------------------------------------------------------------

class Game:
    def __init__(self, gid, spec, path=None, library=None):
        self.id = gid
        self.spec = spec
        self.name = spec["name"]
        self.appid = spec.get("appid") or 0
        self.nexus = spec.get("nexus", "")
        self.thunderstore = spec.get("thunderstore", "")
        self.layout = spec.get("layout", ROOT)
        self.plugins = spec.get("plugins")
        self.adopt = spec.get("adopt")
        self.custom = spec.get("custom", False)
        self.launch = spec.get("launch", "")
        self.path = path
        self.library = library

    @property
    def found(self):
        return bool(self.path and os.path.isdir(self.path))

    @property
    def prefix(self):
        """the Proton prefix's drive_c, or None (native games, or never run)"""
        if self.spec.get("prefix"):
            return self.spec["prefix"]
        if not self.appid:
            return None
        libs = ([self.library] if self.library else []) + steam_libraries()
        for lib in libs:
            d = os.path.join(lib, "steamapps", "compatdata", str(self.appid), "pfx", "drive_c")
            if os.path.isdir(d):
                return d
        return None

    @property
    def prefix_user(self):
        d = self.prefix
        return os.path.join(d, "users", "steamuser") if d else None

    @property
    def windows_build(self):
        if not self.found:
            return True
        try:
            return any(n.lower().endswith(".exe") for n in os.listdir(self.path))
        except OSError:
            return True

    def root_for(self, rel):
        """(base folder, path under it) for a staged path: the game folder, the Proton prefix's user
        folder (@prefix/) or your home folder (@home/); base is None when it doesn't exist"""
        if rel.startswith("@prefix/"):
            return self.prefix_user, rel[len("@prefix/"):]
        if rel.startswith("@home/"):
            return HOME, rel[len("@home/"):]
        if rel.startswith("@keep/"):
            # kept with the mod, never put in the game (BG3's info.json)
            return None, rel
        return self.path, rel

    def resolve(self, rel):
        """a staged path (game-relative, @prefix/... or @home/...) to where it goes on disk, or None"""
        base, sub = self.root_for(rel)
        return os.path.join(base, sub) if base else None


def proof_ok(path, spec):
    proof = spec.get("proof")
    return bool(path) and os.path.isdir(path) and (not proof or os.path.exists(os.path.join(path, proof)))


def custom_games():
    return get("custom_games", {}) or {}


def all_specs():
    specs = dict(GAMES)
    for gid, spec in custom_games().items():
        specs[gid] = dict(spec, custom=True)
    return specs


def make_game(gid, spec=None):
    spec = spec or all_specs()[gid]
    override = (get("game_dirs", {}) or {}).get(gid)
    if override and os.path.isdir(override):
        lib = None
        m = re.match(r"(.*)/steamapps/common/[^/]+/?$", override)
        if m:
            lib = m.group(1)
        return Game(gid, spec, override, lib)
    if spec.get("path"):
        return Game(gid, spec, spec["path"])
    if spec.get("appid"):
        lib, d = steam_install(spec["appid"])
        if d and proof_ok(d, spec):
            return Game(gid, spec, d, lib)
    return Game(gid, spec)


def detect():
    """every supported game that is installed, plus the ones you added: [Game]"""
    added = set(get("games_added", []) or [])
    removed = set(get("games_removed", []) or [])
    out = []
    for gid, spec in all_specs().items():
        g = make_game(gid, spec)
        if gid in removed and gid not in added:
            continue
        if g.found or gid in added or spec.get("custom"):
            out.append(g)
    out.sort(key=lambda g: g.name.lower())
    return out


def set_game_dir(gid, path):
    dirs = dict(get("game_dirs", {}) or {})
    if path:
        dirs[gid] = path
    else:
        dirs.pop(gid, None)
    save_conf(game_dirs=dirs)


def add_game(gid):
    added = [g for g in get("games_added", []) or [] if g != gid] + [gid]
    removed = [g for g in get("games_removed", []) or [] if g != gid]
    save_conf(games_added=added, games_removed=removed)


def remove_game(gid):
    added = [g for g in get("games_added", []) or [] if g != gid]
    removed = [g for g in get("games_removed", []) or [] if g != gid] + [gid]
    customs = dict(custom_games())
    customs.pop(gid, None)
    save_conf(games_added=added, games_removed=removed, custom_games=customs)


def save_custom_game(gid, spec):
    customs = dict(custom_games())
    customs[gid] = spec
    save_conf(custom_games=customs)
    add_game(gid)
