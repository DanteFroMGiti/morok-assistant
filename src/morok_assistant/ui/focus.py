from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from morok_assistant.productivity.focus import FocusController


class FocusDialog(QDialog):
    def __init__(self, controller: FocusController, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Режим концентрации")
        self.setMinimumWidth(360)

        self.work = QSpinBox()
        self.work.setRange(1, 180)
        self.work.setValue(controller.work_minutes)
        self.work.setSuffix(" мин")
        self.break_time = QSpinBox()
        self.break_time.setRange(1, 60)
        self.break_time.setValue(controller.break_minutes)
        self.break_time.setSuffix(" мин")
        form = QFormLayout()
        form.addRow("Работа:", self.work)
        form.addRow("Перерыв:", self.break_time)

        self.status = QLabel()
        self.status.setStyleSheet("font-size: 22px; font-weight: 600")
        self.status.setMinimumHeight(40)

        self.start_button = QPushButton("Начать")
        self.start_button.clicked.connect(self._start)
        self.pause_button = QPushButton("Пауза")
        self.pause_button.clicked.connect(controller.toggle_pause)
        stop = QPushButton("Завершить")
        stop.clicked.connect(controller.stop)
        controls = QHBoxLayout()
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(stop)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addLayout(controls)
        self.controller.changed.connect(self.refresh)
        self.refresh()

    def _start(self) -> None:
        self.controller.start(self.work.value(), self.break_time.value())

    def refresh(self) -> None:
        remaining = self.controller.remaining_seconds
        minutes, seconds = divmod(remaining, 60)
        names = {
            "idle": "Сеанс не запущен",
            "focus": "Работа",
            "paused": "Пауза",
            "break": "Перерыв",
        }
        self.status.setText(
            names[self.controller.phase]
            if self.controller.phase == "idle"
            else f"{names[self.controller.phase]} · {minutes:02d}:{seconds:02d}"
        )
        self.pause_button.setEnabled(self.controller.phase in {"focus", "paused"})
        self.pause_button.setText("Продолжить" if self.controller.phase == "paused" else "Пауза")
