from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from morok_assistant.ai.settings import AISettingsStore
from morok_assistant.system.autostart import AutostartManager
from morok_assistant.system.behavior_settings import BehaviorSettingsStore
from morok_assistant.system.startup_apps import (
    StartupApplication,
    StartupApplicationsStore,
)
from morok_assistant.ui.ai_settings import AISettingsDialog


def test_behavior_checkboxes_apply_autostart_and_video_setting(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    ai_store = AISettingsStore(tmp_path / "config" / "ai.json")
    behavior_store = BehaviorSettingsStore(tmp_path / "config" / "behavior.json")
    autostart = AutostartManager(tmp_path / "autostart" / "morok-assistant.desktop")
    startup_apps = StartupApplicationsStore(tmp_path / "config" / "startup-apps.json")
    startup_apps.save([StartupApplication("Telegram", "/apps/telegram.desktop")])
    dialog = AISettingsDialog(
        ai_store,
        behavior_store=behavior_store,
        autostart=autostart,
        startup_apps_store=startup_apps,
    )

    dialog.autostart.setChecked(True)
    dialog.watch_videos.setChecked(False)
    dialog.react_to_music.setChecked(False)
    dialog.react_to_code.setChecked(False)
    dialog.wayland_mode.setCurrentIndex(dialog.wayland_mode.findData("native"))
    dialog.personality_mode.setCurrentIndex(dialog.personality_mode.findData("curious"))
    dialog.reaction_frequency.setCurrentIndex(dialog.reaction_frequency.findData("often"))
    dialog.startup_apps.item(0).setCheckState(Qt.CheckState.Unchecked)
    dialog._save()

    assert dialog.result() == dialog.DialogCode.Accepted
    assert autostart.enabled
    behavior = behavior_store.load()
    assert not behavior.watch_videos
    assert not behavior.react_to_music
    assert not behavior.react_to_code
    assert behavior.wayland_mode == "native"
    assert behavior.personality_mode == "curious"
    assert behavior.reaction_frequency == "often"
    assert startup_apps.load() == [
        StartupApplication("Telegram", "/apps/telegram.desktop", enabled=False)
    ]
    dialog.close()
    assert app is not None
