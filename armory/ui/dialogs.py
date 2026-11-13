"""Settings (Nexus account, links, deploying), adding games, the FOMOD wizard, picking a Nexus
file, and a mod's files and conflicts."""
import os
import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
                             QGridLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QRadioButton,
                             QScrollArea, QSpinBox, QStackedWidget, QTextBrowser, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

from .. import config, games, links, nexus, oauth
from ..config import human
from . import tasks, theme
from .theme import Segments, button, label, rounded


def frame(name="panel"):
    f = QFrame()
    f.setObjectName(name)
    return f


class SettingsDialog(QDialog):
    def __init__(self, window, tab="nexus"):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Armory settings")
        self.setMinimumSize(660, 700)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(14)
        v.addWidget(label("Settings", "title"))
        self.segs = Segments([("appearance", "Appearance"), ("nexus", "Nexus Mods"), ("links", "Links"),
                              ("deploy", "Installing"), ("browse", "Browse")], self.show_tab, tab)
        v.addWidget(self.segs, 0, Qt.AlignmentFlag.AlignLeft)
        self.stack = QStackedWidget()
        self.pages = {}
        for key, build in (("appearance", self.build_appearance), ("nexus", self.build_nexus),
                           ("links", self.build_links), ("deploy", self.build_deploy), ("browse", self.build_browse)):
            w = QWidget()
            build(w)
            self.pages[key] = self.stack.addWidget(w)
        v.addWidget(self.stack, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Done", self.accept, "primary"))
        v.addLayout(row)
        self.show_tab(tab)

    def done(self, r):
        self.oauth_stop()
        super().done(r)

    def show_tab(self, key):
        self.segs.set(key)
        self.stack.setCurrentIndex(self.pages[key])
        if key == "links":
            self.refresh_links()

    # -- appearance --
    def build_appearance(self, w):
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(12)
        v.addWidget(label("Theme", "h2"))
        grid = QGridLayout()
        grid.setSpacing(10)
        self.swatches = {}
        group = QButtonGroup(self)
        current = config.get("theme", "armory")
        for i, (key, t) in enumerate(theme.THEMES.items()):
            sw = ThemeSwatch(key, t)
            sw.setChecked(key == current)
            sw.clicked.connect(lambda _=False, k=key: self.pick_theme(k))
            group.addButton(sw)
            grid.addWidget(sw, i // 3, i % 3)
            self.swatches[key] = sw
        v.addLayout(grid)

        box = frame()
        f = QVBoxLayout(box)
        f.setContentsMargins(16, 14, 16, 14)
        f.setSpacing(10)
        row = QHBoxLayout()
        t = QVBoxLayout()
        t.addWidget(label("Accent colour", "h2"))
        self.accent_note = label("", "muted", True)
        t.addWidget(self.accent_note)
        row.addLayout(t, 1)
        row.addWidget(button("Choose...", self.pick_accent))
        self.accent_reset = button("Theme's own", lambda: self.set_accent(""))
        row.addWidget(self.accent_reset)
        f.addLayout(row)
        self.anim = QCheckBox("Animations (fades, sliding highlights)")
        self.anim.setChecked(config.get("animations", True) is not False)
        self.anim.toggled.connect(lambda on: config.save_conf(animations=on))
        f.addWidget(self.anim)
        self.ambient = QCheckBox("Show the game's artwork behind the page")
        self.ambient.setChecked(config.get("ambient", True))
        self.ambient.toggled.connect(self.toggle_ambient)
        f.addWidget(self.ambient)
        v.addWidget(box)
        v.addStretch(1)
        self.refresh_accent()

    def refresh_accent(self):
        acc = config.get("accent", "")
        self.accent_note.setText(f"Your own: {acc}" if acc else "The theme's own colour, used for buttons, "
                                 "switches and highlights.")
        self.accent_reset.setVisible(bool(acc))

    def pick_theme(self, key):
        config.save_conf(theme=key)
        self.window.retheme()
        for k, sw in self.swatches.items():
            sw.setChecked(k == key)

    def pick_accent(self):
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(theme.ACCENT), self, "Accent colour")
        if c.isValid():
            self.set_accent(c.name())

    def set_accent(self, color):
        config.save_conf(accent=color)
        self.window.retheme()
        self.refresh_accent()
        for sw in self.swatches.values():
            sw.update()

    def toggle_ambient(self, on):
        config.save_conf(ambient=on)
        self.window.main.update()

    # -- Nexus --
    def build_nexus(self, w):
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(12)
        box = frame()
        b = QVBoxLayout(box)
        b.setContentsMargins(16, 14, 16, 14)
        b.setSpacing(10)
        top = QHBoxLayout()
        self.avatar = label("")
        self.avatar.setFixedSize(48, 48)
        top.addWidget(self.avatar)
        who = QVBoxLayout()
        self.who = label("Not logged in", "h2")
        self.who_sub = label("", "muted", True)
        who.addWidget(self.who)
        who.addWidget(self.who_sub)
        top.addLayout(who, 1)
        self.logout_btn = button("Log out", self.logout)
        top.addWidget(self.logout_btn, 0, Qt.AlignmentFlag.AlignTop)
        b.addLayout(top)
        v.addWidget(box)

        self.oauth_box = frame()
        ob = QVBoxLayout(self.oauth_box)
        ob.setContentsMargins(16, 14, 16, 14)
        ob.setSpacing(10)
        ob.addWidget(label("Sign in with your Nexus Mods account", "h2"))
        ob.addWidget(label("Opens the Nexus sign-in page in your browser. Armory never sees your password; "
                           "Nexus gives it a token that's kept in your desktop's keyring.", "muted", True))
        orow = QHBoxLayout()
        self.oauth_btn = button("Sign in with Nexus Mods", self.oauth_login, "primary")
        orow.addWidget(self.oauth_btn)
        self.oauth_cancel = button("Cancel", self.oauth_stop)
        self.oauth_cancel.hide()
        orow.addWidget(self.oauth_cancel)
        orow.addStretch(1)
        ob.addLayout(orow)
        self.oauth_msg = label("", "muted", True)
        ob.addWidget(self.oauth_msg)
        v.addWidget(self.oauth_box)
        self.oauth_box.setVisible(oauth.available())

        self.login_box = frame()
        lb = QVBoxLayout(self.login_box)
        lb.setContentsMargins(16, 14, 16, 14)
        lb.setSpacing(10)
        lb.addWidget(label("Or log in with your personal API key" if oauth.available()
                           else "Log in with your personal API key", "h2"))
        lb.addWidget(label("Open the API keys page, copy your Personal API Key at the bottom, and paste it here. "
                           "It's kept in your desktop's keyring (or, without one, in a file only you can read). "
                           "Anyone with this key can use your Nexus account through the API: don't share it, "
                           "and you can make a new one on that page at any time." +
                           ("" if oauth.available() else "\n\nOne-click sign-in comes once Nexus Mods has "
                            "registered Armory as an app."), "muted", True))
        row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("Personal API key")
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.returnPressed.connect(self.login)
        row.addWidget(self.key_edit, 1)
        self.login_btn = button("Log in", self.login, "primary")
        row.addWidget(self.login_btn)
        lb.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(button("Open the API keys page", lambda: webbrowser.open(nexus.KEY_PAGE)))
        row2.addStretch(1)
        lb.addLayout(row2)
        self.login_msg = label("", "muted", True)
        lb.addWidget(self.login_msg)
        v.addWidget(self.login_box)

        how = frame()
        hb = QVBoxLayout(how)
        hb.setContentsMargins(16, 14, 16, 14)
        hb.addWidget(label("Downloading from Nexus", "h2"))
        hb.addWidget(label("Free accounts: press “Mod Manager Download” (or “Download with Manager”) on a mod's "
                           "Files tab and Armory downloads and installs it. That needs Armory to open nxm:// links "
                           "(Settings → Links). Premium accounts can also download from Browse and update mods "
                           "with one click.\n\nGames without that button: use Manual download and drop the file "
                           "on Armory.", "muted", True))
        v.addWidget(how)
        v.addStretch(1)
        self.refresh_account()

    def refresh_account(self):
        nx = self.window.nexus
        u = nx.user
        how = "signed in through Nexus" if oauth.signed_in() else "API key"
        if nx.logged_in and u:
            self.who.setText(u.get("name", "Logged in"))
            kind = "Premium" if nx.premium else "Supporter" if u.get("is_supporter") else "Free account"
            self.who_sub.setText(f"{kind}  ·  {how}")
            tasks.set_picture(self.avatar, u.get("profile_url"), 48, 48, u.get("name", ""), 24)
            self.logout_btn.show()
            self.login_box.hide()
            self.oauth_box.hide()
        elif nx.logged_in:
            self.who.setText("Checking your login...")
            self.who_sub.setText("")
            self.logout_btn.show()
            self.login_box.hide()
            self.oauth_box.hide()
        else:
            self.oauth_box.setVisible(oauth.available())
            self.who.setText("Not logged in")
            self.who_sub.setText("Log in to download with the Mod Manager button, check for updates and endorse mods.")
            tasks.set_picture(self.avatar, None, 48, 48, "?", 24)
            self.logout_btn.hide()
            self.login_box.show()

    def login(self):
        key = self.key_edit.text().strip()
        if not key:
            return
        self.login_btn.setEnabled(False)
        self.login_msg.setText("Checking...")
        nx = nexus.Nexus(key)

        def done(user):
            where = config.set_nexus_key(key)
            self.window.set_nexus(nx)
            self.key_edit.clear()
            self.login_msg.setText("" if where == "keyring" else
                                   "No desktop keyring found: the key is in ~/.config/armory/nexus.json (only you "
                                   "can read it).")
            self.login_btn.setEnabled(True)
            self.refresh_account()

        def fail(msg):
            self.login_btn.setEnabled(True)
            self.login_msg.setText("That key didn't work: " + msg)

        tasks.run(nx.validate, done, fail)

    def logout(self):
        config.set_nexus_key("")
        tasks.run(oauth.logout)
        self.window.set_nexus(nexus.Nexus(""))
        self.refresh_account()

    def oauth_login(self):
        import webbrowser as wb
        run, self._oauth_cancel = oauth.threading_login(wb.open)
        self.oauth_btn.setEnabled(False)
        self.oauth_cancel.show()
        self.oauth_msg.setText("Finish signing in in your browser...")

        def done(_tokens):
            self.oauth_btn.setEnabled(True)
            self.oauth_cancel.hide()
            self.oauth_msg.setText("")
            nx = nexus.Nexus("")
            self.window.set_nexus(nx)
            tasks.run(nx.validate, lambda _: (self.window.account_changed(), self.refresh_account()),
                      lambda m: self.oauth_msg.setText("Signed in, but Nexus didn't answer: " + m))
            self.refresh_account()

        def fail(msg):
            self.oauth_btn.setEnabled(True)
            self.oauth_cancel.hide()
            self.oauth_msg.setText(msg)

        tasks.run(run, done, fail)

    def oauth_stop(self):
        if getattr(self, "_oauth_cancel", None):
            self._oauth_cancel()

    # -- links --
    def build_links(self, w):
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(12)
        v.addWidget(label("When you press a mod manager button on a website, your desktop opens a link with "
                          "the app set for that kind of link. Armory only takes them over when you ask.", "muted", True))
        self.link_rows = {}
        for scheme, what in links.SCHEMES.items():
            box = frame()
            b = QHBoxLayout(box)
            b.setContentsMargins(16, 12, 12, 12)
            t = QVBoxLayout()
            t.addWidget(label(what, "h2"))
            st = label("", "muted", True)
            t.addWidget(st)
            b.addLayout(t, 1)
            use = button("Open them with Armory", lambda _=False, s=scheme: self.take(s), "primary")
            stop = button("Stop", lambda _=False, s=scheme: self.release(s))
            b.addWidget(use)
            b.addWidget(stop)
            self.link_rows[scheme] = (st, use, stop)
            v.addWidget(box)
        v.addStretch(1)

    def refresh_links(self):
        for scheme, (st, use, stop) in self.link_rows.items():
            name = links.handler_name(scheme)
            ours = links.is_ours(scheme)
            st.setText(f"{scheme}:// links open with: {name}")
            use.setVisible(not ours)
            stop.setVisible(ours)

    def take(self, scheme):
        other = links.handler_name(scheme)
        if other not in ("nothing", "Armory"):
            if QMessageBox.question(self, "Open these links with Armory?",
                                    f"{other} opens {scheme}:// links now. Armory will open them instead "
                                    "(you can switch back in that app).") != QMessageBox.StandardButton.Yes:
                return
        links.register([scheme])
        self.refresh_links()

    def release(self, scheme):
        links.unregister(scheme)
        self.refresh_links()

    # -- installing --
    def build_deploy(self, w):
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(12)
        box = frame()
        f = QFormLayout(box)
        f.setContentsMargins(16, 14, 16, 14)
        f.setSpacing(12)
        self.method = QComboBox()
        for key, text in (("hardlink", "Hard links (fast, no extra space)"), ("symlink", "Symbolic links"),
                          ("copy", "Copies (uses more space)")):
            self.method.addItem(text, key)
        self.method.setCurrentIndex(max(0, self.method.findData(config.get("deploy_method", "hardlink"))))
        self.method.currentIndexChanged.connect(lambda: config.save_conf(deploy_method=self.method.currentData()))
        f.addRow(label("Put mods in games as"), self.method)
        self.auto = QCheckBox("Install downloads as soon as they finish")
        self.auto.setChecked(config.get("auto_install", True))
        self.auto.toggled.connect(lambda on: config.save_conf(auto_install=on))
        f.addRow(self.auto)
        self.scan = QCheckBox("Scan mods with ClamAV before installing them")
        from ..layout import scanner
        has_clam = bool(scanner())
        self.scan.setChecked(config.get("scan_mods", False) and has_clam)
        self.scan.setEnabled(has_clam)
        self.scan.setToolTip("" if has_clam else "Install ClamAV (clamav package) to use this")
        self.scan.toggled.connect(lambda on: config.save_conf(scan_mods=on))
        f.addRow(self.scan)
        if not has_clam:
            f.addRow(label("ClamAV isn't installed: install the clamav package to scan mods", "small", True))
        self.watch = QCheckBox("Offer to install archives that land in the Downloads folder")
        self.watch.setChecked(config.get("watch_downloads", True))
        self.watch.toggled.connect(lambda on: (config.save_conf(watch_downloads=on), self.window.watch_downloads()))
        f.addRow(self.watch)
        self.upd = QCheckBox("Check GitHub for Armory updates once a day")
        self.upd.setToolTip("Only asks GitHub for the newest release; nothing about you or your mods is sent")
        self.upd.setChecked(config.get("check_updates", True))
        self.upd.toggled.connect(lambda on: config.save_conf(check_updates=on))
        urow = QHBoxLayout()
        urow.addWidget(self.upd, 1)
        urow.addWidget(button("Check now", lambda: self.window.check_armory_update(quiet=False)))
        f.addRow(urow)
        self.limit = QSpinBox()
        self.limit.setRange(1, 2000)
        self.limit.setSuffix(" GB")
        self.limit.setValue(int(config.get("max_unpack_gb", 100) or 100))
        self.limit.valueChanged.connect(lambda v: config.save_conf(max_unpack_gb=v))
        f.addRow(label("Largest a mod may unpack to"), self.limit)
        self.keep = QCheckBox("Keep downloaded files (to reinstall without downloading again)")
        self.keep.setChecked(config.get("keep_downloads", True))
        self.keep.toggled.connect(lambda on: config.save_conf(keep_downloads=on))
        f.addRow(self.keep)
        v.addWidget(box)
        v.addWidget(label("Mods are kept apart from the games in ~/.local/share/armory and put in a game's folder "
                          "when they're on. Hard links need the mods and the game on the same drive; elsewhere "
                          "Armory copies them. Files a mod replaces are backed up and put back when it's off.",
                          "muted", True))
        v.addStretch(1)

    # -- browse --
    def build_browse(self, w):
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(12)
        box = frame()
        f = QVBoxLayout(box)
        f.setContentsMargins(16, 14, 16, 14)
        self.adult = QCheckBox("Show adult (NSFW) mods in Browse")
        self.adult.setChecked(config.get("browse_adult", False))
        self.adult.toggled.connect(lambda on: config.save_conf(browse_adult=on))
        f.addWidget(self.adult)
        v.addWidget(box)
        v.addStretch(1)


class CollectionDialog(QDialog):
    """the mods of a Nexus collection: pick which to install (optional ones start unticked)"""
    def __init__(self, parent, c, store):
        super().__init__(parent)
        self.c = c
        self.setWindowTitle(c["name"])
        self.resize(640, 620)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(10)
        v.addWidget(label(c["name"], "title"))
        if c.get("summary"):
            v.addWidget(label(c["summary"], "muted", True))
        have = {(int((m.get("source") or {}).get("mod_id") or 0), int((m.get("source") or {}).get("file_id") or 0))
                for m in store.mods.values() if (m.get("source") or {}).get("type") == "nexus"}
        self.list = QListWidget()
        self.list.setObjectName("plain")
        for f in c["files"]:
            installed = (f["mod_id"], f["file_id"]) in have
            it = QListWidgetItem(f"{f['name']}   ·   {f['file_name']} v{f['version'] or '?'}"
                                 + ("   ·   optional" if f["optional"] else "")
                                 + ("   ·   installed" if installed else ""))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked if f["optional"] else Qt.CheckState.Checked)
            it.setData(Qt.ItemDataRole.UserRole, f)
            self.list.addItem(it)
        v.addWidget(label(f"Revision {c.get('revision')}  ·  {len(c['files'])} mods", "small"))
        v.addWidget(self.list, 1)
        self.new_profile = QCheckBox("Install into a new profile named after the collection")
        self.new_profile.setChecked(True)
        v.addWidget(self.new_profile)
        v.addWidget(label("Mods with an installer (FOMOD) ask their questions as they arrive. Collections can also "
                          "carry extra steps (patches, preset choices) that Armory doesn't apply.", "small", True))
        r = QHBoxLayout()
        r.addStretch(1)
        r.addWidget(button("Cancel", self.reject))
        r.addWidget(button("Install", self.accept, "primary"))
        v.addLayout(r)

    def chosen(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]


