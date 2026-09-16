from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from morok_assistant.ai.providers import DEFAULT_MODELS, KEY_ENVIRONMENTS, PROVIDER_NAMES


@dataclass(frozen=True, slots=True)
class AISettings:
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-5-mini"
    api_key: str = ""
    api_keys: dict[str, str] = field(default_factory=dict)
    models: dict[str, str] = field(default_factory=dict)
    endpoint_url: str = ""

    @property
    def effective_api_key(self) -> str:
        return (
            self.api_key.strip()
            or self.api_keys.get(self.provider, "").strip()
            or os.environ.get(KEY_ENVIRONMENTS.get(self.provider, ""), "").strip()
        )

    @property
    def ready(self) -> bool:
        return (
            self.enabled
            and self.provider in PROVIDER_NAMES
            and bool(self.model.strip())
            and (
                self.provider == "ollama"
                or (self.provider == "compatible" and bool(self.endpoint_url.strip()))
                or (self.provider not in {"ollama", "compatible"} and bool(self.effective_api_key))
            )
        )


def default_settings_path() -> Path:
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_root / "morok-assistant" / "ai.json"


class AISettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_settings_path()

    def load(self) -> AISettings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return AISettings()
        if not isinstance(raw, dict):
            return AISettings()
        provider = str(raw.get("provider") or "openai")
        if provider not in PROVIDER_NAMES:
            provider = "openai"
        raw_keys = raw.get("api_keys")
        keys = (
            {str(name): str(key) for name, key in raw_keys.items() if name in PROVIDER_NAMES}
            if isinstance(raw_keys, dict)
            else {}
        )
        legacy_key = raw.get("api_key")
        if isinstance(legacy_key, str) and legacy_key and "openai" not in keys:
            keys["openai"] = legacy_key
        raw_models = raw.get("models")
        models = (
            {str(name): str(model) for name, model in raw_models.items() if name in PROVIDER_NAMES}
            if isinstance(raw_models, dict)
            else {}
        )
        model = str(raw.get("model") or models.get(provider) or DEFAULT_MODELS[provider])
        models[provider] = model
        return AISettings(
            enabled=raw.get("enabled") is True,
            provider=provider,
            model=model,
            api_key=keys.get(provider, ""),
            api_keys=keys,
            models=models,
            endpoint_url=str(raw.get("endpoint_url") or ""),
        )

    def save(self, settings: AISettings) -> None:
        model = settings.model.strip()
        if not model:
            raise ValueError("Укажите модель ИИ")
        if settings.provider not in PROVIDER_NAMES:
            raise ValueError("Неизвестный сервис ИИ")
        if settings.provider == "compatible":
            endpoint = urlsplit(settings.endpoint_url.strip())
            if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
                raise ValueError("Укажите полный HTTP-адрес совместимого API")
        keys = {name: key.strip() for name, key in settings.api_keys.items() if key.strip()}
        if settings.api_key.strip():
            keys[settings.provider] = settings.api_key.strip()
        models = dict(settings.models)
        models[settings.provider] = model
        raw = {
            "enabled": settings.enabled,
            "provider": settings.provider,
            "model": model,
            "api_keys": keys,
            "models": models,
            "endpoint_url": settings.endpoint_url.strip(),
        }
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".ai-", suffix=".json", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(raw, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
