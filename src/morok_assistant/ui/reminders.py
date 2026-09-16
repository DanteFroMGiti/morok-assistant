from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QGroupBox,
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

from morok_assistant.productivity.reminders import ReminderManager


class RemindersDialog(QDialog):
    def __init__(self, manager: ReminderManager, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Таймеры и напоминания")
        self.setMinimumSize(500, 440)

        self.timer_text = QLineEdit()
        self.timer_text.setPlaceholderText("Например: проверить загрузку")
        self.timer_value = QSpinBox()
        self.timer_value.setRange(1, 999)
        self.timer_value.setValue(25)
        self.timer_unit = QComboBox()
        self.timer_unit.addItem("минут", 60)
        self.timer_unit.addItem("часов", 3600)
        start_timer = QPushButton("Запустить таймер")
        start_timer.clicked.connect(self._add_timer)

        timer_group = QGroupBox("Таймер")
        timer_form = QFormLayout(timer_group)
        timer_form.addRow("Что напомнить:", self.timer_text)
        duration = QHBoxLayout()
        duration.addWidget(self.timer_value)
        duration.addWidget(self.timer_unit)
        timer_form.addRow("Через:", duration)
        timer_form.addRow(start_timer)

        self.reminder_text = QLineEdit()
        self.reminder_text.setPlaceholderText("Например: позвонить")
        self.reminder_time = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.reminder_time.setCalendarPopup(True)
        self.reminder_time.setDisplayFormat("dd.MM.yyyy HH:mm")
        add_reminder = QPushButton("Добавить напоминание")
        add_reminder.clicked.connect(self._add_reminder)

        reminder_group = QGroupBox("Напоминание")
        reminder_form = QFormLayout(reminder_group)
        reminder_form.addRow("Текст:", self.reminder_text)
        reminder_form.addRow("Когда:", self.reminder_time)
        reminder_form.addRow(add_reminder)

        self.items = QListWidget()
        self.empty = QLabel("Активных таймеров и напоминаний нет")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        remove = QPushButton("Удалить выбранное")
        remove.clicked.connect(self._remove_selected)

        layout = QVBoxLayout(self)
        layout.addWidget(timer_group)
        layout.addWidget(reminder_group)
        layout.addWidget(QLabel("Ожидают:"))
        layout.addWidget(self.empty)
        layout.addWidget(self.items, 1)
        layout.addWidget(remove)
        self.manager.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.items.clear()
        for reminder in self.manager.reminders:
            timestamp = datetime.fromtimestamp(reminder.due_at, tz=UTC).astimezone()
            timestamp_text = timestamp.strftime("%d.%m %H:%M")
            item = QListWidgetItem(f"{timestamp_text} — {reminder.text}")
            item.setData(Qt.ItemDataRole.UserRole, reminder.reminder_id)
            self.items.addItem(item)
        self.empty.setVisible(not self.manager.reminders)
        self.items.setVisible(bool(self.manager.reminders))

    def _add_timer(self) -> None:
        seconds = self.timer_value.value() * int(self.timer_unit.currentData())
        try:
            self.manager.add_timer(self.timer_text.text(), seconds)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Таймер не создан", str(error))
            return
        self.timer_text.clear()

    def _add_reminder(self) -> None:
        try:
            self.manager.add(
                self.reminder_text.text(),
                float(self.reminder_time.dateTime().toSecsSinceEpoch()),
            )
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Напоминание не создано", str(error))
            return
        self.reminder_text.clear()

    def _remove_selected(self) -> None:
        item = self.items.currentItem()
        if item is not None:
            self.manager.remove(str(item.data(Qt.ItemDataRole.UserRole)))