class ImportProfileDialog(QDialog):
    """a profile code, or an .r2z file, from r2modman or Gale"""
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Import a profile")
        self.setMinimumWidth(520)
        self.path = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(10)
        v.addWidget(label("Import a profile", "title"))
        v.addWidget(label("Paste a profile code from r2modman or Gale (Export → as code), or pick an exported "
                          ".r2z file. It becomes a new profile here, with the same mods, versions and config "
                          "files.", "muted", True))
        self.code = QLineEdit()
        self.code.setPlaceholderText("Profile code, like 018f2a6e-...")
        v.addWidget(self.code)
        row = QHBoxLayout()
        self.file_note = label("", "small")
        row.addWidget(button("Or pick a file...", self.pick))
        row.addWidget(self.file_note, 1)
        v.addLayout(row)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name for the new profile (optional)")
        v.addWidget(self.name)
        r = QHBoxLayout()
        r.addStretch(1)
        r.addWidget(button("Cancel", self.reject))
        r.addWidget(button("Import", self.ok, "primary"))
        v.addLayout(r)

    def pick(self):
        p, _ = QFileDialog.getOpenFileName(self, "Profile file", config.HOME, "Profiles (*.r2z *.zip);;All files (*)")
        if p:
            self.path = p
            self.file_note.setText(os.path.basename(p))
            self.code.clear()

    def ok(self):
        if self.code.text().strip() or self.path:
            self.accept()


