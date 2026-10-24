"""Video display with mouse picking and on-canvas editing.

The video item is sized to the video's native resolution and the view scales the whole
scene to fit the widget. Scene coordinates are therefore video pixels, so a mouse click
mapped with mapToScene() already accounts for scaling and letterboxing.

Two mouse modes: draw (drag a new region, or a line when the arrow tool is on) and select
(click an annotation, drag it, resize it with the handles; an arrow has a handle on each end
point). Geometry changes are reported on mouse release.
"""

from __future__ import annotations

from dataclasses import astuple
from typing import List, Optional, Tuple

from PySide6.QtCore import QLineF, QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen, QPolygonF
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from . import arrowgeom, colors, textfit
from .models import ARROW, BLUR, TEXT, Annotation

CLICK_THRESHOLD_PX = 4  # smaller drags count as a click
MIN_BOX_PX = 10  # smallest box when resizing on the canvas
HANDLE_PX = 8  # handle size on screen
HANDLE_HIT_PX = 6  # hit distance from a handle centre, on screen
ARROW_HIT_PX = 8  # minimum hit distance from an arrow line, on screen
SEL_FILL_ALPHA = 40  # selection fill while the annotation is active at the playhead
SEL_DIM_FILL_ALPHA = 15  # selection fill while it is not
SEL_DIM_PEN_ALPHA = 120
SEL_DIM_HANDLE_OPACITY = 0.5

HANDLES = ("tl", "t", "tr", "r", "br", "b", "bl", "l")
ARROW_HANDLES = ("p1", "p2")  # start and end point of a selected arrow
_HANDLE_CURSORS = {
    "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
    "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
    "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
    "p1": Qt.CursorShape.SizeAllCursor, "p2": Qt.CursorShape.SizeAllCursor,
}


def _cosmetic_pen(color: str, width: int = 2, dashed: bool = False) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidth(width)
    pen.setCosmetic(True)  # constant on-screen width regardless of zoom
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    return pen


def _dim_pen() -> QPen:
    pen = _cosmetic_pen("#ffd400", 2, dashed=True)
    color = pen.color()
    color.setAlpha(SEL_DIM_PEN_ALPHA)
    pen.setColor(color)
    return pen


def _highlight_item() -> QGraphicsRectItem:
    item = QGraphicsRectItem()
    item.setPen(_cosmetic_pen("#ffd400"))
    item.setBrush(QBrush(QColor(255, 212, 0, SEL_FILL_ALPHA)))
    item.setZValue(100)
    item.hide()
    return item


def _line_item() -> QGraphicsLineItem:
    item = QGraphicsLineItem()
    item.setPen(_cosmetic_pen("#ffd400"))
    item.setZValue(100)
    item.hide()
    return item


def _clamp_delta(d: int, lo: int, hi: int) -> int:
    return d if lo > hi else min(max(d, lo), hi)


def _handle_point(rect: QRectF, name: str) -> QPointF:
    cx, cy = rect.center().x(), rect.center().y()
    x = rect.left() if "l" in name else rect.right() if "r" in name else cx
    y = rect.top() if "t" in name else rect.bottom() if "b" in name else cy
    return QPointF(x, y)


