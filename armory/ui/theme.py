"""Colours, the stylesheet, and small shared widgets."""
import os
import re

from PyQt6.QtCore import QPropertyAnimation, QRectF, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPalette, QPixmap
from PyQt6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QToolButton)

ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "armory.svg")

THEMES = {
    # name: (background, sidebar, text, muted, accent, light or dark)
    "armory": dict(label="Armory", bg="#0d0d11", panel="#121217", text="#ececf2", muted="#8b8b9a", accent="#c9a96e"),
    "midnight": dict(label="Midnight", bg="#0b0e14", panel="#10141c", text="#e6eaf2", muted="#8a93a6", accent="#7aa2f7"),
    "violet": dict(label="Violet", bg="#0f0c14", panel="#15111b", text="#ede8f4", muted="#9389a3", accent="#b48cf2"),
    "ember": dict(label="Ember", bg="#110d0b", panel="#17120f", text="#f2ebe6", muted="#a3938a", accent="#ff8a4c"),
    "forest": dict(label="Forest", bg="#0b100d", panel="#101612", text="#e7f0ea", muted="#89a093", accent="#7fc99a"),
    "rose": dict(label="Rose", bg="#110c0e", panel="#171114", text="#f2e8ec", muted="#a38a94", accent="#f08aa8"),
    "frost": dict(label="Frost", bg="#1b1f27", panel="#20252f", text="#e5e9f0", muted="#8f99ab", accent="#88c0d0"),
    "oled": dict(label="OLED black", bg="#000000", panel="#070707", text="#f0f0f0", muted="#8a8a8a", accent="#e0e0e0"),
    "light": dict(label="Light", bg="#f3f3f6", panel="#e9e9ee", text="#1b1b22", muted="#6b6b78", accent="#a8802f",
                  light=True),
}


def _mix(a, b, t):
    ca, cb = QColor(a), QColor(b)
    return QColor(int(ca.red() + (cb.red() - ca.red()) * t), int(ca.green() + (cb.green() - ca.green()) * t),
                  int(ca.blue() + (cb.blue() - ca.blue()) * t)).name()


def palette_for(key, accent=None):
    t = dict(THEMES.get(key) or THEMES["armory"])
    if accent and QColor(accent).isValid():
        t["accent"] = QColor(accent).name()
    light = t.get("light", False)
    acc = QColor(t["accent"])
    # text on the accent: dark on bright accents, white on dark ones
    on = "#16130d" if acc.lightnessF() > 0.55 else "#ffffff"
    return {
        "BG": t["bg"], "PANEL": t["panel"], "TEXT": t["text"], "MUTED": t["muted"],
        "DIM": _mix(t["muted"], t["bg"], 0.35), "SOFT": _mix(t["text"], t["muted"], 0.35),
        "ACCENT": t["accent"], "ACCENT_HI": acc.lighter(112).name(), "ACCENT_LO": acc.darker(115).name(),
        "ACCENT_DIS": _mix(t["accent"], t["bg"], 0.65), "ACCENT_RGB": f"{acc.red()},{acc.green()},{acc.blue()}",
        "ON_ACCENT": on, "FG": "0,0,0" if light else "255,255,255",
        "POPUP": _mix(t["bg"], "#ffffff" if not light else "#ffffff", 0.07 if not light else 0.9),
        "POPUP_LINE": _mix(t["bg"], t["text"], 0.16),
        "LIGHT": light, "CARD": t["panel"], "LINE": _mix(t["bg"], t["text"], 0.1),
        "GOOD": "#2f9e5a" if light else "#8fd6a2", "BAD": "#c94653" if light else "#e88b93",
        "PINK": "#c2468a" if light else "#ee93c8", "BLUE": "#2f6fc0" if light else "#8fb8ee", "FONT": FONT,
    }


