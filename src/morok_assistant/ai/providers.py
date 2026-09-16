from __future__ import annotations

PROVIDER_NAMES = {
    "openai": "OpenAI (GPT)",
    "anthropic": "Anthropic (Claude)",
    "gemini": "Google (Gemini)",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter (Llama и другие)",
    "ollama": "Ollama (локально)",
    "compatible": "Другой совместимый API",
}

MODEL_OPTIONS = {
    "openai": ("gpt-5-mini", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-6-astra"),
    "anthropic": ("claude-sonnet-5", "claude-haiku-4-5-20251001", "claude-opus-5"),
    "gemini": ("gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"),
    "deepseek": ("deepseek-v4-flash", "deepseek-v4-pro"),
    "openrouter": (
        "meta-llama/llama-4-maverick",
        "meta-llama/llama-4-scout",
        "anthropic/claude-sonnet-5",
    ),
    "ollama": (),
    "compatible": (),
}

DEFAULT_MODELS = {
    provider: models[0] if models else "" for provider, models in MODEL_OPTIONS.items()
}

KEY_ENVIRONMENTS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "compatible": "MOROK_COMPATIBLE_API_KEY",
}

KEY_URLS = {
    "openai": "https://platform.openai.com/api-keys",
    "anthropic": "https://platform.claude.com/settings/keys",
    "gemini": "https://aistudio.google.com/api-keys",
    "deepseek": "https://platform.deepseek.com/api_keys",
    "openrouter": "https://openrouter.ai/settings/keys",
}

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"


def provider_name(provider: str) -> str:
    return PROVIDER_NAMES.get(provider, provider)
