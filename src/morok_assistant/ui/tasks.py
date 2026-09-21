from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from morok_assistant.productivity.focus import FocusController
from morok_assistant.productivity.tasks import Task, TaskManager


class TasksDialog(QDialog):
    def __init__(self, manager: TaskManager, focus: FocusController, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.manager = manager
        self.focus = focus
        self.setWindowTitle("Задачи Морока")
        self.setMinimumSize(560, 560)
        self.setStyleSheet(
            "QDialog { background: #25212b; color: #f5e9ef; } "
            "QLineEdit, QListWidget, QComboBox, QDateTimeEdit, QSpinBox { "
            "background: #1b1821; color: #f5e9ef; border: 1px solid #814861; padding: 5px; } "
            "QPushButton { background: #753b58; color: white; padding: 7px; border-radius: 6px; }"
        )
        self.suggestion = QLabel()
        self.suggestion.setWordWrap(True)
        self.suggestion.setStyleSheet("font-size: 15px; font-weight: 600; color: #f1b9d1")
        self.items = QListWidget()
        self.items.currentItemChanged.connect(self._load_selected)

        self.title = QLineEdit()
        self.title.setPlaceholderText("Что нужно сделать?")
        self.priority = QComboBox()
        for label, value in (("Низкий", 1), ("Обычный", 2), ("Высокий", 3)):
            self.priority.addItem(label, value)
        self.priority.setCurrentIndex(1)
        self.estimate = QSpinBox()
        self.estimate.setRange(5, 480)
        self.estimate.setSingleStep(5)
        self.estimate.setValue(25)
        self.estimate.setSuffix(" мин")
        self.has_due = QCheckBox("Установить срок")
        self.due = QDateTimeEdit(QDateTime.currentDateTime().addDays(1))
        self.due.setCalendarPopup(True)
        self.due.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.due.setEnabled(False)
        self.has_due.toggled.connect(self.due.setEnabled)

        form = QFormLayout()
        form.addRow("Задача:", self.title)
        form.addRow("Приоритет:", self.priority)
        form.addRow("Оценка времени:", self.estimate)
        form.addRow(self.has_due, self.due)

        add = QPushButton("Добавить")
        add.clicked.connect(self._add)
        save = QPushButton("Сохранить правки")
        save.clicked.connect(self._update)
        edit_row = QHBoxLayout()
        edit_row.addWidget(add)
        edit_row.addWidget(save)

        start = QPushButton("Начать")
        start.clicked.connect(self._start)
        focus_button = QPushButton("Начать с концентрацией")
        focus_button.clicked.connect(lambda: self._start(with_focus=True))
        done = QPushButton("Готово")
        done.clicked.connect(self._complete)
        pause = QPushButton("Отложить на час")
        pause.clicked.connect(self._snooze)
        remove = QPushButton("Удалить")
        remove.clicked.connect(self._remove)
        action_row = QHBoxLayout()
        for button in (start, focus_button, done, pause, remove):
            action_row.addWidget(button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.suggestion)
        layout.addWidget(self.items, 1)
        layout.addLayout(form)
        layout.addLayout(edit_row)
        layout.addLayout(action_row)
        self.manager.changed.connect(self.refresh)
        self.refresh()

    def _selected(self) -> Task | None:
        item = self.items.currentItem()
        if item is None:
            return None
        return next((task for task in self.manager.tasks if task.task_id == item.data(Qt.ItemDataRole.UserRole)), None)

    def _load_selected(self) -> None:
        task = self._selected()
        if task is None:
            return
        self.title.setText(task.title)
        self.priority.setCurrentIndex(self.priority.findData(task.priority))
        self.estimate.setValue(task.estimate_minutes)
        self.has_due.setChecked(task.due_at is not None)
        if task.due_at is not None:
            self.due.setDateTime(QDateTime.fromSecsSinceEpoch(int(task.due_at)))

    def _values(self) -> dict:
        return {
            "title": self.title.text().strip(),
            "priority": self.priority.currentData(),
            "estimate_minutes": self.estimate.value(),
            "due_at": self.due.dateTime().toSecsSinceEpoch() if self.has_due.isChecked() else None,
        }

    def _add(self) -> None:
        try:
            self.manager.add(**self._values())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Задача не добавлена", str(error))
            return
        self.title.clear()

    def _update(self) -> None:
        task = self._selected()
        if task is None:
            return
        values = self._values()
        if not values["title"]:
            QMessageBox.warning(self, "Задача не сохранена", "Введите название задачи")
            return
        try:
            self.manager.update(task.task_id, **values)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Задача не сохранена", str(error))

    def _start(self, *, with_focus: bool = False) -> None:
        task = self._selected()
        if task is None or task.status == "done":
            return
        try:
            self.manager.start(task.task_id)
        except OSError as error:
            QMessageBox.warning(self, "Задача не начата", str(error))
            return
        if with_focus:
            self.focus.start(task.estimate_minutes, 5)

    def _complete(self) -> None:
        task = self._selected()
        if task is not None:
            try:
                self.manager.complete(task.task_id)
            except OSError as error:
                QMessageBox.warning(self, "Задача не завершена", str(error))

    def _snooze(self) -> None:
        task = self._selected()
        if task is not None and task.status != "done":
            try:
                self.manager.snooze(task.task_id)
            except OSError as error:
                QMessageBox.warning(self, "Задача не отложена", str(error))

    def _remove(self) -> None:
        task = self._selected()
        if task is not None:
            try:
                self.manager.remove(task.task_id)
            except OSError as error:
                QMessageBox.warning(self, "Задача не удалена", str(error))

    def refresh(self) -> None:
        selected = self._selected()
        selected_id = selected.task_id if selected else None
        self.items.clear()
        status = {"todo": "○", "in_progress": "▶", "done": "✓"}
        for task in sorted(self.manager.tasks, key=lambda item: (item.status == "done", -item.priority, item.created_at)):
            due = (
                f" · до {datetime.fromtimestamp(task.due_at, tz=UTC).astimezone():%d.%m %H:%M}"
                if task.due_at is not None else ""
            )
            item = QListWidgetItem(
                f"{status[task.status]} {task.title} · {task.estimate_minutes} мин{due}"
            )
            item.setData(Qt.ItemDataRole.UserRole, task.task_id)
            self.items.addItem(item)
            if task.task_id == selected_id:
                self.items.setCurrentItem(item)
        suggestion = self.manager.recommend()
        self.suggestion.setText(
            f"Сейчас стоит: {suggestion.task.title}\n{suggestion.reason}"
            if suggestion else "Сейчас нет задач, которые требуют внимания."
        )
