from __future__ import annotations

from collections.abc import Callable
from html import escape

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from morok_assistant.ai.client import AIConnector
from morok_assistant.ai.providers import provider_name
from morok_assistant.ai.settings import AISettingsStore


class AIChatDialog(QDialog):
    interacted = Signal()
    answer_received = Signal(str)
    request_started = Signal()
    request_finished = Signal()

    def __init__(
        self,
        store: AISettingsStore,
        open_settings: Callable[[], bool],
        parent: QWidget | None = None,
        connector: AIConnector | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.open_settings = open_settings
        self.settings = store.load()
        self._previous_response_id: str | None = None
        self._history: list[tuple[str, str]] = []
        self._pending_message: str | None = None
        self.connector = connector or AIConnector(self)
        self.connector.answered.connect(self._on_answer)
        self.connector.failed.connect(self._on_error)
        self.setObjectName("morokChat")
        self.setWindowTitle("Диалог с Мороком")
        self.resize(540, 600)
        self.setMinimumSize(440, 460)
        self.setStyleSheet(
            """
            QDialog#morokChat {
                background-color: #110f16;
                color: #f5eaf0;
            }
            QFrame#chatHeader {
                background-color: #1c1722;
                border: 1px solid #4f3144;
                border-radius: 14px;
            }
            QLabel#eyeMark {
                color: #e84f78;
                font-size: 28px;
                font-weight: 700;
            }
            QLabel#chatTitle {
                color: #fff1f6;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#modelLabel {
                color: #bda8b5;
                font-size: 12px;
            }
            QTextBrowser#transcript {
                background-color: #15121a;
                color: #f2e9ef;
                border: 1px solid #513747;
                border-radius: 14px;
                padding: 10px;
                selection-background-color: #8f3658;
            }
            QPlainTextEdit#messageInput {
                background-color: #201a25;
                color: #fff4f8;
                border: 1px solid #684257;
                border-radius: 12px;
                padding: 10px;
                selection-background-color: #9f3f63;
                font-size: 14px;
            }
            QPlainTextEdit#messageInput:focus {
                border: 1px solid #c25078;
            }
            QLabel#statusLabel {
                color: #aa98a5;
                padding: 1px 4px;
            }
            QPushButton {
                background-color: #28202d;
                color: #eadde5;
                border: 1px solid #654357;
                border-radius: 10px;
                padding: 8px 13px;
                min-height: 18px;
            }
            QPushButton:hover {
                background-color: #382633;
                border-color: #a34a6b;
            }
            QPushButton:pressed {
                background-color: #1c171f;
            }
            QPushButton#sendButton {
                background-color: #87304f;
                color: #fff7fa;
                border-color: #c6577d;
                font-weight: 700;
                padding-left: 18px;
                padding-right: 18px;
            }
            QPushButton#sendButton:hover {
                background-color: #a13b60;
            }
            QPushButton:disabled {
                background-color: #28242b;
                color: #746a71;
                border-color: #3d343a;
            }
            QScrollBar:vertical {
                background: #15121a;
                width: 10px;
                margin: 4px 2px;
            }
            QScrollBar::handle:vertical {
                background: #624052;
                min-height: 28px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )

        header = QFrame()
        header.setObjectName("chatHeader")
        eye = QLabel("◉")
        eye.setObjectName("eyeMark")
        title = QLabel("Морок")
        title.setObjectName("chatTitle")
        self.model_label = QLabel()
        self.model_label.setObjectName("modelLabel")
        self.model_label.setWordWrap(True)
        self._update_model_label()
        title_column = QVBoxLayout()
        title_column.setSpacing(1)
        title_column.addWidget(title)
        title_column.addWidget(self.model_label)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 11, 16, 11)
        header_layout.setSpacing(11)
        header_layout.addWidget(eye)
        header_layout.addLayout(title_column, 1)

        self.transcript = QTextBrowser()
        self.transcript.setObjectName("transcript")
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setPlaceholderText("Здесь появится ваш разговор с Мороком.")
        self.input = QPlainTextEdit()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Напишите Мороку…  Ctrl+Enter — отправить")
        self.input.setFixedHeight(86)
        self.input.installEventFilter(self)
        self.input.textChanged.connect(self.interacted)
        self.status = QLabel("Диалог отправляется выбранному сервису ИИ.")
        self.status.setObjectName("statusLabel")
        self.status.setWordWrap(True)

        self.send_button = QPushButton("Отправить Мороку")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self.send_message)
        new_button = QPushButton("Новый диалог")
        new_button.clicked.connect(self.new_conversation)
        settings_button = QPushButton("Настройки")
        settings_button.clicked.connect(self._open_settings)

        controls = QHBoxLayout()
        controls.addWidget(new_button)
        controls.addWidget(settings_button)
        controls.addStretch()
        controls.addWidget(self.send_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(header)
        layout.addWidget(self.transcript, 1)
        layout.addWidget(self.input)
        layout.addWidget(self.status)
        layout.addLayout(controls)

    def _update_model_label(self) -> None:
        self.model_label.setText(
            f"Сервис: {provider_name(self.settings.provider)} · модель: {self.settings.model}"
        )

    def set_draft(self, text: str) -> None:
        self.input.setPlainText(text)
        self.input.setFocus()

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if (
            watched is self.input
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.send_message()
            return True
        return super().eventFilter(watched, event)

    def _append(self, speaker: str, text: str) -> None:
        safe = escape(text).replace("\n", "<br>")
        is_morok = speaker == "Морок"
        align = "left" if is_morok else "right"
        background = "#2a1d29" if is_morok else "#352232"
        accent = "#ef7599" if is_morok else "#c7a6d7"
        self.transcript.append(
            f"<div align='{align}' style='margin:8px 2px'>"
            f"<table width='86%' cellspacing='0' cellpadding='9' bgcolor='{background}'>"
            f"<tr><td><span style='color:{accent}; font-weight:600'>"
            f"{escape(speaker)}</span><br><span style='color:#f5edf2'>{safe}</span>"
            "</td></tr></table></div>"
        )

    def send_message(self) -> None:
        message = self.input.toPlainText().strip()
        if not message or self.connector.busy:
            return
        updated = self.store.load()
        if updated != self.settings:
            self.settings = updated
            self.new_conversation()
        self._update_model_label()
        if not self.settings.ready:
            self.status.setText("Подключите ИИ и заполните настройки выбранного сервиса.")
            return
        try:
            self.connector.send(self.settings, message, self._previous_response_id, self._history)
        except (RuntimeError, ValueError) as error:
            self.status.setText(str(error))
            return
        self._append("Вы", message)
        self._pending_message = message
        self.input.clear()
        self.send_button.setEnabled(False)
        self.status.setText("Морок думает…")
        self.request_started.emit()
        self.interacted.emit()

    def _on_answer(self, text: str, response_id: str) -> None:
        if self._pending_message is not None:
            self._history.extend((("user", self._pending_message), ("assistant", text)))
        self._pending_message = None
        self._previous_response_id = response_id or None
        self._append("Морок", text)
        self.answer_received.emit(text)
        self._end_request("Ответ получен.")

    def _on_error(self, message: str) -> None:
        if self._pending_message is not None and not self.input.toPlainText().strip():
            self.input.setPlainText(self._pending_message)
        self._pending_message = None
        self._end_request(f"Ошибка подключения: {message}")

    def _end_request(self, status: str) -> None:
        self.send_button.setEnabled(True)
        self.status.setText(status)
        self.request_finished.emit()

    def new_conversation(self) -> None:
        if self.connector.busy:
            self.connector.cancel()
            self._end_request("Запрос отменён.")
        self._previous_response_id = None
        self._history.clear()
        self._pending_message = None
        self.transcript.clear()
        self.status.setText("Новый диалог начат.")
        self.interacted.emit()

    def _open_settings(self) -> None:
        if not self.open_settings():
            return
        updated = self.store.load()
        if updated != self.settings:
            self.settings = updated
            self.new_conversation()
            self._update_model_label()
            self.status.setText("Настройки обновлены. Начат новый диалог.")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.connector.busy:
            self.connector.cancel()
            self._end_request("Запрос отменён.")
        super().closeEvent(event)
