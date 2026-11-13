"""Settings (Nexus account, links, deploying), adding games, the FOMOD wizard, picking a Nexus
file, and a mod's files and conflicts."""
import os
import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
                             QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QRadioButton,
                             QScrollArea, QSpinBox, QStackedWidget, QTextBrowser, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

from .. import config, games, links, nexus
from ..config import human
from . import tasks
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
        self.segs = Segments([("nexus", "Nexus Mods"), ("links", "Links"), ("deploy", "Installing"),
                              ("browse", "Browse")], self.show_tab, tab)
        v.addWidget(self.segs, 0, Qt.AlignmentFlag.AlignLeft)
        self.stack = QStackedWidget()
        self.pages = {}
        for key, build in (("nexus", self.build_nexus), ("links", self.build_links), ("deploy", self.build_deploy),
                           ("browse", self.build_browse)):
            w = QWidget()
            build(w)
            self.pages[key] = self.stack.addWidget(w)
        v.addWidget(self.stack, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Done", self.accept, "primary"))
        v.addLayout(row)
        self.show_tab(tab)

    def show_tab(self, key):
        self.segs.set(key)
        self.stack.setCurrentIndex(self.pages[key])
        if key == "links":
            self.refresh_links()

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

        self.login_box = frame()
        lb = QVBoxLayout(self.login_box)
        lb.setContentsMargins(16, 14, 16, 14)
        lb.setSpacing(10)
        lb.addWidget(label("Log in with your personal API key", "h2"))
        lb.addWidget(label("Nexus Mods only lets apps it has registered use one-click sign-in, so Armory uses "
                           "the personal API key from your account instead. Open the API keys page, copy your "
                           "Personal API Key at the bottom, and paste it here. It's kept in "
                           "~/.config/armory/nexus.json, readable only by you.", "muted", True))
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
        if nx.logged_in and u:
            self.who.setText(u.get("name", "Logged in"))
            kind = "Premium" if nx.premium else "Supporter" if u.get("is_supporter") else "Free account"
            self.who_sub.setText(f"{kind}  ·  {u.get('email', '')}".strip(" ·"))
            tasks.set_picture(self.avatar, u.get("profile_url"), 48, 48, u.get("name", ""), 24)
            self.logout_btn.show()
            self.login_box.hide()
        elif nx.logged_in:
            self.who.setText("Checking your key...")
            self.who_sub.setText("")
            self.logout_btn.show()
            self.login_box.hide()
        else:
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
            config.set_nexus_key(key)
            self.window.set_nexus(nx)
            self.key_edit.clear()
            self.login_msg.setText("")
            self.login_btn.setEnabled(True)
            self.refresh_account()

        def fail(msg):
            self.login_btn.setEnabled(True)
            self.login_msg.setText("That key didn't work: " + msg)

        tasks.run(nx.validate, done, fail)

    def logout(self):
        config.set_nexus_key("")
        self.window.set_nexus(nexus.Nexus(""))
        self.refresh_account()

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
        tree.setStyleSheet("QTreeWidget { background: #1c1c22; border: 1px solid #2a2a33; border-radius: 10px; }")
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
