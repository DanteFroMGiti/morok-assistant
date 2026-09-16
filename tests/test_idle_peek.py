from random import Random
from types import SimpleNamespace

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from morok_assistant.application.bootstrap import bundled_characters_path
from morok_assistant.characters.repository import CharacterRepository
from morok_assistant.core.models import FrameCell
from morok_assistant.system.idle import _has_active_stream
from morok_assistant.ui.idle_peek import IdlePeekController, PeekWindow


class FakeIdleMonitor:
    def __init__(self, seconds: float) -> None:
        self.value = seconds

    def seconds(self) -> float:
        return self.value

    def close(self) -> None:
        pass


class FakeAudioMonitor:
    def __init__(self, active: bool = False) -> None:
        self.value = active

    def active(self) -> bool:
        return self.value


def test_audio_activity_requires_unmuted_uncorked_stream() -> None:
    assert _has_active_stream("Sink Input #1\n Corked: no\n Mute: no\n")
    assert not _has_active_stream("Sink Input #1\n Corked: yes\n Mute: no\n")
    assert not _has_active_stream("Sink Input #1\n Corked: no\n Mute: yes\n")


def test_peek_reveals_horns_first_from_every_edge() -> None:
    app = QApplication.instance() or QApplication([])
    atlas = QPixmap(20, 20)
    atlas.fill(QColor("blue"))
    painter = QPainter(atlas)
    painter.fillRect(0, 0, 20, 2, QColor("red"))
    painter.fillRect(0, 18, 20, 2, QColor("green"))
    painter.end()
    manifest = SimpleNamespace(
        frame_width=20,
        frame_height=20,
        animations={"idle": SimpleNamespace(frames=(FrameCell(0, 0),))},
    )
    character = QWidget()
    peek = PeekWindow(character, manifest, atlas)

    for edge in ("top", "left", "right", "bottom"):
        peek.set_edge(edge)
        peek.set_reveal(1.0, 0.1)
        first_size = peek.size()
        first = QImage(first_size, QImage.Format.Format_ARGB32)
        first.fill(Qt.GlobalColor.transparent)
        peek.render(first)
        colors = {
            first.pixelColor(x, y).name()
            for y in range(first.height())
            for x in range(first.width())
        }
        assert colors == {"#ff0000"}

        peek.set_reveal(1.0, 0.8)
        later = QImage(peek.size(), QImage.Format.Format_ARGB32)
        later.fill(Qt.GlobalColor.transparent)
        peek.render(later)
        colors = {
            later.pixelColor(x, y).name()
            for y in range(later.height())
            for x in range(later.width())
        }
        assert "#0000ff" in colors
        assert peek.width() > first_size.width() or peek.height() > first_size.height()
        outer_x = later.width() - 1 if edge == "left" else 0 if edge == "right" else 10
        outer_y = later.height() - 1 if edge == "top" else 0 if edge == "bottom" else 10
        assert later.pixelColor(outer_x, outer_y).name() == "#ff0000"

    peek.set_edge("bottom")
    peek.set_reveal(1.0, 1.0)
    upright = QImage(peek.size(), QImage.Format.Format_ARGB32)
    upright.fill(Qt.GlobalColor.transparent)
    peek.render(upright)
    assert upright.pixelColor(10, 0).name() == "#ff0000"
    assert upright.pixelColor(10, upright.height() - 1).name() == "#008000"

    peek.set_edge("top")
    peek.set_reveal(1.0, 1.0)
    inverted = QImage(peek.size(), QImage.Format.Format_ARGB32)
    inverted.fill(Qt.GlobalColor.transparent)
    peek.render(inverted)
    assert inverted.pixelColor(10, 0).name() == "#008000"
    assert inverted.pixelColor(10, inverted.height() - 1).name() == "#ff0000"

    peek.close()
    character.close()
    assert app is not None


