"""Video display with mouse picking.

The video item is sized to the video's native resolution and the view scales the whole
scene to fit the widget. Scene coordinates are therefore video pixels, so a mouse click
mapped with mapToScene() already accounts for scaling and letterboxing.
"""

from __future__ import annotations

from dataclasses import astuple
from typing import List

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from . import textfit
from .models import BLUR, Annotation

CLICK_THRESHOLD_PX = 4  # smaller drags count as a click


def _cosmetic_pen(color: str, width: int = 2, dashed: bool = False) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidth(width)
    pen.setCosmetic(True)  # constant on-screen width regardless of zoom
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    return pen


class VideoView(QGraphicsView):
    # x, y, w, h in video pixels. w == h == 0 means a plain click.
    regionSelected = Signal(int, int, int, int)

    def __init__(self, parent=None):
        self._scene = QGraphicsScene()
        super().__init__(self._scene, parent)

        self.video_item = QGraphicsVideoItem()
        self._scene.addItem(self.video_item)
        self.video_item.nativeSizeChanged.connect(self._on_native_size)

        self.setBackgroundBrush(QBrush(Qt.GlobalColor.black))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumSize(320, 180)

        self._video_size = QSizeF()
        self._drag_start = None
        self._overlay_items: list = []
        self._overlay_key = None

        self._selection = QGraphicsRectItem()
        self._selection.setPen(_cosmetic_pen("#ffd400"))
        self._selection.setBrush(QBrush(QColor(255, 212, 0, 40)))
        self._selection.setZValue(100)
        self._selection.hide()
        self._scene.addItem(self._selection)

    # ---- geometry -------------------------------------------------------------------
    def video_size(self) -> QSizeF:
        return self._video_size

    def _on_native_size(self, size: QSizeF) -> None:
        if size.isEmpty():
            return
        self._video_size = QSizeF(size)
        self.video_item.setSize(size)
        self._scene.setSceneRect(QRectF(QPointF(0, 0), size))
        self._fit()

    def _fit(self) -> None:
        if not self._video_size.isEmpty():
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit()

    def _clamp(self, p: QPointF) -> QPointF:
        return QPointF(
            min(max(p.x(), 0.0), self._video_size.width()),
            min(max(p.y(), 0.0), self._video_size.height()),
        )

    # ---- mouse picking --------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._video_size.isEmpty():
            self._drag_start = self._clamp(self.mapToScene(event.position().toPoint()))
            self._show_selection(QRectF(self._drag_start, QSizeF(0, 0)))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None:
            cur = self._clamp(self.mapToScene(event.position().toPoint()))
            self._show_selection(QRectF(self._drag_start, cur).normalized())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_start is not None and event.button() == Qt.MouseButton.LeftButton:
            cur = self._clamp(self.mapToScene(event.position().toPoint()))
            rect = QRectF(self._drag_start, cur).normalized()
            start = self._drag_start
            self._drag_start = None
            if rect.width() < CLICK_THRESHOLD_PX and rect.height() < CLICK_THRESHOLD_PX:
                x, y = round(start.x()), round(start.y())
                self._show_selection(QRectF(x - 6, y - 6, 12, 12))
                self.regionSelected.emit(x, y, 0, 0)
            else:
                x, y = round(rect.x()), round(rect.y())
                w, h = round(rect.width()), round(rect.height())
                self._show_selection(QRectF(x, y, w, h))
                self.regionSelected.emit(x, y, w, h)
        super().mouseReleaseEvent(event)

    def _show_selection(self, rect: QRectF) -> None:
        self._selection.setRect(rect)
        self._selection.show()

    def show_selection(self, x: int, y: int, w: int, h: int) -> None:
        """Programmatically highlight a region (used when picking a row in the list)."""
        if w > 0 and h > 0:
            self._show_selection(QRectF(x, y, w, h))
        else:
            self._show_selection(QRectF(x - 6, y - 6, 12, 12))

    # ---- annotation preview ---------------------------------------------------------
    def set_overlays(self, annotations: List[Annotation]) -> None:
        """Draw the annotations that are active at the current playback time."""
        key = tuple(astuple(a) for a in annotations)
        if key == self._overlay_key:
            return
        self._overlay_key = key
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items.clear()

        for a in annotations:
            if a.kind == BLUR:
                rect = QGraphicsRectItem(a.x, a.y, a.w, a.h)
                rect.setBrush(QBrush(QColor(80, 160, 255, 80)))
                rect.setPen(_cosmetic_pen("#50a0ff", 2, dashed=True))
                rect.setZValue(50)
                self._scene.addItem(rect)
                self._overlay_items.append(rect)
            else:
                self._add_text_overlay(a)

    def _add_text_overlay(self, a: Annotation) -> None:
        res = textfit.fit_text(a.text, a.w, a.h)
        bg = QGraphicsRectItem(a.x, a.y, a.w, a.h)
        bg.setBrush(QBrush(QColor(0, 0, 0, 128)))
        bg.setPen(QPen(Qt.PenStyle.NoPen))
        bg.setZValue(51)
        items = [bg]
        if not res.fits:
            outline = QGraphicsRectItem(a.x, a.y, a.w, a.h)
            outline.setPen(_cosmetic_pen("#ff4040", 2, dashed=True))
            outline.setZValue(53)
            items.append(outline)
        font = QFont(textfit.resolve_font().family)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPixelSize(res.size)
        line_h = textfit.line_height(res.size)
        for i, line in enumerate(res.lines):  # one item per line: same pitch as annotate.sh
            label = QGraphicsSimpleTextItem(line)
            label.setFont(font)
            label.setBrush(QBrush(Qt.GlobalColor.white))
            label.setPos(a.x + textfit.PAD, a.y + textfit.PAD + i * line_h)
            label.setZValue(52)
            items.append(label)
        for item in items:
            self._scene.addItem(item)
            self._overlay_items.append(item)
