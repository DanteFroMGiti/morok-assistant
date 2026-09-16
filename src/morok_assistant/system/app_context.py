from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActiveApplication:
    window_id: int
    title: str
    wm_class: str
    kind: str


APP_MARKERS = {
    "game": (
        "steam_app_",
        "gamescope",
        "lutris",
        "heroic",
        "bottles",
        "wine",
    ),
    "music": (
        "spotify",
        "rhythmbox",
        "strawberry",
        "clementine",
        "audacious",
        "amberol",
        "elisa",
        "yandex music",
        "яндекс музыка",
    ),
    "code": (
        "code-oss",
        "visual studio code",
        "vscodium",
        "pycharm",
        "intellij",
        "jetbrains",
        "sublime_text",
        "zed",
    ),
    "document": (
        "libreoffice",
        "onlyoffice",
        "okular",
        "evince",
        "zathura",
        "document viewer",
    ),
}


def classify_application(title: str, wm_class: str) -> str:
    value = f"{title} {wm_class}".casefold()
    for kind, markers in APP_MARKERS.items():
        if any(marker in value for marker in markers):
            return kind
    return "other"


class X11ActiveApplicationMonitor:
    def __init__(self) -> None:
        self._xprop = shutil.which("xprop")
        if self._xprop is None:
            raise RuntimeError("xprop is unavailable")

    @classmethod
    def create_if_available(cls) -> X11ActiveApplicationMonitor | None:
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            return None
        try:
            return cls()
        except RuntimeError:
            return None

    def current(self) -> ActiveApplication | None:
        root = self._run("-root", "_NET_ACTIVE_WINDOW")
        match = re.search(r"window id # (0x[0-9a-fA-F]+)", root)
        if match is None:
            return None
        window_id = int(match.group(1), 16)
        if not window_id:
            return None
        output = self._run(
            "-notype",
            "-f",
            "_NET_WM_NAME",
            "8u",
            "-id",
            hex(window_id),
            "_NET_WM_NAME",
            "WM_NAME",
            "WM_CLASS",
        )
        title_match = re.search(r'^_NET_WM_NAME = "(.*)"$', output, re.MULTILINE)
        if title_match is None:
            title_match = re.search(r'^WM_NAME = "(.*)"$', output, re.MULTILINE)
        class_match = re.search(r"^WM_CLASS = (.+)$", output, re.MULTILINE)
        title = title_match.group(1) if title_match else ""
        wm_class = class_match.group(1).replace('"', "") if class_match else ""
        return ActiveApplication(
            window_id,
            title,
            wm_class,
            classify_application(title, wm_class),
        )

    def _run(self, *arguments: str) -> str:
        environment = os.environ.copy()
        environment["LC_ALL"] = "C.UTF-8"
        try:
            result = subprocess.run(
                [self._xprop, *arguments],
                capture_output=True,
                text=True,
                timeout=0.8,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout if result.returncode == 0 else ""
