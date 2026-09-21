from __future__ import annotations

import configparser
import json
import os
import re
import shlex
import shutil
import subprocess
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


GENERIC_EXECUTABLES = {"bash", "env", "electron", "flatpak", "gio", "java", "node",
                       "python", "python2", "python3", "run", "sh", "snap", "wine"}


def _application_name(value: str) -> str:
    name = Path(value).name.casefold().removesuffix(".desktop")
    if name.startswith(("org.", "com.", "io.")):
        name = name.rsplit(".", 1)[-1]
    for suffix in ("-stable", "-bin", ".bin", ".py", ".mjs"):
        name = name.removesuffix(suffix)
    return name


def _desktop_names(path: Path) -> set[str]:
    names = {_application_name(path.stem)}
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read(path, encoding="utf-8")
        entry = parser["Desktop Entry"]
    except (OSError, UnicodeError, KeyError, configparser.Error):
        return {name for name in names if name and name not in GENERIC_EXECUTABLES}
    wm_class = entry.get("StartupWMClass", "").strip()
    if wm_class:
        names.add(_application_name(wm_class))
    try:
        command = shlex.split(entry.get("Exec", ""))
    except ValueError:
        command = []
    for token in command:
        name = _application_name(token)
        if (name in GENERIC_EXECUTABLES or "=" in token
                or token.startswith(("%", "-"))):
            continue
        names.add(name)
        break
    return {name for name in names if name and name not in GENERIC_EXECUTABLES}


def _running_process_names(proc_root: Path = Path("/proc")) -> set[str]:
    names: set[str] = set()
    try:
        processes = list(proc_root.iterdir())
    except OSError:
        return names
    for process in processes:
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            names.add(_application_name((process / "comm").read_text().strip()))
            with (process / "cmdline").open("rb") as command_line:
                executable = command_line.read(512).split(b"\0", 1)[0]
            if executable:
                names.add(_application_name(os.fsdecode(executable)))
        except (OSError, UnicodeError):
            continue
    return names - GENERIC_EXECUTABLES


def _open_window_classes() -> set[str]:
    xprop = shutil.which("xprop")
    if xprop is None or not os.environ.get("DISPLAY"):
        return set()
    try:
        result = subprocess.run(
            [xprop, "-root", "_NET_CLIENT_LIST_STACKING"],
            capture_output=True, text=True, timeout=2, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if result.returncode:
        return set()
    classes: set[str] = set()
    for identifier in re.findall(r"0x[0-9a-fA-F]+", result.stdout):
        try:
            window = subprocess.run(
                [xprop, "-id", identifier, "WM_CLASS"],
                capture_output=True, text=True, timeout=1, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if window.returncode == 0:
            classes.update(
                _application_name(name)
                for name in re.findall(r'"([^"]+)"', window.stdout)
            )
    return classes


class RunningApplications:
    def __init__(
        self,
        *,
        process_names: set[str] | None = None,
        window_classes: set[str] | None = None,
    ) -> None:
        self.names = process_names if process_names is not None else _running_process_names()
        self.names = set(self.names)
        self.names.update(
            window_classes if window_classes is not None else _open_window_classes()
        )

    def is_running(self, application: DesktopApplication) -> bool:
        return bool(_desktop_names(application.desktop_file) & self.names)

    def mark_launched(self, application: DesktopApplication) -> None:
        self.names.update(_desktop_names(application.desktop_file))


def launch_startup_applications(
    store: StartupApplicationsStore,
    index: ApplicationIndex | None = None,
    running: RunningApplications | None = None,
) -> list[str]:
    application_index = index or ApplicationIndex()
    running_applications = running or RunningApplications()
    launched: list[str] = []
    for item in store.load():
        if not item.enabled:
            continue
        application = DesktopApplication(item.name, Path(item.desktop_file))
        if not application.desktop_file.is_file() or running_applications.is_running(application):
            continue
        if application_index.launch(application):
            launched.append(item.name)
            running_applications.mark_launched(application)
    return launched
