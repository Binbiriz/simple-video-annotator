"""Main window: player, timeline, annotation form and list, export and render."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QProcess, Qt, QUrl
from PySide6.QtGui import QAction, QKeySequence
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
    QVBoxLayout,
    QWidget,
)

from . import exporter
from .models import BLUR, TEXT, Annotation
from .video_view import VideoView

VIDEO_FILTER = "Video files (*.mp4 *.mkv *.webm *.mov *.avi *.m4v);;All files (*)"
ANN_FILTER = "Annotation files (*.txt);;All files (*)"
COLUMNS = ["Type", "Start", "End", "X", "Y", "W", "H", "Text"]


def fmt_clock(ms: int) -> str:
    s = max(ms, 0) / 1000.0
    m = int(s // 60)
    return f"{m:02d}:{s - 60 * m:06.3f}"


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

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.view = VideoView()
        self.player.setVideoOutput(self.view.video_item)

        self._build_ui()
        self._build_actions()
        self._connect()
        self._on_kind_changed()

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
        self.kind_combo.addItems(["Text", "Blur"])
        self.start_spin = self._time_spin()
        self.end_spin = self._time_spin()
        self.x_spin, self.y_spin = self._px_spin(), self._px_spin()
        self.w_spin, self.h_spin = self._px_spin(), self._px_spin()
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Text to show")

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
        form.addRow("Text", self.text_edit)

        self.add_btn = QPushButton("Add")
        self.update_btn = QPushButton("Update selected")
        self.delete_btn = QPushButton("Delete selected")
        btns = QHBoxLayout()
        for b in (self.add_btn, self.update_btn, self.delete_btn):
            btns.addWidget(b)

        hint = QLabel("Click the video for a point, drag for a region.\n"
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

        p = self.menuBar().addMenu("&Playback")
        act("Play / pause", "Space", self.toggle_play, p)
        act("Previous frame", "Left", lambda: self.step(frames=-1), p)
        act("Next frame", "Right", lambda: self.step(frames=1), p)
        act("Back 1 s", "Shift+Left", lambda: self.step(seconds=-1), p)
        act("Forward 1 s", "Shift+Right", lambda: self.step(seconds=1), p)
        p.addSeparator()
        act("Set start to current time", "[", lambda: self.start_spin.setValue(self.snapped_time()), p)
        act("Set end to current time", "]", lambda: self.end_spin.setValue(self.snapped_time()), p)

    def _connect(self) -> None:
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.metaDataChanged.connect(self._on_meta)
        self.player.errorOccurred.connect(self._on_player_error)
        self.slider.sliderMoved.connect(self.player.setPosition)
        self.view.regionSelected.connect(self._on_region)
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
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
        self.view.set_overlays([a for a in self.annotations if a.is_active(t)])

    # ---- annotation editing ---------------------------------------------------------
    def _on_kind_changed(self) -> None:
        is_blur = self.kind_combo.currentIndex() == 1
        self.w_spin.setEnabled(is_blur)
        self.h_spin.setEnabled(is_blur)
        self.text_edit.setEnabled(not is_blur)

    def _on_region(self, x: int, y: int, w: int, h: int) -> None:
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        if w > 0 and h > 0:
            self.w_spin.setValue(w)
            self.h_spin.setValue(h)

    def _form_annotation(self) -> Annotation:
        blur = self.kind_combo.currentIndex() == 1
        return Annotation(
            kind=BLUR if blur else TEXT,
            start=self.start_spin.value(),
            end=self.end_spin.value(),
            x=self.x_spin.value(),
            y=self.y_spin.value(),
            w=self.w_spin.value() if blur else 0,
            h=self.h_spin.value() if blur else 0,
            text="" if blur else self.text_edit.text(),
        )

    def _selected_row(self) -> Optional[int]:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def add_annotation(self) -> None:
        try:
            a = self._form_annotation()
            a.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot add", str(exc))
            return
        self.annotations.append(a)
        self._refresh_table(select=len(self.annotations) - 1)

    def update_annotation(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "vidnote", "Select a row in the list first.")
            return
        try:
            a = self._form_annotation()
            a.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot update", str(exc))
            return
        self.annotations[row] = a
        self._refresh_table(select=row)

    def delete_annotation(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        del self.annotations[row]
        self._refresh_table(select=min(row, len(self.annotations) - 1))

    def _refresh_table(self, select: Optional[int] = None) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.annotations))
        for r, a in enumerate(self.annotations):
            cells = [a.kind, exporter.fmt_time(a.start), exporter.fmt_time(a.end),
                     a.x, a.y, a.w or "", a.h or "", a.text]
            for c, value in enumerate(cells):
                self.table.setItem(r, c, QTableWidgetItem(str(value)))
        if select is not None and 0 <= select < len(self.annotations):
            self.table.selectRow(select)
        self.table.blockSignals(False)
        self._update_overlays()

    def _on_row_selected(self) -> None:
        row = self._selected_row()
        if row is None or row >= len(self.annotations):
            return
        a = self.annotations[row]
        self.kind_combo.setCurrentIndex(1 if a.kind == BLUR else 0)
        self.start_spin.setValue(a.start)
        self.end_spin.setValue(a.end)
        self.x_spin.setValue(a.x)
        self.y_spin.setValue(a.y)
        self.w_spin.setValue(a.w)
        self.h_spin.setValue(a.h)
        self.text_edit.setText(a.text)
        self.view.show_selection(a.x, a.y, a.w, a.h)

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
        self._refresh_table()
        if skipped:
            lines = "\n".join(f"line {n}: {err}" for n, _l, err in skipped[:10])
            QMessageBox.warning(
                self, "Some lines were skipped",
                f"{len(skipped)} line(s) could not be read (expected "
                f"'text|start|end|x|y|text' or 'blur|start|end|x|y|w|h'):\n\n{lines}",
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
