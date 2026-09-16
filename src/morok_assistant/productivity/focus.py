from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QObject, QTimer, Signal


class FocusController(QObject):
    changed = Signal()
    notice = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.phase = "idle"
        self.work_minutes = 25
        self.break_minutes = 5
        self._ends_at = 0.0
        self._paused_remaining = 0
        self.timer = QTimer(self)
        self.timer.setInterval(1_000)
        self.timer.timeout.connect(self._tick)

    @property
    def active(self) -> bool:
        return self.phase in {"focus", "break", "paused"}

    @property
    def remaining_seconds(self) -> int:
        if self.phase == "paused":
            return self._paused_remaining
        if not self.active:
            return 0
        return max(0, round(self._ends_at - monotonic()))

    def start(self, work_minutes: int, break_minutes: int) -> None:
        self.work_minutes = max(1, work_minutes)
        self.break_minutes = max(1, break_minutes)
        self.phase = "focus"
        self._ends_at = monotonic() + self.work_minutes * 60
        self._paused_remaining = 0
        self.timer.start()
        self.changed.emit()
        self.notice.emit(f"Режим концентрации: {self.work_minutes} мин.")

    def toggle_pause(self) -> None:
        if self.phase == "paused":
            self.phase = "focus"
            self._ends_at = monotonic() + self._paused_remaining
            self.timer.start()
        elif self.phase == "focus":
            self._paused_remaining = self.remaining_seconds
            self.phase = "paused"
            self.timer.stop()
        else:
            return
        self.changed.emit()

    def stop(self) -> None:
        self.phase = "idle"
        self._ends_at = 0.0
        self._paused_remaining = 0
        self.timer.stop()
        self.changed.emit()

    def _tick(self) -> None:
        if self.remaining_seconds > 0:
            self.changed.emit()
            return
        if self.phase == "focus":
            self.phase = "break"
            self._ends_at = monotonic() + self.break_minutes * 60
            self.notice.emit(f"Пора отдохнуть {self.break_minutes} мин.")
            self.changed.emit()
            return
        if self.phase == "break":
            self.stop()
            self.notice.emit("Перерыв завершён. Можно продолжать работу.")