class ThemeSwatch(QPushButton):
    """a small picture of a theme: its background, sidebar, a card and the accent"""
    def __init__(self, key, t):
        super().__init__()
        self.key, self.t = key, t
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(92)
        self.setMinimumWidth(180)
        self.setToolTip(t["label"])
        self.setStyleSheet("QPushButton { background: transparent; border: none; padding: 0; }")

    def paintEvent(self, _e):
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.setClipPath(path)
        p.fillRect(r, QColor(self.t["bg"]))
        p.fillRect(QRectF(r.left(), r.top(), r.width() * 0.28, r.height()), QColor(self.t["panel"]))
        fg = QColor(0, 0, 0, 18) if self.t.get("light") else QColor(255, 255, 255, 14)
        for i in range(2):
            card = QRectF(r.left() + r.width() * 0.33, r.top() + 12 + i * 24, r.width() * 0.6, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fg)
            p.drawRoundedRect(card, 5, 5)
        custom = config.get("accent") if self.key == config.get("theme", "armory") else ""
        acc = QColor(custom or self.t["accent"])
        p.setBrush(acc)
        p.drawRoundedRect(QRectF(r.right() - 40, r.top() + 15, 22, 12), 6, 6)
        p.drawRoundedRect(QRectF(r.left() + 8, r.top() + 12, r.width() * 0.28 - 16, 8), 4, 4)
        p.setClipping(False)
        f = QFont()
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(self.t["text"]))
        p.drawText(QRectF(r.left() + r.width() * 0.33, r.bottom() - 26, r.width() * 0.6, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.t["label"])
        pen = QPen(QColor(theme.ACCENT) if self.isChecked() else QColor(128, 128, 140, 70), 2.5 if self.isChecked() else 1)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 12, 12)


