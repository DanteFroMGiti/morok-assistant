import json
from pathlib import Path

import pytest

from morok_assistant.animation.manifest_loader import ManifestLoader
from morok_assistant.core.errors import InvalidCharacterPackError


def write_pack(root: Path, animations: dict) -> Path:
    (root / "sprites.png").touch()
    path = root / "character.json"
    path.write_text(
        json.dumps(
            {
                "id": "test",
                "name": "Test",
                "sprite": "sprites.png",
                "frame": {"width": 16, "height": 16},
                "grid": {"columns": 2, "rows": 2},
                "animations": animations,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_loads_valid_manifest(tmp_path: Path) -> None:
    path = write_pack(
        tmp_path,
        {"idle": {"frames": [[0, 0], [1, 0]], "fps": 8}},
    )
    manifest = ManifestLoader().load(path)
    assert manifest.character_id == "test"
    assert len(manifest.animations["idle"].frames) == 2


def test_rejects_pack_without_idle(tmp_path: Path) -> None:
    path = write_pack(tmp_path, {"wave": {"frames": [[0, 0]], "fps": 8}})
    with pytest.raises(InvalidCharacterPackError):
        ManifestLoader().load(path)


def test_rejects_frame_outside_atlas(tmp_path: Path) -> None:
    path = write_pack(tmp_path, {"idle": {"frames": [[9, 0]], "fps": 8}})
    with pytest.raises(InvalidCharacterPackError):
        ManifestLoader().load(path)
