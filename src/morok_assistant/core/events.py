from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    topic: str
    payload: Any = None


EventHandler = Callable[[Event], None]


class EventBus:
    """Small synchronous bus; transport can later be replaced without touching UI."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: EventHandler) -> Callable[[], None]:
        self._handlers[topic].append(handler)

        def unsubscribe() -> None:
            handlers = self._handlers.get(topic, [])
            if handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    def publish(self, event: Event) -> None:
        for handler in tuple(self._handlers.get(event.topic, [])):
            handler(event)
