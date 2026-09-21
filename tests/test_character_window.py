from types import SimpleNamespace

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtWidgets import QApplication

from morok_assistant.ai.settings import AISettingsStore
from morok_assistant.application.bootstrap import bundled_characters_path
from morok_assistant.characters.repository import CharacterRepository
from morok_assistant.core.events import EventBus
from morok_assistant.jokes.repository import JokeRepository
from morok_assistant.system.app_context import ActiveApplication
from morok_assistant.system.behavior_settings import BehaviorSettings, BehaviorSettingsStore
from morok_assistant.system.video import VideoWindow
from morok_assistant.ui.character_window import CharacterWindow


class FakeVideoMonitor:
    def __init__(self, video: VideoWindow | None) -> None:
        self.video = video
        self.closed = False

    def current(self) -> VideoWindow | None:
        return self.video

    def close(self) -> None:
        self.closed = True


class FakeAppMonitor:
    def __init__(self, kind: str) -> None:
        self.kind = kind

    def current(self) -> ActiveApplication:
        return ActiveApplication(7, self.kind, self.kind, self.kind)


def test_sits_after_inactivity_and_wakes_on_interaction(monkeypatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("morok_assistant.ui.character_window.monotonic", lambda: clock[0])
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus())
    window.timer.stop()

    clock[0] = 29.9
    window._on_tick()
    assert window.player.state == "idle"

    clock[0] = 30.1
    window._on_tick()
    assert window.player.state == "sit_down"

    window.player.tick(1000)
    assert window.player.state == "sitting"

    clock[0] = 30.2
    window._mark_interaction()
    assert window.player.state == "idle"

    clock[0] = 60.0
    window._on_tick()
    assert window.player.state == "idle"

    window.close()
    assert app is not None


def test_tells_joke_from_editable_file_with_bubble(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    joke_file = tmp_path / "jokes.txt"
    joke_file.write_text("A first joke\n", encoding="utf-8")
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus(), JokeRepository(joke_file))
    window.timer.stop()
    window.joke_timer.stop()
    window.show()

    window.tell_joke(manual=True)
    assert window.joke_bubble.label.text() == "A first joke"
    assert window.joke_bubble.isVisible()

    joke_file.write_text("An edited joke\n", encoding="utf-8")
    window.tell_joke(manual=True)
    assert window.joke_bubble.label.text() == "An edited joke"

    window.close()
    assert app is not None


