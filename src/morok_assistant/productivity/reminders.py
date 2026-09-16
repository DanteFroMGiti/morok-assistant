from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time

from PySide6.QtCore import QObject, QTimer, Signal


@dataclass(frozen=True, slots=True)
class Reminder:
    reminder_id: str
    text: str
    due_at: float


def default_reminders_path() -> Path:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "morok-assistant" / "reminders.json"


class ReminderStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_reminders_path()

    def load(self) -> list[Reminder]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        reminders: list[Reminder] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                reminder = Reminder(
                    reminder_id=str(item["reminder_id"]),
                    text=str(item["text"]).strip(),
                    due_at=float(item["due_at"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if reminder.text:
                reminders.append(reminder)
        return sorted(reminders, key=lambda reminder: reminder.due_at)

    def save(self, reminders: list[Reminder]) -> None:
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".reminders-", suffix=".json", dir=directory
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump([asdict(item) for item in reminders], file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class ReminderManager(QObject):
    due = Signal(str)
    changed = Signal()

    def __init__(self, store: ReminderStore | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.store = store or ReminderStore()
        self.reminders = self.store.load()
        self.timer = QTimer(self)
        self.timer.setInterval(1_000)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def add(self, text: str, due_at: float) -> Reminder:
        text = text.strip()
        if not text:
            raise ValueError("Введите текст напоминания")
        if due_at <= time():
            raise ValueError("Время напоминания уже прошло")
        reminder = Reminder(uuid.uuid4().hex, text, due_at)
        self.reminders.append(reminder)
        self.reminders.sort(key=lambda item: item.due_at)
        self.store.save(self.reminders)
        self.changed.emit()
        return reminder

    def add_timer(self, text: str, seconds: int) -> Reminder:
        if seconds <= 0:
            raise ValueError("Продолжительность таймера должна быть больше нуля")
        return self.add(text or "Таймер завершён", time() + seconds)

    def remove(self, reminder_id: str) -> None:
        updated = [item for item in self.reminders if item.reminder_id != reminder_id]
        if len(updated) == len(self.reminders):
            return
        self.reminders = updated
        self.store.save(self.reminders)
        self.changed.emit()

    def _poll(self) -> None:
        now = time()
        ready = [item for item in self.reminders if item.due_at <= now]
        if not ready:
            return
        ready_ids = {item.reminder_id for item in ready}
        self.reminders = [item for item in self.reminders if item.reminder_id not in ready_ids]
        self.store.save(self.reminders)
        self.changed.emit()
        for reminder in ready:
            self.due.emit(reminder.text)

    def stop(self) -> None:
        self.timer.stop()
