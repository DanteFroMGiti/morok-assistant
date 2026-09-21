from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from morok_assistant.system.wayland import WAYLAND_MODES

PERSONALITY_MODES = {"quiet", "active", "curious"}
REACTION_FREQUENCIES = {"off", "rare", "normal", "often"}


@dataclass(frozen=True, slots=True)
class BehaviorSettings:
    watch_videos: bool = True
    react_to_games: bool = True
    react_to_music: bool = True
    react_to_code: bool = True
    break_reminders: bool = True
    wayland_mode: str = "auto"
    personality_mode: str = "active"
    reaction_frequency: str = "rare"


def default_behavior_settings_path() -> Path:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "morok-assistant" / "behavior.json"


class BehaviorSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_behavior_settings_path()

    def load(self) -> BehaviorSettings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return BehaviorSettings()
        if not isinstance(raw, dict):
            return BehaviorSettings()
        mode = raw.get("wayland_mode", "auto")
        personality = raw.get("personality_mode", "active")
        frequency = raw.get("reaction_frequency", "rare")
        return BehaviorSettings(
            watch_videos=raw.get("watch_videos") is not False,
            react_to_games=raw.get("react_to_games") is not False,
            react_to_music=raw.get("react_to_music") is not False,
            react_to_code=raw.get("react_to_code") is not False,
            break_reminders=raw.get("break_reminders") is not False,
            wayland_mode=mode if isinstance(mode, str) and mode in WAYLAND_MODES else "auto",
            personality_mode=(
                personality if isinstance(personality, str) and personality in PERSONALITY_MODES
                else "active"
            ),
            reaction_frequency=(
                frequency if isinstance(frequency, str) and frequency in REACTION_FREQUENCIES
                else "rare"
            ),
        )

    def save(self, settings: BehaviorSettings) -> None:
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".behavior-", suffix=".json", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(asdict(settings), file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