FONT = "Inter Variable"
P = {}
# filled by set_palette(); these names are read when things are drawn, so they follow the theme
BG = PANEL = TEXT = MUTED = DIM = SOFT = ACCENT = ACCENT_HI = ACCENT_LO = ON_ACCENT = ""
POPUP = POPUP_LINE = LINE = CARD = GOOD = BAD = PINK = BLUE = ""
LIGHT = False


def set_palette(key=None, accent=None):
    """pick the theme (from the settings when not given); the module's colour names follow it"""
    from .. import config
    key = key or config.get("theme", "armory")
    accent = accent if accent is not None else config.get("accent", "")
    P.clear()
    P.update(palette_for(key, accent))
    g = globals()
    for k, v in P.items():
        g[k] = v
    return P


def stylesheet():
    return STYLE_TEMPLATE.format(**P)


P.update(palette_for("armory"))
globals().update(P)


STYLE_TEMPLATE = """
* {{ font-family: "{FONT}", "Inter", "Noto Sans", sans-serif; }}
QMainWindow, #root {{ background: {BG}; }}
QWidget#sidebar {{ background: {PANEL}; border-right: 1px solid rgba({FG},0.05); }}
QLabel {{ color: {TEXT}; background: transparent; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#small {{ color: {MUTED}; font-size: 11px; }}
QLabel#title {{ font-size: 24px; font-weight: 700; }}
QLabel#brand {{ font-size: 15px; font-weight: 800; letter-spacing: 3px; color: {TEXT}; }}
QLabel#section {{ color: {DIM}; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#count {{ color: {DIM}; font-size: 11px; font-weight: 600; }}
QLabel#prio {{ color: {DIM}; font-size: 11px; font-weight: 600; font-family: "JetBrains Mono", monospace; }}
QLabel#chipOk {{ background: rgba(120,200,140,0.13); color: {GOOD}; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; }}
QLabel#chipBad {{ background: rgba(224,108,117,0.15); color: {BAD}; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; }}
QLabel#chipBusy {{ background: rgba({ACCENT_RGB},0.15); color: {ACCENT}; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; }}
QLabel#chipGlass {{ background: rgba({FG},0.08); color: {SOFT}; border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600; }}
QLabel#badge {{ background: rgba({FG},0.06); color: {SOFT}; border-radius: 6px; padding: 2px 7px; font-size: 11px; font-weight: 500; }}
QLabel#badgeOld {{ background: rgba(224,108,117,0.14); color: {BAD}; border-radius: 6px; padding: 2px 7px; font-size: 11px; font-weight: 600; }}
QLabel#badgeOk {{ background: rgba(120,200,140,0.12); color: {GOOD}; border-radius: 6px; padding: 2px 7px; font-size: 11px; font-weight: 600; }}
QLabel#badgeNsfw {{ background: rgba(224,108,180,0.14); color: {PINK}; border-radius: 6px; padding: 2px 7px; font-size: 11px; font-weight: 600; }}
QLabel#badgeNexus {{ background: rgba(218,142,53,0.14); color: #f0a95a; border-radius: 6px; padding: 2px 7px; font-size: 11px; font-weight: 600; }}
QLabel#badgeTs {{ background: rgba(80,160,230,0.14); color: {BLUE}; border-radius: 6px; padding: 2px 7px; font-size: 11px; font-weight: 600; }}
QLabel#badgeWin {{ background: rgba({ACCENT_RGB},0.14); color: {ACCENT}; border-radius: 6px; padding: 2px 7px; font-size: 11px; font-weight: 600; }}
QFrame#notice {{ background: rgba({ACCENT_RGB},0.09); border: 1px solid rgba({ACCENT_RGB},0.28); border-radius: 12px; }}
QFrame#noticeBad {{ background: rgba(224,108,117,0.09); border: 1px solid rgba(224,108,117,0.3); border-radius: 12px; }}
QPushButton {{ background: rgba({FG},0.055); color: {TEXT}; border: 1px solid rgba({FG},0.07);
               border-radius: 9px; padding: 8px 14px; font-weight: 500; }}
QPushButton:hover {{ background: rgba({FG},0.09); border: 1px solid rgba({FG},0.11); }}
QPushButton:pressed {{ background: rgba({FG},0.04); }}
QPushButton:disabled {{ color: {DIM}; background: rgba({FG},0.03); }}
QPushButton#primary {{ background: {ACCENT}; color: {ON_ACCENT}; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: {ACCENT_HI}; }}
QPushButton#primary:pressed {{ background: {ACCENT_LO}; }}
QPushButton#primary:disabled {{ background: {ACCENT_DIS}; color: {ON_ACCENT}; }}
QPushButton#play {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {ACCENT_HI}, stop:1 {ACCENT_LO});
                    color: {ON_ACCENT}; border: none; font-weight: 800; font-size: 15px; letter-spacing: 1px;
                    padding: 12px 34px; border-radius: 12px; }}
QPushButton#play:hover {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {ACCENT_HI}, stop:1 {ACCENT}); }}
QPushButton#play:disabled {{ background: rgba({FG},0.08); color: {DIM}; }}
QPushButton#update {{ background: rgba(120,200,140,0.12); color: {GOOD}; border: 1px solid rgba(120,200,140,0.28);
                      border-radius: 6px; padding: 2px 9px; font-size: 11px; font-weight: 600; }}
QPushButton#update:hover {{ background: rgba(120,200,140,0.22); }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; padding: 2px 4px; }}
QPushButton#link:hover {{ color: {ACCENT_HI}; }}
QPushButton#seg {{ border-radius: 7px; padding: 6px 13px; background: transparent; border: none; color: {MUTED}; }}
QPushButton#seg:checked {{ background: rgba({FG},0.09); color: {TEXT}; }}
QPushButton#seg:hover:!checked {{ color: {TEXT}; }}
QPushButton#tab {{ background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0;
                   padding: 10px 4px 9px 4px; margin-right: 18px; color: {MUTED}; font-size: 14px; font-weight: 600; }}
QPushButton#tab:hover {{ color: {TEXT}; }}
QPushButton#tab:checked {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QPushButton#gameRow {{ text-align: left; border: none; background: transparent; border-radius: 10px; padding: 0; }}
QPushButton#gameRow:hover {{ background: rgba({FG},0.04); }}
QPushButton#gameRow:checked {{ background: rgba({ACCENT_RGB},0.11); }}
QPushButton#ghost {{ background: transparent; border: 1px dashed rgba({FG},0.12); color: {MUTED}; }}
QPushButton#ghost:hover {{ border: 1px dashed rgba({ACCENT_RGB},0.6); color: {TEXT}; background: rgba({ACCENT_RGB},0.05); }}
QToolButton {{ background: transparent; color: {MUTED}; border: none; border-radius: 8px; padding: 4px 8px; font-size: 16px; }}
QToolButton:hover {{ background: rgba({FG},0.08); color: {TEXT}; }}
QToolButton#glass {{ background: rgba({FG},0.08); border: 1px solid rgba({FG},0.08); border-radius: 12px;
                     padding: 8px 12px; color: {TEXT}; }}
QToolButton#glass:hover {{ background: rgba({FG},0.14); }}
QToolButton::menu-indicator {{ image: none; }}
QLineEdit, QComboBox, QSpinBox {{ background: rgba({FG},0.045); color: {TEXT}; border: 1px solid rgba({FG},0.07);
                                  border-radius: 9px; padding: 7px 12px; selection-background-color: {ACCENT}; selection-color: {ON_ACCENT}; }}
QLineEdit:hover, QComboBox:hover {{ border: 1px solid rgba({FG},0.12); }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid rgba({ACCENT_RGB},0.7); background: rgba({FG},0.06); }}
QComboBox#glass {{ background: rgba({FG},0.08); border: 1px solid rgba({FG},0.08); }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {POPUP}; color: {TEXT}; border: 1px solid {POPUP_LINE}; padding: 4px;
                               selection-background-color: rgba({FG},0.08); outline: none; }}
QCheckBox {{ color: {TEXT}; spacing: 8px; }}
QFrame#card, QFrame#tile {{ background: rgba({FG},0.032); border: 1px solid rgba({FG},0.055); border-radius: 13px; }}
QFrame#card:hover, QFrame#tile:hover {{ background: rgba({FG},0.055); border: 1px solid rgba({FG},0.09); }}
QFrame#cardOff {{ background: rgba({FG},0.015); border: 1px solid rgba({FG},0.035); border-radius: 13px; }}
QFrame#cardOff:hover {{ background: rgba({FG},0.035); border: 1px solid rgba({FG},0.07); }}
QFrame#panel {{ background: rgba({FG},0.035); border: 1px solid rgba({FG},0.06); border-radius: 14px; }}
QFrame#segbox {{ background: rgba({FG},0.035); border: 1px solid rgba({FG},0.06); border-radius: 10px; }}
QFrame#tabline {{ border: none; border-bottom: 1px solid rgba({FG},0.07); background: transparent; }}
QFrame#toast {{ background: {POPUP}; border: 1px solid rgba({FG},0.1); border-radius: 12px; }}
QScrollArea {{ background: transparent; border: none; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ background: transparent; border: none; padding: 0; }}
QListWidget::item:selected {{ background: transparent; }}
QListWidget#plain::item {{ padding: 7px 10px; border-radius: 8px; color: {TEXT}; }}
QListWidget#plain::item:selected {{ background: rgba({FG},0.08); }}
QListWidget#plain::item:hover {{ background: rgba({FG},0.05); }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba({FG},0.12); border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba({FG},0.2); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}
QMenu {{ background: {POPUP}; color: {TEXT}; border: 1px solid {POPUP_LINE}; border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba({FG},0.08); }}
QMenu::item:disabled {{ color: {DIM}; }}
QMenu::separator {{ height: 1px; background: rgba({FG},0.07); margin: 4px 8px; }}
QProgressBar {{ background: rgba({FG},0.07); border: none; border-radius: 3px; height: 6px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QDialog {{ background: {BG}; }}
QTextBrowser, QTreeWidget {{ background: rgba({FG},0.035); color: {TEXT}; border: 1px solid rgba({FG},0.06); border-radius: 10px; padding: 6px; }}
QHeaderView::section {{ background: transparent; color: {MUTED}; border: none; padding: 4px; font-weight: 600; }}
QToolTip {{ background: {POPUP}; color: {TEXT}; border: 1px solid {POPUP_LINE}; padding: 6px; border-radius: 6px; }}
QWidget#hero QLabel {{ color: #f2f2f6; }}
QWidget#hero QLabel#small {{ color: rgba(255,255,255,0.68); }}
QWidget#hero QLabel#section {{ color: rgba(255,255,255,0.55); }}
QWidget#hero QLabel#chipGlass {{ background: rgba(255,255,255,0.13); color: #f2f2f6; }}
QWidget#hero QComboBox#glass {{ background: rgba(20,20,26,0.45); color: #f2f2f6; border: 1px solid rgba(255,255,255,0.14); }}
QWidget#hero QToolButton {{ color: #f2f2f6; }}
QWidget#hero QToolButton#glass {{ background: rgba(20,20,26,0.45); border: 1px solid rgba(255,255,255,0.14); }}
QLabel#toastDot {{ background: {ACCENT}; border-radius: 4px; }}
QFrame#hline {{ background: rgba({FG},0.07); border: none; }}
QLabel#grip {{ color: {DIM}; font-size: 16px; }}
QLabel#modName {{ font-size: 14px; font-weight: 700; color: {TEXT}; }}
QLabel#modNameOff {{ font-size: 14px; font-weight: 700; color: {DIM}; }}
QLabel#gameName {{ font-weight: 600; font-size: 13px; color: {TEXT}; }}
QLabel#gameNameOff {{ font-weight: 600; font-size: 13px; color: {DIM}; }}
"""


