from __future__ import annotations

from random import Random
from time import monotonic

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QMouseEvent, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QWidget

from morok_assistant.core.models import CharacterManifest
from morok_assistant.system.idle import AudioActivityMonitor, X11IdleMonitor


class PeekWindow(QWidget):
    activated = Signal()

    def __init__(self, parent: QWidget, manifest: CharacterManifest, atlas: QPixmap) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.BypassWindowManagerHint,
        )
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._head = QPixmap()
        self._oriented_head = QPixmap()
        self._paint_rect = QRect()
        self._edge = "top"
        self.set_character(manifest, atlas)
        self.hide()

    def set_character(self, manifest: CharacterManifest, atlas: QPixmap) -> None:
        cell = manifest.animations["idle"].frames[0]
        head_height = min(105, manifest.frame_height)
        source = QRect(
            cell.column * manifest.frame_width,
            cell.row * manifest.frame_height,
            manifest.frame_width,
            head_height,
        )
        head = atlas.copy(source)
        image = head.toImage()
        opaque = [
            (x, y)
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 8
        ]
        if opaque:
            left = min(x for x, _ in opaque)
            top = min(y for _, y in opaque)
            right = max(x for x, _ in opaque)
            bottom = max(y for _, y in opaque)
            head = head.copy(QRect(left, top, right - left + 1, bottom - top + 1))
        self._head = head
        self.set_edge(self._edge)

    def set_edge(self, edge: str) -> None:
        self._edge = edge
        rotation = {"top": 180, "left": 90, "right": -90, "bottom": 0}[edge]
        self._oriented_head = (
            self._head.transformed(QTransform().rotate(rotation)) if rotation else self._head
        )
        self.set_reveal(0.8, 0.08)

    def set_reveal(self, scale: float, fraction: float) -> None:
        full_width = max(1, round(self._oriented_head.width() * scale))
        full_height = max(1, round(self._oriented_head.height() * scale))
        if self._edge in {"left", "right"}:
            visible_width = max(1, min(full_width, round(full_width * fraction)))
            visible_height = full_height
        else:
            visible_width = full_width
            visible_height = max(1, min(full_height, round(full_height * fraction)))
        offset_x = visible_width - full_width if self._edge == "left" else 0
        offset_y = visible_height - full_height if self._edge == "top" else 0
        self._paint_rect = QRect(offset_x, offset_y, full_width, full_height)
        self.resize(visible_width, visible_height)
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawPixmap(self._paint_rect, self._oriented_head)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.activated.emit()
        event.accept()


