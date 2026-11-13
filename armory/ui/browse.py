"""Browse: find mods on Nexus Mods or Thunderstore for the game and install them."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QScrollArea, QVBoxLayout,
                             QWidget)

from .. import config, nexus, thunderstore
from ..config import short_count
from . import tasks
from .theme import Segments, button, label, open_web, tip

PAGE = 30


class ResultTile(QFrame):
    W = 230

    def __init__(self, page, item, width=None):
        super().__init__()
        self.setObjectName("tile")
        self.W = width or self.W
        self.setFixedWidth(self.W)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        pic = label("")
        w = self.W - 20
        tasks.set_picture(pic, item["picture"], w, w * 9 // 16, item["name"], 9)
        lay.addWidget(pic)
        name = label("")
        name.setStyleSheet("font-size: 14px; font-weight: 700;")
        name.setText(QFontMetrics(name.font()).elidedText(item["name"], Qt.TextElideMode.ElideRight, w))
        name.setToolTip(tip(item["name"]))
        lay.addWidget(name)
        by = label("")
        by.setObjectName("small")
        by.setText(QFontMetrics(by.font()).elidedText(f"by {item['author']}", Qt.TextElideMode.ElideRight, w))
        lay.addWidget(by)
        summ = label(item["summary"], "muted", True)
        summ.setStyleSheet("font-size: 12px;")
        fm = QFontMetrics(summ.font())
        text = item["summary"] or ""
        # three lines at most
        out, line = [], ""
        words = []
        for word in text.split():
            while fm.horizontalAdvance(word) > w - 4 and len(word) > 1:
                cut = len(word)
                while cut > 1 and fm.horizontalAdvance(word[:cut]) > w - 4:
                    cut -= 1
                words.append(word[:cut])
                word = word[cut:]
            words.append(word)
        for word in words:
            trial = (line + " " + word).strip()
            if fm.horizontalAdvance(trial) > w - 4:
                out.append(line)
                line = word
                if len(out) == 3:
                    break
            else:
                line = trial
        if len(out) < 3 and line:
            out.append(line)
        if len(out) == 3 and len(" ".join(out)) < len(text):
            out[2] = fm.elidedText(out[2] + " …", Qt.TextElideMode.ElideRight, w - 4)
        summ.setText("\n".join(out))
        summ.setFixedHeight(fm.lineSpacing() * 3 + 2)
        summ.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        summ.setToolTip(tip(text))
        lay.addWidget(summ)
        stats = QHBoxLayout()
        stats.setSpacing(6)
        stats.addWidget(label(f"↓ {short_count(item['downloads'])}", "badge"))
        if item.get("likes") is not None:
            stats.addWidget(label(f"♥ {short_count(item['likes'])}", "badge"))
        if item.get("adult"):
            stats.addWidget(label("NSFW", "badgeNsfw"))
        stats.addStretch(1)
        lay.addLayout(stats)
        row = QHBoxLayout()
        row.setSpacing(6)
        installed = page.installed(item)
        if installed:
            b = button("Installed" if not installed.get("update") else "Update",
                       lambda: page.window.update_mod(installed["id"]) if installed.get("update") else None)
            b.setEnabled(bool(installed.get("update")))
        else:
            b = button("Install" if page.source == "thunderstore" or page.window.nexus.premium else "Download",
                       lambda: page.install(item), "primary")
            if page.source == "nexus" and not page.window.nexus.premium:
                b.setToolTip("Opens the mod's Files tab: press “Mod Manager Download” there and Armory installs it")
        row.addWidget(b, 1)
        row.addWidget(button("Page", lambda: open_web(item["url"]), tip="Open its page in your browser"))
        lay.addLayout(row)
        self.setFixedHeight(self.sizeHint().height())


class BrowsePage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.game = None
        self.source = "nexus"
        self.results = []
        self.total = 0
        self.ts_packages = None
        self.ts_for = None
        self.req = 0
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.sources = Segments([("nexus", "Nexus Mods"), ("thunderstore", "Thunderstore")], self.set_source)
        row.addWidget(self.sources)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search mods")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.run_search)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(450)
        self.debounce.timeout.connect(self.run_search)
        self.search.textChanged.connect(lambda: self.debounce.start())
        row.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.currentIndexChanged.connect(lambda: self.run_search())
        row.addWidget(self.sort)
        v.addLayout(row)
        self.status = label("", "small")
        v.addWidget(self.status)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.viewport().setObjectName("viewport")
        self.scroll.viewport().setStyleSheet("#viewport { background: transparent; }")
        v.addWidget(self.scroll, 1)
        self.cols = 0

    def set_game(self, game):
        if self.game is game:
            return
        self.game = game
        self.results = []
        has_n, has_t = bool(game.nexus), bool(game.thunderstore)
        self.sources.show_key("nexus", has_n)
        self.sources.show_key("thunderstore", has_t)
        self.sources.setVisible(has_n and has_t)
        pick = "thunderstore" if has_t and (not has_n or game.layout.get("loader") == "bepinex") else "nexus"
        self.set_source(pick, run=False)
        self.loaded = False

    def ensure_loaded(self):
        if self.game and not getattr(self, "loaded", False):
            self.loaded = True
            self.run_search()

    def set_source(self, src, run=True):
        self.source = src
        self.sources.set(src)
        self.sort.blockSignals(True)
        self.sort.clear()
        opts = [("popular", "Most downloaded"), ("endorsed", "Most endorsed"), ("updated", "Recently updated"),
                ("new", "Newest")] if src == "nexus" else \
            [("popular", "Most downloaded"), ("rating", "Top rated"), ("updated", "Recently updated"),
             ("new", "Newest"), ("name", "Name")]
        for k, t in opts:
            self.sort.addItem(t, k)
        self.sort.blockSignals(False)
        if run:
            self.run_search()

    def installed(self, item):
        st = self.window.store
        if not st:
            return None
        mid = st.find(nexus=item["id"]) if self.source == "nexus" else st.find(thunderstore=item["id"])
        return dict(st.mods[mid], id=mid) if mid else None

    # -- searching --
    def run_search(self, more=False):
        g = self.game
        if not g or not (g.nexus or g.thunderstore):
            self.show_message("Armory doesn't know where this game's mods are online. Download them in your "
                              "browser and drop the files on the window.")
            return
        self.req += 1
        req = self.req
        offset = len(self.results) if more else 0
        if not more:
            self.results = []
        text, sort = self.search.text(), self.sort.currentData() or "popular"
        adult = config.get("browse_adult", False)
        if self.source == "nexus":
            self.status.setText("Searching Nexus Mods...")

            def work():
                return nexus.search(g.nexus, text, sort, offset, PAGE, adult)

            def done(res):
                if req != self.req:
                    return
                self.total, nodes = res
                self.results += [{"id": n["modId"], "name": n["name"], "author": n.get("author") or
                                  (n.get("uploader") or {}).get("name", ""), "summary": n.get("summary") or "",
                                  "picture": n.get("thumbnailUrl") or n.get("pictureUrl"),
                                  "downloads": n.get("downloads", 0), "likes": n.get("endorsements", 0),
                                  "adult": n.get("adultContent"), "version": n.get("version", ""),
                                  "url": nexus.mod_url(g.nexus, n["modId"]), "raw": n} for n in nodes]
                self.show_results()

            tasks.run(work, done, lambda m: req == self.req and self.show_message("Search failed: " + m))
        else:
            if self.ts_packages is None or self.ts_for != g.thunderstore:
                self.status.setText("Loading the Thunderstore list (once an hour)...")
                community = g.thunderstore

                def load(progress):
                    return thunderstore.listing(community, progress=progress)

                def loaded(pk):
                    self.ts_packages, self.ts_for = pk, community
                    if req == self.req:
                        self.run_search()

                tasks.run(load, loaded, lambda m: self.show_message(m),
                          progress=lambda a, b: self.status.setText(f"Loading the Thunderstore list... {a}/{b}"))
                return
            found = thunderstore.search(self.ts_packages, text, sort, nsfw=adult)
            self.total = len(found)
            self.results += [{"id": p["full"], "name": p["name"].replace("_", " "), "author": p["owner"],
                              "summary": p["desc"], "picture": p["icon"], "downloads": p["downloads"],
                              "likes": p["rating"], "adult": p["nsfw"], "version": p["version"],
                              "url": p["url"] or thunderstore.package_url(g.thunderstore, p["owner"], p["name"]),
                              "raw": p} for p in found[offset:offset + PAGE]]
            self.show_results()

    def show_message(self, text):
        self.status.setText("")
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(40, 60, 40, 0)
        m = label(text, "muted", True)
        m.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(m)
        lay.addStretch(1)
        self.scroll.setWidget(box)

    def columns(self):
        return max(1, (self.width() - 16 + 10) // (ResultTile.W + 10))

    def tile_width(self):
        cols = self.columns()
        return max(ResultTile.W, (self.width() - 16 - 10 * (cols - 1)) // cols)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.results and (self.columns() != self.cols or abs(self.tile_width() - getattr(self, "tw", 0)) > 6):
            QTimer.singleShot(0, self.show_results)

    def show_results(self):
        where = "Nexus Mods" if self.source == "nexus" else "Thunderstore"
        self.status.setText(f"{self.total} mods on {where}" + (f", showing {len(self.results)}"
                                                               if self.total > len(self.results) else ""))
        if not self.results:
            self.show_message("No mods found.")
            return
        old = self.scroll.verticalScrollBar().value()
        self.cols = self.columns()
        tw = self.tw = self.tile_width()
        box = QWidget()
        box.setObjectName("holder")
        box.setStyleSheet("#holder { background: transparent; }")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, item in enumerate(self.results):
            grid.addWidget(ResultTile(self, item, tw), i // self.cols, i % self.cols,
                           Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(self.cols, 1)
        outer.addLayout(grid)
        if self.total > len(self.results):
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(button("Load more", lambda: self.run_search(more=True)))
            row.addStretch(1)
            outer.addLayout(row)
        outer.addStretch(1)
        self.scroll.setWidget(box)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(old))

    def install(self, item):
        if self.source == "nexus":
            self.window.nexus_install(self.game, item["id"], item["raw"])
        else:
            self.window.thunderstore_install(self.game, item["id"], self.ts_packages)

    def refresh_tiles(self):
        if self.results:
            self.show_results()
