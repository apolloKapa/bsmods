#!/usr/bin/env python3
"""BS Mods: a small mod manager for Blade & Sorcery on Linux (Steam + Proton).

Blade & Sorcery mods are folders with a manifest.json that the game loads from
BladeAndSorcery_Data/StreamingAssets/Mods. This finds the game in your Steam libraries,
installs mods from downloaded archives (.zip/.7z/.rar, by button or drag and drop), turns them
off and on (kept in ~/.local/share/bsmods/disabled while off) and removes them.

Mods are kept on three pages, one per game version (1.0, U12, U11), sorted by the GameVersion in
their manifest. Only the page in use is in the game's Mods folder; the others wait in
~/.local/share/bsmods/pages/<page>/{on,off} until you switch to them (after rolling the game back
in Steam, for example).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser

from PyQt6.QtCore import QPropertyAnimation, QRectF, Qt, QTimer, QUrl, pyqtProperty
from PyQt6.QtGui import (QColor, QDesktopServices, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter,
                         QPainterPath, QPalette, QPen, QPixmap)
from PyQt6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QFileDialog, QFrame,
                             QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
                             QMessageBox, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget)

APP_ID = 629730
HOME = os.path.expanduser("~")
DATA = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.join(HOME, ".local/share")), "bsmods")
CONF = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "bsmods", "config.json")
DISABLED = os.path.join(DATA, "disabled")
PAGES_DIR = os.path.join(DATA, "pages")
PAGES = ("1.0", "U12", "U11")
NEXUS = "https://www.nexusmods.com/bladeandsorcery/mods/"
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bsmods.svg")
ARCHIVES = ("*.zip", "*.7z", "*.rar", "*.tar", "*.tar.gz", "*.tgz", "*.tar.xz")
STEAM_ROOTS = [os.path.join(HOME, ".local/share/Steam"), os.path.join(HOME, ".steam/steam"),
               os.path.join(HOME, ".var/app/com.valvesoftware.Steam/.local/share/Steam")]


# ---- finding the game -------------------------------------------------------------------------

def steam_libraries():
    libs = []
    for root in STEAM_ROOTS:
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            text = open(vdf, encoding="utf-8").read()
        except OSError:
            continue
        for p in re.findall(r'"path"\s*"([^"]+)"', text):
            p = p.replace("\\\\", "\\")
            if p not in libs:
                libs.append(p)
    return libs


def load_conf():
    try:
        c = json.load(open(CONF, encoding="utf-8"))
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def save_conf(**changes):
    c = load_conf()
    c.update(changes)
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2)


def find_game():
    """the game folder (the one with BladeAndSorcery_Data), or None"""
    override = load_conf().get("game_dir", "")
    if override and os.path.isdir(os.path.join(override, "BladeAndSorcery_Data")):
        return override
    for lib in steam_libraries():
        manifest = os.path.join(lib, "steamapps", f"appmanifest_{APP_ID}.acf")
        try:
            m = re.search(r'"installdir"\s*"([^"]+)"', open(manifest, encoding="utf-8").read())
        except OSError:
            continue
        if m:
            game = os.path.join(lib, "steamapps", "common", m.group(1))
            if os.path.isdir(os.path.join(game, "BladeAndSorcery_Data")):
                return game
    return None


def save_game_dir(path):
    save_conf(game_dir=path)


def mods_dir(game):
    d = os.path.join(game, "BladeAndSorcery_Data", "StreamingAssets", "Mods")
    os.makedirs(d, exist_ok=True)
    return d


# ---- pages (one mod set per game version) ------------------------------------------------------

def page_for(game_version):
    """the page a mod belongs on, from its manifest's GameVersion (no version: the current game)"""
    v = game_version.strip().lstrip("vV")
    if v.startswith("0.12"):
        return "U12"
    if v.startswith("0."):
        return "U11"
    return "1.0"


def active_page():
    p = load_conf().get("active_page")
    return p if p in PAGES else "1.0"


def page_dirs(game, page):
    """(on, off) folders of a page: the game's own for the page in use, stored ones for the rest"""
    if page == active_page():
        return mods_dir(game), DISABLED
    return os.path.join(PAGES_DIR, page, "on"), os.path.join(PAGES_DIR, page, "off")