def test_half_scale_and_cursor_glance(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus())
    window.timer.stop()

    window.set_scale(0.5)
    assert window.size().width() == 96
    assert window.size().height() == 104

    center = window.mapToGlobal(QPoint(window.width() // 2, window.height() // 3))
    cursor = [QPoint(center.x() + 250, center.y())]
    monkeypatch.setattr(
        "morok_assistant.ui.character_window.QCursor", SimpleNamespace(pos=lambda: cursor[0])
    )
    watch = manifest.animations["mouse_watch"]
    window._update_mouse_watch_direction(watch)
    assert window._mouse_watch_index >= 3
    assert not window._mouse_watch_mirrored

    cursor[0] = QPoint(center.x() - 250, center.y())
    window._update_mouse_watch_direction(watch)
    assert window._mouse_watch_mirrored

    window.player.play("sitting")
    seated_watch = manifest.animations["mouse_watch_sitting"]
    window._update_mouse_watch_direction(seated_watch)
    assert window._mouse_watch_index == 0
    assert window._mouse_watch_mirrored

    cursor[0] = QPoint(center.x() + 20, center.y() - 200)
    window._update_mouse_watch_direction(seated_watch)
    assert window._mouse_watch_index == 1

    window.close()
    assert app is not None


def test_mouse_watch_continues_until_click_or_two_minutes(monkeypatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("morok_assistant.ui.character_window.monotonic", lambda: clock[0])
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus())
    window.timer.stop()
    window.SLEEP_AFTER_SECONDS = 10_000
    window._next_mouse_watch = 20.0

    clock[0] = window._next_mouse_watch + 0.1
    window._on_tick()
    assert window._mouse_watch_until == clock[0] + 120
    assert not window.peek_controller.auto_peek_enabled

    clock[0] += 119
    window._on_tick()
    assert window._mouse_watch_until > clock[0]

    window._mark_interaction()
    assert window._mouse_watch_until == 0
    assert window.peek_controller.auto_peek_enabled

    window._next_mouse_watch = clock[0] + 20
    clock[0] = window._next_mouse_watch + 0.1
    window._on_tick()
    assert window._mouse_watch_until > clock[0]
    end = window._mouse_watch_until
    clock[0] = end + 0.1
    window._on_tick()
    assert window._mouse_watch_until == 0
    assert not window._mouse_watch_available
    assert window.peek_controller.auto_peek_enabled

    clock[0] += 40
    window._on_tick()
    assert window._mouse_watch_until == 0

    window.close()
    assert app is not None


def test_sleep_stays_visible_until_morok_is_touched(monkeypatch, tmp_path) -> None:
    clock = [0.0]
    monkeypatch.setattr("morok_assistant.ui.character_window.monotonic", lambda: clock[0])
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    behavior = BehaviorSettingsStore(tmp_path / "behavior.json")
    behavior.save(BehaviorSettings(personality_mode="quiet"))
    window = CharacterWindow(manifest, EventBus(), behavior_store=behavior)
    window.timer.stop()

    clock[0] = 180.1
    window._on_tick()
    assert window.player.state == "curl_up"
    assert not window.peek_controller.auto_peek_enabled

    window.player.tick(1200)
    assert window.player.state == "sleeping"
    clock[0] = 300
    window._on_tick()
    assert window.player.state == "sleeping"

    window._mark_interaction()
    assert window.player.state == "idle"
    assert not window.peek_controller.auto_peek_enabled

    window.close()
    assert app is not None


def test_sleep_after_peeking_starts_when_morok_returns(monkeypatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("morok_assistant.ui.character_window.monotonic", lambda: clock[0])
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus())
    window.timer.stop()
    window.peek_controller.mode = "hidden"

    clock[0] = 180.1
    window._on_tick()
    assert window.peek_controller.mode == "returning"
    assert window.player.state == "idle"

    clock[0] = 180.2
    window._on_tick()
    assert window.player.state == "idle"

    window.peek_controller.character_animation.stop()
    window.peek_controller._on_character_animation_finished()
    assert window.peek_controller.mode == "visible"
    assert window.player.state == "curl_up"

    window.close()
    assert app is not None


def test_drag_frame_holds_raised_paw_at_pointer() -> None:
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus())
    window.timer.stop()
    window.move(200, 200)
    accepted: list[bool] = []
    press = SimpleNamespace(
        button=lambda: Qt.MouseButton.LeftButton,
        globalPosition=lambda: QPointF(290, 300),
        accept=lambda: accepted.append(True),
    )
    window.mousePressEvent(press)
    assert window.player.state == "idle"

    move = SimpleNamespace(
        buttons=lambda: Qt.MouseButton.LeftButton,
        globalPosition=lambda: QPointF(310, 320),
        accept=lambda: accepted.append(True),
    )
    window.mouseMoveEvent(move)
    assert window.player.state == "drag_hold"
    paw_anchor = QPoint(round(192 * 0.17), round(208 * 0.20))
    assert window.pos() == QPoint(310, 320) - paw_anchor

    release = SimpleNamespace(
        button=lambda: Qt.MouseButton.LeftButton,
        accept=lambda: accepted.append(True),
    )
    window.mouseReleaseEvent(release)
    assert window.player.state == "idle"
    assert window._drag_offset is None
    assert len(accepted) == 3

    window.close()
    assert app is not None


def test_moves_to_video_edge_sits_and_returns_when_video_disappears(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    area = app.primaryScreen().availableGeometry()
    video = VideoWindow(
        42,
        "Ролик - YouTube",
        "vivaldi",
        area.center().x() - 180,
        area.center().y() - 100,
        360,
        240,
    )
    monitor = FakeVideoMonitor(video)
    window = CharacterWindow(
        manifest,
        EventBus(),
        behavior_store=BehaviorSettingsStore(tmp_path / "behavior.json"),
        video_monitor=monitor,  # type: ignore[arg-type]
    )
    window.timer.stop()
    window.video_timer.stop()
    window.move(area.topLeft())
    assert window._video_side_position(video, prefer_nearest=True) is None
    window.move(
        video.x + video.width + 20,
        video.y + video.height - window.height() + 5,
    )
    window._manual_video_placement = True

    window._check_video_window()
    assert window._video_window_id == 42
    assert window._video_side == "right"
    assert window._video_mirrored
    assert window._video_target is not None
    assert window._video_target.x() == video.x + video.width + 12
    assert not QRect(window._video_target, window.size()).intersects(
        QRect(video.x, video.y, video.width, video.height)
    )

    window.video_move.stop()
    window.move(window._video_target)
    window._on_video_move_finished()
    assert window.player.state == "video_watching"

    video_near_right = VideoWindow(
        43,
        "Другой ролик - YouTube",
        "vivaldi",
        area.right() - 400,
        area.top() + 100,
        400,
        260,
    )
    left_placement = window._video_side_position(video_near_right, preferred_side="left")
    assert left_placement is not None
    assert left_placement[1] == "left"
    assert left_placement[0].x() + window.width() < video_near_right.x

    window._leave_video_window(restore=False, suppress=True)
    top_placement = window._video_side_position(video, preferred_side="top")
    assert top_placement is not None
    assert not QRect(top_placement[0], window.size()).intersects(
        QRect(video.x, video.y, video.width, video.height)
    )
    bottom_placement = window._video_side_position(video, preferred_side="bottom")
    assert bottom_placement is not None
    assert not QRect(bottom_placement[0], window.size()).intersects(
        QRect(video.x, video.y, video.width, video.height)
    )
    window.move(top_placement[0] + QPoint(3, -2))
    window._resume_video_after_drag()
    assert window._video_side == "top"
    assert not window._video_mirrored
    window.video_move.stop()
    window.move(window._video_target)
    window._on_video_move_finished()
    assert window.player.state == "video_watching_down"
    window._video_side = "bottom"
    window._start_video_watching()
    assert window.player.state == "video_watching_up"
    window._video_side = "top"

    old_target = window._video_target
    monitor.video = VideoWindow(
        video.window_id,
        video.title,
        video.wm_class,
        video.x + 60,
        video.y + 20,
        video.width,
        video.height,
    )
    window._check_video_window()
    assert window._video_side == "top"
    assert window._video_target != old_target
    assert window.video_move.endValue() == window._video_target

    monitor.video = None
    window._check_video_window()
    assert window._video_window_id is None
    assert window._video_returning or window.player.state == "idle"

    window.close()
    assert monitor.closed
    assert app is not None


def test_reacts_to_music_games_and_code_errors(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    applications = FakeAppMonitor("music")
    window = CharacterWindow(
        manifest,
        EventBus(),
        ai_settings_store=AISettingsStore(tmp_path / "ai.json"),
        video_monitor=FakeVideoMonitor(None),  # type: ignore[arg-type]
        app_monitor=applications,  # type: ignore[arg-type]
    )
    window.timer.stop()
    window.video_timer.stop()
    window.context_timer.stop()

    window._check_app_context()
    assert window.player.state == "music_listening"

    applications.kind = "game"
    window._check_app_context()
    assert window._game_quiet
    assert not window.peek_controller.auto_peek_enabled

    applications.kind = "code"
    QApplication.clipboard().setText("Traceback: ValueError: broken")
    window._check_app_context()
    assert not window._game_quiet
    assert "ошибку" in window.joke_bubble.label.text()

    window.focus_controller.start(1, 1)
    window.focus_controller.timer.stop()
    assert window.player.state == "sitting"
    assert not window.peek_controller.auto_peek_enabled
    window.focus_controller.stop()

    window._on_reminder_due("Проверить чай")
    assert "Проверить чай" in window.joke_bubble.label.text()
    assert window.scale == 2.0
    assert window.player.state == "wave"
    assert window.reminder_escalation_timer.isActive()

    window.close()
    assert app is not None


def test_unanswered_reminder_chases_cursor_until_acknowledged(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(
        manifest,
        EventBus(),
        ai_settings_store=AISettingsStore(tmp_path / "ai.json"),
        video_monitor=FakeVideoMonitor(None),  # type: ignore[arg-type]
        app_monitor=None,
    )
    window.timer.stop()
    window.video_timer.stop()
    window.context_timer.stop()
    window.move(100, 100)

    original_scale = window.scale
    window._on_reminder_due("Проверить чай")
    assert window._reminder_active
    assert not window._reminder_chasing
    assert window.scale == 2.0

    cursor = QPoint(window.frameGeometry().center().x() + 500, window.frameGeometry().center().y())
    monkeypatch.setattr(
        "morok_assistant.ui.character_window.QCursor", SimpleNamespace(pos=lambda: cursor)
    )
    old_position = window.pos()
    window._start_reminder_chase()
    window._tick_reminder_chase(0.1)
    assert window._reminder_chasing
    assert window.player.state == "run_right"
    assert window.x() > old_position.x()

    locked_cursor = window.frameGeometry().center()
    cursor.setX(locked_cursor.x())
    cursor.setY(locked_cursor.y())
    positions: list[QPoint] = []
    monkeypatch.setattr(
        "morok_assistant.ui.character_window.QCursor",
        SimpleNamespace(pos=lambda: cursor, setPos=lambda point: positions.append(QPoint(point))),
    )
    monkeypatch.setattr(window, "grabKeyboard", lambda: None)
    monkeypatch.setattr(window, "releaseKeyboard", lambda: None)
    window._tick_reminder_chase(0.1)
    assert window._reminder_cursor_locked
    assert positions[-1] == cursor
    window._tick_reminder_chase(0.1)
    assert positions[-1] == cursor

    enter = SimpleNamespace(
        key=lambda: Qt.Key.Key_Return,
        accept=lambda: None,
    )
    window.keyPressEvent(enter)
    assert not window._reminder_active
    assert not window._reminder_chasing
    assert not window._reminder_cursor_locked
    assert window.scale == original_scale
    assert window.player.state == "idle"
    assert not window.joke_bubble.isVisible()

    window.close()
    assert app is not None


def test_wayland_reminder_waits_for_click_without_warping_pointer(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(
        manifest, EventBus(), ai_settings_store=AISettingsStore(tmp_path / "ai.json"),
        video_monitor=FakeVideoMonitor(None),  # type: ignore[arg-type]
    )
    window.timer.stop()
    window._on_reminder_due("Чай")
    window._reminder_chasing = True

    def forbid_warp(_point):
        raise AssertionError("Wayland cannot warp the pointer")

    monkeypatch.setattr(
        "morok_assistant.ui.character_window.QCursor",
        SimpleNamespace(setPos=forbid_warp),
    )

    window._lock_reminder_cursor(QPoint(100, 100))

    assert not window._reminder_chasing
    assert not window._reminder_cursor_locked
    assert "Нажмите на меня" in window.joke_bubble.label.text()
    window.close()
    assert app is not None
