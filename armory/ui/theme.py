"""Colours, the stylesheet, and small shared widgets."""
import os
import re

from PyQt6.QtCore import QPropertyAnimation, QRectF, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPalette, QPixmap
from PyQt6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QToolButton)

ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "armory.svg")

BG = "#111115"
PANEL = "#16161b"
CARD = "#1b1b21"
LINE = "#26262e"
TEXT = "#e8e8ef"
MUTED = "#8a8a99"
ACCENT = "#c9a96e"
ACCENT_HI = "#d8b97f"
GOOD = "#8fd6a2"
BAD = "#e88b93"
PINK = "#ee93c8"
BLUE = "#8fb8ee"

STYLE = f"""
QMainWindow, #root {{ background: {BG}; }}
QWidget#sidebar {{ background: {PANEL}; border-right: 1px solid {LINE}; }}
QLabel {{ color: {TEXT}; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#small {{ color: {MUTED}; font-size: 11px; }}
QLabel#title {{ font-size: 22px; font-weight: 700; }}
QLabel#brand {{ font-size: 18px; font-weight: 800; letter-spacing: 1px; }}
QLabel#section {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#h2 {{ font-size: 16px; font-weight: 700; }}
QLabel#chipOk {{ background: rgba(120,200,140,0.14); color: {GOOD}; border-radius: 9px; padding: 3px 10px; font-size: 11px; }}
QLabel#chipBad {{ background: rgba(224,108,117,0.16); color: {BAD}; border-radius: 9px; padding: 3px 10px; font-size: 11px; }}
QLabel#chipBusy {{ background: rgba(201,169,110,0.16); color: {ACCENT}; border-radius: 9px; padding: 3px 10px; font-size: 11px; }}
QLabel#badge {{ background: #2a2a33; color: #c8c8d4; border-radius: 7px; padding: 2px 8px; font-size: 11px; }}
QLabel#badgeOld {{ background: rgba(224,108,117,0.18); color: {BAD}; border-radius: 7px; padding: 2px 8px; font-size: 11px; }}
QLabel#badgeOk {{ background: rgba(120,200,140,0.14); color: {GOOD}; border-radius: 7px; padding: 2px 8px; font-size: 11px; }}
QLabel#badgeNsfw {{ background: rgba(224,108,180,0.16); color: {PINK}; border-radius: 7px; padding: 2px 8px; font-size: 11px; }}
QLabel#badgeNexus {{ background: rgba(218,142,53,0.16); color: #f0a95a; border-radius: 7px; padding: 2px 8px; font-size: 11px; }}
QLabel#badgeTs {{ background: rgba(80,160,230,0.16); color: {BLUE}; border-radius: 7px; padding: 2px 8px; font-size: 11px; }}
QLabel#badgeWin {{ background: rgba(201,169,110,0.16); color: {ACCENT}; border-radius: 7px; padding: 2px 8px; font-size: 11px; }}
QFrame#notice {{ background: rgba(201,169,110,0.10); border: 1px solid rgba(201,169,110,0.35); border-radius: 10px; }}
QFrame#noticeBad {{ background: rgba(224,108,117,0.10); border: 1px solid rgba(224,108,117,0.35); border-radius: 10px; }}
QPushButton {{ background: #24242c; color: {TEXT}; border: 1px solid #30303a; border-radius: 9px; padding: 8px 14px; }}
QPushButton:hover {{ background: #2c2c36; }}
QPushButton:disabled {{ color: #5c5c68; background: #1d1d23; }}
QPushButton#primary {{ background: {ACCENT}; color: #17171c; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: {ACCENT_HI}; }}
QPushButton#primary:disabled {{ background: #5a4d36; color: #2a2a2a; }}
QPushButton#play {{ background: {ACCENT}; color: #17171c; border: none; font-weight: 800; font-size: 15px;
                    padding: 10px 26px; border-radius: 11px; }}
QPushButton#play:hover {{ background: {ACCENT_HI}; }}
QPushButton#update {{ background: rgba(120,200,140,0.14); color: {GOOD}; border: 1px solid rgba(120,200,140,0.3);
                      border-radius: 7px; padding: 2px 10px; font-size: 11px; }}
QPushButton#update:hover {{ background: rgba(120,200,140,0.24); }}
QPushButton#link {{ background: transparent; border: none; color: {ACCENT}; padding: 2px 4px; }}
QPushButton#link:hover {{ color: {ACCENT_HI}; text-decoration: underline; }}
QPushButton#seg {{ border-radius: 8px; padding: 6px 14px; background: transparent; border: 1px solid transparent; color: #a0a0ad; }}
QPushButton#seg:checked {{ background: #2a2a33; color: {TEXT}; border: 1px solid #36363f; }}
QPushButton#seg:hover:!checked {{ color: {TEXT}; }}
QPushButton#gameRow {{ text-align: left; border: 1px solid transparent; background: transparent; border-radius: 10px; padding: 0; }}
QPushButton#gameRow:hover {{ background: #1f1f26; }}
QPushButton#gameRow:checked {{ background: #24242c; border: 1px solid #33333d; }}
QToolButton {{ background: transparent; color: #a0a0ad; border: none; border-radius: 8px; padding: 4px 8px; font-size: 16px; }}
QToolButton:hover {{ background: #2a2a33; color: {TEXT}; }}
QToolButton::menu-indicator {{ image: none; }}
QLineEdit, QComboBox, QSpinBox {{ background: #1c1c22; color: {TEXT}; border: 1px solid #2a2a33; border-radius: 10px; padding: 7px 12px; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: #1f1f26; color: {TEXT}; border: 1px solid #30303a; selection-background-color: #2c2c36; }}
QCheckBox {{ color: {TEXT}; spacing: 8px; }}
QFrame#card, QFrame#tile {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; }}
QFrame#card:hover, QFrame#tile:hover {{ background: #202027; border: 1px solid #30303a; }}
QFrame#panel {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; }}
QFrame#segbox {{ background: #1c1c22; border: 1px solid #2a2a33; border-radius: 10px; }}
QScrollArea {{ background: transparent; border: none; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ background: transparent; border: none; padding: 0; }}
QListWidget::item:selected {{ background: transparent; }}
QListWidget#plain::item {{ padding: 6px 8px; border-radius: 8px; color: {TEXT}; }}
QListWidget#plain::item:selected {{ background: #2a2a33; }}
QListWidget#plain::item:hover {{ background: #22222a; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2e2e38; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 0; }}
QMenu {{ background: #1f1f26; color: {TEXT}; border: 1px solid #30303a; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: #2c2c36; }}
QMenu::item:disabled {{ color: #5c5c68; }}
QMenu::separator {{ height: 1px; background: #2c2c36; margin: 4px 8px; }}
QProgressBar {{ background: #24242c; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QDialog {{ background: {BG}; }}
QTabWidget::pane {{ border: none; }}
QTextBrowser {{ background: #1c1c22; color: {TEXT}; border: 1px solid #2a2a33; border-radius: 10px; padding: 8px; }}
QToolTip {{ background: #24242c; color: {TEXT}; border: 1px solid #36363f; padding: 6px; }}
"""


