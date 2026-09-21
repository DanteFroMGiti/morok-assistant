from __future__ import annotations

import logging
import os
from dataclasses import replace
from math import hypot
from random import Random
from time import monotonic
from typing import Protocol

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QCursor,
    QKeyEvent,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from morok_assistant.ai.settings import AISettingsStore
from morok_assistant.animation.player import AnimationPlayer
from morok_assistant.core.events import Event, EventBus
from morok_assistant.core.models import AnimationSpec, CharacterManifest
from morok_assistant.jokes.repository import JokePicker, JokeRepository
from morok_assistant.productivity.curiosity import CuriosityStore
from morok_assistant.productivity.focus import FocusController
from morok_assistant.productivity.reminders import ReminderManager, ReminderStore
from morok_assistant.productivity.tasks import TaskManager, TaskStore
from morok_assistant.system.app_context import ActiveApplication, X11ActiveApplicationMonitor
from morok_assistant.system.appearance import Appearance, AppearanceStore
from morok_assistant.system.autostart import AutostartManager
from morok_assistant.system.behavior_settings import BehaviorSettingsStore
from morok_assistant.system.video import VideoWindow, X11VideoMonitor
from morok_assistant.system.wayland import is_wayland_session
from morok_assistant.ui.ai_chat import AIChatDialog
from morok_assistant.ui.ai_settings import AISettingsDialog
from morok_assistant.ui.curiosity import CuriosityDialog
from morok_assistant.ui.focus import FocusDialog
from morok_assistant.ui.gesture_settings import GestureSettingsStore
from morok_assistant.ui.idle_peek import IdlePeekController
from morok_assistant.ui.joke_bubble import JokeBubble
from morok_assistant.ui.quick_actions import QuickActionsDialog
from morok_assistant.ui.reminders import RemindersDialog
from morok_assistant.ui.tasks import TasksDialog


class VideoMonitor(Protocol):
    def current(self) -> VideoWindow | None: ...

    def close(self) -> None: ...


class ApplicationMonitor(Protocol):
    def current(self) -> ActiveApplication | None: ...


LOG = logging.getLogger(__name__)


