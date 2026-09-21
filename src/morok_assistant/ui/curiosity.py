from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from morok_assistant.productivity.curiosity import CuriosityStore


class CuriosityDialog(QDialog):
    answered = Signal(str)

    def __init__(self, store: CuriosityStore, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.store = store
        self.question = ""
        self.setWindowTitle("Вопросы и память Морока")
        self.setMinimumSize(480, 420)
        self.setStyleSheet(
            "QDialog { background: #25212b; color: #f5e9ef; } "
            "QLineEdit, QListWidget { background: #1b1821; color: #f5e9ef; "
            "border: 1px solid #814861; padding: 6px; } "
            "QPushButton { background: #753b58; color: white; padding: 7px; border-radius: 6px; }"
        )
        self.prompt = QLabel("Морок пока не задал вопрос.")
        self.prompt.setWordWrap(True)
        self.prompt.setStyleSheet("font-size: 15px; font-weight: 600; color: #f1b9d1")
        self.answer = QLineEdit()
        self.answer.setPlaceholderText("Твой ответ останется только на этом компьютере")
        self.answer.returnPressed.connect(self._remember)
        remember = QPushButton("Запомнить")
        remember.clicked.connect(self._remember)
        later = QPushButton("Позже")
        later.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addWidget(remember)
        row.addWidget(later)

        history_label = QLabel("Что Морок уже запомнил:")
        self.memories = QListWidget()
        self.memories.currentItemChanged.connect(self._show_memory)
        self.memory_detail = QLabel()
        self.memory_detail.setWordWrap(True)
        forget = QPushButton("Забыть выбранный ответ")
        forget.clicked.connect(self._forget)

        layout = QVBoxLayout(self)
        layout.addWidget(self.prompt)
        layout.addWidget(self.answer)
        layout.addLayout(row)
        layout.addWidget(history_label)
        layout.addWidget(self.memories, 1)
        layout.addWidget(self.memory_detail)
        layout.addWidget(forget)
        self.refresh()

    def show_question(self, question: str) -> None:
        self.question = question
        self.prompt.setText(question)
        self.answer.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.answer.setFocus()

    def _remember(self) -> None:
        if not self.question:
            return
        try:
            self.store.remember(self.question, self.answer.text())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Не удалось запомнить ответ", str(error))
            return
        self.answered.emit(self.question)
        self.question = ""
        self.prompt.setText("Спасибо. Я запомнил твой ответ.")
        self.answer.clear()
        self.refresh()

    def refresh(self) -> None:
        self.memories.clear()
        for memory in self.store.load():
            item = QListWidgetItem(memory.question)
            item.setData(Qt.ItemDataRole.UserRole, memory.question)
            self.memories.addItem(item)
        self.memory_detail.clear()

    def _show_memory(self) -> None:
        item = self.memories.currentItem()
        question = item.data(Qt.ItemDataRole.UserRole) if item else None
        memory = next((entry for entry in self.store.load() if entry.question == question), None)
        self.memory_detail.setText(memory.answer if memory else "")

    def _forget(self) -> None:
        item = self.memories.currentItem()
        if item is None:
            return
        try:
            self.store.forget(str(item.data(Qt.ItemDataRole.UserRole)))
        except OSError as error:
            QMessageBox.warning(self, "Не удалось забыть ответ", str(error))
            return
        self.refresh()
