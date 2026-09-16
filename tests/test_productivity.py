from pathlib import Path

from PySide6.QtWidgets import QApplication

from morok_assistant.productivity.focus import FocusController
from morok_assistant.productivity.reminders import ReminderManager, ReminderStore


def test_timer_persists_and_fires_after_restart(monkeypatch, tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    clock = [1_000.0]
    monkeypatch.setattr("morok_assistant.productivity.reminders.time", lambda: clock[0])
    store = ReminderStore(tmp_path / "reminders.json")
    manager = ReminderManager(store)
    manager.timer.stop()

    reminder = manager.add_timer("Проверить чай", 60)
    assert store.load() == [reminder]

    restarted = ReminderManager(store)
    restarted.timer.stop()
    notices: list[str] = []
    restarted.due.connect(notices.append)
    clock[0] += 61
    restarted._poll()

    assert notices == ["Проверить чай"]
    assert store.load() == []
    assert app is not None


def test_focus_session_switches_to_break_and_finishes(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    clock = [0.0]
    monkeypatch.setattr("morok_assistant.productivity.focus.monotonic", lambda: clock[0])
    focus = FocusController()
    notices: list[str] = []
    focus.notice.connect(notices.append)

    focus.start(1, 2)
    focus.timer.stop()
    clock[0] = 61
    focus._tick()
    assert focus.phase == "break"

    clock[0] = 182
    focus._tick()
    assert focus.phase == "idle"
    assert any("отдохнуть" in notice for notice in notices)
    assert any("Перерыв завершён" in notice for notice in notices)
    assert app is not None
