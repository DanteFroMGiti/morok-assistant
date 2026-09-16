from pathlib import Path

from morok_assistant.animation.player import AnimationPlayer
from morok_assistant.core.models import AnimationSpec, CharacterManifest, FrameCell


def manifest() -> CharacterManifest:
    return CharacterManifest(
        character_id="test",
        name="Test",
        sprite_path=Path("sprites.png"),
        frame_width=16,
        frame_height=16,
        columns=2,
        rows=2,
        anchor_x=8,
        anchor_y=16,
        default_scale=1,
        animations={
            "idle": AnimationSpec((FrameCell(0, 0), FrameCell(1, 0)), fps=10),
            "wave": AnimationSpec(
                (FrameCell(0, 1), FrameCell(1, 1)), fps=10, loop=False, fallback="idle"
            ),
        },
    )


def test_advances_looping_animation() -> None:
    player = AnimationPlayer(manifest())
    assert player.tick(100)
    assert player.frame_index == 1
    assert player.tick(100)
    assert player.frame_index == 0


def test_non_looping_animation_returns_to_fallback() -> None:
    player = AnimationPlayer(manifest())
    player.play("wave")
    player.tick(200)
    assert player.state == "idle"
    assert player.frame_index == 0


def test_unknown_state_uses_idle() -> None:
    player = AnimationPlayer(manifest())
    player.play("does-not-exist")
    assert player.state == "idle"
