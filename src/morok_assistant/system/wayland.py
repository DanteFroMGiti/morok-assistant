from __future__ import annotations

import os

WAYLAND_MODES = {"auto", "xwayland", "native"}


def is_wayland_session() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def is_plasma_wayland() -> bool:
    desktops = os.environ.get("XDG_CURRENT_DESKTOP", "").lower().split(":")
    return is_wayland_session() and any(
        desktop in {"kde", "plasma"} for desktop in desktops
    )


def configure_platform(mode: str) -> str:
    """Select XWayland before constructing QApplication; never override an explicit Qt choice."""
    if not is_wayland_session():
        return "x11"
    if "QT_QPA_PLATFORM" in os.environ:
        return os.environ["QT_QPA_PLATFORM"]
    if mode != "native" and os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        return "xcb"
    return "wayland"
