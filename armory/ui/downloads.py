"""The download queue and the Downloads page."""
import os
import re
import time

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QMenu, QProgressBar, QScrollArea, QVBoxLayout, QWidget)

from .. import net
from ..config import DATA, DOWNLOADS, human, read_json, write_json
from . import tasks
from .theme import button, label, menu_button

LIST = os.path.join(DATA, "downloads.json")
MAX_RUNNING = 3


def safe_name(name):
    return re.sub(r'[\\/:*?"<>|\x00]+', "_", name).strip() or "download"


class Downloads(QObject):
    changed = pyqtSignal()
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.items = read_json(LIST, [])
        for d in self.items:
            if d.get("status") in ("downloading", "queued"):
                d["status"] = "failed"
                d["error"] = "Stopped when Armory closed"
        self.cancel_flags = {}

    def save(self):
        write_json(LIST, self.items)

    def get(self, did):
        return next((d for d in self.items if d["id"] == did), None)

    def add(self, url, filename, game, meta, headers=None, install=True):
        filename = safe_name(filename or os.path.basename(url.split("?")[0]) or "mod.zip")
        folder = os.path.join(DOWNLOADS, game)
        path = os.path.join(folder, filename)
        base, ext = os.path.splitext(filename)
        if ext.lower() in (".gz", ".xz", ".bz2") and base.endswith(".tar"):
            base, ext = base[:-4], ".tar" + ext
        n = 2
        while os.path.exists(path) or any(d["file"] == path and d["status"] in ("queued", "downloading")
                                          for d in self.items):
            path = os.path.join(folder, f"{base} ({n}){ext}")
            n += 1
        d = {"id": f"{time.time():.6f}", "name": meta.get("name") or base, "file": path, "url": url, "game": game,
             "meta": meta, "status": "queued", "done": 0, "total": 0, "error": "", "time": time.time(),
             "install": install, "headers": headers or {}}
        self.items.insert(0, d)
        self.save()
        self.changed.emit()
        self.pump()
        return d

    def add_local(self, path, game, meta):
        """a finished download that came from somewhere else (kept in the list for reinstalls)"""
        d = {"id": f"{time.time():.6f}", "name": meta.get("name") or os.path.basename(path), "file": path,
             "url": "", "game": game, "meta": meta, "status": "done", "done": 0, "total": 0, "error": "",
             "time": time.time(), "install": False}
        self.items.insert(0, d)
        self.save()
        self.changed.emit()
        return d

    def running(self):
        return sum(1 for d in self.items if d["status"] == "downloading")

    def pump(self):
        for d in reversed(self.items):
            if self.running() >= MAX_RUNNING:
                break
            if d["status"] == "queued":
                self._start(d)

    def _start(self, d):
        d["status"] = "downloading"
        flag = {"stop": False}
        self.cancel_flags[d["id"]] = flag

        def work(progress):
            return net.download(d["url"], d["file"], progress, lambda: flag["stop"], d.get("headers"))

        def prog(done, total):
            d["done"], d["total"] = done, total
            self.progress.emit(d["id"])

        def done(_):
            d["status"] = "done"
            d["total"] = d["total"] or d["done"]
            self.save()
            self.changed.emit()
            self.finished.emit(d)
            self.pump()

        def fail(msg):
            d["status"] = "cancelled" if flag["stop"] else "failed"
            d["error"] = "" if flag["stop"] else msg
            self.save()
            self.changed.emit()
            self.pump()

        tasks.run(work, done=done, fail=fail, progress=prog)
        self.changed.emit()

    def cancel(self, did):
        d = self.get(did)
        if not d:
            return
        if d["status"] == "queued":
            d["status"] = "cancelled"
            self.save()
            self.changed.emit()
        elif d["id"] in self.cancel_flags:
            self.cancel_flags[d["id"]]["stop"] = True

    def retry(self, did):
        d = self.get(did)
        if d and d["status"] in ("failed", "cancelled") and d.get("url"):
            d["status"], d["error"], d["done"] = "queued", "", 0
            self.save()
            self.pump()
            self.changed.emit()

    def remove(self, did, delete_file=True):
        d = self.get(did)
        if not d:
            return
        self.cancel(did)
        if delete_file and d["status"] not in ("downloading",):
            try:
                os.unlink(d["file"])
            except OSError:
                pass
        self.items = [x for x in self.items if x["id"] != did]
        self.save()
        self.changed.emit()

    def mark_installed(self, path):
        for d in self.items:
            if d["file"] == path:
                d["status"] = "installed"
        self.save()
        self.changed.emit()

    def clear_finished(self):
        for d in list(self.items):
            if d["status"] in ("installed", "failed", "cancelled"):
                self.remove(d["id"], delete_file=d["status"] != "installed")
        self.changed.emit()