FONT_FILE = os.path.join(os.path.dirname(ICON), "fonts", "InterVariable.ttf")


_started = False


def plain_message_boxes():
    """every QMessageBox shows its text as plain text: mod names in them come from mod sites"""
    from PyQt6.QtWidgets import QMessageBox
    B = QMessageBox.StandardButton

    def make(icon, default_buttons):
        def show(parent, title, text, buttons=default_buttons, default=B.NoButton):
            box = QMessageBox(icon, title, text, buttons, parent)
            box.setTextFormat(Qt.TextFormat.PlainText)
            if default != B.NoButton:
                box.setDefaultButton(default)
            return B(box.exec())
        return show

    QMessageBox.information = staticmethod(make(QMessageBox.Icon.Information, B.Ok))
    QMessageBox.warning = staticmethod(make(QMessageBox.Icon.Warning, B.Ok))
    QMessageBox.critical = staticmethod(make(QMessageBox.Icon.Critical, B.Ok))
    QMessageBox.question = staticmethod(make(QMessageBox.Icon.Question, B.Yes | B.No))


def apply(app, key=None, accent=None):
    """set up the app's look; later calls only change the colours (swapping the style or the font of a
    running app crashes Qt)"""
    global _started
    set_palette(key, accent)
    if not _started:
        _started = True
        plain_message_boxes()
        app.setStyle("Fusion")
        from PyQt6.QtGui import QFontDatabase
        if os.path.exists(FONT_FILE):
            QFontDatabase.addApplicationFont(FONT_FILE)
        f = QFont(FONT)
        f.setPixelSize(13)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(f)
    p = QPalette()
    for role, c in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
                    (QPalette.ColorRole.Base, POPUP), (QPalette.ColorRole.AlternateBase, PANEL),
                    (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, POPUP),
                    (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
                    (QPalette.ColorRole.HighlightedText, ON_ACCENT), (QPalette.ColorRole.ToolTipBase, POPUP),
                    (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.PlaceholderText, DIM),
                    (QPalette.ColorRole.Link, ACCENT)):
        p.setColor(role, QColor(c))
    app.setPalette(p)
    app.setStyleSheet(stylesheet())


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
        off, on = QColor(POPUP_LINE), QColor(ACCENT)
        t = self._pos
        track = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 13, 13)
        p.setBrush(QColor("#ffffff") if t > 0.5 else QColor(SOFT if not LIGHT else "#ffffff"))
        p.drawEllipse(QRectF(3 + (self.width() - 26) * t, 3, 20, 20))


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


