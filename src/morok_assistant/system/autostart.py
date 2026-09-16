from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def project_root() -> Path | None:
    root = Path(__file__).resolve().parents[3]
    return root if (root / "pyproject.toml").is_file() else None


def launcher_command() -> tuple[str, Path | None, Path | None]:
    root = project_root()
    if root is not None:
        python = root / ".venv" / "bin" / "python"
        executable = python if python.is_file() else Path(sys.executable)
        return f'"{executable}" -m morok_assistant', root, root / "morok-icon.png"
    bundled_icon = Path(__file__).resolve().parents[1] / "assets" / "morok-icon.png"
    icon = bundled_icon if bundled_icon.is_file() else None
    return f'"{Path(sys.executable)}" -m morok_assistant', None, icon


def desktop_entry() -> str:
    command, working_directory, icon = launcher_command()
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=Морок",
        "Comment=Настольный помощник Морок",
        f"Exec={command}",
        "Terminal=false",
        "StartupNotify=false",
        "Categories=Utility;",
        "X-GNOME-Autostart-enabled=true",
    ]
    if working_directory is not None:
        lines.append(f"Path={working_directory}")
    if icon is not None and icon.is_file():
        lines.append(f"Icon={icon}")
    return "\n".join(lines) + "\n"


def default_autostart_path() -> Path:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "autostart" / "morok-assistant.desktop"


class AutostartManager:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_autostart_path()

    @property
    def enabled(self) -> bool:
        return self.path.is_file()

    def set_enabled(self, enabled: bool) -> None:
        if not enabled:
            self.path.unlink(missing_ok=True)
            return
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".morok-", suffix=".desktop", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(desktop_entry())
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o700)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
