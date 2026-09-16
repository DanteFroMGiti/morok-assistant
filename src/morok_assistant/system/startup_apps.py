from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from morok_assistant.system.local_actions import ApplicationIndex, DesktopApplication


@dataclass(frozen=True, slots=True)
class StartupApplication:
    name: str
    desktop_file: str
    enabled: bool = True


def default_startup_apps_path() -> Path:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "morok-assistant" / "startup-apps.json"


class StartupApplicationsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_startup_apps_path()

    def load(self) -> list[StartupApplication]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        applications: list[StartupApplication] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            desktop_file = str(item.get("desktop_file") or "").strip()
            if not name or not desktop_file or desktop_file in seen:
                continue
            seen.add(desktop_file)
            applications.append(
                StartupApplication(name, desktop_file, item.get("enabled") is not False)
            )
        return applications

    def save(self, applications: list[StartupApplication]) -> None:
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".startup-apps-", suffix=".json", dir=directory
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump([asdict(item) for item in applications], file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def launch_startup_applications(
    store: StartupApplicationsStore,
    index: ApplicationIndex | None = None,
) -> list[str]:
    application_index = index or ApplicationIndex()
    launched: list[str] = []
    for item in store.load():
        if not item.enabled:
            continue
        application = DesktopApplication(item.name, Path(item.desktop_file))
        if application.desktop_file.is_file() and application_index.launch(application):
            launched.append(item.name)
    return launched
