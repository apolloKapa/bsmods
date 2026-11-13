"""Starting Armory: one window per user; a second start (a clicked nxm:// link, "Open with")
hands its arguments to the running one."""
import os
import shutil
import socket
import struct
import sys
import threading

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from . import links
from .ui import theme

# a plain Unix socket (QtNetwork would pull in Kerberos libraries many desktops don't have)
SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", f"{links.SOCKET}.sock")


def peer_uid(conn):
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)[1]


def send_to_running(args):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.5)
            s.connect(SOCK)
            if peer_uid(s) != os.getuid():
                # someone else's socket: links (with their download keys) aren't handed to it
                return False
            s.sendall("\0".join(args).encode())
        return True
    except OSError:
        return False


class Listener(QObject):
    got = pyqtSignal(list)

    def start(self):
        try:
            os.unlink(SOCK)
        except OSError:
            pass
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(SOCK)
        os.chmod(SOCK, 0o600)
        self.srv.listen(4)
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            with conn:
                try:
                    if peer_uid(conn) != os.getuid():
                        continue
                except OSError:
                    continue
                conn.settimeout(3)
                buf = b""
                try:
                    while True:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        buf += chunk
                except OSError:
                    pass
            self.got.emit([a for a in buf.decode(errors="replace").split("\0") if a])

    def stop(self):
        try:
            self.srv.close()
            os.unlink(SOCK)
        except OSError:
            pass


def main():
    if shutil.which("bsdtar") is None and shutil.which("7z") is None:
        print("armory: install bsdtar (libarchive) or 7-Zip to unpack mods", file=sys.stderr)
    args = sys.argv[1:]
    if send_to_running(args or ["--show"]):
        return
    app = QApplication(sys.argv[:1])
    app.setApplicationName("armory")
    app.setDesktopFileName("armory")
    app.setWindowIcon(QIcon(theme.ICON))
    from . import vault
    try:
        vault.migrate()
    except OSError:
        pass
    theme.apply(app)
    from .ui.window import Window
    w = Window()

    def incoming(got):
        w.showNormal()
        w.raise_()
        w.activateWindow()
        w.handle_args([a for a in got if a != "--show"])

    listener = Listener()
    listener.got.connect(incoming)
    try:
        listener.start()
    except OSError as e:
        print(f"armory: links won't reach this window ({e})", file=sys.stderr)
    w.show()
    if args:
        w.handle_args(args)
    code = app.exec()
    listener.stop()
    os._exit(code)


if __name__ == "__main__":
    main()