class VideoView(QGraphicsView):
    # x, y, w, h in video pixels. w == h == 0 means a plain click.
    regionSelected = Signal(int, int, int, int)
    # index into the full annotation list
    annotationPicked = Signal(int)
    # index, x, y, w, h in whole video pixels
    geometryEdited = Signal(int, int, int, int, int)
    # draw mode with the arrow tool: x1, y1, x2, y2 in whole video pixels
    lineSelected = Signal(int, int, int, int)
    # index, x1, y1, x2, y2 in whole video pixels
    arrowEdited = Signal(int, int, int, int, int)
    # draw mode: a new drag started, so the previous marker is stale
    dragStarted = Signal()

    def __init__(self, parent=None):
        self._scene = QGraphicsScene()
        super().__init__(self._scene, parent)
        # redraw the whole canvas on every change: no pixel trails from cosmetic pens/handles
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        self.video_item = QGraphicsVideoItem()
        self._scene.addItem(self.video_item)
        self.video_item.nativeSizeChanged.connect(self._on_native_size)

        self.setBackgroundBrush(QBrush(Qt.GlobalColor.black))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setMouseTracking(True)
        self.setMinimumSize(320, 180)

        self._video_size = QSizeF()
        self._select_mode = False
        self._draw_line = False  # draw mode: drag a line (arrow) instead of a rectangle
        self._drag_start = None  # draw mode: scene point where the rubber band started
        self._edit: Optional[dict] = None  # select mode: drag in progress
        self._overlays_visible = True
        self._overlay_items: list = []
        self._overlay_hits: List[Tuple[int, Annotation]] = []
        self._overlay_key = None

        self._sel_index: Optional[int] = None
        self._sel_rect: Optional[QRectF] = None
        self._sel_arrow: Optional[Tuple[int, int, int, int]] = None  # x1, y1, x2, y2
        self._sel_dim = False  # selected annotation is not active at the playhead
        self._pen_solid = _cosmetic_pen("#ffd400")
        self._pen_dim = _dim_pen()
        self._brush_solid = QBrush(QColor(255, 212, 0, SEL_FILL_ALPHA))
        self._brush_dim = QBrush(QColor(255, 212, 0, SEL_DIM_FILL_ALPHA))
        self._selection = _highlight_item()  # highlight of the selected annotation
        self._scene.addItem(self._selection)
        self._sel_line = _line_item()  # highlight of the selected arrow
        self._scene.addItem(self._sel_line)
        self._rubber = _highlight_item()  # draw mode: region being dragged / last click
        self._scene.addItem(self._rubber)
        self._rubber_line = _line_item()  # draw mode with the arrow tool: line being dragged
        self._scene.addItem(self._rubber_line)
        self._handles = {}
        for name in HANDLES + ARROW_HANDLES:
            h = QGraphicsRectItem(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX)
            h.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            h.setBrush(QBrush(QColor("#ffd400")))
            h.setPen(_cosmetic_pen("#000000", 1))
            h.setZValue(101)
            h.hide()
            self._scene.addItem(h)
            self._handles[name] = h
        self._update_cursor()

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

    # ---- mode -----------------------------------------------------------------------
    @property
    def mode(self) -> str:
        return "select" if self._select_mode else "draw"

    def set_mode(self, select: bool) -> None:
        """Switch between select (True) and draw (False) mode; cancels any drag in progress."""
        self._cancel_drag()
        self._select_mode = select
        self._rubber.hide()
        self._rubber_line.hide()
        self._refresh_selection_items()
        self._update_cursor()

    def set_draw_line(self, enabled: bool) -> None:
        """Draw mode: drag a line (the arrow tool) instead of a rectangle."""
        if enabled != self._draw_line:
            self._cancel_drag()
            self._draw_line = enabled
            self._refresh_selection_items()

    def _cancel_drag(self) -> None:
        self._drag_start = None
        if self._edit is not None:
            if self._edit["orig"] is not None:
                self._sel_rect = QRectF(self._edit["orig"])
            self._sel_arrow = self._edit["orig_arrow"]
            self._edit = None
        self._rubber.hide()
        self._rubber_line.hide()
        self._refresh_selection_items()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and (self._drag_start is not None
                                                 or self._edit is not None):
            self._cancel_drag()
            event.accept()
            return
        super().keyPressEvent(event)

    def _update_cursor(self, handle: Optional[str] = None) -> None:
        if handle is not None:
            shape = _HANDLE_CURSORS[handle]
        elif self._select_mode:
            shape = Qt.CursorShape.ArrowCursor
        else:
            shape = Qt.CursorShape.CrossCursor
        self.viewport().setCursor(shape)

    # ---- mouse handling -------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._video_size.isEmpty():
            pos = event.position().toPoint()
            if self._select_mode:
                self._select_press(pos)
            else:
                self._drag_start = self._clamp(self.mapToScene(pos))
                self.dragStarted.emit()
                self._selection.hide()
                self._sel_line.hide()
                for h in self._handles.values():
                    h.hide()
                if self._draw_line:
                    self._rubber_line.setLine(QLineF(self._drag_start, self._drag_start))
                    self._rubber_line.show()
                else:
                    self._show_rubber(QRectF(self._drag_start, QSizeF(0, 0)))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if self._select_mode:
            if self._edit is not None:
                self._edit_move(self.mapToScene(pos))
            elif not event.buttons():
                self._update_cursor(self._hit_handle(pos))
        elif self._drag_start is not None:
            cur = self._clamp(self.mapToScene(pos))
            if self._draw_line:  # not normalised: the start stays where the drag began
                self._rubber_line.setLine(QLineF(self._drag_start, cur))
            else:
                self._show_rubber(QRectF(self._drag_start, cur).normalized())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._edit is not None:
                self._edit_release()
            elif self._drag_start is not None:
                self._draw_release(self.mapToScene(event.position().toPoint()))
        super().mouseReleaseEvent(event)

    def _draw_release(self, scene_pos: QPointF) -> None:
        cur = self._clamp(scene_pos)
        rect = QRectF(self._drag_start, cur).normalized()
        start = self._drag_start
        self._drag_start = None
        self.set_marker(None)  # the main window draws the final marker from the form
        self._refresh_selection_items()
        if self._draw_line and (rect.width() >= CLICK_THRESHOLD_PX
                                or rect.height() >= CLICK_THRESHOLD_PX):
            x1, y1, x2, y2 = round(start.x()), round(start.y()), round(cur.x()), round(cur.y())
            self.lineSelected.emit(x1, y1, x2, y2)
            return
        if rect.width() < CLICK_THRESHOLD_PX and rect.height() < CLICK_THRESHOLD_PX:
            self.regionSelected.emit(round(start.x()), round(start.y()), 0, 0)
        else:
            self.regionSelected.emit(round(rect.x()), round(rect.y()),
                                     round(rect.width()), round(rect.height()))

    def _show_rubber(self, rect: QRectF) -> None:
        self._rubber.setRect(rect)
        self._rubber.show()

    def set_marker(self, shape: Optional[Tuple[str, Tuple[float, ...]]]) -> None:
        """Show the yellow "new" marker: None hides it, ("rect", (x, y, w, h)) a rectangle,
        ("line", (x1, y1, x2, y2)) a line."""
        self._rubber.hide()
        self._rubber_line.hide()
        if shape is None:
            return
        kind, values = shape
        if kind == "rect":
            self._show_rubber(QRectF(*values))
        elif kind == "line":
            self._rubber_line.setLine(*values)
            self._rubber_line.show()

    # ---- select mode ----------------------------------------------------------------
    def _selection_visible(self) -> bool:
        return self._overlays_visible and (self._sel_rect is not None
                                           or self._sel_arrow is not None)

    def _handle_scene_point(self, name: str) -> QPointF:
        if self._sel_arrow is not None:
            x1, y1, x2, y2 = self._sel_arrow
            return QPointF(x1, y1) if name == "p1" else QPointF(x2, y2)
        return _handle_point(self._sel_rect, name)

    def _hit_handle(self, pos) -> Optional[str]:
        if not self._selection_visible():
            return None
        names = ARROW_HANDLES if self._sel_arrow is not None else HANDLES
        for name in names:
            p = self.mapFromScene(self._handle_scene_point(name))
            if abs(p.x() - pos.x()) <= HANDLE_HIT_PX and abs(p.y() - pos.y()) <= HANDLE_HIT_PX:
                return name
        return None

    def _arrow_hit_distance(self, thickness: float) -> float:
        scale = self.transform().m11() or 1.0
        return max(thickness / 2, ARROW_HIT_PX / scale)

    def _boxes_at(self, scene_pos: QPointF) -> List[int]:
        """Indices of the visible active overlays under the point, topmost first."""
        if not self._overlays_visible:
            return []
        hits = []
        for i, a in reversed(self._overlay_hits):
            if a.kind == ARROW:
                d = arrowgeom.distance_to_segment(scene_pos.x(), scene_pos.y(),
                                                  a.x, a.y, a.x2, a.y2)
                if d <= self._arrow_hit_distance(a.thickness):
                    hits.append(i)
            elif QRectF(a.x, a.y, a.w, a.h).contains(scene_pos):
                hits.append(i)
        return hits

    def _selection_contains(self, scene_pos: QPointF) -> bool:
        if self._sel_arrow is not None:
            thickness = next((a.thickness for i, a in self._overlay_hits
                              if i == self._sel_index and a.kind == ARROW), 0)
            x1, y1, x2, y2 = self._sel_arrow
            d = arrowgeom.distance_to_segment(scene_pos.x(), scene_pos.y(), x1, y1, x2, y2)
            return d <= self._arrow_hit_distance(thickness)
        return self._sel_rect.contains(scene_pos)

    def _begin_edit(self, mode: str, scene_pos: QPointF) -> None:
        self._edit = {
            "mode": mode, "index": self._sel_index, "start": scene_pos,
            "orig": QRectF(self._sel_rect) if self._sel_rect is not None else None,
            "orig_arrow": self._sel_arrow, "moved": False, "hits": [],
        }

    def _select_press(self, pos) -> None:
        scene_pos = self.mapToScene(pos)
        handle = self._hit_handle(pos)
        if handle is not None:
            self._begin_edit(handle, scene_pos)
            return
        hits = self._boxes_at(scene_pos)
        if self._selection_visible() and self._selection_contains(scene_pos):
            self._begin_edit("move", scene_pos)
            self._edit["hits"] = hits  # a click without a drag cycles through these
            return
        if hits:
            self.annotationPicked.emit(hits[0])
            if self._sel_index == hits[0] and self._selection_visible():
                self._begin_edit("move", scene_pos)

    def _edit_rect(self, scene_pos: QPointF) -> QRectF:
        e = self._edit
        orig: QRectF = e["orig"]
        dx = scene_pos.x() - e["start"].x()
        dy = scene_pos.y() - e["start"].y()
        vw, vh = int(self._video_size.width()), int(self._video_size.height())
        if e["mode"] == "move":
            w, h = round(orig.width()), round(orig.height())
            x = min(max(round(orig.x() + dx), 0), max(vw - w, 0))
            y = min(max(round(orig.y() + dy), 0), max(vh - h, 0))
            return QRectF(x, y, w, h)
        left, top = round(orig.left()), round(orig.top())
        right, bottom = round(orig.right()), round(orig.bottom())
        name = e["mode"]
        if "l" in name:
            left = min(max(round(orig.left() + dx), 0), right - MIN_BOX_PX)
        if "r" in name:
            right = max(min(round(orig.right() + dx), vw), left + MIN_BOX_PX)
        if "t" in name:
            top = min(max(round(orig.top() + dy), 0), bottom - MIN_BOX_PX)
        if "b" in name:
            bottom = max(min(round(orig.bottom() + dy), vh), top + MIN_BOX_PX)
        return QRectF(left, top, right - left, bottom - top)

    def _edit_arrow(self, scene_pos: QPointF) -> Tuple[int, int, int, int]:
        """New end points while dragging: both stay inside the frame and never coincide."""
        e = self._edit
        x1, y1, x2, y2 = e["orig_arrow"]
        dx = round(scene_pos.x() - e["start"].x())
        dy = round(scene_pos.y() - e["start"].y())
        vw, vh = int(self._video_size.width()), int(self._video_size.height())
        if e["mode"] == "move":
            dx = _clamp_delta(dx, -min(x1, x2), vw - max(x1, x2))
            dy = _clamp_delta(dy, -min(y1, y2), vh - max(y1, y2))
            return x1 + dx, y1 + dy, x2 + dx, y2 + dy
        if e["mode"] == "p1":
            nx, ny = min(max(x1 + dx, 0), vw), min(max(y1 + dy, 0), vh)
            return (nx, ny, x2, y2) if (nx, ny) != (x2, y2) else (x1, y1, x2, y2)
        nx, ny = min(max(x2 + dx, 0), vw), min(max(y2 + dy, 0), vh)
        return (x1, y1, nx, ny) if (nx, ny) != (x1, y1) else (x1, y1, x2, y2)

    def _edit_move(self, scene_pos: QPointF) -> None:
        e = self._edit
        if not e["moved"]:
            start_view = self.mapFromScene(e["start"])
            cur_view = self.mapFromScene(scene_pos)
            if (abs(cur_view.x() - start_view.x()) < CLICK_THRESHOLD_PX
                    and abs(cur_view.y() - start_view.y()) < CLICK_THRESHOLD_PX):
                return
            e["moved"] = True
        if e["orig_arrow"] is not None:
            self._sel_arrow = self._edit_arrow(scene_pos)
        else:
            self._sel_rect = self._edit_rect(scene_pos)
        self._refresh_selection_items()

    def _edit_release(self) -> None:
        e = self._edit
        self._edit = None
        if not e["moved"]:
            hits = e["hits"]
            if len(hits) > 1 and e["index"] in hits:
                nxt = hits[(hits.index(e["index"]) + 1) % len(hits)]
                self.annotationPicked.emit(nxt)
            return
        if e["orig_arrow"] is not None:
            if self._sel_arrow != e["orig_arrow"]:
                self.arrowEdited.emit(e["index"], *self._sel_arrow)
            else:
                self._refresh_selection_items()
            return
        rect = self._sel_rect
        if rect != e["orig"]:
            self.geometryEdited.emit(e["index"], round(rect.x()), round(rect.y()),
                                     round(rect.width()), round(rect.height()))
        else:
            self._refresh_selection_items()

    # ---- selection ------------------------------------------------------------------
    def set_selected(self, index: Optional[int], rect: Optional[QRectF],
                     arrow: Optional[Tuple[int, int, int, int]] = None) -> None:
        """Highlight the annotation `index`: a box (`rect`) or an arrow (`arrow` = x1, y1, x2,
        y2); None clears the selection."""
        self._edit = None
        if index is None or (rect is None and arrow is None):
            self._sel_index, self._sel_rect, self._sel_arrow = None, None, None
        elif arrow is not None:
            self._sel_index, self._sel_rect, self._sel_arrow = index, None, tuple(arrow)
        else:
            self._sel_index, self._sel_rect, self._sel_arrow = index, QRectF(rect), None
        self._refresh_selection_items()

    def _refresh_selection_items(self) -> None:
        visible = self._selection_visible() and self._drag_start is None
        is_arrow = self._sel_arrow is not None
        if visible and is_arrow:
            x1, y1, x2, y2 = self._sel_arrow
            self._sel_line.setLine(x1, y1, x2, y2)
        elif visible:
            self._selection.setRect(self._sel_rect)
        dim = self._sel_dim
        pen = self._pen_dim if dim else self._pen_solid
        self._selection.setPen(pen)
        self._selection.setBrush(self._brush_dim if dim else self._brush_solid)
        self._sel_line.setPen(pen)
        self._selection.setVisible(visible and not is_arrow)
        self._sel_line.setVisible(visible and is_arrow)
        show_handles = visible and self._select_mode
        active = ARROW_HANDLES if is_arrow else HANDLES
        for name, item in self._handles.items():
            show = show_handles and name in active
            if show:
                item.setPos(self._handle_scene_point(name))
            item.setOpacity(SEL_DIM_HANDLE_OPACITY if dim else 1.0)
            item.setVisible(show)

    def set_selection_dim(self, dim: bool) -> None:
        """Draw the selection dimmed and dashed (the annotation is not active at the playhead)."""
        if dim != self._sel_dim:
            self._sel_dim = dim
            self._refresh_selection_items()

    # ---- annotation preview ---------------------------------------------------------
    def set_overlays_visible(self, visible: bool) -> None:
        """Show or hide every preview item (rectangles, text, highlight, handles)."""
        self._overlays_visible = visible
        for item in self._overlay_items:
            item.setVisible(visible)
        self._refresh_selection_items()

    def set_overlays(self, items: List[Tuple[int, Annotation]]) -> None:
        """Draw the annotations active at the current time; items are (index, annotation)."""
        key = tuple((i, astuple(a)) for i, a in items)
        if key == self._overlay_key:
            return
        self._overlay_key = key
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items.clear()
        self._overlay_hits = list(items)

        for _i, a in items:
            if a.kind == BLUR:
                rect = QGraphicsRectItem(a.x, a.y, a.w, a.h)
                rect.setBrush(QBrush(QColor(80, 160, 255, 80)))
                rect.setPen(_cosmetic_pen("#50a0ff", 2, dashed=True))
                rect.setZValue(50)
                self._add_overlay_items([rect])
            elif a.kind == ARROW:
                self._add_arrow_overlay(a)
            elif a.kind == TEXT:
                self._add_text_overlay(a)

    def _add_overlay_items(self, items: list) -> None:
        for item in items:
            item.setVisible(self._overlays_visible)
            self._scene.addItem(item)
            self._overlay_items.append(item)

    def _add_arrow_overlay(self, a: Annotation) -> None:
        try:
            polygons = arrowgeom.polygons(a.x, a.y, a.x2, a.y2, a.thickness,
                                          a.start_style, a.end_style)
        except ValueError:
            return
        path = QPainterPath()
        for polygon in polygons:  # union, so shaft and heads never double-darken or cancel out
            part = QPainterPath()
            part.addPolygon(QPolygonF([QPointF(px, py) for px, py in polygon]))
            part.closeSubpath()
            path = path.united(part)
        try:
            color = QColor(colors.normalize_hex(a.color))
        except ValueError:
            color = QColor(0, 0, 0)
        color.setAlpha(round(arrowgeom.ALPHA * 255))
        item = QGraphicsPathItem(path)
        item.setBrush(QBrush(color))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setZValue(54)
        self._add_overlay_items([item])

    def _add_text_overlay(self, a: Annotation) -> None:
        res = textfit.layout_text(a.text, a.w, a.h, a.size)
        try:
            box = QColor(colors.normalize_hex(a.box_color))
        except ValueError:
            box = QColor(0, 0, 0)
        box.setAlpha(128)
        bg = QGraphicsRectItem(a.x, a.y, a.w, a.h)
        bg.setBrush(QBrush(box))
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
        text_color = QColor(a.text_color)
        for i, line in enumerate(res.lines):  # one item per line: same pitch as annotate.sh
            label = QGraphicsSimpleTextItem(line)
            label.setFont(font)
            label.setBrush(QBrush(text_color))
            label.setPos(a.x + textfit.PAD, a.y + textfit.PAD + i * line_h)
            label.setZValue(52)
            items.append(label)
        self._add_overlay_items(items)
