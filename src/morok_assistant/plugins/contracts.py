from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from morok_assistant.core.events import EventBus


class Permission(StrEnum):
    SYSTEM_READ = "system.read"
    PROCESS_START = "process.start"
    AUDIO_CONTROL = "audio.control"
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    POWER_CONTROL = "power.control"


class AssistantPlugin(Protocol):
    plugin_id: str
    permissions: frozenset[Permission]

    def start(self, events: EventBus) -> None: ...

    def stop(self) -> None: ...
