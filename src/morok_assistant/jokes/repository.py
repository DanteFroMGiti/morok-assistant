from __future__ import annotations

from pathlib import Path
from random import Random


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
    def __init__(self, random: Random | None = None) -> None:
        self.random = random or Random()
        self._previous: str | None = None

    def choose(self, jokes: list[str]) -> str | None:
        if not jokes:
            return None
        choices = [joke for joke in jokes if joke != self._previous] or jokes
        chosen = self.random.choice(choices)
        self._previous = chosen
        return chosen
