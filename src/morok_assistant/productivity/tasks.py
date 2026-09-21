from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from time import time

from PySide6.QtCore import QObject, Signal

STATUSES = {"todo", "in_progress", "done"}


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    title: str
    created_at: float
    priority: int = 2
    estimate_minutes: int = 25
    due_at: float | None = None
    status: str = "todo"
    snoozed_until: float = 0.0
    completed_at: float | None = None


@dataclass(frozen=True, slots=True)
class TaskSuggestion:
    task: Task
    reason: str


def default_tasks_path() -> Path:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "morok-assistant" / "tasks.json"


class TaskStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_tasks_path()

    def load(self) -> list[Task]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        tasks = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                task = Task(**{key: item[key] for key in Task.__dataclass_fields__ if key in item})
            except (TypeError, ValueError):
                continue
            if (
                not isinstance(task.task_id, str)
                or not isinstance(task.title, str)
                or not task.title.strip()
                or type(task.priority) is not int
                or task.priority not in {1, 2, 3}
                or type(task.estimate_minutes) is not int
                or not 5 <= task.estimate_minutes <= 480
                or not isinstance(task.status, str)
                or task.status not in STATUSES
                or not isinstance(task.created_at, (int, float))
                or (task.due_at is not None and not isinstance(task.due_at, (int, float)))
                or not isinstance(task.snoozed_until, (int, float))
                or (task.completed_at is not None
                    and not isinstance(task.completed_at, (int, float)))
            ):
                continue
            tasks.append(task)
        return tasks

    def save(self, tasks: list[Task]) -> None:
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".tasks-", suffix=".json", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump([asdict(task) for task in tasks], file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class TaskManager(QObject):
    changed = Signal()

    def __init__(self, store: TaskStore | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.store = store or TaskStore()
        self.tasks = self.store.load()

    def add(self, title: str, *, priority: int = 2, estimate_minutes: int = 25,
            due_at: float | None = None) -> Task:
        title = title.strip()
        if not title:
            raise ValueError("Введите название задачи")
        if priority not in {1, 2, 3} or not 5 <= estimate_minutes <= 480:
            raise ValueError("Проверьте приоритет и время задачи")
        task = Task(uuid.uuid4().hex, title, time(), priority, estimate_minutes, due_at)
        self._save([*self.tasks, task])
        return task

    def update(self, task_id: str, **changes: object) -> Task | None:
        for index, task in enumerate(self.tasks):
            if task.task_id == task_id:
                updated = replace(task, **changes)
                if not updated.title.strip() or updated.priority not in {1, 2, 3}:
                    raise ValueError("Проверьте название и приоритет задачи")
                if not 5 <= updated.estimate_minutes <= 480:
                    raise ValueError("Оценка времени должна быть от 5 до 480 минут")
                revised = self.tasks.copy()
                revised[index] = updated
                self._save(revised)
                return updated
        return None

    def start(self, task_id: str) -> None:
        if not any(task.task_id == task_id and task.status != "done" for task in self.tasks):
            return
        revised = [
            replace(task, status="in_progress", snoozed_until=0.0)
            if task.task_id == task_id and task.status != "done"
            else replace(task, status="todo") if task.status == "in_progress" else task
            for task in self.tasks
        ]
        self._save(revised)

    def complete(self, task_id: str) -> None:
        self.update(task_id, status="done", completed_at=time())

    def snooze(self, task_id: str, seconds: int = 3600) -> None:
        self.update(task_id, status="todo", snoozed_until=time() + seconds)

    def remove(self, task_id: str) -> None:
        self._save([task for task in self.tasks if task.task_id != task_id])

    def recommend(self, now: float | None = None) -> TaskSuggestion | None:
        now = time() if now is None else now
        current = next((task for task in self.tasks if task.status == "in_progress"), None)
        available = [
            task for task in self.tasks
            if task.status == "todo" and task.snoozed_until <= now
        ]
        urgent = [task for task in available if task.due_at is not None and task.due_at <= now]
        if current is not None and not urgent:
            return TaskSuggestion(current, "Вы уже начали эту задачу")
        if not available:
            return None

        def score(task: Task) -> tuple[float, float]:
            due = task.due_at
            urgency = 0.0 if due is None else (
                10_000 + min(1000, (now - due) / 3600)
                if due <= now else max(0, 1000 - (due - now) / 3600 * 40)
            )
            return urgency + task.priority * 100 + (480 - task.estimate_minutes) / 20, -task.created_at

        task = max(available, key=score)
        if task.due_at is not None and task.due_at <= now:
            reason = "Срок уже наступил"
        elif task.due_at is not None and task.due_at - now <= 24 * 3600:
            reason = "Срок скоро наступит"
        elif task.priority == 3:
            reason = "Высокий приоритет"
        else:
            reason = "Подходящая следующая задача"
        return TaskSuggestion(task, reason)

    def _save(self, revised: list[Task]) -> None:
        self.store.save(revised)
        self.tasks = revised
        self.changed.emit()
