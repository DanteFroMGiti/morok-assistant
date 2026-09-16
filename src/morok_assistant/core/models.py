from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from morok_assistant.core.errors import InvalidCharacterPackError


@dataclass(frozen=True, slots=True)
class FrameCell:
    column: int
    row: int


@dataclass(frozen=True, slots=True)
class AnimationSpec:
    frames: tuple[FrameCell, ...]
    fps: float
    loop: bool = True
    fallback: str = "idle"

    @property
    def frame_duration_ms(self) -> float:
        return 1000.0 / self.fps


@dataclass(frozen=True, slots=True)
class CharacterManifest:
    character_id: str
    name: str
    sprite_path: Path
    frame_width: int
    frame_height: int
    columns: int
    rows: int
    anchor_x: int
    anchor_y: int
    default_scale: int
    animations: dict[str, AnimationSpec]

    def validate(self) -> None:
        if not self.character_id or not self.name:
            raise InvalidCharacterPackError("Character id and name are required")
        if min(self.frame_width, self.frame_height, self.columns, self.rows) <= 0:
            raise InvalidCharacterPackError("Frame and grid dimensions must be positive")
        if self.default_scale < 1:
            raise InvalidCharacterPackError("Scale must be an integer greater than zero")
        if "idle" not in self.animations:
            raise InvalidCharacterPackError("Every character must provide an idle animation")

        for state, animation in self.animations.items():
            if not animation.frames or animation.fps <= 0:
                raise InvalidCharacterPackError(f"Invalid animation: {state}")
            for cell in animation.frames:
                if not (0 <= cell.column < self.columns and 0 <= cell.row < self.rows):
                    raise InvalidCharacterPackError(
                        f"Frame ({cell.column}, {cell.row}) is outside the atlas"
                    )
