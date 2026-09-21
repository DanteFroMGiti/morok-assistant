from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from morok_assistant.application.bootstrap import bundled_characters_path
from morok_assistant.characters.repository import CharacterRepository
from morok_assistant.core.events import EventBus
from morok_assistant.system.appearance import Appearance, AppearanceStore
from morok_assistant.ui.character_window import CharacterWindow


def test_appearance_store_rejects_invalid_values_and_protects_file(tmp_path: Path) -> None:
    store = AppearanceStore(tmp_path / "config" / "appearance.json")
    assert store.load() is None
    store.save(Appearance(45, 60, 0.5))
    assert store.load() == Appearance(45, 60, 0.5)
    assert store.path.stat().st_mode & 0o777 == 0o600

    for contents in ('{"x": true, "y": 60, "scale": 1}',
                     '{"x": 45, "y": 60, "scale": 500}',
                     '{"x": 999999, "y": 60, "scale": 1}',
                     "broken"):
        store.path.write_text(contents, encoding="utf-8")
        assert store.load() is None


def test_user_position_and_scale_are_restored(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    store = AppearanceStore(tmp_path / "appearance.json")
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus(), appearance_store=store)
    window.timer.stop()
    window.video_timer.stop()
    window.move(80, 100)
    window._dragging = True
    release = SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton, accept=lambda: None)
    window.mouseReleaseEvent(release)
    window.set_scale(0.5)
    assert store.load() == Appearance(80, 100, 0.5)
    window.close()

    restored = CharacterWindow(manifest, EventBus(), appearance_store=store)
    restored.timer.stop()
    restored.video_timer.stop()
    assert restored.restore_appearance()
    assert restored.pos() == QPoint(80, 100)
    assert restored.scale == 0.5
    restored.move_to_default_position()
    assert store.load() == Appearance(restored.x(), restored.y(), 0.5)
    restored.close()
    assert app is not None


def test_video_position_does_not_replace_user_position(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    store = AppearanceStore(tmp_path / "appearance.json")
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus(), appearance_store=store)
    window.timer.stop()
    window.video_timer.stop()
    window.move(250, 260)
    window._video_window_id = 42
    window._video_origin = QPoint(70, 80)

    window.set_scale(0.5)

    assert store.load() == Appearance(70, 80, 0.5)
    window.close()
    assert app is not None
