"""Dialog for editing the text box colour list (one `hex|label` entry per line)."""

from __future__ import annotations

from typing import List, Tuple

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from . import colors


class ColorListDialog(QDialog):
    def __init__(self, entries: List[Tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Box and arrow colours")
        self.resize(420, 320)
        self._entries = list(entries)

        help_label = QLabel(
            "One colour per line as hex|label, for example #ffd400|Yellow.\n"
            "Invalid or duplicate lines are reported and skipped."
        )
        self.edit = QPlainTextEdit(colors.dump_color_list(entries))
        restore = QPushButton("Restore defaults")
        restore.clicked.connect(lambda: self.edit.setPlainText(colors.default_color_list_text()))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addWidget(self.edit, 1)
        layout.addWidget(restore)
        layout.addWidget(buttons)

    def entries(self) -> List[Tuple[str, str]]:
        return list(self._entries)

    def _accept(self) -> None:
        entries, skipped = colors.parse_color_list(self.edit.toPlainText())
        if not entries:
            QMessageBox.warning(self, self.windowTitle(),
                                "Add at least one valid colour line.")
            return
        if skipped:
            lines = "\n".join(f"line {n}: {err}" for n, _l, err in skipped[:10])
            QMessageBox.warning(
                self, "Some lines were skipped",
                f"{len(skipped)} line(s) were skipped:\n\n{lines}",
            )
        self._entries = entries
        self.accept()
