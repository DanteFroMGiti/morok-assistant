from morok_assistant.ai.settings import AISettings, AISettingsStore


def test_settings_persist_model_and_key_in_owner_only_file(tmp_path) -> None:
    path = tmp_path / "morok-assistant" / "ai.json"
    store = AISettingsStore(path)
    original = AISettings(enabled=True, model="gpt-5.6-luna", api_key="test-key")

    store.save(original)

    loaded = store.load()
    assert loaded.enabled and loaded.model == original.model
    assert loaded.api_key == "test-key"
    assert loaded.api_keys == {"openai": "test-key"}
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700

    store.save(AISettings(enabled=False, model="gpt-5-mini", api_key=""))
    assert store.load().api_key == ""


def test_legacy_openai_key_survives_switch_to_claude(tmp_path) -> None:
    path = tmp_path / "ai.json"
    path.write_text(
        '{"enabled": true, "model": "gpt-5.6-luna", "api_key": "openai-key"}',
        encoding="utf-8",
    )
    store = AISettingsStore(path)
    migrated = store.load()
    assert migrated.api_keys == {"openai": "openai-key"}

    store.save(
        AISettings(
            enabled=True,
            provider="anthropic",
            model="claude-sonnet-5",
            api_key="claude-key",
            api_keys=migrated.api_keys,
        )
    )
    loaded = store.load()
    assert loaded.provider == "anthropic" and loaded.ready
    assert loaded.api_keys == {"openai": "openai-key", "anthropic": "claude-key"}


def test_local_provider_needs_no_api_key_but_compatible_needs_url() -> None:
    assert AISettings(enabled=True, provider="ollama", model="qwen2.5-coder:3b").ready
    assert not AISettings(enabled=True, provider="compatible", model="local-model").ready
    assert not AISettings(
        enabled=True, provider="compatible", model="local-model", api_key="key"
    ).ready
    assert AISettings(
        enabled=True,
        provider="compatible",
        model="local-model",
        endpoint_url="http://127.0.0.1:1234/v1/chat/completions",
    ).ready


def test_environment_key_is_used_when_no_key_is_saved(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")
    assert AISettings(enabled=True).ready
    assert AISettings(enabled=True).effective_api_key == "environment-key"
    assert AISettings(enabled=False).ready is False
    monkeypatch.delenv("OPENAI_API_KEY")
    assert not AISettings(enabled=True).ready


def test_invalid_settings_file_loads_disabled_defaults(tmp_path) -> None:
    path = tmp_path / "ai.json"
    path.write_text("broken json", encoding="utf-8")
    assert AISettingsStore(path).load() == AISettings()
