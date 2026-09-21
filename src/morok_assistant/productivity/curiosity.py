from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time

QUESTIONS = (
    "Что тебе сейчас больше всего хочется успеть?",
    "Какой маленький шаг приблизит тебя к важной цели?",
    "Что помогает тебе восстановить силы после трудного дня?",
    "Какое занятие в последнее время приносит тебе радость?",
    "О чём тебе стоит напомнить позже?",
)


@dataclass(frozen=True, slots=True)
class Memory:
    question: str
    answer: str
    answered_at: float
    reminded_at: float = 0.0


def default_curiosity_path() -> Path:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "morok-assistant" / "memory.json"


class CuriosityStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_curiosity_path()

    def load(self) -> list[Memory]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        result = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                memory = Memory(
                    question=str(item["question"]).strip(),
                    answer=str(item["answer"]).strip(),
                    answered_at=float(item["answered_at"]),
                    reminded_at=float(item.get("reminded_at", 0)),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if memory.question and memory.answer:
                result.append(memory)
        return result

    def remember(self, question: str, answer: str) -> Memory:
        answer = answer.strip()
        if not answer:
            raise ValueError("Напишите ответ или выберите «Позже»")
        memory = Memory(question, answer[:1000], time())
        memories = [item for item in self.load() if item.question != question]
        memories.append(memory)
        self.save(memories)
        return memory

    def next_question(self) -> str | None:
        answered = {memory.question for memory in self.load()}
        return next((question for question in QUESTIONS if question not in answered), None)

    def recollection(self, now: float | None = None) -> Memory | None:
        now = time() if now is None else now
        eligible = [
            memory for memory in self.load()
            if now - memory.answered_at >= 4 * 3600
            and now - memory.reminded_at >= 24 * 3600
        ]
        return min(eligible, key=lambda item: item.reminded_at) if eligible else None

    def mark_reminded(self, question: str, now: float | None = None) -> None:
        now = time() if now is None else now
        self.save([
            Memory(item.question, item.answer, item.answered_at, now)
            if item.question == question else item
            for item in self.load()
        ])

    def forget(self, question: str) -> None:
        self.save([item for item in self.load() if item.question != question])

    def save(self, memories: list[Memory]) -> None:
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".memory-", suffix=".json", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump([asdict(item) for item in memories], file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
