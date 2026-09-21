from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from morok_assistant.ai.settings import AISettingsStore
from morok_assistant.characters.repository import CharacterRepository
from morok_assistant.core.events import EventBus
from morok_assistant.jokes.repository import JokeRepository
from morok_assistant.plugins.manager import PluginManager
from morok_assistant.system.appearance import AppearanceStore
from morok_assistant.system.autostart import project_root
from morok_assistant.system.behavior_settings import BehaviorSettingsStore
from morok_assistant.system.plasma import (
    PlasmaApplicationMonitor,
    PlasmaBridge,
    PlasmaVideoMonitor,
    install_kwin_script,
)
from morok_assistant.system.startup_apps import (
    StartupApplicationsStore,
    launch_startup_applications,
)
from morok_assistant.system.wayland import configure_platform, is_plasma_wayland
from morok_assistant.ui.character_window import CharacterWindow


def bundled_characters_path() -> Path:
    package_root = Path(__file__).resolve().parents[1]
    return package_root / "assets" / "characters"


def jokes_path() -> Path:
    project_root = Path(__file__).resolve().parents[3]
    if (project_root / "pyproject.toml").is_file():
        return project_root / "jokes.txt"
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = config_root / "morok-assistant" / "jokes.txt"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        bundled_jokes = Path(__file__).resolve().parents[1] / "assets" / "jokes.txt"
        contents = (
            bundled_jokes.read_text(encoding="utf-8")
            if bundled_jokes.is_file()
            else "# Каждый анекдот отделяйте пустой строкой.\n"
        )
        path.write_text(contents, encoding="utf-8")
    return path


def application_icon_path() -> Path | None:
    root = project_root()
    project_icon = root / "morok-icon.png" if root is not None else None
    if project_icon is not None and project_icon.is_file():
        return project_icon
    bundled_icon = Path(__file__).resolve().parents[1] / "assets" / "morok-icon.png"
    return bundled_icon if bundled_icon.is_file() else None


def run() -> int:
    behavior_store = BehaviorSettingsStore()
    configure_platform(behavior_store.load().wayland_mode)
    app = QApplication(sys.argv)
    app.setApplicationName("Morok Assistant")
    app.setDesktopFileName("morok-assistant")
    app.setQuitOnLastWindowClosed(True)
    runtime_directory = Path(os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir()))
    instance_lock = QLockFile(str(runtime_directory / f"morok-assistant-{os.getuid()}.lock"))
    if not instance_lock.tryLock(100):
        return 0
    icon = application_icon_path()
    if icon is not None:
        app.setWindowIcon(QIcon(str(icon)))

    events = EventBus()
    plugins = PluginManager(events)
    repository = CharacterRepository(bundled_characters_path())
    manifest = repository.get("morok")

    bridge = PlasmaBridge() if is_plasma_wayland() else None
    if bridge is not None and not bridge.start():
        bridge = None
    window = CharacterWindow(
        manifest, events, JokeRepository(jokes_path()), AISettingsStore(),
        behavior_store=behavior_store,
        appearance_store=AppearanceStore(),
        video_monitor=PlasmaVideoMonitor(bridge) if bridge else None,
        app_monitor=PlasmaApplicationMonitor(bridge) if bridge else None,
    )
    if not window.restore_appearance():
        window.move_to_default_position()
    window.show()
    if bridge is not None:
        QTimer.singleShot(0, install_kwin_script)
        app.aboutToQuit.connect(bridge.stop)
    startup_apps = StartupApplicationsStore()
    QTimer.singleShot(1_000, lambda: launch_startup_applications(startup_apps))
    plugins.start_all()
    app.aboutToQuit.connect(plugins.stop_all)
    app.aboutToQuit.connect(window.stop_jokes)
    app.aboutToQuit.connect(window.stop_ai)
    app.aboutToQuit.connect(window.stop_idle_peek)
    app.aboutToQuit.connect(window.stop_video_watch)
    return app.exec()