class AddGameDialog(QDialog):
    def __init__(self, window, listed):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Add a game")
        self.resize(620, 600)
        self.result_id = None
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(12)
        v.addWidget(label("Add a game", "title"))
        self.segs = Segments([("known", "Supported games"), ("custom", "Another game")], self.show_tab)
        v.addWidget(self.segs, 0, Qt.AlignmentFlag.AlignLeft)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)

        known = QWidget()
        kv = QVBoxLayout(known)
        kv.setContentsMargins(0, 0, 0, 0)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Search")
        self.filter.textChanged.connect(self.fill)
        kv.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setObjectName("plain")
        self.list.itemDoubleClicked.connect(lambda _: self.add_known())
        kv.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(label("Games found in Steam are listed by themselves. Add one that's somewhere else and "
                            "pick its folder.", "small", True), 1)
        row.addWidget(button("Add", self.add_known, "primary"))
        kv.addLayout(row)
        self.stack.addWidget(known)
        self.listed = set(listed)
        self.fill()

        custom = QWidget()
        f = QFormLayout(custom)
        f.setContentsMargins(0, 8, 0, 0)
        f.setSpacing(10)
        self.c_name = QLineEdit()
        f.addRow("Name", self.c_name)
        prow = QHBoxLayout()
        self.c_path = QLineEdit()
        prow.addWidget(self.c_path, 1)
        prow.addWidget(button("Browse...", self.pick_path))
        f.addRow("Game folder", prow)
        self.c_layout = QComboBox()
        for key, (text, _) in games.LAYOUT_PRESETS.items():
            self.c_layout.addItem(text, key)
        self.c_layout.setCurrentIndex(self.c_layout.findData("root"))
        f.addRow("Mods go", self.c_layout)
        self.c_sub = QLineEdit()
        self.c_sub.setPlaceholderText("optional, e.g. Mods  (for “Into the game folder”)")
        f.addRow("Mods folder", self.c_sub)
        self.c_appid = QSpinBox()
        self.c_appid.setRange(0, 99999999)
        self.c_appid.setSpecialValueText("none")
        f.addRow("Steam app id", self.c_appid)
        self.c_nexus = QLineEdit()
        self.c_nexus.setPlaceholderText("optional: the name in nexusmods.com/<name>/mods")
        f.addRow("Nexus Mods game", self.c_nexus)
        self.c_ts = QLineEdit()
        self.c_ts.setPlaceholderText("optional: the name in thunderstore.io/c/<name>")
        f.addRow("Thunderstore", self.c_ts)
        self.c_launch = QLineEdit()
        self.c_launch.setPlaceholderText("optional: a command (otherwise Steam starts it)")
        f.addRow("Launch with", self.c_launch)
        f.addRow(button("Add this game", self.add_custom, "primary"))
        self.stack.addWidget(custom)

    def show_tab(self, key):
        self.stack.setCurrentIndex(0 if key == "known" else 1)

    def fill(self):
        self.list.clear()
        q = self.filter.text().strip().lower()
        for gid, spec in sorted(games.GAMES.items(), key=lambda kv: kv[1]["name"].lower()):
            if gid in self.listed or (q and q not in spec["name"].lower()):
                continue
            g = games.make_game(gid, spec)
            extras = [x for x in ("Nexus" if spec.get("nexus") else "", "Thunderstore" if spec.get("thunderstore") else "") if x]
            it = QListWidgetItem(f"{spec['name']}    —  {'installed' if g.found else 'not found'}"
                                 f"{'  ·  ' + ', '.join(extras) if extras else ''}")
            it.setData(Qt.ItemDataRole.UserRole, gid)
            self.list.addItem(it)

    def add_known(self):
        it = self.list.currentItem()
        if not it:
            return
        gid = it.data(Qt.ItemDataRole.UserRole)
        g = games.make_game(gid)
        if not g.found:
            d = QFileDialog.getExistingDirectory(self, f"{g.name}'s folder", config.HOME)
            if not d:
                return
            if not games.proof_ok(d, g.spec):
                if QMessageBox.question(self, "Is that the game?",
                                        f"{g.spec.get('proof')} isn't in that folder. Use it anyway?") \
                        != QMessageBox.StandardButton.Yes:
                    return
            games.set_game_dir(gid, d)
        games.add_game(gid)
        self.result_id = gid
        self.accept()

    def pick_path(self):
        d = QFileDialog.getExistingDirectory(self, "Game folder", self.c_path.text() or config.HOME)
        if d:
            self.c_path.setText(d)
            if not self.c_name.text():
                self.c_name.setText(os.path.basename(d))

    def add_custom(self):
        name, path = self.c_name.text().strip(), self.c_path.text().strip()
        if not name or not os.path.isdir(path):
            QMessageBox.warning(self, "Missing", "Give it a name and its folder.")
            return
        preset = dict(games.LAYOUT_PRESETS[self.c_layout.currentData()][1])
        sub = self.c_sub.text().strip().strip("/")
        if sub and self.c_layout.currentData() == "root":
            preset = {"root_markers": [], "default": sub + "/{name}"}
        gid = "custom-" + config.slug(name).lower()
        spec = {"name": name, "path": path, "layout": preset, "appid": self.c_appid.value() or 0,
                "nexus": self.c_nexus.text().strip().lower(), "thunderstore": self.c_ts.text().strip().lower(),
                "launch": self.c_launch.text().strip()}
        games.save_custom_game(gid, spec)
        self.result_id = gid
        self.accept()