def move_all(src, dst):
    """move every mod folder from src into dst: the names that were already in dst (left alone)"""
    clashes = []
    if not os.path.isdir(src):
        return clashes
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        path = os.path.join(src, name)
        if not os.path.isdir(path):
            continue
        if os.path.exists(os.path.join(dst, name)):
            clashes.append(name)
            continue
        shutil.move(path, os.path.join(dst, name))
    return clashes


def use_page(game, page):
    """put a page's mods in the game (and the current page's in storage): names that couldn't move"""
    old = active_page()
    if page == old:
        return []
    old_on, old_off = page_dirs(game, old)
    new_on, new_off = page_dirs(game, page)
    store_on, store_off = os.path.join(PAGES_DIR, old, "on"), os.path.join(PAGES_DIR, old, "off")
    clashes = move_all(old_on, store_on) + move_all(old_off, store_off)
    clashes += move_all(new_on, old_on) + move_all(new_off, old_off)
    save_conf(active_page=page)
    return clashes


def sort_into_pages(game):
    """once: mods for another game version, from before there were pages, go to their own page"""
    if load_conf().get("pages_sorted"):
        return
    here = active_page()
    for m in list_mods(game, here):
        if m["page"] != here:
            move_mod(game, m, m["page"])
    save_conf(pages_sorted=True)


# ---- mods ---------------------------------------------------------------------------------------

def read_manifest(folder):
    try:
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def folder_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def list_mods(game, page):
    """the mods on a page; each one's "page" is where its game version says it belongs"""
    out = []
    on_dir, off_dir = page_dirs(game, page)
    for base, enabled in ((on_dir, True), (off_dir, False)):
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base), key=str.lower):
            path = os.path.join(base, name)
            if not os.path.isdir(path):
                continue
            m = read_manifest(path)
            if not isinstance(m, dict):
                m = {}
            # manifests are hand-written: a version can be a number (2.4) instead of text
            field = lambda k: "" if m.get(k) is None else str(m.get(k))
            out.append({"folder": name, "path": path, "enabled": enabled, "name": field("Name") or name,
                        "version": field("ModVersion"), "author": field("Author"),
                        "game": field("GameVersion"), "desc": field("Description"),
                        "thumb": field("Thumbnail"), "size": folder_size(path),
                        "on_page": page, "page": page_for(field("GameVersion"))})
    out.sort(key=lambda m: m["name"].lower())
    return out


def install(game, src):
    """install every mod (folder with a manifest.json) in an archive or folder, each on the page for
    its game version: [(name, page)]"""
    installed = []
    with tempfile.TemporaryDirectory(prefix="bsmods-") as tmp:
        if os.path.isdir(src):
            root = src
        else:
            r = subprocess.run(["bsdtar", "-xf", src, "-C", tmp], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"couldn't unpack {os.path.basename(src)}: {r.stderr.strip()}")
            root = tmp
        dirs = []
        for d, _, files in os.walk(root):
            if any(f.lower() == "manifest.json" for f in files):
                # a mod's own subfolders aren't separate mods
                if not any(d.startswith(p + os.sep) for p in dirs):
                    dirs.append(d)
        if not dirs:
            raise RuntimeError(f"{os.path.basename(src)} has no Blade & Sorcery mod in it (no manifest.json)")
        for d in dirs:
            name = os.path.basename(d) if d != root else re.sub(r"(\.tar)?\.[^.]+$", "", os.path.basename(src))
            m = read_manifest(d)
            page = page_for(str(m.get("GameVersion", "")) if isinstance(m, dict) else "")
            target, off = page_dirs(game, page)
            for base in (target, off):
                old = os.path.join(base, name)
                if os.path.isdir(old):
                    shutil.rmtree(old)
            os.makedirs(target, exist_ok=True)
            shutil.copytree(d, os.path.join(target, name))
            installed.append((name, page))
    return installed


def set_enabled(game, mod, on):
    on_dir, off_dir = page_dirs(game, mod["on_page"])
    os.makedirs(on_dir if on else off_dir, exist_ok=True)
    dest = os.path.join(on_dir if on else off_dir, mod["folder"])
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.move(mod["path"], dest)


def move_mod(game, mod, page):
    """move a mod to another page, keeping it on or off"""
    on_dir, off_dir = page_dirs(game, page)
    base = on_dir if mod["enabled"] else off_dir
    os.makedirs(base, exist_ok=True)
    dest = os.path.join(base, mod["folder"])
    if os.path.exists(dest):
        raise OSError(f"{page} already has a mod in a folder called {mod['folder']}")
    shutil.move(mod["path"], dest)


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


