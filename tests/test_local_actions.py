from pathlib import Path

from morok_assistant.system.app_context import classify_application
from morok_assistant.system.local_actions import ApplicationIndex


def test_application_index_finds_desktop_entries(tmp_path: Path) -> None:
    (tmp_path / "telegram.desktop").write_text(
        """[Desktop Entry]
Type=Application
Name=Telegram Desktop
Exec=telegram-desktop
""",
        encoding="utf-8",
    )
    (tmp_path / "hidden.desktop").write_text(
        """[Desktop Entry]
Type=Application
Name=Hidden Tool
NoDisplay=true
Exec=hidden
""",
        encoding="utf-8",
    )
    index = ApplicationIndex((tmp_path,))

    matches = index.search("телег")

    assert [application.name for application in matches] == ["Telegram Desktop"]
    assert not index.search("Hidden")


def test_classifies_application_reactions() -> None:
    assert classify_application("Game", "steam_app_570") == "game"
    assert classify_application("Spotify", "spotify") == "music"
    assert classify_application("project", "code-oss") == "code"
    assert classify_application("Report", "libreoffice-writer") == "document"
    assert classify_application("Mail", "vivaldi-stable") == "other"