STATUS = {"queued": "Waiting", "downloading": "Downloading", "done": "Downloaded", "installed": "Installed",
          "failed": "Failed", "cancelled": "Cancelled"}


class DownloadRow(QFrame):
    def __init__(self, page, d):
        super().__init__()
        self.setObjectName("card")
        self.d = d
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(4)
        top = QHBoxLayout()
        name = label(d["name"])
        name.setStyleSheet("font-weight: 700; font-size: 14px;")
        top.addWidget(name)
        src = (d.get("meta") or {}).get("source", {}).get("type")
        if src == "nexus":
            top.addWidget(label("Nexus", "badgeNexus"))
        elif src == "thunderstore":
            top.addWidget(label("Thunderstore", "badgeTs"))
        top.addStretch(1)
        text.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(8)
        self.bar.setTextVisible(False)
        text.addWidget(self.bar)
        self.info = label("", "small")
        text.addWidget(self.info)
        lay.addLayout(text, 1)
        st = d["status"]
        if st in ("queued", "downloading"):
            lay.addWidget(button("Cancel", lambda: page.dl.cancel(d["id"])))
        elif st in ("done", "installed") and os.path.exists(d["file"]):
            lay.addWidget(button("Install" if st == "done" else "Reinstall",
                                 lambda: page.window.install_download(d), "primary" if st == "done" else None))
        elif st in ("failed", "cancelled") and d.get("url"):
            lay.addWidget(button("Retry", lambda: page.dl.retry(d["id"])))
        menu = QMenu(self)
        menu.addAction("Show in folder", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.dirname(d["file"]))))
        menu.addSeparator()
        menu.addAction("Remove from the list", lambda: page.dl.remove(d["id"], delete_file=False))
        menu.addAction("Delete the file", lambda: page.dl.remove(d["id"], delete_file=True))
        lay.addWidget(menu_button(menu))
        self.update_progress()

    def update_progress(self):
        d = self.d
        st = d["status"]
        if st == "downloading":
            if d["total"]:
                self.bar.setRange(0, 1000)
                self.bar.setValue(int(d["done"] * 1000 / d["total"]))
                self.info.setText(f"{human(d['done'])} of {human(d['total'])}")
            else:
                self.bar.setRange(0, 0)
                self.info.setText(human(d["done"]))
            self.bar.show()
        else:
            self.bar.setVisible(st == "queued")
            self.bar.setRange(0, 0 if st == "queued" else 1)
            size = ""
            try:
                size = human(os.path.getsize(d["file"]))
            except OSError:
                pass
            bits = [STATUS.get(st, st)]
            if size:
                bits.append(size)
            if d.get("error"):
                bits.append(d["error"])
            bits.append(time.strftime("%d %b %H:%M", time.localtime(d.get("time", 0))))
            self.info.setText("  ·  ".join(bits))


class DownloadsPage(QWidget):
    def __init__(self, window, dl):
        super().__init__()
        self.window = window
        self.dl = dl
        self.rows = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        bar = QHBoxLayout()
        self.title = label("Downloads", "h2")
        bar.addWidget(self.title)
        bar.addStretch(1)
        bar.addWidget(button("Open folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(
            os.makedirs(DOWNLOADS, exist_ok=True) or DOWNLOADS))))
        bar.addWidget(button("Clear finished", dl.clear_finished))
        v.addLayout(bar)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        holder = QWidget()
        holder.setObjectName("holder")
        holder.setStyleSheet("#holder { background: transparent; }")
        self.scroll.viewport().setObjectName("viewport")
        self.scroll.viewport().setStyleSheet("#viewport { background: transparent; }")
        self.list = QVBoxLayout(holder)
        self.list.setContentsMargins(0, 0, 4, 0)
        self.list.setSpacing(8)
        self.scroll.setWidget(holder)
        v.addWidget(self.scroll, 1)
        dl.changed.connect(self.refresh)
        dl.progress.connect(self.on_progress)
        self.game = None
        self.refresh()

    def set_game(self, gid):
        self.game = gid
        self.refresh()

    def on_progress(self, did):
        row = self.rows.get(did)
        if row:
            try:
                row.update_progress()
            except RuntimeError:
                pass

    def refresh(self):
        while self.list.count():
            w = self.list.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.rows = {}
        items = [d for d in self.dl.items if not self.game or d["game"] == self.game]
        self.title.setText(f"Downloads  ({len(items)})")
        if not items:
            e = label("Nothing downloaded for this game yet. Mods you download from Browse, or with Nexus "
                      "Mods' “Mod Manager Download” button, show up here and install by themselves.", "muted", True)
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e.setContentsMargins(40, 60, 40, 0)
            self.list.addWidget(e)
        for d in items:
            r = DownloadRow(self, d)
            self.rows[d["id"]] = r
            self.list.addWidget(r)
        self.list.addStretch(1)
