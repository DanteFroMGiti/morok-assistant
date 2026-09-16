from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

DOUBLE_CLICK_ACTIONS = {
    "wave": "Помахать лапой",
    "chat": "Открыть диалог с ИИ",
    "joke": "Рассказать анекдот",
    "sit": "Сесть",
    "sleep": "Свернуться и заснуть",
    "none": "Ничего",
}

HOVER_ACTIONS = {
    "watch": "Следить за курсором",
    "wave": "Помахать лапой",
    "joke": "Рассказать анекдот",
    "none": "Ничего",
}


@dataclass(frozen=True, slots=True)
class GestureSettings:
    double_click: str = "wave"
    hover: str = "watch"


def default_gesture_settings_path() -> Path:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "morok-assistant" / "gestures.json"


class GestureSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_gesture_settings_path()

    def load(self) -> GestureSettings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return GestureSettings()
        if not isinstance(raw, dict):
            return GestureSettings()
        double_click = raw.get("double_click")
        hover = raw.get("hover")
        return GestureSettings(
            double_click=(
                double_click
                if isinstance(double_click, str) and double_click in DOUBLE_CLICK_ACTIONS
                else "wave"
            ),
            hover=hover if isinstance(hover, str) and hover in HOVER_ACTIONS else "watch",
        )

    def save(self, settings: GestureSettings) -> None:
        if settings.double_click not in DOUBLE_CLICK_ACTIONS or settings.hover not in HOVER_ACTIONS:
            raise ValueError("Неизвестное действие жеста")
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".gestures-", suffix=".json", dir=directory)
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
