from time import time

from PySide6.QtCore import QPropertyAnimation
from PySide6.QtWidgets import QApplication

from morok_assistant.ai.settings import AISettingsStore
from morok_assistant.application.bootstrap import bundled_characters_path
from morok_assistant.characters.repository import CharacterRepository
from morok_assistant.core.events import EventBus
from morok_assistant.productivity.curiosity import QUESTIONS, CuriosityStore
from morok_assistant.productivity.tasks import TaskManager, TaskStore
from morok_assistant.system.behavior_settings import BehaviorSettings, BehaviorSettingsStore
from morok_assistant.ui.character_window import CharacterWindow


def test_task_recommendation_tracks_deadline_progress_and_snooze(tmp_path) -> None:
    manager = TaskManager(TaskStore(tmp_path / "tasks.json"))
    later = manager.add("Долгая важная", priority=3, estimate_minutes=120)
    soon = manager.add("Скоро срок", priority=1, due_at=time() + 1800)
    assert manager.recommend().task.task_id == soon.task_id
    manager.start(later.task_id)
    assert manager.recommend().task.task_id == later.task_id
    assert manager.recommend(now=time() + 3600).task.task_id == soon.task_id
    manager.start("missing")
    assert manager.recommend().task.task_id == later.task_id
    manager.complete(later.task_id)
    assert manager.recommend().task.task_id == soon.task_id
    manager.snooze(soon.task_id)
    assert manager.recommend() is None
    loaded = TaskManager(TaskStore(tmp_path / "tasks.json"))
    assert {task.status for task in loaded.tasks} == {"todo", "done"}


def test_curiosity_remembers_and_forgets_locally(tmp_path) -> None:
    path = tmp_path / "memory.json"
    store = CuriosityStore(path)
    assert store.next_question() == QUESTIONS[0]
    stored = store.remember(QUESTIONS[0], "Писать книгу")
    assert store.next_question() == QUESTIONS[1]
    assert CuriosityStore(path).load()[0].answer == "Писать книгу"
    assert store.recollection(stored.answered_at + 5 * 3600) == stored
    store.mark_reminded(QUESTIONS[0], stored.answered_at + 5 * 3600)
    assert store.recollection(stored.answered_at + 6 * 3600) is None
    store.forget(QUESTIONS[0])
    assert store.next_question() == QUESTIONS[0]
    assert path.stat().st_mode & 0o777 == 0o600


def test_quiet_mode_sits_and_disables_spontaneous_peeking(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    ai_store = AISettingsStore(tmp_path / "ai.json")
    behavior = BehaviorSettingsStore(tmp_path / "behavior.json")
    behavior.save(BehaviorSettings(personality_mode="quiet"))
    window = CharacterWindow(manifest, EventBus(), ai_settings_store=ai_store,
                             behavior_store=behavior)
    window.timer.stop()
    window.personality_timer.stop()
    window._apply_personality_mode()
    assert window._quiet_placed
    assert not window.peek_controller.auto_peek_enabled
    assert window.player.state in {"sitting", "run_left", "run_right"}
    assert window.personality_move.state() in {
        QPropertyAnimation.State.Stopped, QPropertyAnimation.State.Running
    }
    window.set_personality_mode("curious")
    assert behavior.load().personality_mode == "curious"
    assert window.peek_controller.auto_peek_enabled
    window.close()
    assert app is not None


def test_task_dialog_starts_recommended_focus_session(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    window = CharacterWindow(manifest, EventBus(), ai_settings_store=AISettingsStore(tmp_path / "ai.json"))
    window.timer.stop()
    window.personality_timer.stop()
    window.open_tasks()
    dialog = window.tasks_dialog
    assert dialog is not None
    dialog.title.setText("Написать главу")
    dialog.estimate.setValue(30)
    dialog._add()
    assert "Написать главу" in dialog.suggestion.text()
    dialog.items.setCurrentRow(0)
    dialog._start(with_focus=True)
    assert window.focus_controller.phase == "focus"
    assert window.focus_controller.work_minutes == 30
    dialog._complete()
    assert window.task_manager.recommend() is None
    window.close()
    assert app is not None


def test_curious_mode_asks_and_stores_answer(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    manifest = CharacterRepository(bundled_characters_path()).get("morok")
    ai_store = AISettingsStore(tmp_path / "ai.json")
    behavior = BehaviorSettingsStore(tmp_path / "behavior.json")
    behavior.save(BehaviorSettings(personality_mode="curious"))
    window = CharacterWindow(manifest, EventBus(), ai_settings_store=ai_store,
                             behavior_store=behavior)
    window.timer.stop()
    window.personality_timer.stop()
    window._next_curiosity = 0
    window._personality_tick()
    assert window._pending_question == QUESTIONS[0]
    assert window._bubble_action == "curiosity"
    window.open_curiosity()
    dialog = window.curiosity_dialog
    assert dialog is not None
    dialog.answer.setText("Завершить проект")
    dialog._remember()
    assert window._pending_question is None
    assert window.curiosity_store.load()[0].answer == "Завершить проект"
    window.close()
    assert app is not None