class FomodWizard(QDialog):
    """steps through a FOMOD installer; .files is the result when accepted"""
    def __init__(self, parent, fomod, installed=()):
        super().__init__(parent)
        self.fm = fomod
        self.installed = {i.lower() for i in installed}
        self.setWindowTitle(f"Install {fomod.name or 'mod'}")
        self.resize(820, 600)
        self.selections = {}
        self.history = []
        self.files = None
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(12)
        self.title = label(fomod.name or "Installer", "title")
        v.addWidget(self.title)
        self.step_label = label("", "muted")
        v.addWidget(self.step_label)
        body = QHBoxLayout()
        body.setSpacing(14)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        body.addWidget(self.scroll, 3)
        side = QVBoxLayout()
        self.image = label("")
        self.image.setFixedSize(300, 170)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(self.image)
        self.desc = QTextBrowser()
        side.addWidget(self.desc, 1)
        body.addLayout(side, 2)
        v.addLayout(body, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.back = button("Back", self.go_back)
        self.next = button("Next", self.go_next, "primary")
        row.addWidget(button("Cancel", self.reject))
        row.addWidget(self.back)
        row.addWidget(self.next)
        v.addLayout(row)
        self.index = 0
        self.show_step()

    def steps(self):
        return self.fm.visible_steps(self.fm.flags_for(self.selections), self.installed)

    def show_step(self):
        steps = self.steps()
        if not steps:
            self.finish()
            return
        self.index = min(self.index, len(steps) - 1)
        step = steps[self.index]
        self.step_label.setText(f"Step {self.index + 1} of {len(steps)}  ·  {step['name']}")
        self.back.setEnabled(self.index > 0)
        self.next.setText("Install" if self.index == len(steps) - 1 else "Next")
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setSpacing(12)
        self.controls = []
        flags = self.fm.flags_for(self.selections)
        first_desc = None
        for g in step["groups"]:
            key = (step["name"], g["name"])
            box = frame()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(14, 10, 14, 10)
            bl.addWidget(label(g["name"], "h2"))
            single = g["type"] in ("SelectExactlyOne", "SelectAtMostOne")
            group = QButtonGroup(box) if single else None
            if group is not None and g["type"] == "SelectAtMostOne":
                group.setExclusive(False)
            prev = [p["name"] for p in self.selections.get(key, [])]
            widgets = []
            for p in g["plugins"]:
                t = self.fm.plugin_type(p, flags, self.installed)
                w = QRadioButton(p["name"]) if single else QCheckBox(p["name"])
                if group is not None:
                    group.addButton(w)
                if t == "NotUsable":
                    w.setEnabled(False)
                    w.setToolTip("Not usable with what you have")
                checked = p["name"] in prev if key in self.selections else t in ("Required", "Recommended")
                if g["type"] == "SelectAll" or t == "Required":
                    checked = True
                    w.setEnabled(False)
                w.setChecked(checked)
                w.installEventFilter(self)
                w.setProperty("plugin_desc", p["desc"])
                w.setProperty("plugin_image", p["image"])
                if g["type"] == "SelectAtMostOne":
                    w.toggled.connect(lambda on, me=w, ws=widgets: on and [o.setChecked(False) for o in ws if o is not me])
                bl.addWidget(w)
                widgets.append(w)
                first_desc = first_desc or p
            if single and g["type"] == "SelectExactlyOne" and not any(w.isChecked() for w in widgets):
                usable = [w for w in widgets if w.isEnabled()]
                if usable:
                    usable[0].setChecked(True)
            self.controls.append((key, g, widgets))
            lay.addWidget(box)
        lay.addStretch(1)
        self.scroll.setWidget(holder)
        if first_desc:
            self.describe(first_desc["desc"], first_desc["image"])

    def eventFilter(self, obj, ev):
        if ev.type() == ev.Type.Enter:
            self.describe(obj.property("plugin_desc") or "", obj.property("plugin_image") or "")
        return False

    def describe(self, text, image):
        self.desc.setPlainText(text or "")
        path = self.fm.image(image) if image else None
        pix = QPixmap(path) if path else QPixmap()
        if pix.isNull():
            self.image.clear()
        else:
            self.image.setPixmap(rounded(pix, 300, 170))

    def save_step(self):
        for key, g, widgets in self.controls:
            chosen = [p for p, w in zip(g["plugins"], widgets) if w.isChecked()]
            if g["type"] == "SelectAtLeastOne" and not chosen:
                QMessageBox.warning(self, "Pick one", f"Choose at least one option in “{g['name']}”.")
                return False
            self.selections[key] = chosen
        return True

    def go_next(self):
        if not self.save_step():
            return
        steps = self.steps()
        if self.index >= len(steps) - 1:
            self.finish()
        else:
            self.index += 1
            self.show_step()

    def go_back(self):
        self.save_step()
        self.index = max(0, self.index - 1)
        self.show_step()

    def finish(self):
        self.files = self.fm.files(self.selections, self.installed)
        if not self.files:
            QMessageBox.warning(self, "Nothing to install", "Those choices don't install any files.")
            self.files = None
            return
        self.accept()


class NexusFilesDialog(QDialog):
    """pick which file of a Nexus mod to download"""
    def __init__(self, parent, title, files, current=None):
        super().__init__(parent)
        self.setWindowTitle(f"Download {title}")
        self.resize(700, 480)
        self.choice = None
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.addWidget(label(title, "title"))
        v.addWidget(label("Pick a file. Main files are the mod itself; optional files add to it.", "muted"))
        self.list = QListWidget()
        self.list.setObjectName("plain")
        order = {"MAIN": 0, "UPDATE": 1, "OPTIONAL": 2, "MISCELLANEOUS": 3, "OLD_VERSION": 4, "ARCHIVED": 5}
        files = sorted(files, key=lambda f: (order.get(f.get("category_name"), 9), -f.get("uploaded_timestamp", 0)))
        for f in files:
            if f.get("category_name") in ("ARCHIVED", "DELETED"):
                continue
            cat = (f.get("category_name") or "").replace("_", " ").title()
            it = QListWidgetItem(f"{f.get('name')}   v{f.get('version') or '?'}   ·   {cat}   ·   "
                                 f"{human((f.get('size_kb') or 0) * 1024)}")
            it.setToolTip((f.get("description") or "").replace("<br />", "\n"))
            it.setData(Qt.ItemDataRole.UserRole, f)
            self.list.addItem(it)
            if (current and f["file_id"] == current) or (not current and self.list.currentRow() < 0
                                                         and f.get("category_name") == "MAIN"):
                self.list.setCurrentItem(it)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _: self.ok())
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Cancel", self.reject))
        row.addWidget(button("Download", self.ok, "primary"))
        v.addLayout(row)

    def ok(self):
        it = self.list.currentItem()
        if it:
            self.choice = it.data(Qt.ItemDataRole.UserRole)
            self.accept()