def apply(app):
    app.setStyle("Fusion")
    p = QPalette()
    for role, c in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
                    (QPalette.ColorRole.Base, "#1c1c22"), (QPalette.ColorRole.AlternateBase, "#24242c"),
                    (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, "#24242c"),
                    (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
                    (QPalette.ColorRole.HighlightedText, "#17171c"), (QPalette.ColorRole.ToolTipBase, "#24242c"),
                    (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.PlaceholderText, "#6f6f7c"),
                    (QPalette.ColorRole.Link, ACCENT)):
        p.setColor(role, QColor(c))
    app.setPalette(p)
    app.setStyleSheet(STYLE)


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
        off, on = QColor("#3a3a45"), QColor(ACCENT)
        t = self._pos
        track = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 13, 13)
        p.setBrush(QColor("#ffffff") if t > 0.5 else QColor("#c8c8d4"))
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
    grad.setColorAt(0, QColor.fromHsl(hue, 70, 70))
    grad.setColorAt(1, QColor.fromHsl((hue + 40) % 360, 80, 40))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), r, r)
    p.fillPath(path, grad)
    initials = "".join(x[0] for x in re.findall(r"[A-Za-z0-9]+", name or "")[:2]).upper() or "?"
    f = QFont()
    f.setBold(True)
    f.setPixelSize(max(8, int(min(h, w * 0.6) * 0.38)))
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 220))
    p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, initials)
    p.end()
    return out


def label(text, name=None, wrap=False):
    l_ = QLabel(text)
    if name:
        l_.setObjectName(name)
    l_.setWordWrap(wrap)
    if name and name.startswith(("badge", "chip")):
        # a pill keeps its own height instead of filling the row
        l_.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return l_


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


def restyle(w, name):
    w.setObjectName(name)
    w.setStyle(w.style())
