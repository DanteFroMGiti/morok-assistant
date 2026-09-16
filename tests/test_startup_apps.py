from pathlib import Path

from morok_assistant.system.local_actions import ApplicationIndex
from morok_assistant.system.startup_apps import (
    StartupApplication,
    StartupApplicationsStore,
    launch_startup_applications,
)


def test_startup_application_choices_persist_and_only_enabled_apps_launch(tmp_path: Path) -> None:
    first = tmp_path / "first.desktop"
    second = tmp_path / "second.desktop"
    first.write_text("[Desktop Entry]\nType=Application\nName=First\nExec=first\n")
    second.write_text("[Desktop Entry]\nType=Application\nName=Second\nExec=second\n")
    store = StartupApplicationsStore(tmp_path / "startup-apps.json")
    store.save(
        [
            StartupApplication("First", str(first)),
            StartupApplication("Second", str(second), enabled=False),
        ]
    )
    launched: list[str] = []
    index = ApplicationIndex((tmp_path,))
    index.launch = lambda application: launched.append(application.name) or True  # type: ignore[method-assign]

    assert launch_startup_applications(store, index) == ["First"]
    assert launched == ["First"]
    assert store.load()[1].enabled is False