def placeholder(name, w, h, r=10):
    """a tile with initials, for things without a picture"""
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    hue = sum(map(ord, name or "?")) % 360
    grad = QLinearGradient(0, 0, w, h)
    grad.setColorAt(0, QColor.fromHsl(hue, 55, 62))
    grad.setColorAt(1, QColor.fromHsl((hue + 35) % 360, 60, 26))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), r, r)
    p.fillPath(path, grad)
    initials = "".join(x[0] for x in re.findall(r"[A-Za-z0-9]+", name or "")[:2]).upper() or "?"
    f = QFont()
    f.setBold(True)
    f.setPixelSize(max(8, int(min(h, w * 0.6) * 0.38)))
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 200))
    p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, initials)
    p.end()
    return out


def label(text, name=None, wrap=False):
    l_ = QLabel(text)
    # names and summaries come from mod sites: never read them as HTML
    l_.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        l_.setObjectName(name)
    l_.setWordWrap(wrap)
    if name and name.startswith(("badge", "chip")):
        # a pill keeps its own height instead of filling the row
        l_.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return l_


def open_web(url):
    """open a web page from a mod site's data: only https/http, never other kinds of links"""
    import webbrowser
    if isinstance(url, str) and url.lower().startswith(("https://", "http://")):
        webbrowser.open(url)


