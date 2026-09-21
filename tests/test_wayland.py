from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtDBus import QDBusMessage
from PySide6.QtWidgets import QApplication

from morok_assistant.system.behavior_settings import BehaviorSettings, BehaviorSettingsStore
from morok_assistant.system.plasma import (
    PlasmaApplicationMonitor,
    PlasmaBridge,
    PlasmaVideoMonitor,
    install_kwin_script,
)
from morok_assistant.system.wayland import configure_platform, is_plasma_wayland

WINDOW_ID = "{11111111-1111-1111-1111-111111111111}"


def test_wayland_auto_uses_xwayland_without_overriding_explicit_qt_choice(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)

    assert configure_platform("auto") == "xcb"
    assert configure_platform("native") == "xcb"

    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
    assert configure_platform("auto") == "wayland"


def test_wayland_without_xwayland_and_native_selection(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert configure_platform("auto") == "wayland"

    monkeypatch.setenv("DISPLAY", ":1")
    assert configure_platform("native") == "wayland"
    assert "QT_QPA_PLATFORM" not in os.environ

    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert configure_platform("auto") == "x11"


def test_plasma_detection_and_mode_setting(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE:Plasma")
    assert is_plasma_wayland()
    store = BehaviorSettingsStore(tmp_path / "behavior.json")
    store.save(BehaviorSettings(wayland_mode="native"))
    assert store.load().wayland_mode == "native"
    store.path.write_text('{"wayland_mode": "unknown"}', encoding="utf-8")
    assert store.load().wayland_mode == "auto"
    store.path.write_text('{"wayland_mode": []}', encoding="utf-8")
    assert store.load().wayland_mode == "auto"


def test_plasma_bridge_tracks_video_and_active_application() -> None:
    bridge = PlasmaBridge()
    bridge.update_window(WINDOW_ID, "Видео - YouTube - Vivaldi", "vivaldi-stable",
                         20, 30, 840, 480, False, False)
    bridge.set_active_window(WINDOW_ID)

    video = PlasmaVideoMonitor(bridge).current()
    assert video is not None
    assert (video.x, video.y, video.width, video.height) == (20, 30, 840, 480)
    bridge.update_window(WINDOW_ID, "Видео - YouTube - Vivaldi", "vivaldi-stable",
                         70, 80, 840, 480, False, False)
    assert PlasmaVideoMonitor(bridge).current().x == 70
    assert PlasmaApplicationMonitor(bridge).current().wm_class == "vivaldi-stable"

    bridge.set_active_window("morok")
    assert PlasmaVideoMonitor(bridge).current().x == 70
    bridge.forget_window(WINDOW_ID)
    assert PlasmaVideoMonitor(bridge).current() is None


def test_plasma_bridge_sees_floating_video_behind_active_window() -> None:
    bridge = PlasmaBridge()
    bridge.update_window(WINDOW_ID, "Картинка в картинке", "vivaldi", 10, 10, 460, 260,
                         False, True)
    bridge.update_window("{22222222-2222-2222-2222-222222222222}", "Редактор", "code-oss",
                         100, 200, 900, 700, False, False)
    bridge.set_active_window("{22222222-2222-2222-2222-222222222222}")

    assert PlasmaApplicationMonitor(bridge).current().kind == "code"
    assert PlasmaVideoMonitor(bridge).current().window_id == UUID(WINDOW_ID).int


def test_kwin_script_assets_are_bundled() -> None:
    from morok_assistant.system.plasma import SCRIPT_ID

    script_dir = Path(__file__).resolve().parents[1] / "src/morok_assistant/assets/kwin" / SCRIPT_ID
    assert (script_dir / "metadata.json").is_file()
    script = (script_dir / "contents/code/main.js").read_text(encoding="utf-8")
    assert "frameGeometryChanged.connect" in script
    assert "skipTaskbar = true" in script


def test_kwin_method_reaches_the_python_bridge_over_session_dbus() -> None:
    app = QApplication.instance() or QApplication([])
    bridge = PlasmaBridge()
    if not bridge.start():
        pytest.skip("No session D-Bus or Morok bridge already registered")
    try:
        message = QDBusMessage.createMethodCall(
            "org.morok.Assistant", "/DesktopIntegration", "org.morok.DesktopIntegration",
            "update_window",
        )
        message.setArguments(
            [WINDOW_ID, "Видео - YouTube", "vivaldi", 30, 40, 800, 500, False, False]
        )
        bridge.bus.asyncCall(message)
        QTimer.singleShot(100, app.quit)
        app.exec()
        assert bridge.windows[WINDOW_ID].x == 30
    finally:
        bridge.stop()


def test_plasma_installer_copies_script_and_enables_it(tmp_path, monkeypatch) -> None:
    from morok_assistant.system import plasma

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(plasma.shutil, "which", lambda _: "/usr/bin/kwriteconfig6")
    commands = []
    monkeypatch.setattr(
        plasma.subprocess, "run",
        lambda command, **_kwargs: (commands.append(command) or SimpleNamespace(
            returncode=0, stderr=""
        )),
    )

    class FakeKWin:
        def __init__(self, *_args):
            pass

        def isValid(self):
            return True

        def call(self, method):
            assert method == "reconfigure"
            return QDBusMessage()

    monkeypatch.setattr(plasma, "QDBusInterface", FakeKWin)

    assert install_kwin_script()
    installed = tmp_path / "kwin/scripts/morok-integration"
    assert (installed / "metadata.json").is_file()
    assert (installed / "contents/code/main.js").is_file()
    assert commands[0][-2:] == ["morok-integrationEnabled", "true"]