def test_peek_is_clipped_to_each_screen_edge() -> None:
    app = QApplication.instance() or QApplication([])
    character = QWidget()
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    controller = IdlePeekController(
        character,
        manifest,
        QPixmap(str(manifest.sprite_path)),
        Random(7),
        FakeIdleMonitor(0.0),
        FakeAudioMonitor(),
    )
    controller.activity_timer.stop()
    area = QRect(100, 100, 800, 600)
    controller._peek_area = area
    controller._peek_fraction = 0.5

    for edge in ("top", "left", "right", "bottom"):
        controller._peek_edge = edge
        controller.peek_window.set_edge(edge)
        controller._render_peek(0.0)
        first = controller.peek_window.geometry()
        controller._render_peek(1.0)
        later = controller.peek_window.geometry()

        assert area.contains(first)
        assert area.contains(later)
        assert later.width() > first.width() or later.height() > first.height()
        if edge == "top":
            assert first.top() == later.top() == area.top()
        elif edge == "left":
            assert first.left() == later.left() == area.left()
        elif edge == "right":
            assert first.right() == later.right() == area.right()
        else:
            assert first.bottom() == later.bottom() == area.bottom()

    controller.stop()
    character.close()
    assert app is not None


def test_leaves_after_global_idle_peeks_and_returns(monkeypatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("morok_assistant.ui.idle_peek.monotonic", lambda: clock[0])
    app = QApplication.instance() or QApplication([])
    character = QWidget()
    character.resize(192, 208)
    character.show()
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    idle = FakeIdleMonitor(61.0)
    audio = FakeAudioMonitor()
    controller = IdlePeekController(
        character, manifest, QPixmap(str(manifest.sprite_path)), Random(7), idle, audio
    )
    controller.activity_timer.stop()

    clock[0] = 61.0
    controller._check_activity()
    assert controller.mode == "leaving"
    origin = controller._origin
    target = controller.character_animation.endValue()
    assert target != origin

    controller.character_animation.stop()
    character.move(target)
    controller._on_character_animation_finished()
    assert controller.mode == "hidden"

    controller.peek_delay.stop()
    controller._start_peek()
    assert controller.mode == "peeking"
    assert controller._peek_area in [screen.geometry() for screen in QApplication.screens()]
    assert controller.peek_window.isVisible()
    small_width = controller.peek_window.width()
    controller.peek_animation.stop()
    controller._render_peek(1.0)
    assert controller.peek_window.width() > small_width

    first_edge = controller._peek_edge
    controller._retract_peek()
    controller.peek_animation.stop()
    controller._on_peek_animation_finished()
    controller.peek_delay.stop()
    controller._start_peek()
    assert controller._peek_edge != first_edge

    idle.value = 0.0
    controller._check_activity()
    assert controller.mode == "returning"
    assert not controller.peek_window.isVisible()
    assert controller.character_animation.endValue() == origin

    controller.character_animation.stop()
    character.move(origin)
    controller._on_character_animation_finished()
    assert controller.mode == "visible"
    controller.stop()
    character.close()
    assert app is not None


def test_audio_activity_prevents_departure(monkeypatch) -> None:
    clock = [61.0]
    monkeypatch.setattr("morok_assistant.ui.idle_peek.monotonic", lambda: clock[0])
    app = QApplication.instance() or QApplication([])
    character = QWidget()
    character.resize(192, 208)
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    audio = FakeAudioMonitor(active=True)
    controller = IdlePeekController(
        character,
        manifest,
        QPixmap(str(manifest.sprite_path)),
        Random(7),
        FakeIdleMonitor(61.0),
        audio,
    )
    controller.activity_timer.stop()
    controller._visible_since = 0.0
    controller._check_activity()
    assert controller.mode == "visible"
    controller.stop()
    character.close()
    assert app is not None


def test_preview_works_even_when_audio_is_active(monkeypatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("morok_assistant.ui.idle_peek.monotonic", lambda: clock[0])
    app = QApplication.instance() or QApplication([])
    character = QWidget()
    character.resize(192, 208)
    character.show()
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    controller = IdlePeekController(
        character,
        manifest,
        QPixmap(str(manifest.sprite_path)),
        Random(7),
        FakeIdleMonitor(0.0),
        FakeAudioMonitor(active=True),
    )
    controller.activity_timer.stop()
    controller.preview()
    assert controller.mode == "leaving"
    assert controller.preview_timer.isActive()

    controller._check_activity()
    assert controller.mode == "leaving"
    controller.restore()
    assert controller.mode == "returning"
    assert not controller.preview_timer.isActive()

    controller.stop()
    character.close()
    assert app is not None
