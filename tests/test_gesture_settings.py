from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from morok_assistant.ai.settings import AISettingsStore
from morok_assistant.application.bootstrap import bundled_characters_path
from morok_assistant.characters.repository import CharacterRepository
from morok_assistant.core.events import EventBus
from morok_assistant.ui.ai_settings import AISettingsDialog
from morok_assistant.ui.character_window import CharacterWindow
from morok_assistant.ui.gesture_settings import GestureSettingsStore


def test_gesture_choices_persist_and_change_double_click_and_hover(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    store = AISettingsStore(tmp_path / "ai.json")
    dialog = AISettingsDialog(store)
    dialog.double_click.setCurrentIndex(dialog.double_click.findData("sit"))
    dialog.hover.setCurrentIndex(dialog.hover.findData("watch"))
    dialog.hover_cooldown.setCurrentIndex(dialog.hover_cooldown.findData(90))
    dialog._save()
    dialog.close()

    gesture_path = tmp_path / "gestures.json"
    gestures = GestureSettingsStore(gesture_path).load()
    assert (gestures.double_click, gestures.hover, gestures.hover_cooldown_seconds) == (
        "sit", "watch", 90
    )
    assert gesture_path.stat().st_mode & 0o777 == 0o600

    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus(), ai_settings_store=store)
    window.timer.stop()
    window.peek_controller.activity_timer.stop()
    event = SimpleNamespace(
        button=lambda: Qt.MouseButton.LeftButton,
        accept=lambda: None,
    )
    window.mouseDoubleClickEvent(event)
    assert window.player.state == "sit_down"

    monkeypatch.setattr(window, "underMouse", lambda: True)
    window._on_hover_gesture()
    assert window._mouse_watch_until > 0
    window.close()
    assert app is not None
