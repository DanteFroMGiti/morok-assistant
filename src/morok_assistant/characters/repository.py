from __future__ import annotations

from pathlib import Path

from morok_assistant.animation.manifest_loader import ManifestLoader
from morok_assistant.core.models import CharacterManifest


class CharacterRepository:
    def __init__(self, root: Path, loader: ManifestLoader | None = None) -> None:
        self.root = root
        self.loader = loader or ManifestLoader()

    def discover(self) -> dict[str, CharacterManifest]:
        characters: dict[str, CharacterManifest] = {}
        for manifest_path in sorted(self.root.glob("*/character.json")):
            manifest = self.loader.load(manifest_path)
            characters[manifest.character_id] = manifest
        return characters

    def get(self, character_id: str) -> CharacterManifest:
        characters = self.discover()
        if character_id not in characters:
            available = ", ".join(sorted(characters)) or "none"
            raise KeyError(f"Unknown character '{character_id}'. Available: {available}")
        return characters[character_id]
