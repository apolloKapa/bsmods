"""Animations: cross-fades between views, and small helpers. Settings → Appearance → Animations
turns them all off.

Cross-fades use a picture of the old view laid over the new one and faded out, instead of fading
the views themselves: Qt can't nest opacity effects (the cards already use one for mods that are off).
"""
from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QParallelAnimationGroup, Qt, QVariantAnimation
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel

from .. import config

FAST = 160
NORMAL = 240
EASE = QEasingCurve.Type.OutCubic


def enabled():
    return config.get("animations", True) is not False


_overlays = {}


def crossfade(widget, change, slide=0, duration=NORMAL):
    """run change() (which updates widget) and fade from how widget looked before to how it looks now;
    slide: pixels the old picture drifts sideways while it fades (negative = left)"""
    if not enabled() or not widget.isVisible() or widget.width() < 2 or widget.parentWidget() is None:
        change()
        return
    old = _overlays.pop(id(widget), None)
    if old is not None:
        try:
            old[1].stop()
            old[0].deleteLater()
        except RuntimeError:
            pass
    pix = widget.grab()
    parent = widget.parentWidget()
    shot = QLabel(parent)
    shot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    shot.setPixmap(pix)
    shot.setGeometry(widget.geometry())
    change()
    shot.show()
    shot.raise_()
    fx = QGraphicsOpacityEffect(shot)
    shot.setGraphicsEffect(fx)
    group = QParallelAnimationGroup(shot)
    fade = QPropertyAnimation(fx, b"opacity")
    fade.setDuration(duration)
    fade.setStartValue(1.0)
    fade.setEndValue(0.0)
    fade.setEasingCurve(EASE)
    group.addAnimation(fade)
    if slide:
        move = QPropertyAnimation(shot, b"pos")
        move.setDuration(duration)
        start = shot.pos()
        move.setStartValue(start)
        move.setEndValue(start + QPoint(slide, 0))
        move.setEasingCurve(EASE)
        group.addAnimation(move)

    def done():
        _overlays.pop(id(widget), None)
        shot.deleteLater()

    group.finished.connect(done)
    _overlays[id(widget)] = (shot, group)
    group.start()


def tween(owner, start, end, step, duration=NORMAL, easing=EASE, done=None):
    """call step(value) from start to end over duration (values are numbers, QRectF, QColor...);
    without animations it jumps straight to end. Returns the animation (or None)."""
    if not enabled():
        step(end)
        if done:
            done()
        return None
    a = QVariantAnimation(owner)
    a.setDuration(duration)
    a.setStartValue(start)
    a.setEndValue(end)
    a.setEasingCurve(easing)
    a.valueChanged.connect(step)
    if done:
        a.finished.connect(done)
    a.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    return a
