from morok_assistant.core.events import Event, EventBus


def test_subscribe_publish_and_unsubscribe() -> None:
    bus = EventBus()
    received: list[Event] = []
    unsubscribe = bus.subscribe("test", received.append)
    bus.publish(Event("test", 42))
    unsubscribe()
    bus.publish(Event("test", 100))
    assert received == [Event("test", 42)]
