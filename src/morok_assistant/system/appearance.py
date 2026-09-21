from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

SCALES = {0.5, 1.0, 2.0, 3.0}


@dataclass(frozen=True, slots=True)
class Appearance:
    x: int
    y: int
    scale: float


def default_appearance_path() -> Path:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "morok-assistant" / "appearance.json"


class AppearanceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_appearance_path()

    def load(self) -> Appearance | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        x, y, scale = raw.get("x"), raw.get("y"), raw.get("scale")
        if (
            type(x) is not int
            or type(y) is not int
            or abs(x) > 100_000
            or abs(y) > 100_000
            or type(scale) not in (int, float)
            or scale not in SCALES
        ):
            return None
        return Appearance(x, y, float(scale))

    def save(self, appearance: Appearance) -> None:
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".appearance-", suffix=".json", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(asdict(appearance), file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
