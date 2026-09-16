from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class JokeBubble(QWidget):
    dismissed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label = QLabel(self)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label.setStyleSheet(
            "QLabel { color: #f9edf4; background: rgba(24, 20, 30, 235); "
            "border: 1px solid #9c4768; border-radius: 12px; padding: 12px; font-size: 14px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.hide()

    def show_text(self, text: str, max_width: int) -> None:
        self.label.setFixedWidth(min(380, max_width))
        self.label.setText(text)
        self.label.adjustSize()
        self.adjustSize()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.dismissed.emit()
        event.accept()