# ---- window -------------------------------------------------------------------------------------

ACCENT = "#c9a96e"
STYLE = f"""
QMainWindow, #root {{ background: #121216; }}
QLabel {{ color: #e8e8ef; }}
QLabel#muted {{ color: #8a8a99; }}
QLabel#title {{ font-size: 22px; font-weight: 700; }}
QLabel#chipOk {{ background: rgba(120,200,140,0.14); color: #8fd6a2; border-radius: 9px; padding: 3px 10px; font-size: 11px; }}
QLabel#chipBad {{ background: rgba(224,108,117,0.16); color: #e88b93; border-radius: 9px; padding: 3px 10px; font-size: 11px; }}
QLabel#badge {{ background: #2a2a33; color: #c8c8d4; border-radius: 7px; padding: 2px 8px; font-size: 11px; }}
QLabel#badgeOld {{ background: rgba(224,108,117,0.18); color: #e88b93; border-radius: 7px; padding: 2px 8px; font-size: 11px; }}
QLabel#badgeOk {{ background: rgba(120,200,140,0.14); color: #8fd6a2; border-radius: 7px; padding: 2px 8px; font-size: 11px; }}
QPushButton {{ background: #24242c; color: #e8e8ef; border: 1px solid #30303a; border-radius: 9px; padding: 8px 14px; }}
QPushButton:hover {{ background: #2c2c36; }}
QPushButton#primary {{ background: {ACCENT}; color: #17171c; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: #d6b77d; }}
QPushButton#seg {{ border-radius: 8px; padding: 6px 14px; background: transparent; border: 1px solid transparent; color: #a0a0ad; }}
QPushButton#seg:checked {{ background: #2a2a33; color: #e8e8ef; border: 1px solid #36363f; }}
QToolButton {{ background: transparent; color: #a0a0ad; border: none; border-radius: 8px; padding: 4px 8px; font-size: 16px; }}
QToolButton:hover {{ background: #2a2a33; color: #e8e8ef; }}
QToolButton::menu-indicator {{ image: none; }}
QLineEdit {{ background: #1c1c22; color: #e8e8ef; border: 1px solid #2a2a33; border-radius: 10px; padding: 8px 12px; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QFrame#card {{ background: #1b1b21; border: 1px solid #26262e; border-radius: 14px; }}
QFrame#card:hover {{ background: #202027; border: 1px solid #30303a; }}
QFrame#segbox {{ background: #1c1c22; border: 1px solid #2a2a33; border-radius: 10px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2e2e38; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QMenu {{ background: #1f1f26; color: #e8e8ef; border: 1px solid #30303a; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: #2c2c36; }}
"""


class Switch(QAbstractButton):
    """an on/off switch"""
    def __init__(self, on=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(on)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._pos = 1.0 if on else 0.0
        self.anim = QPropertyAnimation(self, b"pos", self)
        self.anim.setDuration(140)
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self.anim.stop()
        self.anim.setEndValue(1.0 if on else 0.0)
        self.anim.start()

    def getPos(self):
        return self._pos

    def setPos(self, v):
        self._pos = v
        self.update()

    pos = pyqtProperty(float, getPos, setPos)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        off, on = QColor("#3a3a45"), QColor(ACCENT)
        track = QColor(int(off.red() + (on.red() - off.red()) * self._pos),
                       int(off.green() + (on.green() - off.green()) * self._pos),
                       int(off.blue() + (on.blue() - off.blue()) * self._pos))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 13, 13)
        p.setBrush(QColor("#ffffff") if self._pos > 0.5 else QColor("#c8c8d4"))
        x = 3 + (self.width() - 26) * self._pos
        p.drawEllipse(QRectF(x, 3, 20, 20))


def rounded(pix, w, h, r=10):
    """pix cropped to w x h with rounded corners"""
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), r, r)
    p.setClipPath(path)
    scaled = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    p.drawPixmap((w - scaled.width()) // 2, (h - scaled.height()) // 2, scaled)
    p.end()
    return out


def placeholder(name, w, h):
    """a tile with the mod's initials, for mods without a thumbnail"""
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    hue = sum(map(ord, name)) % 360
    grad = QLinearGradient(0, 0, w, h)
    grad.setColorAt(0, QColor.fromHsl(hue, 70, 70))
    grad.setColorAt(1, QColor.fromHsl((hue + 40) % 360, 80, 40))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
    p.fillPath(path, grad)
    initials = "".join(w_[0] for w_ in re.findall(r"[A-Za-z0-9]+", name)[:2]).upper() or "?"
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(h * 0.38))
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 220))
    p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, initials)
    p.end()
    return out


