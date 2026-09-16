from pathlib import Path

from morok_assistant.system.autostart import AutostartManager
from morok_assistant.system.behavior_settings import BehaviorSettings, BehaviorSettingsStore
from morok_assistant.system.video import X11VideoMonitor, is_video_window


def test_autostart_file_can_be_enabled_and_disabled(tmp_path: Path) -> None:
    path = tmp_path / "autostart" / "morok-assistant.desktop"
    manager = AutostartManager(path)

    manager.set_enabled(True)

    contents = path.read_text(encoding="utf-8")
    assert manager.enabled
    assert "Name=Морок" in contents
    assert "morok_assistant" in contents
    assert path.stat().st_mode & 0o111

    manager.set_enabled(False)
    assert not manager.enabled


def test_video_behavior_setting_persists(tmp_path: Path) -> None:
    store = BehaviorSettingsStore(tmp_path / "behavior.json")
    assert store.load().watch_videos

    store.save(BehaviorSettings(watch_videos=False))

    assert not store.load().watch_videos


def test_recognizes_players_sites_and_fullscreen_playback() -> None:
    assert is_video_window("film.mkv", "vlc, Vlc", fullscreen=False, audio_active=False)
    assert is_video_window(
        "Новый ролик - YouTube", "vivaldi-stable", fullscreen=False, audio_active=False
    )
    assert is_video_window("Movie", "browser", fullscreen=True, audio_active=True)
    assert not is_video_window("Почта", "browser", fullscreen=False, audio_active=True)


def test_finds_vivaldi_picture_in_picture_when_another_window_is_active() -> None:
    monitor = object.__new__(X11VideoMonitor)
    monitor._last_video_id = None
    root = """\
_NET_ACTIVE_WINDOW(WINDOW): window id # 0x10
_NET_CLIENT_LIST_STACKING(WINDOW): window id # 0x20, 0x10, 0x30
"""
    properties = {
        "0x10": """\
_NET_WM_NAME = "Редактор"
WM_CLASS = "code", "Code"
_NET_WM_STATE = _NET_WM_STATE_FOCUSED
""",
        "0x30": """\
_NET_WM_NAME = "Картинка в картинке"
WM_CLASS:  not found.
_NET_WM_STATE = _NET_WM_STATE_STICKY, _NET_WM_STATE_ABOVE
""",
        "0x20": """\
_NET_WM_NAME = "Видео - YouTube"
WM_CLASS = "vivaldi-stable", "Vivaldi-stable"
_NET_WM_STATE =
""",
    }

    def xprop(*arguments: str) -> str:
        return (
            root
            if "-root" in arguments
            else properties.get(arguments[arguments.index("-id") + 1], "")
        )

    monitor._xprop_output = xprop  # type: ignore[method-assign]
    monitor._geometry = lambda _window_id: (40, 50, 480, 270)  # type: ignore[method-assign]

    video = monitor.current()

    assert video is not None
    assert video.window_id == 0x30
    assert video.title == "Картинка в картинке"


def test_remembers_normal_video_while_morok_is_active() -> None:
    monitor = object.__new__(X11VideoMonitor)
    monitor._last_video_id = None
    active_id = ["0x20"]
    properties = {
        "0x20": """\
_NET_WM_NAME = "Ролик - YouTube - Vivaldi"
WM_CLASS = "vivaldi-stable", "Vivaldi-stable"
_NET_WM_STATE = _NET_WM_STATE_FOCUSED
""",
        "0x30": """\
_NET_WM_NAME = "Морок"
WM_CLASS = "__main__.py", "Morok Assistant"
_NET_WM_STATE = _NET_WM_STATE_ABOVE
""",
    }

    def xprop(*arguments: str) -> str:
        if "-root" in arguments:
            return (
                f"_NET_ACTIVE_WINDOW(WINDOW): window id # {active_id[0]}\n"
                "_NET_CLIENT_LIST_STACKING(WINDOW): window id # 0x20, 0x30\n"
            )
        return properties.get(arguments[arguments.index("-id") + 1], "")

    monitor._xprop_output = xprop  # type: ignore[method-assign]
    monitor._geometry = lambda _window_id: (100, 100, 800, 500)  # type: ignore[method-assign]

    assert monitor.current().window_id == 0x20
    active_id[0] = "0x30"
    assert monitor.current().window_id == 0x20
