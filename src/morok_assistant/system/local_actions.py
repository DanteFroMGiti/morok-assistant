from __future__ import annotations

import configparser
import os
import shutil
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

CYRILLIC_TO_LATIN = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "i",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


@dataclass(frozen=True, slots=True)
class DesktopApplication:
    name: str
    desktop_file: Path


def application_directories() -> tuple[Path, ...]:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    return (data_home / "applications", *(Path(item) / "applications" for item in data_dirs))


class ApplicationIndex:
    def __init__(self, directories: tuple[Path, ...] | None = None) -> None:
        self.directories = directories or application_directories()
        self._applications: list[DesktopApplication] | None = None

    def applications(self) -> list[DesktopApplication]:
        if self._applications is None:
            self._applications = self._load()
        return self._applications

    def _load(self) -> list[DesktopApplication]:
        found: dict[str, DesktopApplication] = {}
        for directory in self.directories:
            if not directory.is_dir():
                continue
            for path in directory.glob("*.desktop"):
                parser = configparser.ConfigParser(interpolation=None, strict=False)
                try:
                    parser.read(path, encoding="utf-8")
                    section = parser["Desktop Entry"]
                except (OSError, UnicodeError, KeyError, configparser.Error):
                    continue
                if section.get("Type", "Application") != "Application":
                    continue
                try:
                    hidden = section.getboolean("NoDisplay", fallback=False)
                except ValueError:
                    hidden = False
                if hidden:
                    continue
                name = section.get("Name[ru]") or section.get("Name")
                if not name:
                    continue
                found.setdefault(name.casefold(), DesktopApplication(name, path))
        return sorted(found.values(), key=lambda application: application.name.casefold())

    def search(self, query: str, limit: int = 20) -> list[DesktopApplication]:
        query = query.strip().casefold()
        if not query:
            return self.applications()[:limit]
        queries = {query, query.translate(CYRILLIC_TO_LATIN)}

        def score(application: DesktopApplication) -> tuple[int, float]:
            name = application.name.casefold()
            contains = 1 if any(item in name for item in queries) else 0
            similarity = max(SequenceMatcher(None, item, name).ratio() for item in queries)
            return contains, similarity

        matches = [item for item in self.applications() if score(item) > (0, 0.25)]
        return sorted(matches, key=score, reverse=True)[:limit]

    def launch(self, application: DesktopApplication) -> bool:
        gio = shutil.which("gio")
        if gio is None:
            return False
        try:
            subprocess.Popen(
                [gio, "launch", str(application.desktop_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return False
        return True
