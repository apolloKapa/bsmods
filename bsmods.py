#!/usr/bin/env python3
"""BS Mods: a small mod manager for Blade & Sorcery on Linux (Steam + Proton).

Blade & Sorcery mods are folders with a manifest.json that the game loads from
BladeAndSorcery_Data/StreamingAssets/Mods. This finds the game in your Steam libraries,
installs mods from downloaded archives (.zip/.7z/.rar, by button or drag and drop), turns them
off and on (kept in ~/.local/share/bsmods/disabled while off) and removes them.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser

from PyQt6.QtCore import Qt, QSize, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPalette, QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
                             QVBoxLayout, QWidget)

APP_ID = 629730
HOME = os.path.expanduser("~")
DATA = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.join(HOME, ".local/share")), "bsmods")
CONF = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "bsmods", "config.json")
DISABLED = os.path.join(DATA, "disabled")
NEXUS = "https://www.nexusmods.com/bladeandsorcery/mods/"
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


def find_game():
    """the game folder (the one with BladeAndSorcery_Data), or None"""
    try:
        override = json.load(open(CONF, encoding="utf-8")).get("game_dir", "")
        if override and os.path.isdir(os.path.join(override, "BladeAndSorcery_Data")):
            return override
    except (OSError, ValueError):
        pass
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
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, "w", encoding="utf-8") as f:
        json.dump({"game_dir": path}, f, indent=2)


def mods_dir(game):
    d = os.path.join(game, "BladeAndSorcery_Data", "StreamingAssets", "Mods")
    os.makedirs(d, exist_ok=True)
    return d


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


def list_mods(game):
    out = []
    for base, enabled in ((mods_dir(game), True), (DISABLED, False)):
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base), key=str.lower):
            path = os.path.join(base, name)
            if not os.path.isdir(path):
                continue
            m = read_manifest(path)
            out.append({"folder": name, "path": path, "enabled": enabled, "name": m.get("Name") or name,
                        "version": m.get("ModVersion", ""), "author": m.get("Author", ""),
                        "game": str(m.get("GameVersion", "")), "desc": m.get("Description", ""),
                        "thumb": m.get("Thumbnail", ""), "size": folder_size(path)})
    out.sort(key=lambda m: m["name"].lower())
    return out


def install(game, src):
    """install every mod (folder with a manifest.json) in an archive or folder: their names"""
    target = mods_dir(game)
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
            for base in (target, DISABLED):
                old = os.path.join(base, name)
                if os.path.isdir(old):
                    shutil.rmtree(old)
            shutil.copytree(d, os.path.join(target, name))
            installed.append(name)
    return installed


def set_enabled(game, mod, on):
    os.makedirs(DISABLED, exist_ok=True)
    dest = os.path.join(mods_dir(game) if on else DISABLED, mod["folder"])
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.move(mod["path"], dest)


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


# ---- window -------------------------------------------------------------------------------------

class ModRow(QWidget):
    def __init__(self, win, mod):
        super().__init__()
        self.win, self.mod = win, mod
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(12)

        self.check = QCheckBox()
        self.check.setChecked(mod["enabled"])
        self.check.setToolTip("On: the game loads it. Off: kept, but not loaded")
        self.check.toggled.connect(self.toggled)
        lay.addWidget(self.check)

        thumb = QLabel()
        thumb.setFixedSize(64, 40)
        pix = QPixmap(os.path.join(mod["path"], mod["thumb"])) if mod["thumb"] else QPixmap()
        if not pix.isNull():
            thumb.setPixmap(pix.scaled(64, 40, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation))
        lay.addWidget(thumb)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(f"<b>{mod['name']}</b>" + (f"  <span style='color:#8a8a99'>{mod['version']}</span>" if mod["version"] else ""))
        text.addWidget(title)
        bits = []
        if mod["author"]:
            bits.append(f"by {mod['author']}")
        if mod["game"]:
            old = mod["game"].startswith("0.")
            bits.append(f"<span style='color:{'#e06c75' if old else '#8a8a99'}'>for game {mod['game']}"
                        + (" (older game version, may not load)" if old else "") + "</span>")
        bits.append(human(mod["size"]))
        sub = QLabel("  ·  ".join(bits))
        sub.setStyleSheet("color:#8a8a99")
        text.addWidget(sub)
        lay.addLayout(text, 1)

        rm = QPushButton("Remove")
        rm.clicked.connect(lambda: win.remove(mod))
        lay.addWidget(rm)
        if mod["desc"]:
            self.setToolTip(mod["desc"])

    def toggled(self, on):
        self.win.toggle(self.mod, on)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BS Mods")
        self.resize(820, 600)
        self.setAcceptDrops(True)
        self.game = find_game()

        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("<span style='font-size:20px'><b>Blade &amp; Sorcery mods</b></span>")
        head.addWidget(title, 1)
        for text, fn in (("Install mods...", self.pick), ("Get mods", lambda: webbrowser.open(NEXUS)),
                         ("Open folder", self.open_folder), ("Refresh", self.refresh)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            head.addWidget(b)
        v.addLayout(head)

        self.where = QLabel()
        self.where.setStyleSheet("color:#8a8a99")
        self.where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(self.where)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Search mods")
        self.filter.textChanged.connect(self.refresh)
        v.addWidget(self.filter)

        self.list = QListWidget()
        self.list.setSpacing(2)
        v.addWidget(self.list, 1)

        self.status = QLabel("Drop mod archives (.zip, .7z, .rar) anywhere on this window to install them")
        self.status.setStyleSheet("color:#8a8a99")
        v.addWidget(self.status)

        self.refresh()

    # -- game folder --
    def ensure_game(self):
        if self.game:
            return True
        QMessageBox.information(self, "Game not found",
                                "Blade & Sorcery wasn't found in your Steam libraries. Pick the game folder "
                                "(the one with BladeAndSorcery_Data in it).")
        d = QFileDialog.getExistingDirectory(self, "Blade & Sorcery folder", HOME)
        if d and os.path.isdir(os.path.join(d, "BladeAndSorcery_Data")):
            save_game_dir(d)
            self.game = d
            return True
        return False

    def refresh(self):
        self.list.clear()
        if not self.game:
            self.where.setText("Blade & Sorcery not found: use Install mods... to pick its folder")
            return
        mods = list_mods(self.game)
        on = sum(1 for m in mods if m["enabled"])
        self.where.setText(f"{len(mods)} mods, {on} on  ·  {mods_dir(self.game)}")
        q = self.filter.text().strip().lower()
        for m in mods:
            if q and q not in m["name"].lower() and q not in m["author"].lower():
                continue
            item = QListWidgetItem()
            row = ModRow(self, m)
            item.setSizeHint(QSize(0, row.sizeHint().height()))
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
        if not mods:
            item = QListWidgetItem("No mods yet. Download some from Nexus Mods (Get mods), then drop them here.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(item)

    # -- actions --
    def install_paths(self, paths):
        if not paths or not self.ensure_game():
            return
        done, errors = [], []
        for p in paths:
            try:
                done += install(self.game, p)
            except (RuntimeError, OSError) as e:
                errors.append(str(e))
        self.refresh()
        if done:
            self.status.setText("Installed: " + ", ".join(done))
        if errors:
            QMessageBox.warning(self, "Some mods weren't installed", "\n".join(errors))

    def pick(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Mod archives", os.path.join(HOME, "Downloads"),
                                                "Mod archives (" + " ".join(ARCHIVES) + ");;All files (*)")
        self.install_paths(paths)

    def toggle(self, mod, on):
        try:
            set_enabled(self.game, mod, on)
            self.status.setText(f"{mod['name']} is {'on' if on else 'off'}")
        except OSError as e:
            QMessageBox.warning(self, "Couldn't change it", str(e))
        self.refresh()

    def remove(self, mod):
        if QMessageBox.question(self, "Remove mod", f"Remove {mod['name']}? Its files are deleted.") \
                != QMessageBox.StandardButton.Yes:
            return
        shutil.rmtree(mod["path"], ignore_errors=True)
        self.status.setText(f"Removed {mod['name']}")
        self.refresh()

    def open_folder(self):
        if self.ensure_game():
            QDesktopServices.openUrl(QUrl.fromLocalFile(mods_dir(self.game)))

    # -- drag and drop --
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.install_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])


def dark(app):
    app.setStyle("Fusion")
    p = QPalette()
    for role, c in ((QPalette.ColorRole.Window, "#17171c"), (QPalette.ColorRole.WindowText, "#e8e8ef"),
                    (QPalette.ColorRole.Base, "#1f1f26"), (QPalette.ColorRole.AlternateBase, "#24242c"),
                    (QPalette.ColorRole.Text, "#e8e8ef"), (QPalette.ColorRole.Button, "#2a2a33"),
                    (QPalette.ColorRole.ButtonText, "#e8e8ef"), (QPalette.ColorRole.Highlight, "#c9a96e"),
                    (QPalette.ColorRole.HighlightedText, "#17171c"), (QPalette.ColorRole.ToolTipBase, "#2a2a33"),
                    (QPalette.ColorRole.ToolTipText, "#e8e8ef")):
        p.setColor(role, QColor(c))
    app.setPalette(p)


def main():
    if shutil.which("bsdtar") is None:
        print("bsmods needs bsdtar (libarchive) to unpack mods", file=sys.stderr)
    app = QApplication(sys.argv)
    app.setApplicationName("bsmods")
    app.setDesktopFileName("bsmods")
    icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bsmods.svg")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    dark(app)
    w = Window()
    w.show()
    # files given on the command line (or from "Open with") are installed straight away
    if len(sys.argv) > 1:
        w.install_paths([a for a in sys.argv[1:] if os.path.exists(a)])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