def label(text, name=None, wrap=False):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


class ModCard(QFrame):
    def __init__(self, win, mod):
        super().__init__()
        self.setObjectName("card")
        self.win, self.mod = win, mod
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 12, 14, 12)
        lay.setSpacing(14)

        tw, th = 128, 72
        thumb = QLabel()
        thumb.setFixedSize(tw, th)
        pix = QPixmap(os.path.join(mod["path"], mod["thumb"])) if mod["thumb"] else QPixmap()
        thumb.setPixmap(rounded(pix, tw, th) if not pix.isNull() else placeholder(mod["name"], tw, th))
        if not mod["enabled"]:
            eff = QGraphicsOpacityEffect(thumb)
            eff.setOpacity(0.4)
            thumb.setGraphicsEffect(eff)
        lay.addWidget(thumb)

        text = QVBoxLayout()
        text.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        name = label(mod["name"])
        name.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {'#e8e8ef' if mod['enabled'] else '#7a7a88'};")
        top.addWidget(name)
        if mod["version"]:
            top.addWidget(label("v" + mod["version"].lstrip("vV"), "badge"))
        top.addStretch(1)
        text.addLayout(top)

        if mod["desc"]:
            d = label(mod["desc"].replace("\n", " "), "muted")
            d.setMaximumWidth(10000)
            fm = QFontMetrics(d.font())
            d.setText(fm.elidedText(d.text(), Qt.TextElideMode.ElideRight, 520))
            d.setToolTip(mod["desc"])
            text.addWidget(d)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        if mod["author"]:
            chips.addWidget(label("by " + mod["author"], "muted"))
        if mod["game"]:
            wrong = mod["page"] != mod["on_page"]
            c = label(("Made for " if wrong else "Game ") + mod["game"], "badgeOld" if wrong else "badgeOk")
            if wrong:
                c.setToolTip(f"Made for a different game version than {mod['on_page']}: it may not load. "
                             f"⋯ → Move to {mod['page']} puts it on its own page")
            chips.addWidget(c)
        chips.addWidget(label(human(mod["size"]), "badge"))
        if not mod["enabled"]:
            chips.addWidget(label("Off", "badge"))
        chips.addStretch(1)
        text.addLayout(chips)
        lay.addLayout(text, 1)

        sw = Switch(mod["enabled"])
        sw.setToolTip("On: the game loads it. Off: kept, but the game doesn't see it")
        sw.toggled.connect(lambda on: win.toggle(mod, on))
        lay.addWidget(sw, 0, Qt.AlignmentFlag.AlignVCenter)

        more = QToolButton()
        more.setText("⋯")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.addAction("Open its folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(mod["path"])))
        menu.addSeparator()
        for page in PAGES:
            if page != mod["on_page"]:
                menu.addAction(f"Move to {page} page", lambda p=page: win.move(mod, p))
        menu.addSeparator()
        menu.addAction("Remove...", lambda: win.remove(mod))
        more.setMenu(menu)
        lay.addWidget(more, 0, Qt.AlignmentFlag.AlignVCenter)


class DropOverlay(QWidget):
    """shown over the window while files are dragged onto it"""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(18, 18, 22, 210))
        r = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        pen = QPen(QColor(ACCENT), 2, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(201, 169, 110, 26))
        p.drawRoundedRect(r, 18, 18)
        f = QFont()
        f.setPixelSize(22)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#e8e8ef"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Drop to install\n")
        f.setPixelSize(13)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor("#a0a0ad"))
        p.drawText(r.adjusted(0, 40, 0, 0), Qt.AlignmentFlag.AlignCenter, ".zip, .7z or .rar from Nexus Mods")


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BS Mods")
        self.resize(900, 640)
        self.setMinimumSize(640, 420)
        self.setAcceptDrops(True)
        self.game = find_game()
        self.show_mode = "all"
        if self.game:
            try:
                sort_into_pages(self.game)
            except OSError as e:
                print(f"bsmods: couldn't sort mods into pages: {e}", file=sys.stderr)
        self.page = active_page()

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(22, 20, 22, 14)
        v.setSpacing(14)

        # header
        head = QHBoxLayout()
        head.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(QIcon(ICON).pixmap(44, 44) if os.path.exists(ICON) else QPixmap())
        head.addWidget(icon)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("BS Mods", "title"))
        self.subtitle = label("", "muted")
        titles.addWidget(self.subtitle)
        head.addLayout(titles)
        self.chip = label("")
        head.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        get = QPushButton("Get mods")
        get.setCursor(Qt.CursorShape.PointingHandCursor)
        get.clicked.connect(lambda: webbrowser.open(NEXUS))
        head.addWidget(get)
        add = QPushButton("+  Install mods")
        add.setObjectName("primary")
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(self.pick)
        head.addWidget(add)
        more = QToolButton()
        more.setText("⋯")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.addAction("Open the Mods folder", self.open_folder)
        menu.addAction("Refresh", self.refresh)
        menu.addSeparator()
        menu.addAction("Turn all on", lambda: self.set_all(True))
        menu.addAction("Turn all off", lambda: self.set_all(False))
        menu.addSeparator()
        menu.addAction("Change game folder...", self.change_game)
        more.setMenu(menu)
        head.addWidget(more)
        v.addLayout(head)

        # pages: one mod set per game version
        pages = QHBoxLayout()
        pages.setSpacing(10)
        pbox = QFrame()
        pbox.setObjectName("segbox")
        pl = QHBoxLayout(pbox)
        pl.setContentsMargins(3, 3, 3, 3)
        pl.setSpacing(2)
        self.page_buttons = {}
        pgroup = QButtonGroup(self)
        for page in PAGES:
            b = QPushButton(page)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, p=page: self.set_page(p))
            pgroup.addButton(b)
            pl.addWidget(b)
            self.page_buttons[page] = b
        self.page_buttons[self.page].setChecked(True)
        pages.addWidget(pbox)
        self.page_note = label("", "muted", wrap=True)
        pages.addWidget(self.page_note, 1)
        self.use_btn = QPushButton("Use this page")
        self.use_btn.setObjectName("primary")
        self.use_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.use_btn.clicked.connect(self.use_current_page)
        pages.addWidget(self.use_btn)
        v.addLayout(pages)

        # search + filter
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Search by name or author")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self.refresh)
        bar.addWidget(self.filter, 1)
        seg = QFrame()
        seg.setObjectName("segbox")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        self.segs = {}
        group = QButtonGroup(self)
        for key, text in (("all", "All"), ("on", "On"), ("off", "Off")):
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.set_mode(k))
            group.addButton(b)
            sl.addWidget(b)
            self.segs[key] = b
        self.segs["all"].setChecked(True)
        bar.addWidget(seg)
        v.addLayout(bar)

        # the mods
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.holder = QWidget()
        # only the holder itself: a rule without a selector would reach every card and button in it
        self.holder.setObjectName("holder")
        self.holder.setStyleSheet("#holder { background: transparent; }")
        self.scroll.viewport().setObjectName("viewport")
        self.scroll.viewport().setStyleSheet("#viewport { background: transparent; }")
        self.cards = QVBoxLayout(self.holder)
        self.cards.setContentsMargins(0, 0, 4, 0)
        self.cards.setSpacing(8)
        self.scroll.setWidget(self.holder)
        v.addWidget(self.scroll, 1)

        self.status = label("Tip: drop mod files anywhere on this window to install them", "muted")
        v.addWidget(self.status)
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(
            lambda: self.status.setText("Tip: drop mod files anywhere on this window to install them"))

        self.overlay = DropOverlay(root)
        self.refresh()

    def say(self, text):
        self.status.setText(text)
        self.status_timer.start(6000)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.overlay.setGeometry(self.centralWidget().rect())

    # -- game folder --
    def change_game(self):
        d = QFileDialog.getExistingDirectory(self, "Blade & Sorcery folder (the one with BladeAndSorcery_Data)",
                                             self.game or HOME)
        if not d:
            return False
        if not os.path.isdir(os.path.join(d, "BladeAndSorcery_Data")):
            QMessageBox.warning(self, "Not the game folder", "That folder has no BladeAndSorcery_Data in it.")
            return False
        save_game_dir(d)
        self.game = d
        self.refresh()
        return True

    def ensure_game(self):
        if self.game:
            return True
        QMessageBox.information(self, "Game not found", "Blade & Sorcery wasn't found in your Steam libraries. "
                                "Pick the game folder (the one with BladeAndSorcery_Data in it).")
        return self.change_game()

    # -- pages --
    def set_page(self, page):
        self.page = page
        self.page_buttons[page].setChecked(True)
        self.refresh()

    def use_current_page(self):
        if not self.ensure_game():
            return
        old = active_page()
        try:
            clashes = use_page(self.game, self.page)
        except OSError as e:
            QMessageBox.warning(self, "Couldn't switch pages", str(e))
            clashes = []
        self.refresh()
        self.say(f"The game now loads the {self.page} mods ({old} mods are stored)")
        if clashes:
            QMessageBox.warning(self, "Some mods stayed where they were",
                                "These were in both places, so they weren't moved:\n\n" + "\n".join(clashes))

    def move(self, mod, page):
        try:
            move_mod(self.game, mod, page)
            self.say(f"Moved {mod['name']} to the {page} page")
        except OSError as e:
            QMessageBox.warning(self, "Couldn't move it", str(e))
        self.refresh()

    # -- list --
    def set_mode(self, mode):
        self.show_mode = mode
        self.refresh()

    def clear_cards(self):
        while self.cards.count():
            w = self.cards.takeAt(0).widget()
            if w:
                # gone at once: deleteLater alone left it drawn until the next event loop pass
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def empty_state(self, title, text, buttons=True):
        box = QWidget()
        l = QVBoxLayout(box)
        l.setContentsMargins(0, 60, 0, 0)
        l.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(QIcon(ICON).pixmap(72, 72) if os.path.exists(ICON) else QPixmap())
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(icon)
        t = label(title)
        t.setStyleSheet("font-size: 17px; font-weight: 700;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(t)
        s = label(text, "muted", wrap=True)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(s)
        if buttons:
            row = QHBoxLayout()
            row.addStretch(1)
            g = QPushButton("Get mods on Nexus")
            g.clicked.connect(lambda: webbrowser.open(NEXUS))
            row.addWidget(g)
            a = QPushButton("+  Install mods")
            a.setObjectName("primary")
            a.clicked.connect(self.pick)
            row.addWidget(a)
            row.addStretch(1)
            l.addLayout(row)
        self.cards.addWidget(box)

    def refresh(self):
        self.clear_cards()
        if not self.game:
            self.subtitle.setText("Blade & Sorcery")
            self.chip.setObjectName("chipBad")
            self.chip.setText("Game not found")
            self.chip.setStyle(self.chip.style())
            self.empty_state("Blade & Sorcery wasn't found",
                             "Install it in Steam, or pick its folder with ⋯ → Change game folder.", buttons=False)
            self.cards.addStretch(1)
            return
        mods = list_mods(self.game, self.page)
        active = active_page()
        for page, b in self.page_buttons.items():
            n = len(list_mods(self.game, page)) if page != self.page else len(mods)
            b.setText(f"{'●  ' if page == active else ''}{page}  ({n})")
            b.setToolTip("In the game now" if page == active else "Stored: the game doesn't see these")
        if self.page == active:
            self.page_note.setText(f"In the game now. Your game should be on {self.page}.")
            self.use_btn.hide()
        else:
            self.page_note.setText(f"Stored, the game doesn't see these. Set the game to {self.page} in Steam "
                                   "(Properties → Betas), then use this page.")
            self.use_btn.show()
        on = sum(1 for m in mods if m["enabled"])
        self.subtitle.setText(f"Blade & Sorcery {self.page}  ·  {len(mods)} mod{'s' if len(mods) != 1 else ''}, "
                              f"{on} on")
        self.chip.setObjectName("chipOk")
        self.chip.setText("Game found")
        self.chip.setToolTip(mods_dir(self.game))
        self.chip.setStyle(self.chip.style())
        q = self.filter.text().strip().lower()
        shown = [m for m in mods
                 if (self.show_mode == "all" or m["enabled"] == (self.show_mode == "on"))
                 and (not q or q in m["name"].lower() or q in m["author"].lower())]
        if not mods:
            self.empty_state(f"No {self.page} mods yet", "Download mods from Nexus Mods (use Manual download), "
                             "then drop the files on this window or press Install mods. Each one goes on the "
                             "page for the game version it was made for.")
        elif not shown:
            self.empty_state("Nothing matches", "Try another search, or show All.", buttons=False)
        for m in shown:
            self.cards.addWidget(ModCard(self, m))
        self.cards.addStretch(1)

    # -- actions --
    def install_paths(self, paths):
        if not paths or not self.ensure_game():
            return
        done, errors = [], []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for p in paths:
                self.say(f"Installing {os.path.basename(p)}...")
                QApplication.processEvents()
                try:
                    done += install(self.game, p)
                except (RuntimeError, OSError) as e:
                    errors.append(str(e))
        finally:
            QApplication.restoreOverrideCursor()
        # show the page the mods went to
        pages = {p for _, p in done}
        if len(pages) == 1 and self.page not in pages:
            self.set_page(pages.pop())
        self.refresh()
        if done:
            self.say("Installed " + ", ".join(f"{n} ({p})" for n, p in done))
        if errors:
            QMessageBox.warning(self, "Some mods weren't installed", "\n\n".join(errors))

    def pick(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Mod files", os.path.join(HOME, "Downloads"),
                                                "Mod archives (" + " ".join(ARCHIVES) + ");;All files (*)")
        self.install_paths(paths)

    def toggle(self, mod, on):
        try:
            set_enabled(self.game, mod, on)
            self.say(f"{mod['name']} is {'on' if on else 'off'}")
        except OSError as e:
            QMessageBox.warning(self, "Couldn't change it", str(e))
        QTimer.singleShot(160, self.refresh)    # let the switch finish moving

    def set_all(self, on):
        if not self.ensure_game():
            return
        n = 0
        for m in list_mods(self.game, self.page):
            if m["enabled"] != on:
                set_enabled(self.game, m, on)
                n += 1
        self.refresh()
        self.say(f"Turned {n} mod{'s' if n != 1 else ''} {'on' if on else 'off'}")

    def remove(self, mod):
        if QMessageBox.question(self, "Remove mod", f"Remove {mod['name']}? Its files are deleted.") \
                != QMessageBox.StandardButton.Yes:
            return
        shutil.rmtree(mod["path"], ignore_errors=True)
        self.say(f"Removed {mod['name']}")
        self.refresh()

    def open_folder(self):
        if self.ensure_game():
            QDesktopServices.openUrl(QUrl.fromLocalFile(mods_dir(self.game)))

    # -- drag and drop --
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.overlay.setGeometry(self.centralWidget().rect())
            self.overlay.raise_()
            self.overlay.show()

    def dragLeaveEvent(self, _e):
        self.overlay.hide()

    def dropEvent(self, e):
        self.overlay.hide()
        self.install_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])


