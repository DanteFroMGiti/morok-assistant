from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import ClassInfo, QObject, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface

from morok_assistant.system.app_context import ActiveApplication, classify_application
from morok_assistant.system.idle import AudioActivityMonitor
from morok_assistant.system.video import VideoWindow, is_video_window
from morok_assistant.system.wayland import is_plasma_wayland

LOG = logging.getLogger(__name__)
SCRIPT_ID = "morok-integration"


@dataclass(frozen=True)
class PlasmaWindow:
    identifier: str
    title: str
    wm_class: str
    x: int
    y: int
    width: int
    height: int
    fullscreen: bool
    floating: bool

    @property
    def window_id(self) -> int:
        # KWin's internalId is a UUID; use a stable non-negative integer for the UI.
        return UUID(self.identifier).int


@ClassInfo({"D-Bus Interface": "org.morok.DesktopIntegration"})
class PlasmaBridge(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.windows: dict[str, PlasmaWindow] = {}
        self.active_id = ""
        self.last_video_id = ""
        self.audio = AudioActivityMonitor()
        self.bus = QDBusConnection.sessionBus()

    def start(self) -> bool:
        if not self.bus.isConnected() or not self.bus.registerService("org.morok.Assistant"):
            return False
        if not self.bus.registerObject(
            "/DesktopIntegration", self, QDBusConnection.RegisterOption.ExportAllSlots
        ):
            self.bus.unregisterService("org.morok.Assistant")
            return False
        return True

    @Slot(str, str, str, int, int, int, int, bool, bool)
    def update_window(
        self, identifier: str, title: str, wm_class: str, x: int, y: int,
        width: int, height: int, fullscreen: bool, floating: bool,
    ) -> None:
        if not identifier or width <= 0 or height <= 0:
            return
        self.windows[identifier] = PlasmaWindow(
            identifier, title, wm_class, x, y, width, height, fullscreen, floating
        )

    @Slot(str)
    def set_active_window(self, identifier: str) -> None:
        self.active_id = identifier

    @Slot(str)
    def forget_window(self, identifier: str) -> None:
        self.windows.pop(identifier, None)
        if self.active_id == identifier:
            self.active_id = ""
        if self.last_video_id == identifier:
            self.last_video_id = ""

    def stop(self) -> None:
        self.bus.unregisterObject("/DesktopIntegration")
        self.bus.unregisterService("org.morok.Assistant")


class PlasmaApplicationMonitor:
    def __init__(self, bridge: PlasmaBridge) -> None:
        self.bridge = bridge

    def current(self) -> ActiveApplication | None:
        window = self.bridge.windows.get(self.bridge.active_id)
        if window is None:
            return None
        return ActiveApplication(
            window.window_id, window.title, window.wm_class,
            classify_application(window.title, window.wm_class),
        )


class PlasmaVideoMonitor:
    def __init__(self, bridge: PlasmaBridge) -> None:
        self.bridge = bridge

    def current(self) -> VideoWindow | None:
        windows = self.bridge.windows
        active = windows.get(self.bridge.active_id)
        candidates = [window for window in windows.values() if window.floating]
        if active is not None:
            candidates.append(active)
        elif self.bridge.active_id == "morok":
            remembered = windows.get(self.bridge.last_video_id)
            if remembered is not None:
                candidates.append(remembered)
        for window in reversed(candidates):
            if window.width < 320 or window.height < 180:
                continue
            if is_video_window(
                window.title, window.wm_class, fullscreen=window.fullscreen, audio_active=False
            ) or (window.fullscreen and is_video_window(
                window.title, window.wm_class, fullscreen=True,
                audio_active=self.bridge.audio.active(),
            )):
                self.bridge.last_video_id = window.identifier
                return VideoWindow(
                    window.window_id, window.title, window.wm_class,
                    window.x, window.y, window.width, window.height, window.fullscreen,
                )
        return None

    def close(self) -> None:
        pass  # The bridge belongs to the application, not the window.


def install_kwin_script() -> bool:
    """Install Morok's user-level KWin script and enable it for the current session."""
    if not is_plasma_wayland():
        return False
    config = shutil.which("kwriteconfig6")
    if config is None:
        LOG.warning("Plasma integration requires kwriteconfig6")
        return False
    source = Path(__file__).resolve().parents[1] / "assets" / "kwin" / SCRIPT_ID
    target = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    target = target / "kwin" / "scripts" / SCRIPT_ID
    try:
        for relative in ("metadata.json", "contents/code/main.js"):
            destination = target / relative
            contents = (source / relative).read_bytes()
            if not destination.is_file() or destination.read_bytes() != contents:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(contents)
        result = subprocess.run(
            [config, "--file", "kwinrc", "--group", "Plugins",
             "--key", f"{SCRIPT_ID}Enabled", "true"],
            capture_output=True, text=True, timeout=4, check=False,
        )
        if result.returncode:
            LOG.warning("KWin script could not be enabled: %s", result.stderr.strip())
            return False
        kwin = QDBusInterface("org.kde.KWin", "/KWin", "org.kde.KWin")
        if not kwin.isValid():
            return False
        reply = kwin.call("reconfigure")
        return reply.type() != reply.MessageType.ErrorMessage
    except (OSError, subprocess.TimeoutExpired) as error:
        LOG.warning("KWin integration could not be installed: %s", error)
        return False
