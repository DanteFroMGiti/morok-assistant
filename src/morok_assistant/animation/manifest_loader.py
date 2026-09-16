from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from morok_assistant.core.errors import InvalidCharacterPackError
from morok_assistant.core.models import AnimationSpec, CharacterManifest, FrameCell


class ManifestLoader:
    def load(self, manifest_path: Path) -> CharacterManifest:
        try:
            raw: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
            pack_root = manifest_path.parent.resolve()
            sprite_path = (pack_root / raw["sprite"]).resolve()
            sprite_path.relative_to(pack_root)

            animations = {
                state: AnimationSpec(
                    frames=tuple(FrameCell(column=cell[0], row=cell[1]) for cell in spec["frames"]),
                    fps=float(spec["fps"]),
                    loop=bool(spec.get("loop", True)),
                    fallback=str(spec.get("fallback", "idle")),
                )
                for state, spec in raw["animations"].items()
            }
            frame = raw["frame"]
            grid = raw["grid"]
            anchor = raw.get("anchor", {"x": frame["width"] // 2, "y": frame["height"]})
            manifest = CharacterManifest(
                character_id=str(raw["id"]),
                name=str(raw["name"]),
                sprite_path=sprite_path,
                frame_width=int(frame["width"]),
                frame_height=int(frame["height"]),
                columns=int(grid["columns"]),
                rows=int(grid["rows"]),
                anchor_x=int(anchor["x"]),
                anchor_y=int(anchor["y"]),
                default_scale=int(raw.get("default_scale", 1)),
                animations=animations,
            )
            manifest.validate()
            if not sprite_path.is_file():
                raise InvalidCharacterPackError(f"Sprite atlas not found: {sprite_path.name}")
            return manifest
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise InvalidCharacterPackError(
                f"Cannot parse character manifest {manifest_path.name}: {error}"
            ) from error