def dark(app):
    app.setStyle("Fusion")
    p = QPalette()
    for role, c in ((QPalette.ColorRole.Window, "#121216"), (QPalette.ColorRole.WindowText, "#e8e8ef"),
                    (QPalette.ColorRole.Base, "#1c1c22"), (QPalette.ColorRole.AlternateBase, "#24242c"),
                    (QPalette.ColorRole.Text, "#e8e8ef"), (QPalette.ColorRole.Button, "#24242c"),
                    (QPalette.ColorRole.ButtonText, "#e8e8ef"), (QPalette.ColorRole.Highlight, ACCENT),
                    (QPalette.ColorRole.HighlightedText, "#17171c"), (QPalette.ColorRole.ToolTipBase, "#24242c"),
                    (QPalette.ColorRole.ToolTipText, "#e8e8ef"), (QPalette.ColorRole.PlaceholderText, "#6f6f7c")):
        p.setColor(role, QColor(c))
    app.setPalette(p)
    app.setStyleSheet(STYLE)


def main():
    if shutil.which("bsdtar") is None:
        print("bsmods needs bsdtar (libarchive) to unpack mods", file=sys.stderr)
    app = QApplication(sys.argv)
    app.setApplicationName("bsmods")
    app.setDesktopFileName("bsmods")
    if os.path.exists(ICON):
        app.setWindowIcon(QIcon(ICON))
    dark(app)
    w = Window()
    w.show()
    # files given on the command line (or from "Open with") are installed straight away
    if len(sys.argv) > 1:
        w.install_paths([a for a in sys.argv[1:] if os.path.exists(a)])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
