from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from random import Random

LOG = logging.getLogger(__name__)


class JokeRepository:
    """Read jokes afresh so edits take effect without restarting the application."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[str]:
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []

        source_lines = content.splitlines()
        dash_separators = any(self._is_dash_separator(line) for line in source_lines)
        jokes: list[str] = []
        lines: list[str] = []
        for line in source_lines:
            if line.lstrip().startswith("#"):
                continue

            if self._is_dash_separator(line) or (not dash_separators and not line.strip()):
                joke = "\n".join(lines).strip()
                if joke:
                    jokes.append(joke)
                lines = []
            else:
                lines.append(line.strip())

        joke = "\n".join(lines).strip()
        if joke:
            jokes.append(joke)
        return jokes

    @staticmethod
    def _is_dash_separator(line: str) -> bool:
        stripped = line.strip()
        return len(stripped) >= 3 and set(stripped) == {"—"}


class JokePicker:
    """Draw every joke once per cycle, even when the application is restarted."""

    def __init__(self, random: Random | None = None, history_path: Path | None = None) -> None:
        self.random = random or Random()
        self.history_path = history_path
        self._previous: str | None = None
        self._known: set[str] = set()
        self._remaining: list[str] = []
        self._load_history()

    def choose(self, jokes: list[str]) -> str | None:
        available = {
            hashlib.sha256(joke.encode("utf-8")).hexdigest(): joke
            for joke in jokes if joke.strip()
        }
        if not available:
            return None
        current = set(available)
        seen: set[str] = set()
        remaining: list[str] = []
        for identifier in self._remaining:
            if identifier in current and identifier not in seen:
                remaining.append(identifier)
                seen.add(identifier)
        self._remaining = remaining
        added = list(current - self._known - seen)
        self.random.shuffle(added)
        self._remaining.extend(added)
        self._known = current
        if not self._remaining:
            self._remaining = list(available)
            self.random.shuffle(self._remaining)
            if len(self._remaining) > 1 and self._remaining[-1] == self._previous:
                self._remaining[0], self._remaining[-1] = (
                    self._remaining[-1], self._remaining[0]
                )
        identifier = self._remaining.pop()
        self._previous = identifier
        self._save_history()
        return available[identifier]

    def _load_history(self) -> None:
        if self.history_path is None:
            return
        try:
            raw = json.loads(self.history_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        known = raw.get("known")
        remaining = raw.get("remaining")
        previous = raw.get("previous")
        if isinstance(known, list) and all(isinstance(item, str) for item in known):
            self._known = set(known)
        if isinstance(remaining, list) and all(isinstance(item, str) for item in remaining):
            self._remaining = remaining
        if isinstance(previous, str):
            self._previous = previous

    def _save_history(self) -> None:
        if self.history_path is None:
            return
        temporary: str | None = None
        try:
            directory = self.history_path.parent
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=".joke-history-", suffix=".json", dir=directory
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump({
                    "known": sorted(self._known),
                    "remaining": self._remaining,
                    "previous": self._previous,
                }, file)
                file.write("\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.history_path)
        except OSError as error:
            LOG.warning("Could not save joke history: %s", error)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