def tip(text):
    """a tooltip for text from a mod site, escaped so it can't be HTML"""
    import html
    return "<p style='white-space:pre-wrap'>" + html.escape(text or "") + "</p>" if text else ""


def button(text, slot=None, name=None, tip=None):
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


def menu_button(menu, text="⋯", tip=None):
    b = QToolButton()
    b.setText(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    b.setMenu(menu)
    if tip:
        b.setToolTip(tip)
    return b


class Segments(QFrame):
    """a row of buttons where one is chosen"""
    def __init__(self, items, on_pick, current=None):
        super().__init__()
        self.setObjectName("segbox")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for key, text in items:
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: on_pick(k))
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b
        if items:
            self.set(current if current in self.buttons else items[0][0])

    def set(self, key):
        if key in self.buttons:
            self.buttons[key].setChecked(True)

    def set_text(self, key, text):
        if key in self.buttons:
            self.buttons[key].setText(text)

    def show_key(self, key, visible):
        if key in self.buttons:
            self.buttons[key].setVisible(visible)


class Tabs(QFrame):
    """page tabs: text with a line under the one that's open"""
    def __init__(self, items, on_pick, current=None):
        super().__init__()
        self.setObjectName("tabline")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QButtonGroup(self)
        self.buttons = {}
        self.names = dict(items)
        for key, text in items:
            b = QPushButton(text)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: on_pick(k))
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b
        self.trail = QHBoxLayout()
        self.trail.setSpacing(8)
        lay.addStretch(1)
        lay.addLayout(self.trail)
        if items:
            self.set(current if current in self.buttons else items[0][0])

    def set(self, key):
        if key in self.buttons:
            self.buttons[key].setChecked(True)

    def set_text(self, key, text):
        if key in self.buttons:
            self.buttons[key].setText(text)

    def show_key(self, key, visible):
        if key in self.buttons:
            self.buttons[key].setVisible(visible)