class IdlePeekController(QObject):
    """Move Morok offscreen after global inactivity, then show growing head peeks."""

    left_screen = Signal()
    returned = Signal()
    arrived = Signal()
    IDLE_SECONDS = 60.0

    def __init__(
        self,
        character: QWidget,
        manifest: CharacterManifest,
        atlas: QPixmap,
        random: Random,
        idle_monitor: X11IdleMonitor | None = None,
        audio_monitor: AudioActivityMonitor | None = None,
    ) -> None:
        super().__init__(character)
        self.character = character
        self.random = random
        self.idle_monitor = idle_monitor or X11IdleMonitor.create_if_available()
        self.audio_monitor = audio_monitor or AudioActivityMonitor()
        self.mode = "visible"
        self._visible_since = monotonic()
        self._origin = QPoint(character.pos())
        self._previous_edge: str | None = None
        self._peek_edge = "left"
        self._peek_area = QRect()
        self._peek_fraction = 0.5
        self._preview = False
        self.auto_peek_enabled = True

        self.peek_window = PeekWindow(character, manifest, atlas)
        self.peek_window.activated.connect(self.restore)
        self.character_animation = QPropertyAnimation(character, b"pos", self)
        self.character_animation.finished.connect(self._on_character_animation_finished)
        self.peek_animation = QVariantAnimation(self)
        self.peek_animation.valueChanged.connect(self._render_peek)
        self.peek_animation.finished.connect(self._on_peek_animation_finished)

        self.activity_timer = QTimer(self)
        self.activity_timer.setInterval(1000)
        self.activity_timer.timeout.connect(self._check_activity)
        if self.idle_monitor is not None:
            self.activity_timer.start()
        self.peek_delay = QTimer(self)
        self.peek_delay.setSingleShot(True)
        self.peek_delay.timeout.connect(self._start_peek)
        self.peek_hold = QTimer(self)
        self.peek_hold.setSingleShot(True)
        self.peek_hold.timeout.connect(self._retract_peek)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.restore)

    @property
    def active(self) -> bool:
        return self.mode != "visible"

    def update_character(self, manifest: CharacterManifest, atlas: QPixmap) -> None:
        self.peek_window.set_character(manifest, atlas)

    def _check_activity(self) -> None:
        if self.idle_monitor is None:
            return
        idle_seconds = self.idle_monitor.seconds()
        if idle_seconds is None:
            return
        if self.active:
            if self._preview:
                return
            if (
                not self.auto_peek_enabled
                or idle_seconds < self.IDLE_SECONDS
                or self.audio_monitor.active()
            ):
                self.restore()
            return
        if not self.auto_peek_enabled:
            return
        if (
            monotonic() - self._visible_since >= self.IDLE_SECONDS
            and idle_seconds >= self.IDLE_SECONDS
            and not self.audio_monitor.active()
        ):
            self._leave_screen()

    def _leave_screen(self) -> None:
        screen = self.character.screen() or QApplication.primaryScreen()
        if screen is None or self.mode != "visible":
            return
        area = screen.availableGeometry()
        self._origin = QPoint(self.character.pos())
        distances = {
            "left": self.character.x() - area.left(),
            "right": area.right() - (self.character.x() + self.character.width()),
            "top": self.character.y() - area.top(),
            "bottom": area.bottom() - (self.character.y() + self.character.height()),
        }
        edge = min(distances, key=distances.get)
        target = QPoint(self._origin)
        if edge == "left":
            target.setX(area.left() - self.character.width() - 16)
        elif edge == "right":
            target.setX(area.left() + area.width() + 16)
        elif edge == "top":
            target.setY(area.top() - self.character.height() - 16)
        else:
            target.setY(area.top() + area.height() + 16)
        self.mode = "leaving"
        self.left_screen.emit()
        self.character_animation.stop()
        self.character_animation.setDuration(850)
        self.character_animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.character_animation.setStartValue(self._origin)
        self.character_animation.setEndValue(target)
        self.character_animation.start()

    def preview(self) -> None:
        if self.mode != "visible":
            return
        self._preview = True
        self._leave_screen()
        if self.mode == "leaving":
            self.preview_timer.start(9000)
        else:
            self._preview = False

    def _on_character_animation_finished(self) -> None:
        if self.mode == "leaving":
            self.mode = "hidden"
            self.peek_delay.start(1800)
        elif self.mode == "returning":
            self.mode = "visible"
            self._visible_since = monotonic()
            self.character.raise_()
            self.arrived.emit()

    def _start_peek(self) -> None:
        if self.mode != "hidden":
            return
        screens = QApplication.screens()
        if not screens:
            return
        self._peek_area = self.random.choice(screens).geometry()
        edges = [edge for edge in ("left", "right", "top", "bottom") if edge != self._previous_edge]
        self._peek_edge = self.random.choice(edges)
        self._previous_edge = self._peek_edge
        self._peek_fraction = self.random.uniform(0.2, 0.8)
        self.peek_window.set_edge(self._peek_edge)
        self.mode = "peeking"
        self._render_peek(0.0)
        self.peek_window.show()
        self.peek_window.raise_()
        self.peek_animation.stop()
        self.peek_animation.setDuration(1400)
        self.peek_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.peek_animation.setStartValue(0.0)
        self.peek_animation.setEndValue(1.0)
        self.peek_animation.start()

    def _render_peek(self, value) -> None:  # type: ignore[no-untyped-def]
        progress = max(0.0, min(1.0, float(value)))
        self.peek_window.set_reveal(0.8 + progress, 0.08 + 0.70 * progress)
        area = self._peek_area
        width = self.peek_window.width()
        height = self.peek_window.height()
        if self._peek_edge in {"left", "right"}:
            center_y = area.top() + round(area.height() * self._peek_fraction)
            y = max(area.top(), min(center_y - height // 2, area.top() + area.height() - height))
            x = area.left() if self._peek_edge == "left" else area.right() - width + 1
        else:
            center_x = area.left() + round(area.width() * self._peek_fraction)
            x = max(area.left(), min(center_x - width // 2, area.left() + area.width() - width))
            y = area.top() if self._peek_edge == "top" else area.bottom() - height + 1
        self.peek_window.move(x, y)

    def _on_peek_animation_finished(self) -> None:
        if self.mode == "peeking":
            self.peek_hold.start(2400)
        elif self.mode == "retracting":
            self.peek_window.hide()
            self.mode = "hidden"
            self.peek_delay.start(self.random.randint(6500, 14000))

    def _retract_peek(self) -> None:
        if self.mode != "peeking":
            return
        self.mode = "retracting"
        self.peek_animation.stop()
        self.peek_animation.setDuration(800)
        self.peek_animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.peek_animation.setStartValue(1.0)
        self.peek_animation.setEndValue(0.0)
        self.peek_animation.start()

    def restore(self) -> None:
        if self.mode in {"visible", "returning"}:
            return
        self._preview = False
        self.preview_timer.stop()
        self.peek_delay.stop()
        self.peek_hold.stop()
        self.peek_animation.stop()
        self.peek_window.hide()
        self.character_animation.stop()
        self.mode = "returning"
        self.returned.emit()
        self.character_animation.setDuration(650)
        self.character_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.character_animation.setStartValue(self.character.pos())
        self.character_animation.setEndValue(self._origin)
        self.character_animation.start()

    def stop(self) -> None:
        self.activity_timer.stop()
        self.preview_timer.stop()
        self.peek_delay.stop()
        self.peek_hold.stop()
        self.peek_animation.stop()
        self.character_animation.stop()
        self.peek_window.close()
        if self.idle_monitor is not None:
            self.idle_monitor.close()