class ModDetailsDialog(QDialog):
    """a mod's files (and which other mods it beats or loses to for each)"""
    def __init__(self, parent, store, mid):
        super().__init__(parent)
        m = store.mods[mid]
        self.setWindowTitle(m.get("name", mid))
        self.resize(760, 560)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label(m.get("name", mid), "title"))
        bits = [x for x in (("v" + str(m["version"]).lstrip("vV")) if m.get("version") else "",
                            ("by " + m["author"]) if m.get("author") else "", human(m.get("size", 0)),
                            f"{m.get('files', 0)} files") if x]
        v.addWidget(label("  ·  ".join(bits), "muted"))
        if m.get("summary"):
            v.addWidget(label(m["summary"], "muted", True))
        fmap = store.file_map()
        names = {k: store.mods[k].get("name", k) for k in store.mods}
        tree = QTreeWidget()
        tree.setHeaderLabels(["File", "Conflict"])
        tree.setColumnWidth(0, 470)
        from ..store import staged_files
        n_win = n_lose = 0
        for key, rel in sorted(staged_files(store.mod_path(mid)).items()):
            owners = [o for o, _ in fmap.get(key, [])]
            note = ""
            if len(owners) > 1 and mid in owners:
                if owners[-1] == mid:
                    note = "wins over " + ", ".join(names[o] for o in owners if o != mid)
                    n_win += 1
                else:
                    note = "replaced by " + names[owners[-1]]
                    n_lose += 1
            it = QTreeWidgetItem([rel, note])
            if note.startswith("replaced"):
                it.setForeground(0, Qt.GlobalColor.gray)
            tree.addTopLevelItem(it)
        v.addWidget(label(f"{n_win} files win over other mods, {n_lose} are replaced by mods lower in the list"
                          if (n_win or n_lose) else "No conflicts with the other mods that are on", "small"))
        v.addWidget(tree, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Close", self.accept, "primary"))
        v.addLayout(row)