class Toast(QFrame):
    """a short message that rises at the bottom of the window and fades away"""
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 18, 10)
        lay.setSpacing(10)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.dot.setObjectName("toastDot")
        lay.addWidget(self.dot)
        self.text = QLabel()
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setStyleSheet("font-weight: 500;")
        lay.addWidget(self.text)
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        from PyQt6.QtCore import QTimer
        self.fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fx)
        self.fade = QPropertyAnimation(self.fx, b"opacity", self)
        self.fade.setDuration(220)
        self.fade.finished.connect(lambda: self.fx.opacity() < 0.05 and self.hide())
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        self.hide()

    def say(self, text, ms=4200):
        self.text.setText(text)
        self.adjustSize()
        self.place()
        self.raise_()
        self.show()
        self.fade.stop()
        self.fade.setStartValue(self.fx.opacity() if self.isVisible() else 0.0)
        self.fade.setEndValue(1.0)
        self.fade.start()
        self.timer.start(ms)

    def dismiss(self):
        self.fade.stop()
        self.fade.setStartValue(self.fx.opacity())
        self.fade.setEndValue(0.0)
        self.fade.start()

    def place(self):
        p = self.parentWidget()
        if p:
            w = min(self.sizeHint().width(), p.width() - 40)
            self.resize(w, self.sizeHint().height())
            self.move((p.width() - w) // 2, p.height() - self.height() - 22)


def blurred(pix, w, h):
    """a soft, blurred copy of a picture filling w x h (scaled down and up again)"""
    if pix.isNull() or w <= 0 or h <= 0:
        return QPixmap()
    fill = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    small = fill.scaled(max(1, w // 28), max(1, h // 28), Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    mid = small.scaled(max(1, w // 7), max(1, h // 7), Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    return mid.scaled(fill.width(), fill.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def restyle(w, name):
    w.setObjectName(name)
    w.setStyle(w.style())
