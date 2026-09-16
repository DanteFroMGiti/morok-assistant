from dataclasses import dataclass, field

from morok_assistant.core.events import EventBus
from morok_assistant.plugins.contracts import Permission
from morok_assistant.plugins.manager import PluginManager


@dataclass
class FakePlugin:
    plugin_id: str
    permissions: frozenset[Permission]
    calls: list[str] = field(default_factory=list)

    def start(self, _events: EventBus) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")


def test_starts_only_plugins_with_granted_permissions() -> None:
    allowed = FakePlugin("allowed", frozenset({Permission.SYSTEM_READ}))
    blocked = FakePlugin("blocked", frozenset({Permission.POWER_CONTROL}))
    manager = PluginManager(EventBus(), granted={Permission.SYSTEM_READ})
    manager.register(allowed)
    manager.register(blocked)
    manager.start_all()
    manager.stop_all()
    assert allowed.calls == ["start", "stop"]
    assert blocked.calls == []
