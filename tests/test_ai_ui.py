from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from morok_assistant.ai.settings import AISettings, AISettingsStore
from morok_assistant.application.bootstrap import bundled_characters_path
from morok_assistant.characters.repository import CharacterRepository
from morok_assistant.core.events import EventBus
from morok_assistant.ui.ai_settings import AISettingsDialog
from morok_assistant.ui.character_window import CharacterWindow


class FakeConnector(QObject):
    answered = Signal(str, str)
    failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.busy = False
        self.sent = []

    def send(self, settings, message, previous_response_id, history) -> None:
        self.busy = True
        self.sent.append(
            (settings.provider, settings.model, message, previous_response_id, list(history))
        )

        def respond() -> None:
            self.busy = False
            self.answered.emit("Ответ Морока", "resp_1")

        QTimer.singleShot(0, respond)

    def cancel(self) -> None:
        self.busy = False


def test_switching_provider_keeps_each_key_and_model(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    store = AISettingsStore(tmp_path / "ai.json")
    store.save(AISettings(enabled=True, model="gpt-5.6-luna", api_key="openai-key"))
    dialog = AISettingsDialog(store)

    dialog.provider.setCurrentIndex(dialog.provider.findData("anthropic"))
    dialog.model.setCurrentText("claude-sonnet-5")
    dialog.api_key.setText("claude-key")
    dialog.provider.setCurrentIndex(dialog.provider.findData("openai"))
    assert dialog.model.currentText() == "gpt-5.6-luna"
    assert dialog.api_key.text() == "openai-key"
    dialog.provider.setCurrentIndex(dialog.provider.findData("anthropic"))
    assert dialog.api_key.text() == "claude-key"
    dialog._save()

    loaded = store.load()
    assert loaded.provider == "anthropic" and loaded.model == "claude-sonnet-5"
    assert loaded.api_keys == {"openai": "openai-key", "anthropic": "claude-key"}
    dialog.close()
    assert app is not None


def test_settings_enable_model_and_chat_reply_appears_in_morok_bubble(
    tmp_path: Path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    store = AISettingsStore(tmp_path / "ai.json")
    settings = AISettingsDialog(store)
    settings.enabled.setChecked(True)
    settings.model.setCurrentText("gpt-5.6-luna")
    settings.api_key.setText("test-key")
    settings._save()
    assert store.load().ready
    assert store.load().model == "gpt-5.6-luna"
    assert settings.result() == settings.DialogCode.Accepted
    settings.close()

    monkeypatch.setattr("morok_assistant.ui.ai_chat.AIConnector", FakeConnector)
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus(), ai_settings_store=store)
    window.timer.stop()
    window.peek_controller.activity_timer.stop()
    window.show()
    window.open_ai_chat()
    chat = window.ai_chat_dialog
    assert chat is not None
    assert chat.objectName() == "morokChat"
    assert "#87304f" in chat.styleSheet()
    assert chat.model_label.text() == "Сервис: OpenAI (GPT) · модель: gpt-5.6-luna"
    assert not window.peek_controller.auto_peek_enabled

    loop = QEventLoop()
    chat.answer_received.connect(lambda _text: loop.quit())
    chat.input.setPlainText("Привет!")
    chat.send_message()
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert chat.connector.sent == [("openai", "gpt-5.6-luna", "Привет!", None, [])]
    assert "Ответ Морока" in chat.transcript.toPlainText()
    assert window.joke_bubble.label.text() == "Ответ Морока"

    store.save(AISettings(enabled=True, model="gpt-5.6-terra", api_key="test-key"))
    chat.input.setPlainText("Второй вопрос")
    chat.send_message()
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert chat.connector.sent[-1] == ("openai", "gpt-5.6-terra", "Второй вопрос", None, [])
    assert chat.model_label.text() == "Сервис: OpenAI (GPT) · модель: gpt-5.6-terra"

    chat.close()
    assert window.peek_controller.auto_peek_enabled
    window.close()
    assert app is not None
