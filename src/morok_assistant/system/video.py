from __future__ import annotations

import ast
import ctypes
import ctypes.util
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from morok_assistant.system.idle import AudioActivityMonitor

VIDEO_PLAYERS = {
    "celluloid",
    "dragon",
    "haruna",
    "kodi",
    "mpv",
    "smplayer",
    "totem",
    "vlc",
}
VIDEO_TITLE_MARKERS = (
    "youtube",
    "twitch",
    "netflix",
    "vimeo",
    "rutube",
    "кинопоиск",
    "vk видео",
    "vk video",
    "ivi.ru",
    "okko",
    "кион",
    "wink",
    "dailymotion",
    "picture-in-picture",
    "картинка в картинке",
)


@dataclass(frozen=True, slots=True)
class VideoWindow:
    window_id: int
    title: str
    wm_class: str
    x: int
    y: int
    width: int
    height: int
    fullscreen: bool = False


class _XWindowAttributes(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("border_width", ctypes.c_int),
        ("depth", ctypes.c_int),
        ("visual", ctypes.c_void_p),
        ("root", ctypes.c_ulong),
        ("window_class", ctypes.c_int),
        ("bit_gravity", ctypes.c_int),
        ("win_gravity", ctypes.c_int),
        ("backing_store", ctypes.c_int),
        ("backing_planes", ctypes.c_ulong),
        ("backing_pixel", ctypes.c_ulong),
        ("save_under", ctypes.c_int),
        ("colormap", ctypes.c_ulong),
        ("map_installed", ctypes.c_int),
        ("map_state", ctypes.c_int),
        ("all_event_masks", ctypes.c_long),
        ("your_event_mask", ctypes.c_long),
        ("do_not_propagate_mask", ctypes.c_long),
        ("override_redirect", ctypes.c_int),
        ("screen", ctypes.c_void_p),
    ]


def is_video_window(title: str, wm_class: str, *, fullscreen: bool, audio_active: bool) -> bool:
    title_lower = title.casefold()
    classes = {part.strip().casefold() for part in wm_class.split(",")}
    if any(player in item for player in VIDEO_PLAYERS for item in classes):
        return True
    if any(marker in title_lower for marker in VIDEO_TITLE_MARKERS):
        return True
    return fullscreen and audio_active


def _quoted_property(output: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)} = (\".*\")$", output, re.MULTILINE)
    if match is None:
        return ""
    try:
        value = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return ""
    return value if isinstance(value, str) else ""


class X11VideoMonitor:
    """Find a video in the currently active X11 window."""

    def __init__(self, audio_monitor: AudioActivityMonitor | None = None) -> None:
        x11_path = ctypes.util.find_library("X11")
        self._xprop = shutil.which("xprop")
        if not x11_path or not self._xprop:
            raise RuntimeError("X11 window tools are unavailable")
        self._x11 = ctypes.CDLL(x11_path)
        self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._x11.XOpenDisplay.restype = ctypes.c_void_p
        self._x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self._x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self._x11.XGetWindowAttributes.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(_XWindowAttributes),
        ]
        self._x11.XGetWindowAttributes.restype = ctypes.c_int
        self._x11.XTranslateCoordinates.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong),
        ]
        self._x11.XTranslateCoordinates.restype = ctypes.c_int
        self._x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self._display = self._x11.XOpenDisplay(None)
        if not self._display:
            raise RuntimeError("Cannot open X11 display")
        self._root = self._x11.XDefaultRootWindow(self._display)
        self._audio = audio_monitor or AudioActivityMonitor()
        self._last_video_id: int | None = None

    @classmethod
    def create_if_available(cls) -> X11VideoMonitor | None:
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            return None
        try:
            return cls()
        except (OSError, RuntimeError):
            return None

    def _xprop_output(self, *arguments: str) -> str:
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

    def current(self) -> VideoWindow | None:
        root = self._xprop_output("-root", "_NET_ACTIVE_WINDOW", "_NET_CLIENT_LIST_STACKING")
        active_match = re.search(
            r"^_NET_ACTIVE_WINDOW.*window id # (0x[0-9a-fA-F]+)", root, re.MULTILINE
        )
        active_id = int(active_match.group(1), 16) if active_match is not None else 0
        active_output = self._window_properties(active_id) if active_id else ""
        if active_id:
            active = self._window(active_id, output=active_output)
            if active is not None:
                self._last_video_id = active.window_id
                return active
        active_is_morok = "Morok Assistant" in active_output or (
            '_NET_WM_NAME = "Морок"' in active_output
        )
        if active_is_morok and self._last_video_id is not None:
            remembered = self._window(self._last_video_id)
            if remembered is not None:
                return remembered

        stacking_match = re.search(
            r"^_NET_CLIENT_LIST_STACKING.*window id # (.+)$", root, re.MULTILINE
        )
        if stacking_match is None:
            return None
        window_ids = [
            int(value, 16) for value in re.findall(r"0x[0-9a-fA-F]+", stacking_match.group(1))
        ]
        for window_id in reversed(window_ids):
            if window_id == active_id:
                continue
            video = self._window(window_id, require_floating=True)
            if video is not None:
                self._last_video_id = video.window_id
                return video
        return None

    def _window_properties(self, window_id: int) -> str:
        return self._xprop_output(
            "-notype",
            "-f",
            "_NET_WM_NAME",
            "8u",
            "-id",
            hex(window_id),
            "_NET_WM_NAME",
            "WM_NAME",
            "WM_CLASS",
            "_NET_WM_STATE",
        )

    def _window(
        self,
        window_id: int,
        *,
        require_floating: bool = False,
        output: str | None = None,
    ) -> VideoWindow | None:
        output = output if output is not None else self._window_properties(window_id)
        title = _quoted_property(output, "_NET_WM_NAME") or _quoted_property(output, "WM_NAME")
        wm_class_match = re.search(r"^WM_CLASS = (.+)$", output, re.MULTILINE)
        wm_class = wm_class_match.group(1).replace('"', "") if wm_class_match else ""
        fullscreen = "_NET_WM_STATE_FULLSCREEN" in output
        if "_NET_WM_STATE_HIDDEN" in output:
            return None
        floating = "_NET_WM_STATE_ABOVE" in output
        picture_in_picture = any(
            marker in title.casefold() for marker in ("picture-in-picture", "картинка в картинке")
        )
        if require_floating and not (floating or picture_in_picture):
            return None
        geometry = self._geometry(window_id)
        if geometry is None or geometry[2] < 320 or geometry[3] < 180:
            return None
        recognized = is_video_window(title, wm_class, fullscreen=fullscreen, audio_active=False)
        if not recognized and fullscreen:
            recognized = is_video_window(
                title, wm_class, fullscreen=True, audio_active=self._audio.active()
            )
        if not recognized:
            return None
        return VideoWindow(window_id, title, wm_class, *geometry, fullscreen)

    def _geometry(self, window_id: int) -> tuple[int, int, int, int] | None:
        attributes = _XWindowAttributes()
        if not self._x11.XGetWindowAttributes(self._display, window_id, ctypes.byref(attributes)):
            return None
        x = ctypes.c_int()
        y = ctypes.c_int()
        child = ctypes.c_ulong()
        if not self._x11.XTranslateCoordinates(
            self._display,
            window_id,
            self._root,
            0,
            0,
            ctypes.byref(x),
            ctypes.byref(y),
            ctypes.byref(child),
        ):
            return None
        return x.value, y.value, attributes.width, attributes.height

    def close(self) -> None:
        if self._display:
            self._x11.XCloseDisplay(self._display)
            self._display = None
