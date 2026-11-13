"""The Mods page (a list you drag to set priority, or a grid) and the Plugins page (Bethesda)."""
import os

from PyQt6.QtCore import QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QFontMetrics
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout,
                             QLineEdit, QListWidget, QListWidgetItem, QMenu, QScrollArea, QStackedWidget,
                             QVBoxLayout, QWidget)

from .. import config, nexus, thunderstore
from ..config import human
from . import tasks
from .theme import Segments, Switch, button, label, menu_button, open_web, tip

TAB_NAMES = {"mods": "Mods", "nsfw": "NSFW", "hidden": "Hidden"}


def picture_of(store, m):
    if m.get("thumb_rel"):
        p = os.path.join(store.mod_path(m["id"]), m["thumb_rel"])
        if os.path.isfile(p):
            return p
    return m.get("picture") or None


def source_badge(m):
    t = (m.get("source") or {}).get("type")
    if t == "nexus":
        return label("Nexus", "badgeNexus")
    if t == "thunderstore":
        return label("Thunderstore", "badgeTs")
    return None


class ModCard(QFrame):
    def __init__(self, page, m, conflicts):
        super().__init__()
        self.setObjectName("card")
        self.page, self.m = page, m
        store = page.store
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 12, 10)
        lay.setSpacing(12)
        grip = label("⋮⋮", "muted")
        grip.setToolTip("Drag to change the order: mods lower in the list win the files they share")
        grip.setStyleSheet("font-size: 14px; color: #55555f;")
        grip.setCursor(Qt.CursorShape.OpenHandCursor)
        lay.addWidget(grip)
        thumb = label("")
        tasks.set_picture(thumb, picture_of(store, m), 112, 63, m.get("name", ""))
        if not m["enabled"]:
            eff = QGraphicsOpacityEffect(thumb)
            eff.setOpacity(0.4)
            thumb.setGraphicsEffect(eff)
        lay.addWidget(thumb)

        text = QVBoxLayout()
        text.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        name = label(m.get("name") or m["id"])
        name.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {'#e8e8ef' if m['enabled'] else '#7a7a88'};")
        top.addWidget(name)
        if m.get("version"):
            top.addWidget(label("v" + str(m["version"]).lstrip("vV"), "badge"))
        b = source_badge(m)
        if b:
            top.addWidget(b)
        up = m.get("update")
        if up and up.get("version") is not None:
            ub = button(f"Update to v{str(up.get('version') or '?').lstrip('vV')}", lambda: page.window.update_mod(m["id"]),
                        "update")
            top.addWidget(ub)
        top.addStretch(1)
        text.addLayout(top)
        if m.get("summary"):
            d = label(m["summary"].replace("\n", " "), "muted")
            d.setText(QFontMetrics(d.font()).elidedText(d.text(), Qt.TextElideMode.ElideRight, 520))
            d.setToolTip(tip(m["summary"]))
            text.addWidget(d)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        if m.get("author"):
            chips.addWidget(label("by " + m["author"], "muted"))
        if m.get("game_version"):
            chips.addWidget(label("Game " + m["game_version"], "badgeOk"))
        chips.addWidget(label(human(m.get("size", 0)), "badge"))
        c = conflicts.get(m["id"])
        if c and m["enabled"]:
            names = lambda d_: ", ".join(store.mods[k].get("name", k) for k in d_)
            if c["wins"]:
                w = label(f"Wins {sum(c['wins'].values())}", "badgeWin")
                w.setToolTip(tip("Replaces files of: " + names(c["wins"])))
                chips.addWidget(w)
            if c["loses"]:
                l_ = label(f"Loses {sum(c['loses'].values())}", "badgeOld")
                l_.setToolTip(tip("Some of its files are replaced by: " + names(c["loses"]) +
                                  "\nMove it lower in the list to win them"))
                chips.addWidget(l_)
        if store.is_nsfw(m):
            chips.addWidget(label("NSFW", "badgeNsfw"))
        if not m["enabled"]:
            chips.addWidget(label("Off", "badge"))
        chips.addStretch(1)
        text.addLayout(chips)
        lay.addLayout(text, 1)
        lay.addWidget(mod_switch(page, m), 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(menu_button(mod_menu(page, m, self)), 0, Qt.AlignmentFlag.AlignVCenter)


class ModTile(QFrame):
    W = 220

    def __init__(self, page, m):
        super().__init__()
        self.setObjectName("tile")
        self.setFixedWidth(self.W)
        store = page.store
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        thumb = label("")
        tasks.set_picture(thumb, picture_of(store, m), self.W - 20, (self.W - 20) * 9 // 16, m.get("name", ""))
        if not m["enabled"]:
            eff = QGraphicsOpacityEffect(thumb)
            eff.setOpacity(0.4)
            thumb.setGraphicsEffect(eff)
        lay.addWidget(thumb)
        name = label("")
        name.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {'#e8e8ef' if m['enabled'] else '#7a7a88'};")
        name.setText(QFontMetrics(name.font()).elidedText(m.get("name", ""), Qt.TextElideMode.ElideRight, self.W - 40))
        name.setToolTip(tip(m.get("name", "") + (f"\nby {m['author']}" if m.get("author") else "") +
                        (f"\n\n{m['summary']}" if m.get("summary") else "")))
        lay.addWidget(name)
        row = QHBoxLayout()
        row.setSpacing(6)
        mid = Qt.AlignmentFlag.AlignVCenter
        if m.get("version"):
            row.addWidget(label("v" + str(m["version"]).lstrip("vV"), "badge"), 0, mid)
        if m.get("update"):
            u = label("Update", "badgeOk")
            u.setToolTip(tip(f"v{m['update'].get('version')} is out: ⋯ → Update"))
            row.addWidget(u, 0, mid)
        if store.is_nsfw(m):
            row.addWidget(label("NSFW", "badgeNsfw"), 0, mid)
        row.addStretch(1)
        row.addWidget(mod_switch(page, m), 0, mid)
        row.addWidget(menu_button(mod_menu(page, m, self)), 0, mid)
        lay.addLayout(row)
        self.setFixedHeight(self.sizeHint().height())


def mod_switch(page, m):
    sw = Switch(m["enabled"])
    sw.setToolTip("On: it's in the game. Off: kept here, the game doesn't see it")
    sw.toggled.connect(lambda on: page.toggle(m, on))
    return sw


def mod_menu(page, m, parent):
    w = page.window
    store = page.store
    menu = QMenu(parent)
    src = m.get("source") or {}
    if src.get("type") == "nexus" and src.get("mod_id"):
        dom = src.get("domain") or store.game.nexus
        menu.addAction("Open on Nexus Mods", lambda: QDesktopServices.openUrl(QUrl(nexus.mod_url(dom, src["mod_id"]))))
        if w.nexus.logged_in:
            endorsed = m.get("endorsed")
            menu.addAction("Remove endorsement" if endorsed else "Endorse", lambda: w.endorse(m["id"], not endorsed))
    elif src.get("type") == "thunderstore" and src.get("full_name"):
        url = src.get("url") or thunderstore.package_url(store.game.thunderstore, *src["full_name"].split("-", 1))
        menu.addAction("Open on Thunderstore", lambda: open_web(url))
    if m.get("update"):
        menu.addAction(f"Update to v{m['update'].get('version')}", lambda: w.update_mod(m["id"]))
    menu.addAction("Check for an update", lambda: w.check_updates([m["id"]]))
    menu.addSeparator()
    menu.addAction("Files and conflicts...", lambda: w.mod_details(m["id"]))
    menu.addAction("Open its folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(store.mod_path(m["id"]))))
    if m.get("archive") and os.path.exists(m["archive"]):
        menu.addAction("Reinstall", lambda: w.install_paths([m["archive"]], meta=dict(m), replace=m["id"]))
    menu.addAction("Rename...", lambda: w.rename_mod(m["id"]))
    menu.addSeparator()
    order = menu.addMenu("Order")
    order.addAction("To the top (loses every conflict)", lambda: page.move(m, "top"))
    order.addAction("Up", lambda: page.move(m, "up"))
    order.addAction("Down", lambda: page.move(m, "down"))
    order.addAction("To the bottom (wins every conflict)", lambda: page.move(m, "bottom"))
    nsfw, hidden = store.is_nsfw(m), bool(m.get("hidden"))
    menu.addAction("Not NSFW" if nsfw else "Mark as NSFW", lambda: page.mark_nsfw(m, not nsfw))
    menu.addAction("Unhide" if hidden else "Hide", lambda: page.mark_hidden(m, not hidden))
    menu.addSeparator()
    menu.addAction("Remove...", lambda: w.remove_mod(m["id"]))
    return menu


class OrderList(QListWidget):
    """the list of mod cards; dragging one reorders the mods"""
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSpacing(4)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def dropEvent(self, e):
        before = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        super().dropEvent(e)
        after = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        if after != before:
            QTimer.singleShot(0, lambda: self.page.reordered(after))


class ModsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.store = None
        self.tab = "mods"
        self.show_mode = "all"
        self.view = config.get("view") if config.get("view") in ("list", "grid") else "list"
        self.grid_cols = 0
        self.scroll_keep = 0
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.tabs = Segments([(k, t) for k, t in TAB_NAMES.items()], self.set_tab, "mods")
        row.addWidget(self.tabs)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Search your mods")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self.refresh)
        row.addWidget(self.filter, 1)
        self.modes = Segments([("all", "All"), ("on", "On"), ("off", "Off"), ("updates", "Updates")],
                              self.set_mode, "all")
        row.addWidget(self.modes)
        self.views = Segments([("list", "☰"), ("grid", "▦")], self.set_view, self.view)
        self.views.buttons["list"].setToolTip("List (drag to set the order)")
        self.views.buttons["grid"].setToolTip("Grid")
        row.addWidget(self.views)
        v.addLayout(row)

        self.stack = QStackedWidget()
        self.list = OrderList(self)
        self.stack.addWidget(self.list)
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.viewport().setObjectName("viewport")
        self.grid_scroll.viewport().setStyleSheet("#viewport { background: transparent; }")
        self.stack.addWidget(self.grid_scroll)
        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.setContentsMargins(40, 50, 40, 0)
        el.setSpacing(10)
        self.empty_title = label("", "h2")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text = label("", "muted", True)
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self.empty_title)
        el.addWidget(self.empty_text)
        self.empty_buttons = QHBoxLayout()
        self.empty_buttons.addStretch(1)
        self.empty_buttons.addWidget(button("Browse mods", lambda: window.show_page("browse")))
        self.empty_buttons.addWidget(button("+  Install from file", window.pick_files, "primary"))
        self.empty_buttons.addStretch(1)
        el.addLayout(self.empty_buttons)
        el.addStretch(1)
        self.stack.addWidget(self.empty)
        v.addWidget(self.stack, 1)

    def set_store(self, store):
        self.store = store
        self.refresh()

    def set_tab(self, t):
        self.tab = t
        self.tabs.set(t)
        self.refresh()

    def set_mode(self, mode):
        self.show_mode = mode
        self.refresh()

    def set_view(self, view):
        self.view = view
        self.views.set(view)
        config.save_conf(view=view)
        self.refresh()

    def tab_of(self, m):
        return "hidden" if m.get("hidden") else "nsfw" if self.store.is_nsfw(m) else "mods"

    def columns(self):
        # the page's width: the grid's own viewport is still tiny while it's hidden
        return max(1, (self.width() - 16 + 10) // (ModTile.W + 10))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.view == "grid" and self.store and self.columns() != self.grid_cols:
            QTimer.singleShot(0, self.refresh)

    def visible(self):
        mods = self.store.ordered()
        q = self.filter.text().strip().lower()
        tabs = {m["id"]: self.tab_of(m) for m in mods}
        for key in TAB_NAMES:
            n = sum(1 for t in tabs.values() if t == key)
            self.tabs.set_text(key, f"{TAB_NAMES[key]}  ({n})" if n or key == "mods" else TAB_NAMES[key])
        n_up = sum(1 for m in mods if m.get("update"))
        self.modes.set_text("updates", f"Updates ({n_up})" if n_up else "Updates")
        shown = [m for m in mods if tabs[m["id"]] == self.tab
                 and (self.show_mode == "all" or (self.show_mode == "updates" and m.get("update"))
                      or (self.show_mode in ("on", "off") and m["enabled"] == (self.show_mode == "on")))
                 and (not q or q in (m.get("name") or "").lower() or q in (m.get("author") or "").lower())]
        return mods, tabs, shown

    def refresh(self):
        if not self.store:
            return
        mods, tabs, shown = self.visible()
        sb = self.list.verticalScrollBar().value()
        self.list.clear()
        if not shown:
            if not mods:
                g = self.store.game
                where = []
                if g.nexus or g.thunderstore:
                    where.append("find some in Browse")
                where.append("drop a downloaded .zip, .7z or .rar on this window")
                self.empty_title.setText(f"No mods for {g.name} yet")
                self.empty_text.setText("You can " + ", or ".join(where) + ".")
                show_buttons = True
            elif not any(t == self.tab for t in tabs.values()):
                self.empty_title.setText({"mods": "Every mod is NSFW or hidden", "nsfw": "No NSFW mods",
                                          "hidden": "No hidden mods"}[self.tab])
                self.empty_text.setText({"mods": "They're in the NSFW and Hidden tabs.",
                                         "nsfw": "Mods marked adult on Nexus or Thunderstore, or with NSFW words in "
                                                 "their name or summary, show here. ⋯ → Mark as NSFW moves any mod here.",
                                         "hidden": "⋯ → Hide moves a mod here. Hiding doesn't turn it off."}[self.tab])
                show_buttons = False
            else:
                self.empty_title.setText("Nothing matches")
                self.empty_text.setText("Try another search, or show All.")
                show_buttons = False
            for i in range(self.empty_buttons.count()):
                it = self.empty_buttons.itemAt(i).widget()
                if it:
                    it.setVisible(show_buttons)
            self.stack.setCurrentWidget(self.empty)
            return
        if self.view == "grid":
            self.grid_cols = self.columns()
            box = QWidget()
            box.setObjectName("holder")
            box.setStyleSheet("#holder { background: transparent; }")
            grid = QGridLayout(box)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(10)
            for i, m in enumerate(shown):
                grid.addWidget(ModTile(self, m), i // self.grid_cols, i % self.grid_cols,
                               Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            grid.setColumnStretch(self.grid_cols, 1)
            grid.setRowStretch(len(shown) // self.grid_cols + 1, 1)
            old = self.grid_scroll.verticalScrollBar().value()
            self.grid_scroll.setWidget(box)
            QTimer.singleShot(0, lambda: self.grid_scroll.verticalScrollBar().setValue(old))
            self.stack.setCurrentWidget(self.grid_scroll)
            return
        conflicts = self.store.conflicts()
        width = self.list.viewport().width() - 8
        for m in shown:
            card = ModCard(self, m, conflicts)
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, m["id"])
            it.setSizeHint(QSize(max(200, width), card.sizeHint().height()))
            self.list.addItem(it)
            self.list.setItemWidget(it, card)
        self.stack.setCurrentWidget(self.list)
        QTimer.singleShot(0, lambda: self.list.verticalScrollBar().setValue(sb))

    def reordered(self, visible_order):
        """the visible mods were dragged into a new order: keep the hidden ones where they are"""
        full = list(self.store.profile["order"])
        slots = [i for i, mid in enumerate(full) if mid in set(visible_order)]
        for i, mid in zip(slots, visible_order):
            full[i] = mid
        self.store.set_order(full)
        self.window.changed()

    def move(self, m, where):
        self.store.move(m["id"], where)
        self.window.changed()

    def toggle(self, m, on):
        self.store.set_enabled(m["id"], on)
        self.window.say(f"{m.get('name')} is {'on' if on else 'off'}")
        QTimer.singleShot(160, self.window.changed)

    def mark_nsfw(self, m, on):
        self.store.set_nsfw(m["id"], on)
        self.refresh()

    def mark_hidden(self, m, on):
        self.store.update_meta(m["id"], hidden=True if on else None)
        self.window.say(f"{m.get('name')} {'is hidden (it still loads while it is on)' if on else 'is back'}")
        self.refresh()


class PluginsPage(QWidget):
    """Bethesda load order: drag to reorder, tick to turn on"""
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.store = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        row = QHBoxLayout()
        self.title = label("Plugins", "h2")
        row.addWidget(self.title)
        row.addStretch(1)
        row.addWidget(button("Sort by masters", self.sort, tip="Masters first, and every plugin after the ones it needs"))
        v.addLayout(row)
        self.note = label("", "small", True)
        v.addWidget(self.note)
        self.list = QListWidget()
        self.list.setObjectName("plain")
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, self.save))
        self.list.itemChanged.connect(lambda *_: self.save())
        v.addWidget(self.list, 1)

    def set_store(self, store):
        self.store = store
        self.refresh()

    def refresh(self):
        if not self.store or not self.store.game.plugins:
            return
        self.list.blockSignals(True)
        self.list.clear()
        items = self.store.plugins()
        implicit = {m.lower() for m in self.store.game.plugins.get("masters", [])}
        for i, (n, on, path, master) in enumerate(items):
            it = QListWidgetItem(f"{i:02X}   {n}" + ("    · master" if master else ""))
            it.setData(Qt.ItemDataRole.UserRole, n)
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if n.lower() not in implicit:
                flags |= Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled
            it.setFlags(flags)
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.list.addItem(it)
        self.list.blockSignals(False)
        path = self.store.plugins_txt()
        self.title.setText(f"Plugins  ({sum(1 for x in items if x[1])} of {len(items)} on)")
        self.note.setText(f"Load order, top first. Written to {path}" if path else
                          "Run the game once from Steam so its Proton prefix exists; then Armory can write the "
                          "load order (Plugins.txt).")

    def save(self):
        items = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            items.append((it.data(Qt.ItemDataRole.UserRole), it.checkState() == Qt.CheckState.Checked))
        self.store.set_plugins(items)
        try:
            self.store.write_plugins()
        except OSError as e:
            self.window.say(f"Couldn't write Plugins.txt: {e}")
        QTimer.singleShot(0, self.refresh)

    def sort(self):
        self.store.sort_plugins()
        self.store.write_plugins()
        self.refresh()
        self.window.say("Plugins sorted")
