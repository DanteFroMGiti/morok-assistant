from pathlib import Path

from morok_assistant.system.local_actions import ApplicationIndex
from morok_assistant.system.startup_apps import (
    RunningApplications,
    StartupApplication,
    StartupApplicationsStore,
    _running_process_names,
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

    assert launch_startup_applications(
        store, index, RunningApplications(process_names=set(), window_classes=set())
    ) == ["First"]
    assert launched == ["First"]
    assert store.load()[1].enabled is False


def test_restart_skips_programs_that_are_already_running(tmp_path: Path) -> None:
    vivaldi = tmp_path / "vivaldi-stable.desktop"
    code = tmp_path / "code-oss.desktop"
    fresh = tmp_path / "fresh.desktop"
    vivaldi.write_text(
        "[Desktop Entry]\nType=Application\nExec=/usr/bin/vivaldi-stable %U\n"
        "StartupWMClass=vivaldi\n"
    )
    code.write_text("[Desktop Entry]\nType=Application\nExec=code-oss %F\n")
    fresh.write_text("[Desktop Entry]\nType=Application\nExec=fresh %U\n")
    store = StartupApplicationsStore(tmp_path / "startup-apps.json")
    store.save([
        StartupApplication("Vivaldi", str(vivaldi)),
        StartupApplication("Code - OSS", str(code)),
        StartupApplication("Fresh", str(fresh)),
    ])
    launched: list[str] = []
    index = ApplicationIndex((tmp_path,))
    index.launch = lambda application: launched.append(application.name) or True  # type: ignore[method-assign]
    running = RunningApplications(
        process_names={"code-oss"}, window_classes={"vivaldi"}
    )

    assert launch_startup_applications(store, index, running) == ["Fresh"]
    assert launched == ["Fresh"]
    assert "fresh" in running.names


def test_running_process_scan_uses_application_names(tmp_path: Path) -> None:
    first = tmp_path / "123"
    first.mkdir()
    (first / "comm").write_text("vivaldi-bin\n")
    (first / "cmdline").write_bytes(b"/opt/vivaldi/vivaldi-bin\0--type=renderer\0")
    second = tmp_path / "456"
    second.mkdir()
    (second / "comm").write_text("code-oss\n")
    (second / "cmdline").write_bytes(b"/usr/lib/electron/electron\0")

    assert {"vivaldi", "code-oss"}.issubset(_running_process_names(tmp_path))
