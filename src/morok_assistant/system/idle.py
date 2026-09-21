from __future__ import annotations

import ctypes
import ctypes.util
import os
import shutil
import subprocess
from time import monotonic


class _XScreenSaverInfo(ctypes.Structure):
    _fields_ = [
        ("window", ctypes.c_ulong),
        ("state", ctypes.c_int),
        ("kind", ctypes.c_int),
        ("til_or_since", ctypes.c_ulong),
        ("idle", ctypes.c_ulong),
        ("event_mask", ctypes.c_ulong),
    ]


class X11IdleMonitor:
    """Read X11's idle duration for mouse and keyboard activity across the desktop."""

    def __init__(self) -> None:
        x11_path = ctypes.util.find_library("X11")
        xss_path = ctypes.util.find_library("Xss")
        if not x11_path or not xss_path:
            raise RuntimeError("X11 screen saver libraries are unavailable")
        self._x11 = ctypes.CDLL(x11_path)
        self._xss = ctypes.CDLL(xss_path)
        self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._x11.XOpenDisplay.restype = ctypes.c_void_p
        self._x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self._x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self._x11.XFree.argtypes = [ctypes.c_void_p]
        self._x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self._xss.XScreenSaverQueryExtension.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        self._xss.XScreenSaverQueryExtension.restype = ctypes.c_int
        self._xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(_XScreenSaverInfo)
        self._xss.XScreenSaverQueryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(_XScreenSaverInfo),
        ]
        self._xss.XScreenSaverQueryInfo.restype = ctypes.c_int
        self._display = self._x11.XOpenDisplay(None)
        if not self._display:
            raise RuntimeError("Cannot open X11 display")
        event = ctypes.c_int()
        error = ctypes.c_int()
        if not self._xss.XScreenSaverQueryExtension(
            self._display, ctypes.byref(event), ctypes.byref(error)
        ):
            self._x11.XCloseDisplay(self._display)
            raise RuntimeError("X11 screen saver extension is unavailable")
        self._root = self._x11.XDefaultRootWindow(self._display)
        self._info = self._xss.XScreenSaverAllocInfo()
        if not self._info:
            self._x11.XCloseDisplay(self._display)
            raise RuntimeError("Cannot allocate X11 screen saver info")

    @classmethod
    def create_if_available(cls) -> X11IdleMonitor | None:
        # XWayland's idle time excludes input directed at native Wayland windows.
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            return None
        try:
            return cls()
        except (OSError, RuntimeError):
            return None

    def seconds(self) -> float | None:
        if not self._display:
            return None
        if not self._xss.XScreenSaverQueryInfo(self._display, self._root, self._info):
            return None
        return self._info.contents.idle / 1000.0

    def close(self) -> None:
        if self._display:
            self._x11.XFree(ctypes.cast(self._info, ctypes.c_void_p))
            self._x11.XCloseDisplay(self._display)
            self._display = None


def _has_active_stream(output: str) -> bool:
    for section in output.split("#"):
        if "Corked: no" in section and "Mute: no" in section:
            return True
    return False


class AudioActivityMonitor:
    """Treat unmuted PulseAudio/PipeWire playback or capture as activity."""

    def __init__(self) -> None:
        self._pactl = shutil.which("pactl")
        self._last_checked = 0.0
        self._cached = False

    def active(self) -> bool:
        if not self._pactl:
            return False
        now = monotonic()
        if now - self._last_checked < 5:
            return self._cached
        self._last_checked = now
        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        for stream_type in ("sink-inputs", "source-outputs"):
            try:
                result = subprocess.run(
                    [self._pactl, "list", stream_type],
                    capture_output=True,
                    text=True,
                    env=environment,
                    timeout=0.7,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode == 0 and _has_active_stream(result.stdout):
                self._cached = True
                return True
        self._cached = False
        return False
