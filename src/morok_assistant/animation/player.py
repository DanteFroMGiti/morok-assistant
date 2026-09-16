from __future__ import annotations

from morok_assistant.core.errors import UnknownAnimationError
from morok_assistant.core.models import AnimationSpec, CharacterManifest, FrameCell


class AnimationPlayer:
    """Toolkit-independent animation state machine."""

    def __init__(self, manifest: CharacterManifest, initial_state: str = "idle") -> None:
        self.manifest = manifest
        self.state = ""
        self.frame_index = 0
        self._elapsed_ms = 0.0
        self.play(initial_state)

    @property
    def animation(self) -> AnimationSpec:
        return self.manifest.animations[self.state]

    @property
    def current_frame(self) -> FrameCell:
        return self.animation.frames[self.frame_index]

    def play(self, state: str, *, restart: bool = True) -> None:
        resolved = state if state in self.manifest.animations else "idle"
        if resolved not in self.manifest.animations:
            raise UnknownAnimationError(state)
        if resolved == self.state and not restart:
            return
        self.state = resolved
        self.frame_index = 0
        self._elapsed_ms = 0.0

    def tick(self, delta_ms: float) -> bool:
        if delta_ms <= 0:
            return False
        self._elapsed_ms += delta_ms
        changed = False
        while self._elapsed_ms >= self.animation.frame_duration_ms:
            self._elapsed_ms -= self.animation.frame_duration_ms
            changed = self._advance() or changed
        return changed

    def _advance(self) -> bool:
        last_index = len(self.animation.frames) - 1
        if self.frame_index < last_index:
            self.frame_index += 1
            return True
        if self.animation.loop:
            self.frame_index = 0
            return True

        fallback = self.animation.fallback
        self.play(fallback if fallback in self.manifest.animations else "idle")
        return True
