"""The main window: games on the left, the chosen game's mods, plugins, browse and downloads."""
import os
import shutil
import subprocess
import tempfile
import time
import webbrowser

from PyQt6.QtCore import QRectF, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                             QInputDialog, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
                             QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import VERSION, config, games, install, layout, net, nexus, thunderstore
from ..config import DATA, HOME
from ..fomod import Fomod
from ..store import DeployError, Store, resolve_case, staged_files
from . import tasks
from .browse import BrowsePage
from .dialogs import (AddGameDialog, FomodWizard, ImportProfileDialog, ModDetailsDialog, NexusFilesDialog,
                      SettingsDialog)
from .downloads import Downloads, DownloadsPage
from .mods import ModsPage, PluginsPage
from . import theme as T
from .theme import ICON, Tabs, Toast, blurred, button, label, menu_button, placeholder, restyle, rounded

PROXY_DLLS = {"winhttp.dll": "BepInEx", "version.dll": "MelonLoader", "dinput8.dll": "the script loader",
              "dxgi.dll": "the injector", "d3d11.dll": "the injector", "winmm.dll": "the loader",
              "dsound.dll": "the loader"}
OLD_BSMODS = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local/share"), "bsmods")


class Ambient(QWidget):
    """the main area: the game's art, blurred and dark, glowing behind the top of the page"""
    def __init__(self):
        super().__init__()
        self.src = QPixmap()
        self.cache = QPixmap()

    def set_image(self, path):
        self.src = QPixmap(path) if path else QPixmap()
        self.cache = QPixmap()
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.cache = QPixmap()

    def paintEvent(self, _e):
        p = QPainter(self)
        bg = QColor(T.BG)
        p.fillRect(self.rect(), bg)
        if self.src.isNull() or not config.get("ambient", True):
            return
        h = min(self.height(), 520)
        if self.cache.isNull() or self.cache.width() < self.width():
            self.cache = blurred(self.src, self.width(), h)
        p.setOpacity(0.30 if T.LIGHT else 0.42)
        p.drawPixmap(0, 0, self.cache, (self.cache.width() - self.width()) // 2, 0, self.width(), h)
        p.setOpacity(1)
        fade = QLinearGradient(0, 0, 0, h)
        for at, alpha in ((0, 90), (0.55, 200), (1, 255)):
            c = QColor(bg)
            c.setAlpha(alpha)
            fade.setColorAt(at, c)
        p.fillRect(0, 0, self.width(), h, fade)


class Hero(QWidget):
    """the game's banner from Steam behind its logo (or name) and the Play button"""
    def __init__(self):
        super().__init__()
        self.pix = QPixmap()
        self.setFixedHeight(230)

    def set_image(self, path):
        self.pix = QPixmap(path) if path else QPixmap()
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        p.setClipPath(path)
        if not self.pix.isNull():
            s = self.pix.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((self.width() - s.width()) // 2, (self.height() - s.height()) // 3, s)
        else:
            g = QLinearGradient(0, 0, self.width(), self.height())
            g.setColorAt(0, QColor(T.ACCENT).darker(420))
            g.setColorAt(1, QColor("#15151b"))
            p.fillRect(self.rect(), g)
        side = QLinearGradient(0, 0, self.width(), 0)
        side.setColorAt(0, QColor(10, 10, 14, 200))
        side.setColorAt(0.5, QColor(10, 10, 14, 90))
        side.setColorAt(1, QColor(10, 10, 14, 20))
        p.fillRect(self.rect(), side)
        low = QLinearGradient(0, 0, 0, self.height())
        low.setColorAt(0.35, QColor(10, 10, 14, 0))
        low.setColorAt(1, QColor(10, 10, 14, 215))
        p.fillRect(self.rect(), low)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)


class GameRow(QPushButton):
    def __init__(self, game, count):
        super().__init__()
        self.setObjectName("gameRow")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(56)
        self.game = game
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 10, 6)
        lay.setSpacing(11)
        pic = label("")
        pic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        pic.setFixedSize(30, 44)
        img = games.steam_image(game.appid, "capsule")
        pix = QPixmap(img) if img else QPixmap()
        pic.setPixmap(rounded(pix, 30, 44, 6) if not pix.isNull() else placeholder(game.name, 30, 44, 6))
        if not game.found:
            fx = QGraphicsOpacityEffect(pic)
            fx.setOpacity(0.4)
            pic.setGraphicsEffect(fx)
        lay.addWidget(pic)
        t = QVBoxLayout()
        t.setSpacing(2)
        t.addStretch(1)
        n = label(game.name, "gameName" if game.found else "gameNameOff")
        n.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        s = label("", "small")
        s.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.sub = s
        self.set_count(count)
        t.addWidget(n)
        t.addWidget(s)
        t.addStretch(1)
        lay.addLayout(t, 1)

    def set_count(self, count, on=None):
        if not self.game.found:
            self.sub.setText("not found")
        elif not count:
            self.sub.setText("no mods yet")
        else:
            self.sub.setText(f"{count} mod{'s' if count != 1 else ''}" + (f" · {on} on" if on is not None else ""))


class DropOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.text = ""
        self.hide()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        shade = QColor(T.BG)
        shade.setAlpha(220)
        p.fillRect(self.rect(), shade)
        r = QRectF(self.rect()).adjusted(16, 16, -16, -16)
        acc = QColor(T.ACCENT)
        p.setPen(QPen(acc, 2, Qt.PenStyle.DashLine))
        acc.setAlpha(26)
        p.setBrush(acc)
        p.drawRoundedRect(r, 18, 18)
        f = QFont()
        f.setPixelSize(22)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(T.TEXT))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Drop to install\n")
        f.setPixelSize(13)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(T.MUTED))
        p.drawText(r.adjusted(0, 40, 0, 0), Qt.AlignmentFlag.AlignCenter, self.text)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Armory")
        self.resize(*config.get("window_size", [1240, 800]))
        self.setMinimumSize(900, 560)
        self.setAcceptDrops(True)
        self.nexus = nexus.Nexus()
        self.dl = Downloads()
        self.dl.finished.connect(self.download_finished)
        self.stores = {}
        self.games = []
        self.game = None
        self.store = None
        self.queue = []
        self.installing = False
        self.deploying = False
        self.deploy_again = False
        self.play_after = False
        self.page = "mods"
        self.deploy_timer = QTimer(self)
        self.deploy_timer.setSingleShot(True)
        self.deploy_timer.setInterval(350)
        self.deploy_timer.timeout.connect(self.deploy)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self.build_sidebar())

        self.main = Ambient()
        v = QVBoxLayout(self.main)
        v.setContentsMargins(26, 22, 26, 14)
        v.setSpacing(14)
        v.addWidget(self.build_hero())
        self.notice = QFrame()
        self.notice.setObjectName("notice")
        nl = QHBoxLayout(self.notice)
        nl.setContentsMargins(16, 11, 11, 11)
        self.notice_text = label("", wrap=True)
        self.notice_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        nl.addWidget(self.notice_text, 1)
        self.notice_btns = QHBoxLayout()
        nl.addLayout(self.notice_btns)
        self.notice.hide()
        v.addWidget(self.notice)

        self.pages_seg = Tabs([("mods", "Mods"), ("plugins", "Plugins"), ("browse", "Browse"),
                               ("downloads", "Downloads")], self.show_page, "mods")
        self.updates_btn = button("Check for updates", lambda: self.check_updates())
        self.pages_seg.trail.addWidget(self.updates_btn)
        self.pages_seg.trail.addWidget(button("+  Install from file", self.pick_files, "primary"))
        v.addWidget(self.pages_seg)

        self.stack = QStackedWidget()
        self.mods_page = ModsPage(self)
        self.plugins_page = PluginsPage(self)
        self.browse_page = BrowsePage(self)
        self.downloads_page = DownloadsPage(self, self.dl)
        self.no_game = QWidget()
        ng = QVBoxLayout(self.no_game)
        ng.setContentsMargins(40, 80, 40, 0)
        t = label("No games yet", "h2")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ng.addWidget(t)
        s = label("Armory lists the supported games it finds in your Steam libraries. Add one with “Add game”.",
                  "muted", True)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ng.addWidget(s)
        ng.addStretch(1)
        for w in (self.mods_page, self.plugins_page, self.browse_page, self.downloads_page, self.no_game):
            self.stack.addWidget(w)
        v.addWidget(self.stack, 1)
        h.addWidget(self.main, 1)
        self.toast = Toast(self.main)
        self.overlay = DropOverlay(root)

        self.load_games(config.get("last_game"))
        if self.nexus.logged_in:
            tasks.run(self.nexus.validate, lambda _: self.account_changed(),
                      lambda m: self.say(f"Nexus Mods: {m}"))
        self.account_changed()

    # ---- building ----
    def build_sidebar(self):
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(264)
        v = QVBoxLayout(side)
        v.setContentsMargins(14, 20, 14, 14)
        v.setSpacing(10)
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 0)
        brand.setSpacing(10)
        icon = label("")
        icon.setPixmap(QIcon(ICON).pixmap(30, 30))
        brand.addWidget(icon)
        brand.addWidget(label("ARMORY", "brand"))
        brand.addStretch(1)
        v.addLayout(brand)
        v.addSpacing(10)
        self.game_search = QLineEdit()
        self.game_search.setPlaceholderText("Search games")
        self.game_search.setClearButtonEnabled(True)
        self.game_search.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.game_search.textChanged.connect(self.filter_games)
        v.addWidget(self.game_search)
        head = QHBoxLayout()
        head.setContentsMargins(6, 6, 4, 0)
        head.addWidget(label("GAMES", "section"))
        head.addStretch(1)
        self.games_count = label("", "count")
        head.addWidget(self.games_count)
        v.addLayout(head)
        self.game_scroll = QScrollArea()
        self.game_scroll.setWidgetResizable(True)
        self.game_scroll.viewport().setObjectName("viewport")
        self.game_scroll.viewport().setStyleSheet("#viewport { background: transparent; }")
        self.game_holder = QWidget()
        self.game_holder.setObjectName("holder")
        self.game_holder.setStyleSheet("#holder { background: transparent; }")
        self.game_list = QVBoxLayout(self.game_holder)
        self.game_list.setContentsMargins(0, 0, 4, 0)
        self.game_list.setSpacing(2)
        self.game_scroll.setWidget(self.game_holder)
        v.addWidget(self.game_scroll, 1)
        v.addWidget(button("+  Add game", self.add_game, "ghost"))
        line = QFrame()
        line.setObjectName("hline")
        line.setFixedHeight(1)
        v.addSpacing(4)
        v.addWidget(line)
        v.addSpacing(2)
        foot = QHBoxLayout()
        foot.setSpacing(4)
        self.account = QPushButton()
        self.account.setObjectName("gameRow")
        self.account.setCursor(Qt.CursorShape.PointingHandCursor)
        self.account.setFixedHeight(52)
        self.account.setToolTip("Nexus Mods account")
        self.account.clicked.connect(lambda: self.settings("nexus"))
        al = QHBoxLayout(self.account)
        al.setContentsMargins(6, 6, 6, 6)
        al.setSpacing(10)
        self.avatar = label("")
        self.avatar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        al.addWidget(self.avatar)
        at = QVBoxLayout()
        at.setSpacing(1)
        self.acc_name = label("Nexus Mods")
        self.acc_name.setStyleSheet("font-weight: 600;")
        self.acc_name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.acc_sub = label("Log in", "small")
        self.acc_sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        at.addWidget(self.acc_name)
        at.addWidget(self.acc_sub)
        al.addLayout(at, 1)
        foot.addWidget(self.account, 1)
        gear = QToolButton()
        gear.setText("⚙")
        gear.setToolTip(f"Settings  ·  Armory v{VERSION}")
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.setStyleSheet("font-size: 18px; padding: 8px 10px;")
        gear.clicked.connect(lambda: self.settings("appearance"))
        foot.addWidget(gear)
        v.addLayout(foot)
        return side

    def build_hero(self):
        self.hero = Hero()
        self.hero.setObjectName("hero")
        lay = QHBoxLayout(self.hero)
        lay.setContentsMargins(30, 22, 24, 22)
        lay.setSpacing(16)
        t = QVBoxLayout()
        t.setSpacing(8)
        t.addStretch(1)
        self.logo = label("")
        self.logo.hide()
        t.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self.title = label("", "title")
        self.title.setStyleSheet("font-size: 30px; font-weight: 800;")
        t.addWidget(self.title)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.count_chip = label("", "chipGlass")
        chips.addWidget(self.count_chip)
        self.deploy_chip = label("", "chipOk")
        chips.addWidget(self.deploy_chip)
        self.subtitle = label("", "small")
        chips.addSpacing(4)
        chips.addWidget(self.subtitle)
        chips.addStretch(1)
        t.addLayout(chips)
        lay.addLayout(t, 1)

        right = QVBoxLayout()
        right.setSpacing(10)
        right.addStretch(1)
        prof = QHBoxLayout()
        prof.setSpacing(6)
        prof.addStretch(1)
        prof.addWidget(label("PROFILE", "section"))
        self.profile_box = QComboBox()
        self.profile_box.setObjectName("glass")
        self.profile_box.setMinimumWidth(160)
        self.profile_box.setToolTip("Profiles: each keeps its own mods on/off, order and plugins")
        self.profile_box.activated.connect(self.profile_picked)
        prof.addWidget(self.profile_box)
        pm = QMenu(self)
        pm.addAction("New profile...", lambda: self.new_profile(True))
        pm.addAction("New empty profile...", lambda: self.new_profile(False))
        pm.addAction("Rename this profile...", self.rename_profile)
        pm.addAction("Delete this profile", self.delete_profile)
        prof.addWidget(menu_button(pm, "⋯", "Profiles"))
        right.addLayout(prof)
        prow = QHBoxLayout()
        prow.setSpacing(8)
        prow.addStretch(1)
        self.play_btn = button("▶   PLAY", self.play, "play")
        prow.addWidget(self.play_btn)
        gm = QMenu(self)
        self.game_menu = gm
        gm.aboutToShow.connect(self.fill_game_menu)
        more = menu_button(gm, "⋯", "Game")
        more.setObjectName("glass")
        prow.addWidget(more)
        right.addLayout(prow)
        lay.addLayout(right)
        return self.hero

    def filter_games(self):
        q = self.game_search.text().strip().lower()
        for row in self.rows.values():
            row.setVisible(not q or q in row.game.name.lower())

    # ---- games ----
    def load_games(self, select=None):
        self.games = games.detect()
        while self.game_list.count():
            w = self.game_list.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.rows = {}
        for g in self.games:
            st = self.store_for(g)
            row = GameRow(g, len(st.mods))
            row.clicked.connect(lambda _=False, gid=g.id: self.select_game(gid))
            self.rows[g.id] = row
            self.game_list.addWidget(row)
        self.game_list.addStretch(1)
        self.games_count.setText(str(len(self.games)))
        self.filter_games()
        ids = [g.id for g in self.games]
        if not ids:
            self.game = self.store = None
            self.stack.setCurrentWidget(self.no_game)
            self.title.setText("Armory")
            self.title.show()
            self.logo.hide()
            self.subtitle.setText("A mod manager for your games")
            self.hero.set_image(None)
            self.main.set_image(None)
            return
        self.select_game(select if select in ids else (self.game.id if self.game and self.game.id in ids else ids[0]))

    def store_for(self, g):
        st = self.stores.get(g.id)
        if st is None or st.game is not g:
            st = Store(g)
            self.stores[g.id] = st
        return st

    def select_game(self, gid):
        g = next((x for x in self.games if x.id == gid), None)
        if not g:
            return
        self.game = g
        self.store = self.store_for(g)
        for k, r in self.rows.items():
            r.setChecked(k == gid)
        config.save_conf(last_game=gid)
        art = games.steam_image(g.appid, "hero") or games.steam_image(g.appid, "header")
        self.hero.set_image(art)
        self.main_art = art or games.steam_image(g.appid, "capsule")
        self.main.set_image(self.main_art)
        self.title.setText(g.name)
        logo = games.steam_image(g.appid, "logo")
        pix = QPixmap(logo) if logo else QPixmap()
        if not pix.isNull():
            pix = pix.scaled(340, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo.setPixmap(pix)
            self.logo.setFixedSize(pix.size())
            self.logo.setToolTip(g.name)
            self.logo.show()
            self.title.hide()
        else:
            self.logo.hide()
            self.title.show()
        self.pages_seg.show_key("plugins", bool(g.plugins))
        self.pages_seg.show_key("browse", bool(g.nexus or g.thunderstore))
        if self.page == "plugins" and not g.plugins or self.page == "browse" and not (g.nexus or g.thunderstore):
            self.page = "mods"
        self.mods_page.set_store(self.store)
        self.plugins_page.set_store(self.store)
        self.browse_page.set_game(g)
        self.downloads_page.set_game(g.id)
        self.fill_profiles()
        self.show_page(self.page)
        self.refresh_header()
        self.first_run_import()
        self.check_notices()
        if g.found:
            # in case Steam (verifying files, an update) took mods out
            self.deploy_timer.start()
        QTimer.singleShot(400, self.auto_check_updates)

    def first_run_import(self):
        """the first time a game is opened: mods already in its mods folder move under Armory"""
        g, st = self.game, self.store
        done = config.get("adopted", []) or []
        if not g.found or not g.adopt or g.id in done:
            return
        sources = []
        if g.id == "bladeandsorcery" and os.path.isdir(OLD_BSMODS):
            # BS Mods: mods turned off, and the pages for other game versions
            sources.append(os.path.join(OLD_BSMODS, "disabled"))
            pages = os.path.join(OLD_BSMODS, "pages")
            if os.path.isdir(pages):
                for p in sorted(os.listdir(pages)):
                    sources += [os.path.join(pages, p, "on"), os.path.join(pages, p, "off")]
        try:
            names = st.adopt(g.adopt, sources)
        except OSError as e:
            self.say(f"Couldn't bring in the mods already in the game: {e}")
            return
        config.save_conf(adopted=done + [g.id])
        if names:
            self.say(f"Armory now manages the {len(names)} mods that were already in {g.name}")
            self.changed()

    def refresh_header(self):
        g, st = self.game, self.store
        if not g:
            return
        mods = st.ordered()
        on = sum(1 for m in mods if m["enabled"])
        self.count_chip.setText(f"{len(mods)} mod{'s' if len(mods) != 1 else ''}  ·  {on} on")
        path = g.path.replace(HOME, "~") if g.found else "game folder not found"
        self.subtitle.setText(self.subtitle.fontMetrics().elidedText(path, Qt.TextElideMode.ElideMiddle, 340))
        self.subtitle.setToolTip(g.path or "")
        if g.id in self.rows:
            self.rows[g.id].set_count(len(mods), on)
        self.play_btn.setEnabled(g.found and bool(g.appid or g.launch))
        self.play_btn.setToolTip("Starts the game through Steam" if g.appid and not g.launch else g.launch)
        if self.deploying:
            self.deploy_chip.setText("●  Updating game files...")
            restyle(self.deploy_chip, "chipBusy")
        elif not g.found:
            self.deploy_chip.setText("●  Game not found")
            restyle(self.deploy_chip, "chipBad")
        else:
            self.deploy_chip.setText("●  Ready")
            restyle(self.deploy_chip, "chipOk")
            self.deploy_chip.setToolTip(f"{st.deployed_count()} mod files are in the game")

    def fill_profiles(self):
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        for name in self.store.profiles:
            self.profile_box.addItem(name)
        self.profile_box.setCurrentText(self.store.active)
        self.profile_box.blockSignals(False)

    def show_page(self, key):
        if not self.game:
            return
        self.page = key
        self.pages_seg.set(key)
        self.stack.setCurrentWidget({"mods": self.mods_page, "plugins": self.plugins_page,
                                     "browse": self.browse_page, "downloads": self.downloads_page}[key])
        if key == "browse":
            self.browse_page.ensure_loaded()
        if key == "plugins":
            self.plugins_page.refresh()

    def say(self, text):
        self.toast.say(text)

    def changed(self):
        """the mods changed: show it and put the game in line"""
        if not self.store:
            return
        self.mods_page.refresh()
        if self.game.plugins:
            self.plugins_page.refresh()
        self.refresh_header()
        self.deploy_timer.start()

    # ---- deploying ----
    def deploy(self):
        g, st = self.game, self.store
        if not g or not g.found:
            return
        if self.deploying:
            self.deploy_again = True
            return
        self.deploying = True
        self.refresh_header()

        def done(stats):
            self.deploying = False
            if stats.get("skipped"):
                self.say(f"Some files weren't put in the game: {', '.join(stats['skipped'][:3])}"
                         + (" ..." if len(stats["skipped"]) > 3 else ""))
            self.after_deploy()

        def fail(msg):
            self.deploying = False
            self.play_after = False
            QMessageBox.warning(self, "Couldn't put the mods in the game", msg)
            self.after_deploy()

        tasks.run(st.deploy, done, fail)

    def after_deploy(self):
        self.refresh_header()
        self.check_notices()
        if self.game and self.game.plugins:
            self.plugins_page.refresh()
        if self.deploy_again:
            self.deploy_again = False
            self.deploy()
        elif self.play_after:
            self.play()
            self.play_after = False

    def check_notices(self):
        g = self.game
        while self.notice_btns.count():
            w = self.notice_btns.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        if not g:
            self.notice.hide()
            return
        if not g.found:
            self.notice_text.setText(f"{g.name} wasn't found. Install it in Steam, or pick its folder.")
            self.notice_btns.addWidget(button("Pick folder", self.change_game_dir, "primary"))
            restyle(self.notice, "noticeBad")
            self.notice.show()
            return
        if g.appid and g.windows_build and not g.launch:
            deployed = self.store.deployed()["files"]
            needed = sorted({k for k in deployed if k in PROXY_DLLS})
            opts = (games.steam_launch_options(g.appid) or "").lower()
            missing = [d for d in needed if d.removesuffix(".dll") + "=" not in opts.replace(" ", "")
                       and d.removesuffix(".dll") not in opts]
            if missing:
                over = ";".join(f"{d.removesuffix('.dll')}=n,b" for d in missing)
                line = f'WINEDLLOVERRIDES="{over}" %command%'
                who = PROXY_DLLS[missing[0]]
                self.notice_text.setText(f"Under Proton, {who} only loads with this in Steam → {g.name} → "
                                         f"Properties → Launch Options:\n{line}")
                self.notice_btns.addWidget(button("Copy", lambda: (QApplication.clipboard().setText(line),
                                                                   self.say("Copied: paste it in Steam"))))
                restyle(self.notice, "notice")
                self.notice.show()
                return
        self.notice.hide()

    # ---- installing ----
    def pick_files(self):
        if not self.game:
            return
        exts = " ".join("*" + e for e in layout.ARCHIVE_EXTS)
        paths, _ = QFileDialog.getOpenFileNames(self, f"Mods for {self.game.name}", os.path.join(HOME, "Downloads"),
                                                f"Mod archives ({exts});;All files (*)")
        self.install_paths(paths)

    def install_paths(self, paths, meta=None, replace=None, game=None, download=None):
        game = game or self.game
        if not game:
            return
        for p in paths:
            self.queue.append({"path": p, "meta": dict(meta or {}), "replace": replace, "game": game.id,
                               "download": download})
        self.next_install()

    def install_download(self, d):
        meta = dict(d.get("meta") or {})
        g = next((x for x in self.games if x.id == d["game"]), None)
        if not g:
            QMessageBox.warning(self, "Game not listed", "Add the game this was downloaded for first.")
            return
        self.install_paths([d["file"]], meta, meta.pop("replace", None), g, download=d)

    def download_finished(self, d):
        src = (d.get("meta") or {}).get("source") or {}
        if src.get("type") == "nexus" and self.nexus.logged_in and src.get("file_id"):
            self.verify_nexus(d, src)
            return
        self.downloaded(d)

    def downloaded(self, d):
        if d.get("install", True) and config.get("auto_install", True):
            self.install_download(d)
        else:
            self.say(f"Downloaded {d['name']}: install it from Downloads")

    def verify_nexus(self, d, src):
        """the downloaded file is the Nexus file it should be: Nexus knows every file's checksum"""
        domain = src.get("domain") or (self.game.nexus if self.game else "")

        def work():
            hits = self.nexus.md5_search(domain, net.md5(d["file"]))
            return any(int((h.get("file_details") or {}).get("file_id") or 0) == int(src["file_id"]) for h in hits), hits

        def done(res):
            ok, hits = res
            if ok:
                d.setdefault("meta", {})["verified"] = True
                self.downloaded(d)
                return
            why = "It doesn't match any file on Nexus Mods." if not hits else \
                "It matches a different file on Nexus Mods than the one asked for."
            if QMessageBox.warning(self, "Download didn't check out",
                                   f"{d['name']}: {why} It may be damaged or not what Nexus sent. Install it anyway?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                   QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.downloaded(d)

        def fail(msg):
            self.say(f"Couldn't check {d['name']} with Nexus ({msg}); installing it anyway")
            self.downloaded(d)

        tasks.run(work, done, fail)

    def next_install(self):
        if self.installing or not self.queue:
            return
        job = self.queue.pop(0)
        g = next((x for x in self.games if x.id == job["game"]), None)
        if not g:
            self.next_install()
            return
        st = self.store_for(g)
        self.installing = True
        src = job["path"]
        name = job["meta"].get("name") or layout.mod_name_from_file(src)
        self.say(f"Installing {name}...")
        os.makedirs(os.path.join(DATA, "tmp"), exist_ok=True)
        tmp = tempfile.mkdtemp(prefix="install-", dir=os.path.join(DATA, "tmp"))

        def cleanup():
            shutil.rmtree(tmp, ignore_errors=True)
            self.installing = False
            QTimer.singleShot(0, self.next_install)

        def fail(msg):
            cleanup()
            QMessageBox.warning(self, f"Couldn't install {name}", msg)

        def unpacked(root):
            if config.get("scan_mods", False):
                self.say(f"Scanning {name} with ClamAV...")
                tasks.run(lambda: layout.scan(root), lambda found: scanned(root, found),
                          lambda msg: scan_failed(root, msg))
                return
            go_on(root)

        def scanned(root, found):
            if found:
                cleanup()
                QMessageBox.critical(self, f"{name} wasn't installed",
                                     "ClamAV found something in it:\n\n" +
                                     "\n".join(f"{f}: {what}" for f, what in found[:10]))
                return
            go_on(root)

        def scan_failed(root, msg):
            if QMessageBox.question(self, "Not scanned", f"{msg}\n\nInstall {name} anyway?") \
                    == QMessageBox.StandardButton.Yes:
                go_on(root)
            else:
                cleanup()

        def go_on(root):
            fomod_files = None
            found = layout.find_fomod(root)
            if found:
                try:
                    fm = Fomod(*found)
                except Exception as e:  # noqa: BLE001 - a broken installer: fall back to the files
                    fm = None
                    self.say(f"{name}'s installer couldn't be read ({e}); installing its files as they are")
                if fm and (fm.steps or fm.required or fm.conditional):
                    installed = set()
                    for mid in st.profile["enabled"]:
                        for key in staged_files(st.mod_path(mid)):
                            installed.add(key.split("/")[-1])
                    wiz = FomodWizard(self, fm, installed)
                    if not wiz.exec() or not wiz.files:
                        cleanup()
                        self.say(f"{name} wasn't installed")
                        return
                    fomod_files = [(s, d) for s, d in wiz.files]
            meta = job["meta"]
            meta.setdefault("source", {"type": "local"})
            if not meta.get("archive") and not os.path.isdir(src):
                meta["archive"] = src
            replace = job["replace"]
            if replace is None:
                replace = self.ask_replace(st, meta, name)
                if replace is False:
                    cleanup()
                    return
            enable = not meta.pop("disabled", False)
            tasks.run(lambda: install.stage(st, root, name, meta, fomod_files, replace, enable), staged, fail)

        def staged(mid):
            cleanup()
            if job.get("download"):
                self.dl.mark_installed(job["download"]["file"])
            elif not os.path.isdir(src) and config.get("keep_downloads", True) and \
                    not os.path.abspath(src).startswith(os.path.join(DATA, "downloads")):
                self.dl.add_local(src, g.id, {"name": st.mods[mid].get("name"), "source": st.mods[mid].get("source")})
                self.dl.mark_installed(src)
            m = st.mods[mid]
            self.say(f"Installed {m.get('name')}")
            if g is self.game:
                self.changed()
            else:
                self.deploy_store(st)
            if (m.get("source") or {}).get("type") == "local" and self.nexus.logged_in and g.nexus and \
                    os.path.isfile(src):
                self.link_to_nexus(st, mid, src)

        tasks.run(lambda: install.unpack(src, tmp), unpacked, fail)

    def ask_replace(self, st, meta, name):
        """a mod that's already installed: replace it (an update), install next to it, or stop"""
        s = meta.get("source") or {}
        if s.get("type") == "thunderstore":
            return st.find(thunderstore=s.get("full_name", ""))
        if s.get("type") != "nexus":
            return None
        same = [mid for mid, m in st.mods.items() if (m.get("source") or {}).get("type") == "nexus"
                and int((m.get("source") or {}).get("mod_id") or 0) == int(s.get("mod_id") or 0)]
        if not same:
            return None
        for mid in same:
            if (st.mods[mid].get("source") or {}).get("file_id") == s.get("file_id"):
                return mid
        box = QMessageBox(self)
        box.setWindowTitle("Already installed")
        old = st.mods[same[0]]
        box.setText(f"{old.get('name')} is already installed. Is {s.get('file_name') or name} a new version of it, "
                    "or another file to install next to it (an add-on, an optional file)?")
        rep = box.addButton("Replace it", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Install next to it", QMessageBox.ButtonRole.ActionRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is cancel:
            return False
        return same[0] if box.clickedButton() is rep else None

    def deploy_store(self, st):
        if st.game.found:
            tasks.run(st.deploy, None, lambda m: self.say(f"{st.game.name}: {m}"))

    def link_to_nexus(self, st, mid, archive):
        """a manually downloaded file: find which Nexus mod it is by its checksum"""
        domain = st.game.nexus

        def work():
            hits = self.nexus.md5_search(domain, net.md5(archive))
            return hits[0] if hits else None

        def done(hit):
            if not hit or mid not in st.mods:
                return
            mod, f = hit.get("mod", {}), hit.get("file_details", {})
            m = st.mods[mid]
            st.update_meta(mid, source={"type": "nexus", "domain": domain, "mod_id": mod.get("mod_id"),
                                        "file_id": f.get("file_id"), "file_name": f.get("name")},
                           name=m.get("name") if m.get("name") and m.get("name") != mid else mod.get("name"),
                           version=f.get("version") or mod.get("version") or m.get("version"),
                           author=m.get("author") or mod.get("author"), summary=m.get("summary") or mod.get("summary"),
                           picture=mod.get("picture_url"), adult=bool(mod.get("contains_adult_content")) or None)
            if st is self.store:
                self.mods_page.refresh()

        tasks.run(work, done)

    # ---- Nexus ----
    def need_login(self):
        if self.nexus.logged_in:
            return False
        QMessageBox.information(self, "Log in to Nexus Mods",
                                "Downloading from Nexus Mods needs your account. Log in under Settings → Nexus Mods.")
        self.settings("nexus")
        return not self.nexus.logged_in

    def nexus_install(self, g, mod_id, raw=None):
        """Browse → Download: Premium downloads straight away, others go to the mod's Files tab"""
        if not self.nexus.premium:
            webbrowser.open(nexus.mod_url(g.nexus, mod_id, "files"))
            if not links_ready("nxm"):
                self.say("Tip: let Armory open “Mod Manager Download” links in Settings → Links")
            else:
                self.say("Press “Mod Manager Download” on the file you want: Armory takes it from there")
            return
        self.say("Getting the file list...")
        tasks.run(lambda: self.nexus.files(g.nexus, mod_id),
                  lambda res: self.pick_nexus_file(g, mod_id, res.get("files", []), raw),
                  lambda m: QMessageBox.warning(self, "Nexus Mods", m))

    def pick_nexus_file(self, g, mod_id, files, raw=None, replace=None, current=None):
        if not files:
            QMessageBox.information(self, "No files", "That mod has no files to download.")
            return
        title = (raw or {}).get("name") or f"Mod {mod_id}"
        dlg = NexusFilesDialog(self, title, files, current)
        if not dlg.exec() or not dlg.choice:
            return
        f = dlg.choice
        self.nexus_download(g, mod_id, f["file_id"], replace=replace)

    def nexus_download(self, g, mod_id, file_id, key=None, expires=None, replace=None):
        """ask Nexus for the download, with the mod's details, and queue it"""
        nx = self.nexus

        def work():
            info = nx.mod(g.nexus, mod_id)
            files = nx.files(g.nexus, mod_id).get("files", [])
            f = next((x for x in files if x["file_id"] == file_id), {})
            urls = nx.download_links(g.nexus, mod_id, file_id, key, expires)
            return info, f, urls

        def done(res):
            info, f, urls = res
            if not urls:
                QMessageBox.warning(self, "Nexus Mods", "Nexus didn't give a download link.")
                return
            meta = {"name": info.get("name"), "version": f.get("version") or info.get("version"),
                    "author": info.get("author"), "summary": info.get("summary"),
                    "picture": info.get("picture_url"), "adult": bool(info.get("contains_adult_content")) or None,
                    "source": {"type": "nexus", "domain": g.nexus, "mod_id": mod_id, "file_id": file_id,
                               "file_name": f.get("name")}}
            if f.get("category_name") not in (None, "MAIN") and f.get("name") and f.get("name") != info.get("name"):
                meta["name"] = f"{info.get('name')} — {f.get('name')}"
            if replace:
                meta["replace"] = replace
            filename = f.get("file_name") or f"{mod_id}-{file_id}.zip"
            self.dl.add(urls[0]["URI"], filename, g.id, {k: v for k, v in meta.items() if v is not None})
            self.say(f"Downloading {meta['name']}")
            if self.game is g and self.page == "browse":
                pass

        def fail(msg):
            if "403" in msg and not key:
                msg += "\n\nOnly Premium accounts can download without the website's Mod Manager Download button."
            QMessageBox.warning(self, "Nexus Mods", msg)

        tasks.run(work, done, fail)

    def handle_nxm(self, url):
        link = nexus.parse_nxm(url)
        if not link:
            QMessageBox.warning(self, "Link", f"Armory can't read this link:\n{url}")
            return
        g = next((x for x in self.games if x.nexus == link["domain"]), None)
        if not g:
            spec = next(((gid, s) for gid, s in games.GAMES.items() if s.get("nexus") == link["domain"]), None)
            if spec:
                QMessageBox.information(self, "Add the game first",
                                        f"That's a mod for {spec[1]['name']}, which isn't in Armory's list. "
                                        "Add it with “Add game”, then press the button on Nexus again.")
            else:
                QMessageBox.information(self, "Game not supported",
                                        f"Armory doesn't know the game “{link['domain']}”. You can add it as "
                                        "another game, with that name as its Nexus Mods game.")
            return
        if self.need_login():
            return
        me = str((self.nexus.user or {}).get("user_id") or "")
        if link["user_id"] and me and link["user_id"] != me:
            QMessageBox.warning(self, "Not your link", "That download link was made for another Nexus account, "
                                "so Armory won't use it. Press the button on Nexus yourself while logged in.")
            return
        self.raise_()
        self.activateWindow()
        if g is not self.game:
            self.select_game(g.id)
        self.nexus_download(g, link["mod_id"], link["file_id"], link["key"], link["expires"])

    def account_changed(self):
        nx = self.nexus
        if nx.logged_in and nx.user:
            self.acc_name.setText(nx.user.get("name", "Nexus Mods"))
            self.acc_sub.setText("Premium" if nx.premium else "Nexus Mods · free")
            tasks.set_picture(self.avatar, nx.user.get("profile_url"), 36, 36, nx.user.get("name", ""), 18)
        elif nx.logged_in:
            self.acc_name.setText("Nexus Mods")
            self.acc_sub.setText("Checking...")
            tasks.set_picture(self.avatar, None, 36, 36, "N", 18)
        else:
            self.acc_name.setText("Nexus Mods")
            self.acc_sub.setText("Not logged in")
            tasks.set_picture(self.avatar, None, 36, 36, "N", 18)
        self.browse_page.refresh_tiles()

    def set_nexus(self, nx):
        self.nexus = nx
        self.account_changed()

    # ---- Thunderstore ----
    def thunderstore_install(self, g, full, packages=None, replace_all=False):
        st = self.store_for(g)
        have = {}
        for m in st.mods.values():
            s = m.get("source") or {}
            if s.get("type") == "thunderstore":
                have[s.get("full_name", "").lower()] = m.get("version", "")
        if replace_all:
            have.pop(full.lower(), None)

        def work():
            pk = packages or thunderstore.listing(g.thunderstore)
            todo = thunderstore.resolve(full, pk, have)
            if not todo and full.lower() not in thunderstore.index(pk):
                owner, _, name = full.partition("-")
                p = thunderstore.package_info(owner, name)
                todo = thunderstore.resolve(full, pk + [p], have)
            return todo

        def done(todo):
            if not todo:
                self.say("Already installed and up to date")
                return
            for p in todo:
                meta = {"name": p["name"].replace("_", " "), "version": p["version"], "author": p["owner"],
                        "summary": p["desc"], "picture": p["icon"], "adult": p.get("nsfw") or None,
                        "source": {"type": "thunderstore", "full_name": p["full"], "url": p.get("url", "")}}
                rep = st.find(thunderstore=p["full"])
                if rep:
                    meta["replace"] = rep
                self.dl.add(thunderstore.download_url(p["owner"], p["name"], p["version"]),
                            f"{p['full']}-{p['version']}.zip", g.id, meta)
            names = ", ".join(p["name"] for p in todo)
            self.say(f"Downloading {names}" if len(todo) < 5 else f"Downloading {len(todo)} packages")

        tasks.run(work, done, lambda m: QMessageBox.warning(self, "Thunderstore", m))

    def handle_ror2mm(self, url):
        link = thunderstore.parse_link(url)
        if not link:
            QMessageBox.warning(self, "Link", f"Armory can't read this link:\n{url}")
            return
        cands = [g for g in self.games if g.thunderstore]
        if not cands:
            QMessageBox.information(self, "No game", "None of your games in Armory use Thunderstore.")
            return
        g = self.game if self.game in cands else None
        if len(cands) > 1 and g is None:
            names = [x.name for x in cands]
            pick, ok = QInputDialog.getItem(self, "Which game?", f"Install {link['name']} for:", names, 0, False)
            if not ok:
                return
            g = cands[names.index(pick)]
        g = g or cands[0]
        self.raise_()
        self.activateWindow()
        # any web page can open these links: nothing is installed without a yes
        box = QMessageBox(self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setWindowTitle("Install from Thunderstore?")
        box.setText(f"Install {link['name']} by {link['owner']} for {g.name}? Mods it needs come with it.\n\n"
                    "Only say yes if you just pressed an install button on thunderstore.io.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        if g is not self.game:
            self.select_game(g.id)
        self.thunderstore_install(g, link["full"])

    # ---- updates ----
    def auto_check_updates(self):
        g = self.game
        if not g:
            return
        last = (config.get("update_checked", {}) or {}).get(g.id, 0)
        if time.time() - last > 6 * 3600:
            self.check_updates(quiet=True)

    def check_updates(self, ids=None, quiet=False):
        g, st = self.game, self.store
        if not g:
            return
        mods = {mid: dict(m) for mid, m in st.mods.items() if ids is None or mid in ids}
        nx = self.nexus if self.nexus.logged_in else None
        has_ts = any((m.get("source") or {}).get("type") == "thunderstore" for m in mods.values())
        has_nx = any((m.get("source") or {}).get("type") == "nexus" for m in mods.values())
        if not has_ts and not (has_nx and nx):
            if not quiet:
                self.say("Only mods from Nexus Mods (when you're logged in) and Thunderstore can be checked"
                         if mods else "No mods to check")
            return
        self.updates_btn.setEnabled(False)
        self.updates_btn.setText("Checking...")

        def work():
            out, errors = {}, []
            pk = None
            if has_ts:
                try:
                    pk = thunderstore.index(thunderstore.listing(g.thunderstore))
                except net.NetError as e:
                    errors.append(str(e))
            for mid, m in mods.items():
                s = m.get("source") or {}
                try:
                    if s.get("type") == "thunderstore" and pk is not None:
                        p = pk.get(s.get("full_name", "").lower())
                        if p and thunderstore.vtuple(p["version"]) > thunderstore.vtuple(m.get("version")):
                            out[mid] = {"version": p["version"]}
                        else:
                            out[mid] = None
                    elif s.get("type") == "nexus" and nx and s.get("mod_id"):
                        out[mid] = nx.update_for(s.get("domain") or g.nexus, s["mod_id"], s.get("file_id"),
                                                 m.get("version"))
                except net.NetError as e:
                    errors.append(f"{m.get('name')}: {e}")
                    if e.status == 429:
                        break
            return out, errors

        def done(res):
            out, errors = res
            self.updates_btn.setEnabled(True)
            self.updates_btn.setText("Check for updates")
            for mid, up in out.items():
                if mid in st.mods:
                    st.update_meta(mid, update=up)
            checked = dict(config.get("update_checked", {}) or {})
            checked[g.id] = time.time()
            config.save_conf(update_checked=checked)
            n = sum(1 for v in out.values() if v)
            if st is self.store:
                self.mods_page.refresh()
            if n:
                self.say(f"{n} update{'s' if n != 1 else ''} available: see Updates")
            elif not quiet:
                self.say("Everything is up to date" + (f" ({len(errors)} couldn't be checked)" if errors else ""))

        def fail(msg):
            self.updates_btn.setEnabled(True)
            self.updates_btn.setText("Check for updates")
            if not quiet:
                QMessageBox.warning(self, "Couldn't check for updates", msg)

        tasks.run(work, done, fail)

    def update_mod(self, mid):
        g, st = self.game, self.store
        m = st.mods.get(mid)
        if not m:
            return
        s = m.get("source") or {}
        up = m.get("update") or {}
        if s.get("type") == "thunderstore":
            self.thunderstore_install(g, s["full_name"], replace_all=True)
        elif s.get("type") == "nexus":
            if self.need_login():
                return
            if self.nexus.premium and up.get("file_id"):
                self.nexus_download(g, s["mod_id"], up["file_id"], replace=mid)
            else:
                webbrowser.open(nexus.mod_url(s.get("domain") or g.nexus, s["mod_id"], "files"))
                self.say("Press “Mod Manager Download” on the new file; Armory will ask to replace the old one")

    def endorse(self, mid, on):
        st, g = self.store, self.game
        m = st.mods[mid]
        s = m.get("source") or {}

        def done(_):
            st.update_meta(mid, endorsed=True if on else None)
            self.say(f"{'Endorsed' if on else 'Took back your endorsement of'} {m.get('name')}")
            self.mods_page.refresh()

        tasks.run(lambda: self.nexus.endorse(s.get("domain") or g.nexus, s["mod_id"], m.get("version"), on), done,
                  lambda msg: QMessageBox.warning(self, "Nexus Mods", msg))

    # ---- mod actions ----
    def remove_mod(self, mid):
        st = self.store
        m = st.mods.get(mid)
        if not m:
            return
        if QMessageBox.question(self, "Remove mod", f"Remove {m.get('name')}? It's taken out of the game and its "
                                "files are deleted.") != QMessageBox.StandardButton.Yes:
            return
        st.set_enabled(mid, False)
        # out of the game first: its files there are links to the ones about to be deleted
        try:
            if st.game.found:
                st.deploy()
        except (OSError, DeployError) as e:
            QMessageBox.warning(self, "Couldn't take it out of the game", str(e))
            return
        st.remove(mid)
        self.say(f"Removed {m.get('name')}")
        self.changed()

    def rename_mod(self, mid):
        m = self.store.mods[mid]
        name, ok = QInputDialog.getText(self, "Rename", "Name:", text=m.get("name", ""))
        if ok and name.strip():
            self.store.update_meta(mid, name=name.strip())
            self.mods_page.refresh()

    def mod_details(self, mid):
        ModDetailsDialog(self, self.store, mid).exec()

    # ---- profiles ----
    def profile_picked(self):
        name = self.profile_box.currentText()
        if name and name != self.store.active:
            self.store.switch_profile(name)
            self.say(f"Using the {name} profile")
            self.changed()

    def new_profile(self, copy):
        name, ok = QInputDialog.getText(self, "New profile", "Name:")
        name = name.strip()
        if not ok or not name:
            return
        if name in self.store.profiles:
            QMessageBox.warning(self, "Profile", "There's a profile with that name.")
            return
        self.store.new_profile(name, copy)
        self.fill_profiles()
        self.changed()

    def rename_profile(self):
        old = self.store.active
        name, ok = QInputDialog.getText(self, "Rename profile", "Name:", text=old)
        if ok and name.strip() and name.strip() not in self.store.profiles:
            self.store.rename_profile(old, name.strip())
            self.fill_profiles()

    def delete_profile(self):
        if len(self.store.profiles) < 2:
            QMessageBox.information(self, "Profile", "This is the only profile.")
            return
        name = self.store.active
        if QMessageBox.question(self, "Delete profile", f"Delete the {name} profile? Its mods stay installed.") \
                == QMessageBox.StandardButton.Yes:
            self.store.delete_profile(name)
            self.fill_profiles()
            self.changed()

    # ---- the game ----
    def play(self):
        g = self.game
        if not g or not g.found:
            return
        if not self.play_after:
            # the game always gets exactly the mods that are on, then starts
            self.play_after = True
            self.deploy_timer.stop()
            if not self.deploying:
                self.deploy()
            else:
                self.deploy_again = True
            self.say("Putting the mods in first...")
            return
        try:
            if g.launch:
                subprocess.Popen(g.launch, shell=True, cwd=g.path, start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["xdg-open", f"steam://rungameid/{g.appid}"], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.say(f"Starting {g.name}...")
        except OSError as e:
            QMessageBox.warning(self, "Couldn't start it", str(e))

    def fill_game_menu(self):
        m = self.game_menu
        m.clear()
        g = self.game
        if not g:
            return
        if g.found:
            m.addAction("Open the game folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(g.path)))
        m.addAction("Open where its mods are kept", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.makedirs(self.store.mods_dir, exist_ok=True) or self.store.mods_dir)))
        if g.nexus:
            m.addAction("Nexus Mods page", lambda: webbrowser.open(nexus.game_url(g.nexus)))
        if g.thunderstore:
            m.addAction("Thunderstore page", lambda: webbrowser.open(f"{thunderstore.SITE}/c/{g.thunderstore}/"))
        m.addSeparator()
        m.addAction("Turn all mods on", lambda: self.set_all(True))
        m.addAction("Turn all mods off", lambda: self.set_all(False))
        m.addAction("Put the mods in the game again", self.redeploy)
        m.addAction("Take every mod out of the game", self.purge)
        if g.adopt:
            m.addAction("Bring in mods already in the game", self.adopt_now)
        if g.thunderstore:
            m.addSeparator()
            m.addAction("Import an r2modman / Gale profile...", self.import_ts_profile)
            m.addAction("Share this profile as a code...", lambda: self.export_ts_profile(share=True))
            m.addAction("Export this profile (.r2z)...", lambda: self.export_ts_profile(share=False))
        m.addSeparator()
        m.addAction("Change game folder...", self.change_game_dir)
        m.addAction("Remove from Armory...", self.remove_game)

    def set_all(self, on):
        st = self.store
        st.profile["enabled"] = list(st.mods) if on else []
        st.save()
        self.changed()

    def redeploy(self):
        self.deploy()

    def purge(self):
        if QMessageBox.question(self, "Take mods out", f"Take every mod out of {self.game.name}? They stay in "
                                "Armory, turned on or off as they are; turn one on or off (or Play) to put "
                                "them back.") != QMessageBox.StandardButton.Yes:
            return
        st = self.store
        tasks.run(st.purge, lambda s: (self.say(f"Took {s['removed']} files out of the game"), self.refresh_header()),
                  lambda msg: QMessageBox.warning(self, "Couldn't", msg))

    # ---- r2modman / Gale profiles ----
    def import_ts_profile(self):
        g = self.game
        dlg = ImportProfileDialog(self)
        if not dlg.exec():
            return
        code, path = dlg.code.text().strip(), dlg.path
        os.makedirs(os.path.join(DATA, "tmp"), exist_ok=True)
        tmp = tempfile.mkdtemp(prefix="profile-", dir=os.path.join(DATA, "tmp"))
        self.say("Reading the profile...")

        def work():
            if path:
                if os.path.getsize(path) > 256 * 1024 * 1024:
                    raise ValueError("That file is too big to be a profile")
                data = open(path, "rb").read()
            else:
                data = thunderstore.code_profile(code)
            name, mods = thunderstore.read_r2z(data, tmp)
            pk = thunderstore.index(thunderstore.listing(g.thunderstore))
            return name, mods, pk

        def done(res):
            name, mods, pk = res
            self.apply_ts_profile(g, dlg.name.text().strip() or name or "Imported", mods, pk, tmp)

        def fail(msg):
            shutil.rmtree(tmp, ignore_errors=True)
            QMessageBox.warning(self, "Couldn't import the profile", msg)

        tasks.run(work, done, fail)

    def apply_ts_profile(self, g, name, mods, pk, tmp):
        st = self.store_for(g)
        base, n = name, 2
        while name in st.profiles:
            name = f"{base} ({n})"
            n += 1
        st.new_profile(name, copy=False)
        # the profile's config files: one mod at the bottom, so they win
        files = [(os.path.join(d, f), os.path.relpath(os.path.join(d, f), tmp).replace(os.sep, "/"))
                 for d, _, fs in os.walk(tmp) for f in fs]
        if files:
            st.add(f"{name} config", files, {"name": f"{name}: config files", "source": {"type": "local"},
                                              "summary": "Config files that came with the imported profile",
                                              "pin_bottom": True})
        shutil.rmtree(tmp, ignore_errors=True)
        queued, ready, missing = 0, 0, []
        for m in mods:
            full, ver, on = m["full"], m["version"], m["enabled"]
            have = st.find(thunderstore=full)
            if have and str(st.mods[have].get("version")) == ver:
                st.set_enabled(have, on)
                ready += 1
                continue
            p = pk.get(full.lower())
            owner, _, pname = full.partition("-")
            if not pname:
                missing.append(full)
                continue
            meta = {"name": (p or {}).get("name", pname).replace("_", " "), "version": ver, "author": owner,
                    "summary": (p or {}).get("desc", ""), "picture": (p or {}).get("icon", ""),
                    "source": {"type": "thunderstore", "full_name": full, "url": (p or {}).get("url", "")}}
            if have:
                meta["replace"] = have
            if not on:
                meta["disabled"] = True
            self.dl.add(thunderstore.download_url(owner, pname, ver), f"{full}-{ver}.zip", g.id, meta)
            queued += 1
        self.fill_profiles()
        self.changed()
        self.say(f"Profile {name}: {ready} mods ready, {queued} downloading" +
                 (f", {len(missing)} not understood" if missing else ""))

    def export_ts_profile(self, share):
        g, st = self.game, self.store
        mods = []
        for m in st.ordered():
            s = m.get("source") or {}
            if s.get("type") == "thunderstore" and s.get("full_name"):
                mods.append({"full": s["full_name"], "version": m.get("version") or "0.0.0", "enabled": m["enabled"]})
        if not mods:
            QMessageBox.information(self, "Nothing to export", "This profile has no Thunderstore mods.")
            return
        files = []
        cfg = resolve_case(g.path, "BepInEx/config") if g.found else ""
        if cfg and os.path.isdir(cfg):
            total = 0
            for d, _, fs in os.walk(cfg):
                for f in fs:
                    p = os.path.join(d, f)
                    total += os.path.getsize(p)
                    if total > 50 * 1024 * 1024:
                        break
                    files.append((p, "BepInEx/config/" + os.path.relpath(p, cfg).replace(os.sep, "/")))
        data = thunderstore.make_r2z(st.active, mods, files)
        if not share:
            path, _ = QFileDialog.getSaveFileName(self, "Export profile", os.path.join(HOME, f"{st.active}.r2z"),
                                                  "r2modman profile (*.r2z)")
            if path:
                with open(path, "wb") as f:
                    f.write(data)
                self.say(f"Exported {len(mods)} mods to {os.path.basename(path)}")
            return
        if QMessageBox.question(self, "Share as a code", f"Upload this profile ({len(mods)} mods and your BepInEx "
                                "config files) to Thunderstore? Anyone with the code can import it.") \
                != QMessageBox.StandardButton.Yes:
            return

        def done(key):
            QApplication.clipboard().setText(key)
            box = QMessageBox(self)
            box.setWindowTitle("Profile code")
            box.setText(f"Copied to the clipboard:\n\n{key}\n\nFriends paste it in r2modman, Gale or Armory "
                        "(Import a profile).")
            box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.exec()

        tasks.run(lambda: thunderstore.share_profile(data), done,
                  lambda msg: QMessageBox.warning(self, "Couldn't share it", msg))

    def adopt_now(self):
        try:
            names = self.store.adopt(self.game.adopt)
        except OSError as e:
            QMessageBox.warning(self, "Couldn't", str(e))
            return
        self.say(f"Brought in {len(names)} mods" if names else "No other mods in the game")
        if names:
            self.changed()

    def change_game_dir(self):
        g = self.game
        d = QFileDialog.getExistingDirectory(self, f"{g.name}'s folder", g.path or HOME)
        if not d:
            return
        if not games.proof_ok(d, g.spec) and QMessageBox.question(
                self, "Is that the game?", f"{g.spec.get('proof')} isn't in that folder. Use it anyway?") \
                != QMessageBox.StandardButton.Yes:
            return
        if g.custom:
            spec = dict(games.custom_games().get(g.id, {}), path=d)
            games.save_custom_game(g.id, spec)
        else:
            games.set_game_dir(g.id, d)
        self.stores.pop(g.id, None)
        self.load_games(g.id)

    def remove_game(self):
        g = self.game
        box = QMessageBox(self)
        box.setWindowTitle("Remove game")
        box.setText(f"Remove {g.name} from Armory? Its mods are taken out of the game. They stay kept, so adding "
                    "the game again brings them back.")
        ok = box.addButton("Remove", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not ok:
            return
        try:
            if g.found:
                self.store.purge()
        except (OSError, DeployError) as e:
            QMessageBox.warning(self, "Couldn't take the mods out", str(e))
            return
        games.remove_game(g.id)
        self.stores.pop(g.id, None)
        self.game = None
        self.load_games()

    def add_game(self):
        dlg = AddGameDialog(self, [g.id for g in self.games])
        if dlg.exec() and dlg.result_id:
            self.load_games(dlg.result_id)

    def retheme(self):
        """the theme changed: new colours everywhere, keeping what's on screen"""
        T.apply(QApplication.instance())
        self.main.update()
        self.load_games(self.game.id if self.game else None)
        self.downloads_page.refresh()
        self.browse_page.refresh_tiles()
        self.account_changed()
        self.update()

    def settings(self, tab="nexus"):
        SettingsDialog(self, tab).exec()
        self.account_changed()

    # ---- links and files from outside ----
    def handle_args(self, args):
        files = []
        for a in args:
            if a.lower().startswith("nxm://"):
                self.handle_nxm(a)
            elif a.lower().startswith("ror2mm://"):
                self.handle_ror2mm(a)
            elif os.path.exists(a):
                files.append(os.path.abspath(a))
        if files:
            self.raise_()
            self.activateWindow()
            self.install_paths(files)

    # ---- window ----
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.overlay.setGeometry(self.centralWidget().rect())
        if self.toast.isVisible():
            self.toast.place()

    def closeEvent(self, e):
        config.save_conf(window_size=[self.width(), self.height()])
        super().closeEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and self.game:
            e.acceptProposedAction()
            self.overlay.text = f"Mods for {self.game.name}: .zip, .7z, .rar, or a folder"
            self.overlay.setGeometry(self.centralWidget().rect())
            self.overlay.raise_()
            self.overlay.show()

    def dragLeaveEvent(self, _e):
        self.overlay.hide()

    def dropEvent(self, e):
        self.overlay.hide()
        self.install_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])


def links_ready(scheme):
    from .. import links
    return links.is_ours(scheme)
