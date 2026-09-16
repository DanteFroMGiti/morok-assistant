from __future__ import annotations

from morok_assistant.core.events import EventBus
from morok_assistant.plugins.contracts import AssistantPlugin, Permission


class PluginManager:
    def __init__(self, events: EventBus, granted: set[Permission] | None = None) -> None:
        self.events = events
        self.granted = granted or set()
        self._plugins: dict[str, AssistantPlugin] = {}
        self._started: list[AssistantPlugin] = []

    def register(self, plugin: AssistantPlugin) -> None:
        if plugin.plugin_id in self._plugins:
            raise ValueError(f"Plugin already registered: {plugin.plugin_id}")
        self._plugins[plugin.plugin_id] = plugin

    def start_all(self) -> None:
        for plugin in self._plugins.values():
            missing = plugin.permissions - self.granted
            if missing:
                continue
            plugin.start(self.events)
            self._started.append(plugin)

    def stop_all(self) -> None:
        for plugin in reversed(self._started):
            plugin.stop()
        self._started.clear()
