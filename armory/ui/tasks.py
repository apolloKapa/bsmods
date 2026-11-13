"""Running work off the UI thread, and loading pictures into labels."""
import os
import traceback

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtGui import QPixmap

from .. import net
from .theme import placeholder, rounded

_pool = QThreadPool.globalInstance()
_pool.setMaxThreadCount(max(8, _pool.maxThreadCount()))
_images = QThreadPool()
_images.setMaxThreadCount(6)
_alive = set()


class _Signals(QObject):
    done = pyqtSignal(object)
    fail = pyqtSignal(str)
    progress = pyqtSignal(int, int)


class _Task(QRunnable):
    def __init__(self, fn, wants_progress):
        super().__init__()
        self.fn = fn
        self.wants_progress = wants_progress
        self.sig = _Signals()

    def run(self):
        try:
            if self.wants_progress:
                res = self.fn(lambda a, b: self.sig.progress.emit(int(a), int(b)))
            else:
                res = self.fn()
        except Exception as e:  # noqa: BLE001 - shown to the user
            msg = str(e) or e.__class__.__name__
            expected = isinstance(e, (OSError, net.NetError)) or \
                e.__class__.__name__ in ("LayoutError", "DeployError", "ParseError")
            if not expected or os.environ.get("ARMORY_DEBUG"):
                traceback.print_exc()
            if not expected:
                msg = f"{e.__class__.__name__}: {msg}"
            self.sig.fail.emit(msg)
        else:
            self.sig.done.emit(res)


def run(fn, done=None, fail=None, progress=None, pool=None):
    """fn() in a thread; done(result) / fail(message) / progress(a, b) back on the UI thread.
    With progress given, fn is called as fn(progress_callback)."""
    t = _Task(fn, progress is not None)
    sig = t.sig
    _alive.add(sig)

    def finish(*_):
        _alive.discard(sig)

    if done:
        sig.done.connect(done)
    if fail:
        sig.fail.connect(fail)
    if progress:
        sig.progress.connect(progress)
    sig.done.connect(finish)
    sig.fail.connect(finish)
    (pool or _pool).start(t)
    return sig


def set_picture(lbl, source, w, h, name="", r=10, dim=False):
    """show a picture (a file or a URL) in a label once it's loaded, initials until then"""
    lbl.setFixedSize(w, h)
    lbl.setPixmap(placeholder(name, w, h, r))
    if not source:
        return

    def load():
        return net.cached_image(source) if not os.path.isfile(source) else source

    def show(path):
        try:
            if not path:
                return
            pix = QPixmap(path)
            if pix.isNull():
                return
            lbl.setPixmap(rounded(pix, w, h, r))
        except RuntimeError:
            # the label is gone (the list was rebuilt)
            pass

    run(load, done=show, pool=_images)
