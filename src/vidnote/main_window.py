"""Main window: player, timeline, annotation form and list, export and render."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QProcess, QRectF, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from . import canvasstate, colors, exporter, textfit
from .colors_dialog import ColorListDialog
from .models import (
    ARROW,
    ARROW_STYLES,
    BLUR,
    DEFAULT_ARROW_COLOR,
    DEFAULT_END_STYLE,
    DEFAULT_SIZE,
    DEFAULT_START_STYLE,
    DEFAULT_THICKNESS,
    MAX_SIZE,
    MAX_THICKNESS,
    MIN_SIZE,
    MIN_THICKNESS,
    TEXT,
    Annotation,
)
from .video_view import VideoView

VIDEO_FILTER = "Video files (*.mp4 *.mkv *.webm *.mov *.avi *.m4v);;All files (*)"
ANN_FILTER = "Annotation files (*.txt);;All files (*)"
COLUMNS = ["Type", "Start", "End", "X", "Y", "W", "H", "Size", "Box", "Color", "Text"]
COLUMN_TIPS = {"Size": "Font size in px", "Box": "Text box / arrow colour", "Color": "Text colour"}
STYLE_LABELS = {"none": "None", "arrow": "Arrowhead"}
SETTINGS_BOX_COLORS = "boxColors"


def fmt_clock(ms: int) -> str:
    s = max(ms, 0) / 1000.0
    m = int(s // 60)
    return f"{m:02d}:{s - 60 * m:06.3f}"


def swatch(color: str) -> QIcon:
    pix = QPixmap(14, 14)
    pix.fill(QColor(color))
    return QIcon(pix)


def find_script() -> Optional[Path]:
    override = os.environ.get("VIDNOTE_SCRIPT")
    if override and Path(override).is_file():
        return Path(override)
    # Running from the source tree: src/vidnote/main_window.py -> project root/scripts
    candidate = Path(__file__).resolve().parents[2] / "scripts" / "annotate.sh"
    return candidate if candidate.is_file() else None


class RenderDialog(QDialog):
    """Runs scripts/annotate.sh and shows its output."""

    def __init__(self, script: Path, video: Path, ann: Path, out: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rendering...")
        self.resize(760, 380)
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setMaximumBlockCount(2000)
        self.close_btn = QPushButton("Cancel")
        self.close_btn.clicked.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.log)
        layout.addWidget(self.close_btn)

        self.out = out
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(lambda _e: self.log.appendPlainText("Failed to start bash."))
        self.proc.start("bash", [str(script), str(video), str(ann), str(out)])

    def _read(self) -> None:
        text = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        # ffmpeg updates its progress line with carriage returns
        for line in text.replace("\r", "\n").splitlines():
            if line.strip():
                self.log.appendPlainText(line)

    def _finished(self, code: int, _status) -> None:
        ok = code == 0
        self.setWindowTitle("Done" if ok else "Failed")
        self.log.appendPlainText(f"\nSaved: {self.out}" if ok else f"\nffmpeg exited with code {code}")
        self.close_btn.setText("Close")

    def done(self, result: int) -> None:
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.kill()
            self.proc.waitForFinished(2000)
        super().done(result)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("vidnote")
        self.resize(1320, 780)

        self.annotations: List[Annotation] = []
        self.video_path: Optional[Path] = None
        self.fps = 30.0
        self._render_dialog: Optional[RenderDialog] = None
        self.color_list, self._color_list_skipped = self._load_color_list()

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.view = VideoView()
        self.player.setVideoOutput(self.view.video_item)

        self._marker = canvasstate.MarkerState()
        self._marker_timer = QTimer(self)
        self._marker_timer.setSingleShot(True)
        self._marker_timer.setInterval(canvasstate.POINT_MARKER_MS)
        self._marker_timer.timeout.connect(self._on_marker_timeout)

        self._build_ui()
        self._build_actions()
        self._connect()
        self._on_kind_changed()
        if self._color_list_skipped:
            self.statusBar().showMessage(
                f"{len(self._color_list_skipped)} invalid line(s) in the saved colour list were "
                "skipped (Edit > Box and arrow colours...)", 10000)
        if not textfit.resolve_font().preferred:
            QTimer.singleShot(0, self._warn_font)

    # ---- UI construction ------------------------------------------------------------
    def _build_ui(self) -> None:
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.time_label = QLabel("00:00.000 / 00:00.000")
        self.time_label.setMinimumWidth(170)

        def button(text: str, slot) -> QPushButton:
            b = QPushButton(text)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keep Space/arrows for shortcuts
            b.clicked.connect(slot)
            return b

        self.play_btn = button("Play", self.toggle_play)
        controls = QHBoxLayout()
        controls.addWidget(button("-1 s", lambda: self.step(seconds=-1)))
        controls.addWidget(button("< Frame", lambda: self.step(frames=-1)))
        controls.addWidget(self.play_btn)
        controls.addWidget(button("Frame >", lambda: self.step(frames=1)))
        controls.addWidget(button("+1 s", lambda: self.step(seconds=1)))
        controls.addStretch(1)
        controls.addWidget(self.time_label)

        left = QVBoxLayout()
        left.addWidget(self.view, 1)
        left.addWidget(self.slider)
        left.addLayout(controls)

        # --- annotation form
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(["Text", "Blur", "Arrow"])
        self.start_spin = self._time_spin()
        self.end_spin = self._time_spin()
        self.x_spin, self.y_spin = self._px_spin(), self._px_spin()
        self.w_spin, self.h_spin = self._px_spin(), self._px_spin()
        self.x2_spin, self.y2_spin = self._px_spin(), self._px_spin()
        self.thickness_spin = QSpinBox()
        self.thickness_spin.setRange(MIN_THICKNESS, MAX_THICKNESS)
        self.thickness_spin.setValue(DEFAULT_THICKNESS)
        self.thickness_spin.setSuffix(" px")
        self.start_style_combo = self._style_combo(DEFAULT_START_STYLE)
        self.end_style_combo = self._style_combo(DEFAULT_END_STYLE)
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Text to show")
        self.size_spin = QSpinBox()
        self.size_spin.setRange(MIN_SIZE, MAX_SIZE)
        self.size_spin.setValue(DEFAULT_SIZE)
        self.size_spin.setSuffix(" px")
        self.box_combo = QComboBox()
        self._populate_box_combo()
        self.text_color_combo = QComboBox()
        self.text_color_combo.addItem(swatch("#000000"), "Black", "#000000")
        self.text_color_combo.addItem(swatch("#ffffff"), "White", "#ffffff")
        self.text_color_combo.setCurrentIndex(1)

        form = QFormLayout()
        form.addRow("Type", self.kind_combo)
        form.addRow("Start", self._with_set_button(self.start_spin, "Set ["))
        form.addRow("End", self._with_set_button(self.end_spin, "Set ]"))
        xy = QHBoxLayout()
        xy.addWidget(QLabel("X"))
        xy.addWidget(self.x_spin)
        xy.addWidget(QLabel("Y"))
        xy.addWidget(self.y_spin)
        form.addRow("Position", xy)
        wh = QHBoxLayout()
        wh.addWidget(QLabel("W"))
        wh.addWidget(self.w_spin)
        wh.addWidget(QLabel("H"))
        wh.addWidget(self.h_spin)
        form.addRow("Size", wh)
        x2y2 = QHBoxLayout()
        x2y2.addWidget(QLabel("X"))
        x2y2.addWidget(self.x2_spin)
        x2y2.addWidget(QLabel("Y"))
        x2y2.addWidget(self.y2_spin)
        self.end_point_label = QLabel("End point")
        form.addRow(self.end_point_label, x2y2)
        form.addRow("Text", self.text_edit)
        form.addRow("Font size", self.size_spin)
        self.box_label = QLabel("Box colour")
        form.addRow(self.box_label, self.box_combo)
        form.addRow("Text colour", self.text_color_combo)
        form.addRow("Thickness", self.thickness_spin)
        form.addRow("Start style", self.start_style_combo)
        form.addRow("End style", self.end_style_combo)

        self.add_btn = QPushButton("Add")
        self.update_btn = QPushButton("Update selected")
        self.delete_btn = QPushButton("Delete selected")
        btns = QHBoxLayout()
        for b in (self.add_btn, self.update_btn, self.delete_btn):
            btns.addWidget(b)

        hint = QLabel("Draw mode: click the video for a point, drag for a region\n"
                      "(text and blur both need a dragged box).\n"
                      "Arrow type: drag from the start point to the end point.\n"
                      "Select mode: click an annotation, drag it or use the handles.\n"
                      "Double-click a row to jump to its start.")
        hint.setStyleSheet("color: gray;")

        group = QGroupBox("Annotation")
        gl = QVBoxLayout(group)
        gl.addLayout(form)
        gl.addLayout(btns)
        gl.addWidget(hint)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for c, name in enumerate(COLUMNS):
            self.table.horizontalHeaderItem(c).setToolTip(COLUMN_TIPS.get(name, name))

        right = QVBoxLayout()
        right.addWidget(group)
        right.addWidget(self.table, 1)
        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setFixedWidth(420)

        root = QHBoxLayout()
        root.addLayout(left, 1)
        root.addWidget(right_w)
        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Open a video with Ctrl+O")

    @staticmethod
    def _time_spin() -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setDecimals(3)
        s.setRange(0, 1_000_000)
        s.setSingleStep(0.1)
        s.setSuffix(" s")
        return s

    @staticmethod
    def _style_combo(default: str) -> QComboBox:
        combo = QComboBox()
        for style in ARROW_STYLES:
            combo.addItem(STYLE_LABELS[style], style)
        combo.setCurrentIndex(max(combo.findData(default), 0))
        return combo

    @staticmethod
    def _px_spin() -> QSpinBox:
        s = QSpinBox()
        s.setRange(0, 20000)
        return s

    def _with_set_button(self, spin: QDoubleSpinBox, label: str) -> QWidget:
        b = QPushButton(label.strip())
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setToolTip("Use the current playback time")
        b.clicked.connect(lambda: spin.setValue(self.snapped_time()))
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(spin, 1)
        lay.addWidget(b)
        return w

    def _build_actions(self) -> None:
        def act(text: str, shortcut: str, slot, menu=None) -> QAction:
            a = QAction(text, self)
            a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            self.addAction(a)
            if menu is not None:
                menu.addAction(a)
            return a

        m = self.menuBar().addMenu("&File")
        act("Open video...", "Ctrl+O", self.open_video_dialog, m)
        m.addSeparator()
        act("Load annotations...", "Ctrl+L", self.load_annotations, m)
        act("Save annotations...", "Ctrl+S", self.save_annotations, m)
        m.addSeparator()
        act("Render annotated video...", "Ctrl+R", self.render, m)
        m.addSeparator()
        act("Quit", "Ctrl+Q", self.close, m)

        e = self.menuBar().addMenu("&Edit")
        act("Box and arrow colours...", "", self.edit_colors, e)

        p = self.menuBar().addMenu("&Playback")
        act("Play / pause", "Space", self.toggle_play, p)
        act("Previous frame", "Left", lambda: self.step(frames=-1), p)
        act("Next frame", "Right", lambda: self.step(frames=1), p)
        act("Back 1 s", "Shift+Left", lambda: self.step(seconds=-1), p)
        act("Forward 1 s", "Shift+Right", lambda: self.step(seconds=1), p)
        p.addSeparator()
        act("Set start to current time", "[", lambda: self.start_spin.setValue(self.snapped_time()), p)
        act("Set end to current time", "]", lambda: self.end_spin.setValue(self.snapped_time()), p)

        # no shortcuts: they would steal keys from the text field
        tools = QToolBar("Tools", self)
        tools.setMovable(False)
        self.addToolBar(tools)
        self.select_action = QAction("Select", self)
        self.select_action.setCheckable(True)
        self.select_action.setToolTip("Select mode: click, move and resize annotations")
        self.select_action.toggled.connect(self._on_mode_toggled)
        tools.addAction(self.select_action)
        self.hide_action = QAction("Hide preview", self)
        self.hide_action.setCheckable(True)
        self.hide_action.setToolTip("Hide all preview items on the canvas")
        self.hide_action.toggled.connect(self._on_hide_toggled)
        tools.addAction(self.hide_action)

    def _connect(self) -> None:
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.metaDataChanged.connect(self._on_meta)
        self.player.errorOccurred.connect(self._on_player_error)
        self.slider.sliderMoved.connect(self.player.setPosition)
        self.view.regionSelected.connect(self._on_region)
        self.view.annotationPicked.connect(self._on_annotation_picked)
        self.view.geometryEdited.connect(self._on_geometry_edited)
        self.view.lineSelected.connect(self._on_line)
        self.view.arrowEdited.connect(self._on_arrow_edited)
        self.view.dragStarted.connect(self._clear_marker)
        for spin in (self.x_spin, self.y_spin, self.w_spin, self.h_spin,
                     self.x2_spin, self.y2_spin):
            spin.valueChanged.connect(self._on_geometry_field_changed)
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        self.size_spin.valueChanged.connect(self._update_overlays)
        self.box_combo.currentIndexChanged.connect(self._update_overlays)
        self.text_color_combo.currentIndexChanged.connect(self._update_overlays)
        self.thickness_spin.valueChanged.connect(self._update_overlays)
        self.start_style_combo.currentIndexChanged.connect(self._update_overlays)
        self.end_style_combo.currentIndexChanged.connect(self._update_overlays)
        self.add_btn.clicked.connect(self.add_annotation)
        self.update_btn.clicked.connect(self.update_annotation)
        self.delete_btn.clicked.connect(self.delete_annotation)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)

    # ---- video loading and playback -------------------------------------------------
    def open_video_dialog(self) -> None:
        start = str(self.video_path.parent) if self.video_path else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Open video", start, VIDEO_FILTER)
        if path:
            self.open_video(path)

    def open_video(self, path: str) -> None:
        p = Path(path).expanduser()
        if not p.is_file():
            QMessageBox.warning(self, "vidnote", f"File not found:\n{p}")
            return
        self.video_path = p.resolve()
        self.setWindowTitle(f"vidnote - {p.name}")
        self.player.setSource(QUrl.fromLocalFile(str(self.video_path)))
        self._clear_marker()
        self.table.clearSelection()
        self.player.pause()  # shows the first frame
        self.statusBar().showMessage(str(self.video_path))

    def toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def step(self, frames: int = 0, seconds: float = 0.0) -> None:
        self.player.pause()
        pos = self.player.position()
        if frames:
            idx = round(pos / 1000.0 * self.fps) + frames
            # land slightly inside the frame so the backend does not pick the previous one
            target = (idx + 0.25) / self.fps * 1000.0
        else:
            target = pos + seconds * 1000.0
        target = min(max(target, 0), max(self.player.duration(), 0))
        self.player.setPosition(int(target))

    def snapped_time(self) -> float:
        """Current time snapped to a frame boundary, in seconds."""
        t = self.player.position() / 1000.0
        return round(round(t * self.fps) / self.fps, 3)

    def _on_position(self, ms: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.time_label.setText(f"{fmt_clock(ms)} / {fmt_clock(self.player.duration())}")
        self._update_overlays()

    def _on_duration(self, ms: int) -> None:
        self.slider.setRange(0, ms)
        self.end_spin.setMaximum(max(ms / 1000.0, 0.001))
        self.start_spin.setMaximum(max(ms / 1000.0, 0.001))

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setText("Pause" if playing else "Play")

    def _on_meta(self) -> None:
        try:
            fps = self.player.metaData().value(QMediaMetaData.Key.VideoFrameRate)
            if fps and float(fps) > 0:
                self.fps = float(fps)
        except (TypeError, ValueError):
            pass
        vs = self.view.video_size()
        if not vs.isEmpty():
            self.statusBar().showMessage(
                f"{self.video_path.name if self.video_path else ''}  "
                f"{int(vs.width())}x{int(vs.height())}  {self.fps:.2f} fps"
            )

    def _on_player_error(self, _error, message: str) -> None:
        QMessageBox.warning(
            self, "Playback error",
            f"{message}\n\nSee the Troubleshooting section of the README (Qt media backend).",
        )

    def _update_overlays(self) -> None:
        t = self.player.position() / 1000.0
        selected = self._selected_row()
        items = []
        for i, a in enumerate(self.annotations):
            if a.is_active(t):
                if i == selected and a.kind in (TEXT, ARROW):
                    a = self._with_form_style(a)  # live preview of unsaved style changes
                items.append((i, a))
        self.view.set_overlays(items)
        self._sync_selection_dim()

    def _with_form_style(self, a: Annotation) -> Annotation:
        if a.kind == ARROW:
            return replace(
                a,
                thickness=self.thickness_spin.value(),
                color=self.box_combo.currentData() or a.color,
                start_style=self.start_style_combo.currentData() or a.start_style,
                end_style=self.end_style_combo.currentData() or a.end_style,
            )
        return replace(
            a,
            size=self.size_spin.value(),
            box_color=self.box_combo.currentData() or a.box_color,
            text_color=self.text_color_combo.currentData() or a.text_color,
        )

    # ---- annotation editing ---------------------------------------------------------
    def _on_hide_toggled(self, hidden: bool) -> None:
        self.hide_action.setText("Show preview" if hidden else "Hide preview")
        self.view.set_overlays_visible(not hidden)

    def _kind(self) -> str:
        return (TEXT, BLUR, ARROW)[self.kind_combo.currentIndex()]

    def _on_kind_changed(self) -> None:
        kind = self._kind()
        is_text, is_arrow = kind == TEXT, kind == ARROW
        self.text_edit.setEnabled(is_text)
        self.size_spin.setEnabled(is_text)
        self.text_color_combo.setEnabled(is_text)
        self.box_combo.setEnabled(is_text or is_arrow)
        self.box_label.setText("Colour" if is_arrow else "Box colour")
        self.w_spin.setEnabled(not is_arrow)
        self.h_spin.setEnabled(not is_arrow)
        for widget in (self.x2_spin, self.y2_spin, self.thickness_spin,
                       self.start_style_combo, self.end_style_combo):
            widget.setEnabled(is_arrow)
        self._clear_marker()
        self.view.set_draw_line(is_arrow)

    # ---- colour list ----------------------------------------------------------------
    @staticmethod
    def _settings() -> QSettings:
        return QSettings("vidnote", "vidnote")

    def _load_color_list(self):
        text = self._settings().value(SETTINGS_BOX_COLORS, None)
        if not isinstance(text, str) or not text.strip():
            return list(colors.DEFAULT_COLOR_LIST), []
        entries, skipped = colors.parse_color_list(text)
        return (entries or list(colors.DEFAULT_COLOR_LIST)), skipped

    def _save_color_list(self) -> None:
        self._settings().setValue(SETTINGS_BOX_COLORS, colors.dump_color_list(self.color_list))

    def edit_colors(self) -> None:
        dialog = ColorListDialog(self.color_list, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.color_list = dialog.entries()
        self._save_color_list()
        self._set_box_color(self.box_combo.currentData())

    def _populate_box_combo(self, extra: Optional[str] = None) -> None:
        """Fill the box colour combo from the list; `extra` is a colour not in the list."""
        self.box_combo.blockSignals(True)
        self.box_combo.clear()
        for hex_value, label in self.color_list:
            self.box_combo.addItem(swatch(hex_value), label, hex_value)
        if extra is not None:
            self.box_combo.addItem(swatch(extra), f"{extra} (not in list)", extra)
        self.box_combo.blockSignals(False)

    def _set_box_color(self, value: Optional[str]) -> None:
        try:
            hex_value = colors.normalize_hex(value or "")
        except ValueError:
            hex_value = None
        known = {h for h, _label in self.color_list}
        self._populate_box_combo(extra=hex_value if hex_value not in known else None)
        idx = self.box_combo.findData(hex_value) if hex_value else -1
        self.box_combo.setCurrentIndex(max(idx, 0))

    # ---- yellow canvas graphics -----------------------------------------------------
    def _form_geometry(self) -> canvasstate.FormGeometry:
        return canvasstate.FormGeometry(
            self.x_spin.value(), self.y_spin.value(), self.w_spin.value(), self.h_spin.value(),
            self.x2_spin.value(), self.y2_spin.value())

    def _show_marker(self) -> None:
        self.view.set_marker(self._marker.shape(self._form_geometry()))

    def _clear_marker(self) -> None:
        self._marker.clear()
        self._marker_timer.stop()
        self.view.set_marker(None)
        self._sync_selection_highlight()  # it may go back to following the form

    def _on_marker_timeout(self) -> None:
        if self._marker.expire_point():
            self._clear_marker()

    def _sync_selection_highlight(self) -> None:
        row = self._selected_row()
        if row is None or row >= len(self.annotations):
            self.view.set_selected(None, None)
            return
        a = self.annotations[row]
        geom = canvasstate.selection_geometry(
            a, self._kind(), self._form_geometry(), self._marker.active)
        if a.kind == ARROW:
            self.view.set_selected(row, None, arrow=geom)
        else:
            self.view.set_selected(row, QRectF(*geom))
        self._sync_selection_dim()

    def _sync_selection_dim(self) -> None:
        row = self._selected_row()
        if row is not None and row < len(self.annotations):
            self.view.set_selection_dim(canvasstate.selection_dimmed(
                self.annotations[row], self.player.position() / 1000.0))

    def _on_geometry_field_changed(self) -> None:
        if self._marker.active:
            self._show_marker()  # the marker moves with the form
        self._sync_selection_highlight()

    def _on_mode_toggled(self, select: bool) -> None:
        self._clear_marker()
        self.view.set_mode(select)

    def _on_region(self, x: int, y: int, w: int, h: int) -> None:
        is_region = w > 0 and h > 0 and self._kind() != ARROW
        self._marker.pick(canvasstate.REGION if is_region else canvasstate.POINT)
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        if is_region:
            self.w_spin.setValue(w)
            self.h_spin.setValue(h)
        self._show_marker()
        if is_region:
            self._marker_timer.stop()
        else:
            self._marker_timer.start()  # restarts when already running
        self._sync_selection_highlight()

    def _on_line(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self._marker.pick(canvasstate.LINE)
        self._marker_timer.stop()
        self.x_spin.setValue(x1)
        self.y_spin.setValue(y1)
        self.x2_spin.setValue(x2)
        self.y2_spin.setValue(y2)
        self._show_marker()
        self._sync_selection_highlight()

    def _form_annotation(self) -> Annotation:
        kind = self._kind()
        if kind == ARROW:
            return Annotation(
                kind=ARROW,
                start=self.start_spin.value(),
                end=self.end_spin.value(),
                x=self.x_spin.value(),
                y=self.y_spin.value(),
                x2=self.x2_spin.value(),
                y2=self.y2_spin.value(),
                thickness=self.thickness_spin.value(),
                color=self.box_combo.currentData() or DEFAULT_ARROW_COLOR,
                start_style=self.start_style_combo.currentData(),
                end_style=self.end_style_combo.currentData(),
            )
        blur = kind == BLUR
        return Annotation(
            kind=kind,
            start=self.start_spin.value(),
            end=self.end_spin.value(),
            x=self.x_spin.value(),
            y=self.y_spin.value(),
            w=self.w_spin.value(),
            h=self.h_spin.value(),
            text="" if blur else self.text_edit.text(),
            size=self.size_spin.value(),
            box_color=self.box_combo.currentData() or "#000000",
            text_color=self.text_color_combo.currentData(),
        )

    def _selected_row(self) -> Optional[int]:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def add_annotation(self) -> None:
        try:
            a = self._form_annotation()
            a.validate()
            self._check_in_frame(a)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot add", str(exc))
            return
        self.annotations.append(a)
        self._refresh_table(select=len(self.annotations) - 1)
        self._warn_if_unfit(a)

    def update_annotation(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "vidnote", "Select a row in the list first.")
            return
        try:
            a = self._form_annotation()
            a.validate()
            self._check_in_frame(a)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot update", str(exc))
            return
        self.annotations[row] = a
        self._refresh_table(select=row)
        self._warn_if_unfit(a)

    def _check_in_frame(self, a: Annotation) -> None:
        vs = self.view.video_size()
        if a.kind not in (TEXT, ARROW) or vs.isEmpty():
            return
        vw, vh = int(vs.width()), int(vs.height())
        if a.kind == ARROW:
            if not (0 <= a.x <= vw and 0 <= a.y <= vh and 0 <= a.x2 <= vw and 0 <= a.y2 <= vh):
                raise ValueError(f"The arrow extends beyond the video frame ({vw}x{vh}).")
            return
        if a.x < 0 or a.y < 0 or a.x + a.w > vw or a.y + a.h > vh:
            raise ValueError(f"The text box extends beyond the video frame ({vw}x{vh}).")

    def _warn_if_unfit(self, a: Annotation, notes: Optional[List[str]] = None) -> None:
        messages = list(notes or [])
        if a.kind == TEXT:
            if not textfit.layout_text(a.text, a.w, a.h, a.size).fits:
                messages.append(f"Text is taller than the box at {a.size} px; "
                                f"it will still be drawn at {a.size} px.")
            if colors.normalize_hex(a.box_color) == colors.normalize_hex(a.text_color):
                messages.append("Text colour equals the box colour; the text will be hard to read.")
        if messages:
            self.statusBar().showMessage(" ".join(messages), 8000)

    def _warn_font(self) -> None:
        QMessageBox.information(
            self, "vidnote",
            f"Ubuntu Mono is not installed. Using {textfit.resolve_font().family} instead; "
            "text layout may differ slightly.",
        )

    def delete_annotation(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        del self.annotations[row]
        new_row = min(row, len(self.annotations) - 1)
        self._refresh_table(select=new_row)
        if new_row >= 0:
            self._fill_form(self.annotations[new_row])  # the highlight follows the form

    def _refresh_table(self, select: Optional[int] = None) -> None:
        self._clear_marker()
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.annotations))
        for r, a in enumerate(self.annotations):
            is_text, is_arrow = a.kind == TEXT, a.kind == ARROW
            if is_arrow:
                box = a.color
                text = (f"to ({a.x2},{a.y2}), {a.thickness} px, "
                        f"{a.start_style}>{a.end_style}")
            else:
                box = a.box_color if is_text else "-"
                text = a.text
            cells = [a.kind, exporter.fmt_time(a.start), exporter.fmt_time(a.end),
                     a.x, a.y, a.w or "", a.h or "",
                     a.size if is_text else "-",
                     box,
                     a.text_color if is_text else "-",
                     text]
            for c, value in enumerate(cells):
                item = QTableWidgetItem(str(value))
                if COLUMNS[c] == "Box" and (is_text or is_arrow):
                    item.setIcon(swatch(str(value)))
                elif COLUMNS[c] == "Color" and is_text:
                    item.setIcon(swatch(str(value)))
                self.table.setItem(r, c, item)
        if select is not None and 0 <= select < len(self.annotations):
            self.table.selectRow(select)
        self.table.blockSignals(False)
        self._sync_view_selection()
        self._update_overlays()

    def _sync_view_selection(self) -> None:
        self._sync_selection_highlight()

    def _select_in_view(self, _row: int) -> None:
        self._sync_selection_highlight()

    def _fill_form(self, a: Annotation) -> None:
        self.kind_combo.setCurrentIndex((TEXT, BLUR, ARROW).index(a.kind))
        self.start_spin.setValue(a.start)
        self.end_spin.setValue(a.end)
        self.x_spin.setValue(a.x)
        self.y_spin.setValue(a.y)
        self.w_spin.setValue(a.w)
        self.h_spin.setValue(a.h)
        self.text_edit.setText(a.text)
        if a.kind == ARROW:
            self.x2_spin.setValue(a.x2)
            self.y2_spin.setValue(a.y2)
            self.thickness_spin.setValue(a.thickness)
            self._set_box_color(a.color)
            for combo, style in ((self.start_style_combo, a.start_style),
                                 (self.end_style_combo, a.end_style)):
                combo.setCurrentIndex(max(combo.findData(style), 0))
        if a.kind == TEXT:
            self.size_spin.setValue(a.size)
            self._set_box_color(a.box_color)
            idx = self.text_color_combo.findData(colors.normalize_hex(a.text_color))
            self.text_color_combo.setCurrentIndex(max(idx, 0))

    def _on_row_selected(self) -> None:
        row = self._selected_row()
        if row is None or row >= len(self.annotations):
            self.view.set_selected(None, None)
            return
        a = self.annotations[row]
        self._clear_marker()  # before the form fill, so the spin signals do not redraw it
        self._fill_form(a)
        if self.hide_action.isChecked():
            self.hide_action.setChecked(False)  # selecting a row brings the preview back
        self._select_in_view(row)

    def _on_annotation_picked(self, index: int) -> None:
        if not 0 <= index < len(self.annotations):
            return
        if self._selected_row() == index:
            self._on_row_selected()
        else:
            self.table.selectRow(index)
        item = self.table.item(index, 0)
        if item is not None:
            self.table.scrollToItem(item)

    def _on_geometry_edited(self, index: int, x: int, y: int, w: int, h: int) -> None:
        if not 0 <= index < len(self.annotations):
            return
        a = self.annotations[index]
        old_w, old_h = a.w, a.h
        a.x, a.y, a.w, a.h = x, y, w, h
        notes: List[str] = []
        if a.kind == TEXT and (w, h) != (old_w, old_h) and old_w > 0 and old_h > 0:
            wanted = round(a.size * min(w / old_w, h / old_h))
            a.size = textfit.scaled_size(a.size, old_w, old_h, w, h)
            if a.size != wanted:
                notes.append(f"Font size limited to {a.size} px.")
        self._refresh_table(select=index)
        self._fill_form(a)
        self._warn_if_unfit(a, notes)

    def _on_arrow_edited(self, index: int, x1: int, y1: int, x2: int, y2: int) -> None:
        if not 0 <= index < len(self.annotations):
            return
        a = self.annotations[index]
        a.x, a.y, a.x2, a.y2 = x1, y1, x2, y2
        self._refresh_table(select=index)
        self._fill_form(a)

    def _on_row_double_clicked(self, row: int, _col: int) -> None:
        if 0 <= row < len(self.annotations):
            self.player.pause()
            self.player.setPosition(int(self.annotations[row].start * 1000 + 1))

    # ---- files ----------------------------------------------------------------------
    def _default_ann_path(self) -> str:
        if self.video_path:
            return str(self.video_path.with_suffix(".annotations.txt"))
        return str(Path.home() / "annotations.txt")

    def save_annotations(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save annotations", self._default_ann_path(),
                                              ANN_FILTER)
        if path:
            exporter.save(self.annotations, path)
            self.statusBar().showMessage(f"Saved {len(self.annotations)} annotations to {path}", 5000)

    def load_annotations(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load annotations", self._default_ann_path(),
                                              ANN_FILTER)
        if not path:
            return
        loaded, skipped = exporter.load(path)
        self.annotations = loaded
        self.table.clearSelection()
        self._refresh_table()
        if skipped:
            lines = "\n".join(f"line {n}: {err}" for n, _l, err in skipped[:10])
            QMessageBox.warning(
                self, "Some lines were skipped",
                f"{len(skipped)} line(s) could not be read (expected "
                f"'text|start|end|x|y|w|h|size|boxcolor|textcolor|text', "
                f"'blur|start|end|x|y|w|h' or "
                f"'arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle'):"
                f"\n\n{lines}",
            )

    def render(self) -> None:
        if not self.video_path:
            QMessageBox.information(self, "vidnote", "Open a video first.")
            return
        if not self.annotations:
            QMessageBox.information(self, "vidnote", "Add at least one annotation first.")
            return
        script = find_script()
        if script is None or shutil.which("ffmpeg") is None:
            QMessageBox.critical(
                self, "Cannot render",
                "Need ffmpeg on PATH and scripts/annotate.sh (set VIDNOTE_SCRIPT to its path).",
            )
            return
        default = self.video_path.with_name(self.video_path.stem + "_annotated.mp4")
        out, _ = QFileDialog.getSaveFileName(self, "Save rendered video", str(default),
                                             "MP4 video (*.mp4);;All files (*)")
        if not out:
            return
        ann_file = Path(tempfile.mkdtemp(prefix="vidnote-")) / "annotations.txt"
        exporter.save(self.annotations, ann_file)
        self._render_dialog = RenderDialog(script, self.video_path, ann_file, Path(out), self)
        self._render_dialog.show()

    def closeEvent(self, event) -> None:
        self.player.stop()
        if self._render_dialog is not None:
            self._render_dialog.close()
        super().closeEvent(event)