class CharacterWindow(QWidget):
    SIT_AFTER_SECONDS = 30.0
    SLEEP_AFTER_SECONDS = 3 * 60.0
    WATCH_SECONDS = 2 * 60.0
    DOCUMENT_BREAK_SECONDS = 45 * 60.0
    REMINDER_CHASE_DELAY_MS = 8_000
    REMINDER_CHASE_SPEED = 360.0

    def __init__(
        self,
        manifest: CharacterManifest,
        events: EventBus,
        jokes: JokeRepository | None = None,
        ai_settings_store: AISettingsStore | None = None,
        behavior_store: BehaviorSettingsStore | None = None,
        appearance_store: AppearanceStore | None = None,
        video_monitor: VideoMonitor | None = None,
        app_monitor: ApplicationMonitor | None = None,
    ) -> None:
        super().__init__()
        self.events = events
        self.manifest = manifest
        self.player = AnimationPlayer(manifest)
        self.atlas = QPixmap()
        self.scale = 1.0
        self.random = Random()
        self.jokes = jokes
        self.joke_picker = JokePicker(self.random)
        self.ai_settings_store = ai_settings_store or AISettingsStore()
        self.gesture_store = GestureSettingsStore(
            self.ai_settings_store.path.with_name("gestures.json")
        )
        self.gesture_settings = self.gesture_store.load()
        self.behavior_store = behavior_store or BehaviorSettingsStore(
            self.ai_settings_store.path.with_name("behavior.json")
        )
        self.behavior_settings = self.behavior_store.load()
        self.appearance_store = appearance_store
        self.video_monitor = video_monitor or X11VideoMonitor.create_if_available()
        self.app_monitor = app_monitor or X11ActiveApplicationMonitor.create_if_available()
        self.ai_chat_dialog: AIChatDialog | None = None
        self.reminders_dialog: RemindersDialog | None = None
        self.focus_dialog: FocusDialog | None = None
        self.quick_actions_dialog: QuickActionsDialog | None = None
        self.tasks_dialog: TasksDialog | None = None
        self.curiosity_dialog: CuriosityDialog | None = None
        self.task_manager = TaskManager(
            TaskStore(self.ai_settings_store.path.with_name("tasks.json")), self
        )
        self.curiosity_store = CuriosityStore(
            self.ai_settings_store.path.with_name("memory.json")
        )
        self._pending_question: str | None = None
        self._bubble_action: str | None = None
        self.reminder_manager = ReminderManager(
            ReminderStore(self.ai_settings_store.path.with_name("reminders.json")), self
        )
        self.focus_controller = FocusController(self)
        self._focus_was_quiet = False
        self._app_kind = "other"
        self._app_context_since = monotonic()
        self._next_context_reaction = self._app_context_since
        self._last_clipboard_error = ""
        self._game_quiet = False
        self._next_hover_gesture = 0.0
        self._drag_offset: QPoint | None = None
        self._drag_pressed_at: QPoint | None = None
        self._dragging = False
        self._reminder_active = False
        self._reminder_chasing = False
        self._reminder_cursor_locked = False
        self._reminder_cursor_anchor: QPoint | None = None
        self._reminder_text = ""
        self._reminder_previous_scale = self.scale
        self._last_tick = monotonic()
        self._last_interaction = self._last_tick
        self._next_mouse_watch = self._last_tick + self.random.uniform(15, 35)
        self._mouse_watch_available = True
        self._mouse_watch_until = 0.0
        self._mouse_watch_index = 0
        self._mouse_watch_mirrored = False
        self._sleep_pending = False
        self._video_window_id: int | None = None
        self._video_suppressed_id: int | None = None
        self._video_origin: QPoint | None = None
        self._video_target: QPoint | None = None
        self._video_side: str | None = None
        self._video_mirrored = False
        self._manual_video_placement = False
        self._video_arriving = False
        self._video_returning = False
        self._quiet_placed = False
        self._personality_arriving = False
        self._next_roam = monotonic() + self.random.uniform(40, 70)
        self._next_curiosity = monotonic() + 90
        self._next_task_suggestion = monotonic() + 12 * 60
        self._next_rare_reaction = monotonic() + self._reaction_delay()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_character(manifest)

        self.joke_bubble = JokeBubble(self)
        self.joke_bubble.dismissed.connect(self._on_bubble_dismissed)
        self.joke_hide_timer = QTimer(self)
        self.joke_hide_timer.setSingleShot(True)
        self.joke_hide_timer.timeout.connect(self._dismiss_joke)
        self.joke_timer = QTimer(self)
        self.joke_timer.setSingleShot(True)
        self.joke_timer.timeout.connect(self._on_joke_timer)
        if jokes is not None:
            self._schedule_next_joke()

        self.reminder_escalation_timer = QTimer(self)
        self.reminder_escalation_timer.setSingleShot(True)
        self.reminder_escalation_timer.timeout.connect(self._start_reminder_chase)

        self.peek_controller = IdlePeekController(self, manifest, self.atlas, self.random)
        self.peek_controller.left_screen.connect(self._on_leave_screen)
        self.peek_controller.returned.connect(self._on_return_to_screen)
        self.peek_controller.arrived.connect(self._on_peek_arrived)
        self.peek_controller.peek_window.activated.connect(self._mark_interaction)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start()

        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self._on_hover_gesture)

        self.video_move = QPropertyAnimation(self, b"pos", self)
        self.video_move.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.video_move.finished.connect(self._on_video_move_finished)
        self.personality_move = QPropertyAnimation(self, b"pos", self)
        self.personality_move.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.personality_move.finished.connect(self._on_personality_move_finished)
        self.personality_timer = QTimer(self)
        self.personality_timer.setInterval(5_000)
        self.personality_timer.timeout.connect(self._personality_tick)
        self.personality_timer.start()
        QTimer.singleShot(500, self._apply_personality_mode)
        self.video_timer = QTimer(self)
        self.video_timer.setInterval(750)
        self.video_timer.timeout.connect(self._check_video_window)
        if self.behavior_settings.watch_videos and self.video_monitor is not None:
            self.video_timer.start()
            QTimer.singleShot(1_500, self._check_video_window)

        self.context_timer = QTimer(self)
        self.context_timer.setInterval(2_000)
        self.context_timer.timeout.connect(self._check_app_context)
        if self.app_monitor is not None:
            self.context_timer.start()

        self.reminder_manager.due.connect(self._on_reminder_due)
        self.focus_controller.notice.connect(self._on_focus_notice)
        self.focus_controller.changed.connect(self._on_focus_changed)

    def _auto_peek_allowed(self) -> bool:
        chatting = self.ai_chat_dialog is not None and self.ai_chat_dialog.isVisible()
        return not (
            self.behavior_settings.personality_mode == "quiet"
            or chatting or self._game_quiet or self._sleep_pending
            or self._mouse_watch_until
            or self.focus_controller.phase in {"focus", "paused"}
            or self._video_window_id is not None
        )

    def _reaction_delay(self) -> float:
        intervals = {"off": (0, 0), "rare": (12, 20), "normal": (5, 9), "often": (2, 4)}
        start, end = intervals[self.behavior_settings.reaction_frequency]
        return self.random.uniform(start, end) * 60 if start else float("inf")

    def _can_act_spontaneously(self) -> bool:
        return not (
            self._reminder_active or self._sleep_pending or self._drag_offset is not None
            or self._mouse_watch_until or self.joke_bubble.isVisible()
            or self._video_window_id is not None or self.peek_controller.active
            or self._game_quiet or self.focus_controller.phase in {"focus", "paused"}
            or (self.ai_chat_dialog is not None and self.ai_chat_dialog.isVisible())
            or (self.tasks_dialog is not None and self.tasks_dialog.isVisible())
            or (self.curiosity_dialog is not None and self.curiosity_dialog.isVisible())
            or self.personality_move.state() == QPropertyAnimation.State.Running
        )

    def _screen_positions(self) -> list[QPoint]:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return []
        area = screen.availableGeometry()
        margin = 20
        left = area.left() + margin
        right = max(left, area.right() - self.width() - margin)
        top = area.top() + margin
        bottom = max(top, area.bottom() - self.height() - margin)
        return [QPoint(x, y) for x, y in (
            (left, top), (right, top), (left, bottom), (right, bottom),
            ((left + right) // 2, bottom),
        )]

    def _move_for_personality(self, target: QPoint) -> None:
        if is_wayland_session() and os.environ.get("QT_QPA_PLATFORM") != "xcb":
            if self.behavior_settings.personality_mode == "quiet":
                self._play_state("sitting" if "sitting" in self.manifest.animations else "idle")
            return
        if (target - self.pos()).manhattanLength() < 20:
            self._personality_arriving = True
            self._on_personality_move_finished()
            return
        self.personality_move.stop()
        self._personality_arriving = True
        self._play_state("run_right" if target.x() >= self.x() else "run_left")
        distance = (target - self.pos()).manhattanLength()
        self.personality_move.setDuration(max(900, min(4_000, distance * 5)))
        self.personality_move.setStartValue(self.pos())
        self.personality_move.setEndValue(target)
        self.personality_move.start()

    def _on_personality_move_finished(self) -> None:
        if not self._personality_arriving:
            return
        self._personality_arriving = False
        if self.behavior_settings.personality_mode == "quiet":
            self._play_state("sitting" if "sitting" in self.manifest.animations else "idle")
        else:
            self._play_state("idle")

    def _apply_personality_mode(self) -> None:
        mode = self.behavior_settings.personality_mode
        self.personality_move.stop()
        self._personality_arriving = False
        self.peek_controller.auto_peek_enabled = self._auto_peek_allowed()
        if mode != "quiet":
            self._quiet_placed = False
            self._next_roam = monotonic() + self.random.uniform(25, 55)
            if self.player.state == "sitting":
                self._play_state("idle")
            return
        self._dismiss_joke()
        self._mouse_watch_until = 0.0
        if self._video_window_id is not None:
            self._leave_video_window(restore=False, suppress=True)
        if self.peek_controller.active:
            self.peek_controller.restore()
        if not self._can_act_spontaneously():
            return
        positions = self._screen_positions()
        if positions and not self._quiet_placed:
            cursor = QCursor.pos()
            # The farthest corner from the pointer is a stable, unobtrusive spot.
            target = max(positions[:4], key=lambda point: (point - cursor).manhattanLength())
            self._quiet_placed = True
            self._move_for_personality(target)
        elif "sitting" in self.manifest.animations:
            self._play_state("sitting")

    def set_personality_mode(self, mode: str) -> None:
        if mode not in {"quiet", "active", "curious"}:
            return
        try:
            self.behavior_store.save(replace(self.behavior_settings, personality_mode=mode))
        except OSError as error:
            LOG.warning("Could not save Morok's behavior: %s", error)
            return
        self.behavior_settings = self.behavior_store.load()
        self._apply_personality_mode()

    def _personality_tick(self) -> None:
        now = monotonic()
        if self.behavior_settings.personality_mode == "quiet":
            if not self._quiet_placed and self._can_act_spontaneously():
                self._apply_personality_mode()
            return
        if not self._can_act_spontaneously():
            return
        if self.behavior_settings.personality_mode == "active" and now >= self._next_roam:
            self._next_roam = now + self.random.uniform(45, 90)
            positions = [point for point in self._screen_positions()
                         if (point - self.pos()).manhattanLength() > self.width()]
            if positions:
                self._move_for_personality(self.random.choice(positions))
        if self.behavior_settings.personality_mode == "curious" and now >= self._next_curiosity:
            if self.joke_bubble.isVisible():
                self._next_curiosity = now + 30
            else:
                self._next_curiosity = now + self.random.uniform(20 * 60, 40 * 60)
            if self._pending_question is None and not self.joke_bubble.isVisible():
                question = self.curiosity_store.next_question()
                if question:
                    self._pending_question = question
                    self._show_joke(f"Можно спросить? {question}\nНажми на меня, чтобы ответить.")
                    self._bubble_action = "curiosity"
                else:
                    memory = self.curiosity_store.recollection()
                    if memory:
                        self._show_joke(f"Помню, ты говорил: {memory.answer[:180]}")
                        try:
                            self.curiosity_store.mark_reminded(memory.question)
                        except OSError as error:
                            LOG.warning("Could not update memory: %s", error)
        if now >= self._next_task_suggestion:
            self._next_task_suggestion = now + self.random.uniform(35 * 60, 55 * 60)
            if not self.joke_bubble.isVisible() and self._pending_question is None:
                suggestion = self.task_manager.recommend()
                if suggestion:
                    self._show_joke(
                        f"Сейчас стоит заняться: {suggestion.task.title}. "
                        f"{suggestion.reason}. Нажми на сообщение, чтобы открыть задачи."
                    )
                    self._bubble_action = "tasks"
        if now >= self._next_rare_reaction:
            self._next_rare_reaction = now + self._reaction_delay()
            if self.player.state in {"idle", "sitting"} and not self.joke_bubble.isVisible():
                state = self.random.choice(["little_wave", "curious_glance", "thinking"])
                if state in self.manifest.animations:
                    self._play_state(state)
                    QTimer.singleShot(3_000, lambda: self._finish_rare_reaction(state))

    def _finish_rare_reaction(self, state: str) -> None:
        if self.player.state == state and self._can_act_spontaneously():
            self._play_state("idle")

    def _resize_to_character(self) -> None:
        self.resize(
            round(self.manifest.frame_width * self.scale),
            round(self.manifest.frame_height * self.scale),
        )

    def play(self, state: str) -> None:
        self._mark_interaction(wake=False)
        if state in {"curl_up", "sleeping"}:
            self._sleep_pending = True
            self.peek_controller.auto_peek_enabled = False
        self._play_state(state)

    def _play_state(self, state: str) -> None:
        self.player.play(state)
        self.events.publish(Event("character.animation.changed", state))
        self.update()

    def _mark_interaction(self, *, wake: bool = True) -> None:
        now = monotonic()
        if self._video_window_id is not None:
            self._leave_video_window(restore=False, suppress=True)
        self._last_interaction = now
        self._next_mouse_watch = now + self.random.uniform(15, 35)
        self._mouse_watch_available = True
        self._sleep_pending = False
        if self._mouse_watch_until:
            self._mouse_watch_until = 0.0
            self.update()
        if hasattr(self, "peek_controller"):
            self.peek_controller.auto_peek_enabled = self._auto_peek_allowed()
            self.peek_controller.restore()
        if wake and self.player.state in {"sit_down", "sitting", "curl_up", "sleeping"}:
            self._play_state("idle")

    def set_character(self, manifest: CharacterManifest) -> None:
        """Hot-swap a character package without recreating the desktop window."""
        atlas = QPixmap(str(manifest.sprite_path))
        if atlas.isNull():
            raise RuntimeError(f"Cannot load sprite atlas: {manifest.sprite_path}")
        self.manifest = manifest
        self.player = AnimationPlayer(manifest)
        self._last_interaction = monotonic()
        self._next_mouse_watch = self._last_interaction + self.random.uniform(15, 35)
        self._mouse_watch_available = True
        self._mouse_watch_until = 0.0
        self._sleep_pending = False
        self.atlas = atlas
        if hasattr(self, "peek_controller"):
            self.peek_controller.auto_peek_enabled = self._auto_peek_allowed()
            self.peek_controller.update_character(manifest, atlas)
        self.scale = manifest.default_scale
        self.setWindowTitle(manifest.name)
        self._resize_to_character()
        self.events.publish(Event("character.changed", manifest.character_id))
        self.update()

    def _on_tick(self) -> None:
        now = monotonic()
        delta_ms = min((now - self._last_tick) * 1000.0, 250.0)
        self._last_tick = now
        if self.player.tick(delta_ms):
            self.update()
        if self._reminder_active:
            if self._reminder_chasing:
                self._tick_reminder_chase(delta_ms / 1000.0)
            return
        if (
            self.focus_controller.phase in {"focus", "paused"}
            or self._game_quiet
            or (self._app_kind == "music" and self.behavior_settings.react_to_music)
        ):
            return
        if self.behavior_settings.personality_mode == "quiet":
            if (
                not self._sleep_pending and self._drag_offset is None
                and {"curl_up", "sleeping"}.issubset(self.manifest.animations)
                and now - self._last_interaction >= self.SLEEP_AFTER_SECONDS
            ):
                self._begin_sleep()
            elif (
                self.player.state == "idle" and not self._sleep_pending
                and now - self._last_interaction >= self.SIT_AFTER_SECONDS
                and "sit_down" in self.manifest.animations
            ):
                self._play_state("sit_down")
            return
        if (
            self.peek_controller.active and not self._sleep_pending
            and now - self._last_interaction >= self.SLEEP_AFTER_SECONDS
        ):
            self._begin_sleep()
            return
        if (
            self.player.state == "idle"
            and self._video_window_id is None
            and not self._sleep_pending
            and not self.peek_controller.active
            and {"sit_down", "sitting"}.issubset(self.manifest.animations)
            and now - self._last_interaction >= self.SIT_AFTER_SECONDS
        ):
            self._play_state("sit_down")
        if not self.peek_controller.active and self._video_window_id is None:
            self._tick_mouse_watch(now)

    def _check_video_window(self) -> None:
        if (
            self._reminder_active
            or self.behavior_settings.personality_mode == "quiet"
            or not self.behavior_settings.watch_videos
            or self.video_monitor is None
            or self.focus_controller.phase in {"focus", "paused"}
            or self._game_quiet
        ):
            return
        video = self.video_monitor.current()
        if video is None:
            self._video_suppressed_id = None
            if self._video_window_id is not None:
                self._leave_video_window(restore=True)
            return
        if video.window_id == self._video_suppressed_id:
            return
        chatting = self.ai_chat_dialog is not None and self.ai_chat_dialog.isVisible()
        if chatting or self._drag_offset is not None or self.peek_controller.active:
            return
        preferred_side = self._video_side if self._video_window_id == video.window_id else None
        manual_placement = self._manual_video_placement
        placement = self._video_side_position(
            video,
            preferred_side=preferred_side,
            prefer_nearest=manual_placement,
        )
        self._manual_video_placement = False
        if placement is None:
            if manual_placement:
                self._video_suppressed_id = video.window_id
            if self._video_window_id is not None:
                self._leave_video_window(restore=True)
            return
        target, side = placement
        mirrored = side == "right"
        if self._video_window_id == video.window_id:
            if (side, mirrored) != (self._video_side, self._video_mirrored):
                self._video_side = side
                self._video_mirrored = mirrored
                self.update()
            if self._video_target is None or (target - self._video_target).manhattanLength() > 12:
                self._video_target = target
                self._video_arriving = True
                self._animate_video_move(target)
            return
        if self._video_window_id is not None:
            self._leave_video_window(restore=False)
        self._video_window_id = video.window_id
        self.personality_move.stop()
        self._personality_arriving = False
        self._video_origin = self.pos()
        self._video_target = target
        self._video_side = side
        self._video_mirrored = mirrored
        self._video_arriving = True
        self._video_returning = False
        self._sleep_pending = False
        self._mouse_watch_until = 0.0
        self._dismiss_joke()
        self.peek_controller.auto_peek_enabled = False
        self._animate_video_move(target)
        self.events.publish(Event("character.video.started", video.title))

    def _video_side_position(
        self,
        video: VideoWindow,
        *,
        preferred_side: str | None = None,
        prefer_nearest: bool = False,
    ) -> tuple[QPoint, str] | None:
        gap = 12
        screen = QApplication.screenAt(
            QPoint(video.x + video.width // 2, video.y + video.height // 2)
        )
        if screen is None:
            screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return None
        area = screen.availableGeometry()
        side_y = max(
            area.top(),
            min(video.y + video.height - self.height(), area.bottom() - self.height() + 1),
        )
        vertical_x = max(
            area.left(),
            min(
                video.x + (video.width - self.width()) // 2,
                area.right() - self.width() + 1,
            ),
        )
        candidates: list[tuple[QPoint, str]] = []
        left_x = video.x - self.width() - gap
        if left_x >= area.left():
            candidates.append((QPoint(left_x, side_y), "left"))
        right_x = video.x + video.width + gap
        if right_x + self.width() - 1 <= area.right():
            candidates.append((QPoint(right_x, side_y), "right"))
        top_y = video.y - self.height() - gap
        if top_y >= area.top():
            candidates.append((QPoint(vertical_x, top_y), "top"))
        bottom_y = video.y + video.height + gap
        if bottom_y + self.height() - 1 <= area.bottom():
            candidates.append((QPoint(vertical_x, bottom_y), "bottom"))
        if not candidates:
            return None
        if preferred_side is not None:
            preferred = next(
                (candidate for candidate in candidates if candidate[1] == preferred_side), None
            )
            if preferred is not None:
                return preferred
        if prefer_nearest:
            nearest = min(
                candidates, key=lambda candidate: (candidate[0] - self.pos()).manhattanLength()
            )
            if (nearest[0] - self.pos()).manhattanLength() > max(self.width(), self.height()):
                return None
            return nearest
        return self.random.choice(candidates)

    def _animate_video_move(self, target: QPoint) -> None:
        self.video_move.stop()
        distance = (target - self.pos()).manhattanLength()
        if distance < 8:
            self.move(target)
            self._on_video_move_finished()
            return
        self._play_state("run_right" if target.x() >= self.x() else "run_left")
        self.video_move.setDuration(max(450, min(1_800, distance * 2)))
        self.video_move.setStartValue(self.pos())
        self.video_move.setEndValue(target)
        self.video_move.start()

    def _on_video_move_finished(self) -> None:
        if self._video_arriving and self._video_window_id is not None:
            self._video_arriving = False
            self._start_video_watching()
        elif self._video_returning:
            self._video_returning = False
            self._play_state("idle")

    def _start_video_watching(self) -> None:
        if self._video_window_id is not None and not self._video_arriving:
            state = {
                "top": "video_watching_down",
                "bottom": "video_watching_up",
            }.get(self._video_side, "video_watching")
            if state not in self.manifest.animations:
                state = "sitting"
            self._play_state(state)

    def _resume_video_after_drag(self) -> None:
        self._video_suppressed_id = None
        self._manual_video_placement = True
        self._check_video_window()

    def _leave_video_window(self, *, restore: bool, suppress: bool = False) -> None:
        old_id = self._video_window_id
        origin = self._video_origin
        self.video_move.stop()
        self._video_window_id = None
        self._video_arriving = False
        self._video_target = None
        self._video_side = None
        self._video_mirrored = False
        self._video_origin = None
        if suppress:
            self._video_suppressed_id = old_id
        if restore and origin is not None:
            self._video_returning = True
            self._animate_video_move(origin)
        else:
            self._video_returning = False
            self._play_state("idle")
        self.peek_controller.auto_peek_enabled = self._auto_peek_allowed()
        self._last_interaction = monotonic()
        self.events.publish(Event("character.video.stopped", old_id))

    def _begin_sleep(self) -> None:
        self._sleep_pending = True
        self._mouse_watch_until = 0.0
        self._mouse_watch_available = False
        self._dismiss_joke()
        self.peek_controller.auto_peek_enabled = False
        if self.peek_controller.active:
            self.peek_controller.restore()
        else:
            self._play_state("curl_up")

    def _on_leave_screen(self) -> None:
        self._mouse_watch_until = 0.0
        self._mouse_watch_available = False
        self._dismiss_joke()

    def _on_return_to_screen(self) -> None:
        if self._sleep_pending:
            self._play_state("idle")
        else:
            self._next_mouse_watch = monotonic() + self.random.uniform(15, 35)
            self._mouse_watch_available = True
            self._play_state("idle")

    def _on_peek_arrived(self) -> None:
        if self._sleep_pending:
            self._play_state("curl_up")

    def _tick_mouse_watch(self, now: float) -> None:
        if self.ai_chat_dialog is not None and self.ai_chat_dialog.isVisible():
            return
        watch = self._watch_animation()
        if self._mouse_watch_until:
            if now >= self._mouse_watch_until:
                self._mouse_watch_until = 0.0
                self._mouse_watch_available = False
                self.peek_controller.auto_peek_enabled = self._auto_peek_allowed()
                self.update()
            elif watch is not None:
                self._update_mouse_watch_direction(watch)
            if self._mouse_watch_until:
                return
        if not self._mouse_watch_available:
            return
        if now < self._next_mouse_watch:
            return
        if watch is None or self._drag_offset is not None:
            self._next_mouse_watch = now + 1.0
            return
        self._mouse_watch_until = now + self.WATCH_SECONDS
        self.peek_controller.auto_peek_enabled = False
        self._update_mouse_watch_direction(watch)

    def _watch_animation(self) -> AnimationSpec | None:
        state = {"idle": "mouse_watch", "sitting": "mouse_watch_sitting"}.get(self.player.state)
        return self.manifest.animations.get(state) if state is not None else None

    def _update_mouse_watch_direction(self, watch: AnimationSpec) -> None:
        cursor = QCursor.pos()
        center = self.mapToGlobal(QPoint(self.width() // 2, self.height() // 3))
        dx = cursor.x() - center.x()
        dy = cursor.y() - center.y()
        if self.player.state == "sitting":
            if abs(dx) < 30 and abs(dy) < 30:
                index = 3
            elif abs(dy) > abs(dx) and dy < -60:
                index = 1
            elif abs(dy) > abs(dx) and dy > 60:
                index = 2
            else:
                index = 0
        else:
            if abs(dy) > abs(dx) and dy < -60:
                index = 1
            elif abs(dy) > abs(dx) and dy > 60:
                index = 6
            else:
                index = min(5, 2 + abs(dx) // 150)
        index = min(index, len(watch.frames) - 1)
        mirrored = dx < 0
        if (index, mirrored) != (self._mouse_watch_index, self._mouse_watch_mirrored):
            self._mouse_watch_index = index
            self._mouse_watch_mirrored = mirrored
            self.update()

    def _schedule_next_joke(self) -> None:
        self.joke_timer.start(self.random.randint(3 * 60_000, 7 * 60_000))

    def _on_joke_timer(self) -> None:
        self.tell_joke()
        self._schedule_next_joke()

    def tell_joke(self, *, manual: bool = False) -> None:
        chatting = self.ai_chat_dialog is not None and self.ai_chat_dialog.isVisible()
        if (
            self.peek_controller.active
            or self.behavior_settings.personality_mode == "quiet"
            or self._sleep_pending
            or self._reminder_active
            or chatting
            or self._video_window_id is not None
            or self.focus_controller.phase in {"focus", "paused"}
            or self._game_quiet
        ) and not manual:
            return
        joke = self.joke_picker.choose(self.jokes.load()) if self.jokes is not None else None
        if joke is None:
            if manual:
                self._show_joke(
                    "Добавьте анекдоты в jokes.txt, разделяя их пустой строкой или строкой из тире."
                )
            return
        self._show_joke(joke)
        self.events.publish(Event("character.joke.told", joke))

    def _show_joke(self, text: str) -> None:
        self._bubble_action = None
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        self.joke_bubble.show_text(text, screen.availableGeometry().width() - 24)
        self._position_joke_bubble()
        self.joke_bubble.show()
        duration_ms = max(10_000, min(35_000, len(text) * 80))
        self.joke_hide_timer.start(duration_ms)

    def _show_ai_reply(self, text: str) -> None:
        preview = text[:500] + ("…" if len(text) > 500 else "")
        self._show_joke(preview)
        self.events.publish(Event("character.ai.answer_received", text))

    def open_ai_settings(self) -> bool:
        self._mark_interaction()
        dialog = AISettingsDialog(
            self.ai_settings_store,
            self,
            self.gesture_store,
            self.behavior_store,
            AutostartManager(),
        )
        dialog.interacted.connect(self._mark_interaction)
        accepted = dialog.exec() == dialog.DialogCode.Accepted
        if accepted:
            self.gesture_settings = self.gesture_store.load()
            previous_video_setting = self.behavior_settings.watch_videos
            self.behavior_settings = self.behavior_store.load()
            self._next_hover_gesture = 0.0
            self._next_rare_reaction = monotonic() + self._reaction_delay()
            self._apply_personality_mode()
            if self.behavior_settings.watch_videos and self.video_monitor is not None:
                self.video_timer.start()
                self._check_video_window()
            else:
                self.video_timer.stop()
                if previous_video_setting and self._video_window_id is not None:
                    self._leave_video_window(restore=True)
        return accepted

    def open_ai_chat(self, draft: str = "") -> None:
        self._mark_interaction()
        if not self.ai_settings_store.load().ready:
            if not self.open_ai_settings():
                return
            if not self.ai_settings_store.load().ready:
                return
        if self.ai_chat_dialog is None:
            dialog = AIChatDialog(self.ai_settings_store, self.open_ai_settings, self)
            dialog.interacted.connect(self._mark_interaction)
            dialog.request_started.connect(lambda: self.play("thinking"))
            dialog.request_finished.connect(lambda: self.play("idle"))
            dialog.answer_received.connect(self._show_ai_reply)
            dialog.finished.connect(self._on_ai_chat_closed)
            self.ai_chat_dialog = dialog
        self.ai_chat_dialog.show()
        if draft:
            self.ai_chat_dialog.set_draft(draft)
        self.peek_controller.auto_peek_enabled = False
        self.ai_chat_dialog.raise_()
        self.ai_chat_dialog.activateWindow()

    def _on_ai_chat_closed(self) -> None:
        if (
            not self._sleep_pending
            and not self._mouse_watch_until
            and not self._game_quiet
            and self.focus_controller.phase not in {"focus", "paused"}
        ):
            self.peek_controller.auto_peek_enabled = self._auto_peek_allowed()

    def stop_ai(self) -> None:
        if self.ai_chat_dialog is not None:
            self.ai_chat_dialog.close()

    def open_reminders(self) -> None:
        self._mark_interaction()
        if self.reminders_dialog is None:
            self.reminders_dialog = RemindersDialog(self.reminder_manager, self)
        self.reminders_dialog.show()
        self.reminders_dialog.raise_()
        self.reminders_dialog.activateWindow()

    def open_tasks(self) -> None:
        self._mark_interaction()
        if self.tasks_dialog is None:
            self.tasks_dialog = TasksDialog(self.task_manager, self.focus_controller, self)
        self.tasks_dialog.refresh()
        self.tasks_dialog.show()
        self.tasks_dialog.raise_()
        self.tasks_dialog.activateWindow()

    def open_curiosity(self) -> None:
        self._mark_interaction()
        if self.curiosity_dialog is None:
            self.curiosity_dialog = CuriosityDialog(self.curiosity_store, self)
            self.curiosity_dialog.answered.connect(self._on_curiosity_answered)
        self.curiosity_dialog.refresh()
        if self._pending_question:
            self.curiosity_dialog.show_question(self._pending_question)
        else:
            self.curiosity_dialog.show()
            self.curiosity_dialog.raise_()
            self.curiosity_dialog.activateWindow()

    def _on_curiosity_answered(self, question: str) -> None:
        if question == self._pending_question:
            self._pending_question = None
        self._dismiss_joke()
        self._next_curiosity = monotonic() + self.random.uniform(20 * 60, 40 * 60)

    def open_focus(self) -> None:
        self._mark_interaction()
        if self.focus_dialog is None:
            self.focus_dialog = FocusDialog(self.focus_controller, self)
        self.focus_dialog.show()
        self.focus_dialog.raise_()
        self.focus_dialog.activateWindow()

    def open_quick_actions(self) -> None:
        self._mark_interaction()
        if self.quick_actions_dialog is None:
            self.quick_actions_dialog = QuickActionsDialog(self)
        self.quick_actions_dialog.show()
        self.quick_actions_dialog.raise_()
        self.quick_actions_dialog.activateWindow()

    def open_code_help(self) -> None:
        clipboard = QApplication.clipboard().text().strip()
        if not clipboard:
            self._show_joke("Скопируйте текст ошибки или фрагмент кода в буфер обмена.")
            return
        excerpt = clipboard[:8_000]
        self.open_ai_chat(
            "Помоги разобраться с этой ошибкой или фрагментом кода. Объясни причину и предложи "
            f"исправление:\n\n{excerpt}"
        )

    def _on_reminder_due(self, text: str) -> None:
        self._release_reminder_cursor()
        if not self._reminder_active:
            self._reminder_previous_scale = self.scale
        self._reminder_active = True
        self._reminder_chasing = False
        self._reminder_text = text
        self._sleep_pending = False
        self._mouse_watch_until = 0.0
        self.personality_move.stop()
        self._personality_arriving = False
        self.video_move.stop()
        if self._video_window_id is not None:
            self._leave_video_window(restore=False, suppress=True)
        self.peek_controller.restore()
        self.peek_controller.auto_peek_enabled = False
        self._apply_scale(2.0)
        self._keep_on_screen()
        if "wave" in self.manifest.animations:
            self._play_state("wave")
        self._show_joke(f"⏰ {text}")
        self.joke_hide_timer.stop()
        self.reminder_escalation_timer.start(self.REMINDER_CHASE_DELAY_MS)
        self.events.publish(Event("productivity.reminder.due", text))

    def _start_reminder_chase(self) -> None:
        if not self._reminder_active:
            return
        self._reminder_chasing = True
        self._set_reminder_run_state(QCursor.pos())
        self.events.publish(Event("productivity.reminder.escalated"))

    def _set_reminder_run_state(self, cursor: QPoint) -> None:
        center = self.frameGeometry().center()
        state = "run_right" if cursor.x() >= center.x() else "run_left"
        if state in self.manifest.animations and self.player.state != state:
            self._play_state(state)

    def _tick_reminder_chase(self, delta_seconds: float) -> None:
        if self._reminder_cursor_locked:
            if self._reminder_cursor_anchor is not None:
                QCursor.setPos(self._reminder_cursor_anchor)
            return
        cursor = QCursor.pos()
        center = self.frameGeometry().center()
        dx = cursor.x() - center.x()
        dy = cursor.y() - center.y()
        distance = hypot(dx, dy)
        self._set_reminder_run_state(cursor)
        if distance <= 24:
            self._lock_reminder_cursor(cursor)
            return
        step = min(self.REMINDER_CHASE_SPEED * delta_seconds, max(0.0, distance - 20))
        if step <= 0:
            return
        target = QPoint(
            self.x() + round(dx / distance * step),
            self.y() + round(dy / distance * step),
        )
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            target.setX(max(area.left(), min(target.x(), area.right() - self.width() + 1)))
            target.setY(max(area.top(), min(target.y(), area.bottom() - self.height() + 1)))
        self.move(target)

    def _lock_reminder_cursor(self, cursor: QPoint) -> None:
        if self._reminder_cursor_locked:
            return
        if is_wayland_session():
            # Wayland does not allow a normal client to confine the global pointer.
            self._reminder_chasing = False
            self._play_state("idle")
            self._show_joke(f"⏰ {self._reminder_text}\n\nЯ рядом! Нажмите на меня, чтобы закрыть напоминание.")
            self.joke_hide_timer.stop()
            return
        self._reminder_cursor_locked = True
        self._reminder_cursor_anchor = QPoint(cursor)
        QCursor.setPos(self._reminder_cursor_anchor)
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.grabKeyboard()
        self._play_state("idle")
        self._show_joke(f"⏰ {self._reminder_text}\n\nПоймал! Нажмите Enter, чтобы я отпустил мышь.")
        self.joke_hide_timer.stop()
        self.events.publish(Event("productivity.reminder.cursor_locked"))

    def _release_reminder_cursor(self) -> None:
        if self._reminder_cursor_locked:
            self.releaseKeyboard()
        self._reminder_cursor_locked = False
        self._reminder_cursor_anchor = None

    def _acknowledge_reminder(self) -> None:
        if not self._reminder_active:
            return
        self.reminder_escalation_timer.stop()
        self._release_reminder_cursor()
        self._reminder_active = False
        self._reminder_chasing = False
        self._apply_scale(self._reminder_previous_scale)
        self._keep_on_screen()
        self._dismiss_joke()
        self._play_state("idle")
        self.peek_controller.auto_peek_enabled = self._auto_peek_allowed()
        if self.behavior_settings.personality_mode == "quiet":
            self._quiet_placed = False
        self.events.publish(Event("productivity.reminder.acknowledged"))

    def _on_focus_notice(self, text: str) -> None:
        self._show_joke(text)
        if self.focus_controller.phase in {"break", "idle"} and "wave" in self.manifest.animations:
            self._play_state("wave")

    def _on_focus_changed(self) -> None:
        quiet = self.focus_controller.phase in {"focus", "paused"}
        if self._reminder_active:
            self._focus_was_quiet = quiet
            return
        if quiet and not self._focus_was_quiet:
            if self._video_window_id is not None:
                self._leave_video_window(restore=True)
            self._dismiss_joke()
            self.peek_controller.auto_peek_enabled = False
            if "sitting" in self.manifest.animations:
                self._play_state("sitting")
        elif not quiet and self._focus_was_quiet:
            self.peek_controller.auto_peek_enabled = self._auto_peek_allowed()
            if self.player.state == "sitting":
                self._play_state("idle")
        self._focus_was_quiet = quiet

    def _check_app_context(self) -> None:
        if (self.app_monitor is None or self._reminder_active
                or self.behavior_settings.personality_mode == "quiet"):
            return
        application = self.app_monitor.current()
        kind = application.kind if application is not None else "other"
        now = monotonic()
        if kind != self._app_kind:
            self._app_kind = kind
            self._app_context_since = now
            self._next_context_reaction = now + 90

        game_quiet = kind == "game" and self.behavior_settings.react_to_games
        if game_quiet != self._game_quiet:
            self._game_quiet = game_quiet
            if game_quiet:
                self._dismiss_joke()
                self.peek_controller.auto_peek_enabled = False
                if self._video_window_id is not None:
                    self._leave_video_window(restore=True)
            else:
                self.peek_controller.auto_peek_enabled = self._auto_peek_allowed()

        if self.focus_controller.phase in {"focus", "paused"} or self._video_window_id is not None:
            return
        if kind == "music" and self.behavior_settings.react_to_music:
            if self.player.state in {"idle", "sitting"}:
                self._play_state("music_listening")
            return
        if self.player.state == "music_listening":
            self._play_state("idle")

        if kind == "code" and self.behavior_settings.react_to_code:
            clipboard = QApplication.clipboard().text().strip()
            error_markers = ("traceback", "exception", "error:", "failed", "ошибка")
            if (
                clipboard
                and clipboard != self._last_clipboard_error
                and any(marker in clipboard.casefold() for marker in error_markers)
            ):
                self._last_clipboard_error = clipboard
                self._show_joke(
                    "В буфере похожий на ошибку текст. Выберите «Разобрать ошибку» в моём меню."
                )
            if now >= self._next_context_reaction and self.player.state in {"idle", "sitting"}:
                self._next_context_reaction = now + self.random.uniform(4 * 60, 8 * 60)
                self._play_state("review")
                QTimer.singleShot(6_000, self._finish_context_reaction)

        if (
            kind == "document"
            and self.behavior_settings.break_reminders
            and now - self._app_context_since >= self.DOCUMENT_BREAK_SECONDS
            and now >= self._next_context_reaction
        ):
            self._next_context_reaction = now + self.DOCUMENT_BREAK_SECONDS
            self._mark_interaction()
            self._show_joke("Вы давно работаете с документом. Стоит размяться и дать глазам отдых.")

    def _finish_context_reaction(self) -> None:
        if self.player.state == "review" and self._video_window_id is None:
            self._play_state("idle")

    def _position_joke_bubble(self) -> None:
        if not hasattr(self, "joke_bubble"):
            return
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = self.x() + (self.width() - self.joke_bubble.width()) // 2
        x = max(area.left() + 8, min(x, area.right() - self.joke_bubble.width() - 8))
        y = self.y() - self.joke_bubble.height() - 12
        if y < area.top() + 8:
            y = self.y() + self.height() + 12
        y = max(area.top() + 8, min(y, area.bottom() - self.joke_bubble.height() - 8))
        self.joke_bubble.move(x, y)

    def _dismiss_joke(self) -> None:
        self.joke_hide_timer.stop()
        self.joke_bubble.hide()
        self._bubble_action = None

    def _on_bubble_dismissed(self) -> None:
        if self._reminder_active:
            self._acknowledge_reminder()
        elif self._bubble_action == "tasks":
            self.open_tasks()
            self._dismiss_joke()
        elif self._bubble_action == "curiosity":
            self.open_curiosity()
            self._dismiss_joke()
        else:
            self._dismiss_joke()

    def stop_jokes(self) -> None:
        self.joke_timer.stop()
        self._dismiss_joke()

    def stop_idle_peek(self) -> None:
        self.peek_controller.stop()

    def stop_video_watch(self) -> None:
        self.video_timer.stop()
        self.video_move.stop()
        if self.video_monitor is not None:
            self.video_monitor.close()

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        cell = self.player.current_frame
        mirrored = False
        watch = self._watch_animation()
        if self._mouse_watch_until and watch is not None:
            cell = watch.frames[self._mouse_watch_index]
            mirrored = self._mouse_watch_mirrored
        elif self.player.state == "video_watching":
            mirrored = self._video_mirrored
        source = QRect(
            cell.column * self.manifest.frame_width,
            cell.row * self.manifest.frame_height,
            self.manifest.frame_width,
            self.manifest.frame_height,
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        if mirrored:
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        painter.drawPixmap(self.rect(), self.atlas, source)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.personality_move.stop()
            self._personality_arriving = False
            if self._reminder_cursor_locked:
                self.setFocus(Qt.FocusReason.MouseFocusReason)
                event.accept()
                return
            self._acknowledge_reminder()
            self._mark_interaction()
            self._drag_pressed_at = event.globalPosition().toPoint()
            self._drag_offset = self._drag_pressed_at - self.frameGeometry().topLeft()
            self._dragging = False
            self.raise_()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._mark_interaction()
            cursor = event.globalPosition().toPoint()
            if not self._dragging:
                if (
                    self._drag_pressed_at is None
                    or (cursor - self._drag_pressed_at).manhattanLength()
                    < QApplication.startDragDistance()
                ):
                    event.accept()
                    return
                self._dragging = True
                if "drag_hold" in self.manifest.animations:
                    self._drag_offset = QPoint(
                        round(self.manifest.frame_width * self.scale * 0.17),
                        round(self.manifest.frame_height * self.scale * 0.20),
                    )
                    self._play_state("drag_hold")
            self.move(cursor - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._mark_interaction()
            was_dragging = self._dragging
            self._drag_offset = None
            self._drag_pressed_at = None
            self._dragging = False
            if was_dragging:
                if self.player.state == "drag_hold":
                    self._play_state("idle")
                self.events.publish(Event("character.position.changed", (self.x(), self.y())))
                if self._video_window_id is None:
                    self._save_appearance()
                if self.behavior_settings.watch_videos and self.video_monitor is not None:
                    QTimer.singleShot(150, self._resume_video_after_drag)
            elif self._pending_question:
                self.open_curiosity()
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._perform_gesture_action(self.gesture_settings.double_click)
            event.accept()

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().enterEvent(event)
        if self.gesture_settings.hover != "none":
            self.hover_timer.start(600)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.hover_timer.stop()
        super().leaveEvent(event)

    def _on_hover_gesture(self) -> None:
        if not self.underMouse() or self.peek_controller.active:
            return
        now = monotonic()
        if now < self._next_hover_gesture:
            return
        self._next_hover_gesture = now + self.gesture_settings.hover_cooldown_seconds
        self._perform_gesture_action(self.gesture_settings.hover)

    def _perform_gesture_action(self, action: str) -> None:
        if action == "wave" and "wave" in self.manifest.animations:
            self.play("wave")
        elif action == "chat":
            self.open_ai_chat()
        elif action == "joke":
            self._mark_interaction()
            self.tell_joke(manual=True)
        elif action == "sit" and "sit_down" in self.manifest.animations:
            self.play("sit_down")
        elif action == "sleep" and "curl_up" in self.manifest.animations:
            self.play("curl_up")
        elif action == "watch":
            self._mark_interaction()
            watch = self._watch_animation()
            if watch is not None:
                self._mouse_watch_until = monotonic() + 8.0
                self.peek_controller.auto_peek_enabled = False
                self._update_mouse_watch_direction(watch)

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._reminder_cursor_locked:
            event.accept()
            return
        self._acknowledge_reminder()
        self._mark_interaction()
        menu = QMenu(self)
        animation_menu = menu.addMenu("Анимация")
        for state in self.manifest.animations:
            if state.startswith(("mouse_watch", "video_watching")) or state in {
                "drag_hold",
                "music_listening",
            }:
                continue
            label = {
                "sit_down": "Сесть",
                "sitting": "Сидеть и ждать",
                "curl_up": "Свернуться",
                "sleeping": "Спать",
            }.get(state, state.replace("_", " ").title())
            action = QAction(label, animation_menu)
            action.triggered.connect(lambda _checked=False, name=state: self.play(name))
            animation_menu.addAction(action)

        scale_menu = menu.addMenu("Масштаб")
        for scale in (0.5, 1, 2, 3):
            action = QAction(f"×{scale:g}", scale_menu)
            action.setCheckable(True)
            action.setChecked(scale == self.scale)
            action.triggered.connect(lambda _checked=False, value=scale: self.set_scale(value))
            scale_menu.addAction(action)

        menu.addSeparator()
        mode_menu = menu.addMenu("Режим поведения")
        for mode, label in (("quiet", "Тихий"), ("active", "Активный"),
                            ("curious", "Любознательный")):
            action = mode_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.behavior_settings.personality_mode == mode)
            action.triggered.connect(lambda _checked=False, value=mode: self.set_personality_mode(value))
        commands_action = menu.addAction("Команды и поиск…")
        commands_action.triggered.connect(self.open_quick_actions)
        tasks_action = menu.addAction("Задачи и план дня…")
        tasks_action.triggered.connect(self.open_tasks)
        curiosity_action = menu.addAction("Вопросы и память…")
        curiosity_action.triggered.connect(self.open_curiosity)
        reminders_action = menu.addAction("Таймеры и напоминания…")
        reminders_action.triggered.connect(self.open_reminders)
        focus_action = menu.addAction("Режим концентрации…")
        focus_action.triggered.connect(self.open_focus)
        code_help_action = menu.addAction("Разобрать код или ошибку из буфера")
        code_help_action.setEnabled(bool(QApplication.clipboard().text().strip()))
        code_help_action.triggered.connect(self.open_code_help)
        menu.addSeparator()
        chat_action = menu.addAction("Поговорить с ИИ")
        chat_action.triggered.connect(lambda: self.open_ai_chat())
        settings_action = menu.addAction("Настройки…")
        settings_action.triggered.connect(lambda: self.open_ai_settings())
        joke_action = menu.addAction("Рассказать анекдот")
        joke_action.triggered.connect(lambda: self.tell_joke(manual=True))
        peek_action = menu.addAction("Выглянуть сейчас")
        peek_action.triggered.connect(self.peek_controller.preview)
        reset_action = menu.addAction("Вернуть в угол")
        reset_action.triggered.connect(lambda: self.move_to_default_position())
        quit_action = menu.addAction("Выйти")
        quit_action.triggered.connect(QApplication.quit)
        menu.exec(event.globalPos())

    def set_scale(self, scale: float) -> None:
        home_position = self._video_origin if self._video_window_id is not None else None
        self._mark_interaction()
        self._apply_scale(scale)
        self._keep_on_screen()
        self._save_appearance(home_position)

    def _apply_scale(self, scale: float) -> None:
        self.scale = max(0.5, float(scale))
        self._resize_to_character()
        self.update()
        self._position_joke_bubble()

    def _keep_on_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = max(area.left(), min(self.x(), area.right() - self.width() + 1))
        y = max(area.top(), min(self.y(), area.bottom() - self.height() + 1))
        self.move(x, y)

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self._position_joke_bubble()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_joke_bubble()

    def move_to_default_position(self) -> None:
        self._mark_interaction()
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 24
        self.move(area.right() - self.width() - margin, area.bottom() - self.height() - margin)
        self._save_appearance()

    def restore_appearance(self) -> bool:
        if self.appearance_store is None:
            return False
        appearance = self.appearance_store.load()
        if appearance is None:
            return False
        self._apply_scale(appearance.scale)
        center = QPoint(appearance.x + self.width() // 2, appearance.y + self.height() // 2)
        screen = QApplication.screenAt(center)
        if screen is None:
            return False
        area = screen.availableGeometry()
        x = max(area.left(), min(appearance.x, area.right() - self.width() + 1))
        y = max(area.top(), min(appearance.y, area.bottom() - self.height() + 1))
        self.move(x, y)
        return True

    def _save_appearance(self, position: QPoint | None = None) -> None:
        if self.appearance_store is None:
            return
        if self.peek_controller.active or self._reminder_active:
            return
        if position is None:
            position = self.pos()
        try:
            self.appearance_store.save(Appearance(position.x(), position.y(), self.scale))
        except OSError as error:
            LOG.warning("Could not save Morok's appearance: %s", error)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._reminder_active and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._acknowledge_reminder()
            event.accept()
            return
        if self._reminder_cursor_locked:
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.personality_timer.stop()
        self.personality_move.stop()
        self.reminder_escalation_timer.stop()
        self._release_reminder_cursor()
        self.stop_ai()
        self.stop_jokes()
        self.stop_idle_peek()
        self.stop_video_watch()
        self.context_timer.stop()
        self.reminder_manager.stop()
        self.focus_controller.stop()
        if self.quick_actions_dialog is not None:
            self.quick_actions_dialog.close()
        if self.reminders_dialog is not None:
            self.reminders_dialog.close()
        if self.focus_dialog is not None:
            self.focus_dialog.close()
        if self.tasks_dialog is not None:
            self.tasks_dialog.close()
        if self.curiosity_dialog is not None:
            self.curiosity_dialog.close()
        super().closeEvent(event)
