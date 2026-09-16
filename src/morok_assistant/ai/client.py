from __future__ import annotations

import json
from urllib.parse import quote

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from morok_assistant.ai.providers import OLLAMA_URL, provider_name
from morok_assistant.ai.settings import AISettings

RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
CHAT_URLS = {
    "deepseek": "https://api.deepseek.com/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}
MOROK_INSTRUCTIONS = (
    "Ты Морок, настольный помощник пользователя. Отвечай ясно, дружелюбно и по делу "
    "на языке пользователя. Обычно хватит одного-двух коротких абзацев. "
    "Ты общаешься текстом; не утверждай, что выполнил действие на компьютере, если не делал его."
)


def response_payload(model: str, message: str, previous_response_id: str | None) -> dict:
    payload: dict = {
        "model": model,
        "input": message,
        "instructions": MOROK_INSTRUCTIONS,
        "store": True,
        "max_output_tokens": 1200,
    }
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    return payload


def parse_response(data: bytes) -> tuple[str, str]:
    raw = json.loads(data)
    if not isinstance(raw, dict):
        raise TypeError("Некорректный ответ сервера")
    if raw.get("status") not in (None, "completed"):
        raise ValueError("Модель не завершила ответ")
    parts: list[str] = []
    for item in raw.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
    result = "\n".join(parts).strip()
    response_id = raw.get("id")
    if not result or not isinstance(response_id, str) or not response_id:
        raise ValueError("Модель не вернула текстовый ответ")
    return result, response_id


def api_error(data: bytes, status: int | None, fallback: str) -> str:
    try:
        raw = json.loads(data)
    except json.JSONDecodeError:
        raw = None
    error = raw.get("error") if isinstance(raw, dict) else None
    detail = error if isinstance(error, dict) else {}
    error_code = detail.get("code")
    error_type = detail.get("type")

    if status == 401:
        return "Ключ API не принят OpenAI (401). Проверьте его в настройках."
    if status == 429:
        if error_code == "credit_balance_exhausted":
            return (
                "Баланс OpenAI API исчерпан (429). Откройте Настройки → Баланс API "
                "и пополните кредиты."
            )
        if error_code == "organization_spend_limit_exceeded":
            return (
                "Лимит расходов организации OpenAI API достигнут (429). Проверьте лимиты аккаунта."
            )
        if error_code == "project_spend_limit_exceeded":
            return "Лимит расходов проекта OpenAI API достигнут (429). Проверьте лимиты проекта."
        if error_code == "organization_usage_limit_exceeded":
            return "Лимит использования организации OpenAI API достигнут (429). Проверьте Limits."
        if error_code == "insufficient_quota" or error_type == "insufficient_quota":
            return "Квота OpenAI API недоступна (429). Проверьте баланс и лимиты аккаунта."
        return "Слишком много запросов к OpenAI API (429). Подождите и повторите."
    message = detail.get("message")
    if isinstance(message, str) and message:
        return message
    return fallback


def chat_messages(history: list[tuple[str, str]], message: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": MOROK_INSTRUCTIONS},
        *({"role": role, "content": text} for role, text in history),
        {"role": "user", "content": message},
    ]


def provider_request(
    settings: AISettings,
    message: str,
    previous_response_id: str | None,
    history: list[tuple[str, str]],
) -> tuple[str, dict[str, str], dict]:
    key = settings.effective_api_key
    if settings.provider == "openai":
        return (
            RESPONSES_URL,
            {"Authorization": f"Bearer {key}"},
            response_payload(settings.model, message, previous_response_id),
        )
    if settings.provider == "anthropic":
        return (
            ANTHROPIC_URL,
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {
                "model": settings.model,
                "max_tokens": 1200,
                "system": MOROK_INSTRUCTIONS,
                "messages": chat_messages(history, message)[1:],
            },
        )
    if settings.provider == "gemini":
        contents = [
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": text}],
            }
            for role, text in [*history, ("user", message)]
        ]
        return (
            f"{GEMINI_BASE_URL}/{quote(settings.model, safe='')}:generateContent",
            {"x-goog-api-key": key},
            {
                "systemInstruction": {"parts": [{"text": MOROK_INSTRUCTIONS}]},
                "contents": contents,
                "generationConfig": {"maxOutputTokens": 1200},
            },
        )
    messages = chat_messages(history, message)
    if settings.provider == "ollama":
        return OLLAMA_URL, {}, {"model": settings.model, "messages": messages, "stream": False}
    if settings.provider in CHAT_URLS or settings.provider == "compatible":
        url = (
            settings.endpoint_url.strip()
            if settings.provider == "compatible"
            else CHAT_URLS[settings.provider]
        )
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        return url, headers, {"model": settings.model, "messages": messages, "max_tokens": 1200}
    raise ValueError("Неизвестный сервис ИИ")


def parse_provider_response(provider: str, data: bytes) -> tuple[str, str]:
    if provider == "openai":
        return parse_response(data)
    raw = json.loads(data)
    if not isinstance(raw, dict):
        raise TypeError("Некорректный ответ сервера")
    text = ""
    if provider == "anthropic":
        text = "\n".join(
            item["text"]
            for item in raw.get("content", [])
            if isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        )
    elif provider == "gemini":
        candidates = raw.get("candidates") or []
        if candidates and isinstance(candidates[0], dict):
            content = candidates[0].get("content") or {}
            parts = content.get("parts") if isinstance(content, dict) else []
            text = "\n".join(
                part["text"]
                for part in parts or []
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
    elif provider == "ollama":
        message = raw.get("message") or {}
        text = message.get("content", "") if isinstance(message, dict) else ""
    else:
        choices = raw.get("choices") or []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            text = message.get("content", "") if isinstance(message, dict) else ""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Модель не вернула текстовый ответ")
    return text.strip(), ""


def provider_error(provider: str, data: bytes, status: int | None, fallback: str) -> str:
    if provider == "openai":
        return api_error(data, status, fallback)
    if provider == "ollama" and status is None:
        return "Ollama не отвечает. Запустите локальный сервер командой ollama serve."
    if status == 401:
        return f"Ключ API сервиса {provider_name(provider)} не принят (401)."
    if status == 404:
        return f"Модель или адрес сервиса {provider_name(provider)} не найдены (404)."
    try:
        raw = json.loads(data)
    except json.JSONDecodeError:
        raw = None
    error = raw.get("error") if isinstance(raw, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    if isinstance(error, str) and error:
        return error
    if status == 429:
        return (
            f"Сервис {provider_name(provider)} ограничил запросы (429). Проверьте квоту и баланс."
        )
    return fallback


class AIConnector(QObject):
    answered = Signal(str, str)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._cancelled = False
        self._provider = "openai"

    @property
    def busy(self) -> bool:
        return self._reply is not None

    def send(
        self,
        settings: AISettings,
        message: str,
        previous_response_id: str | None,
        history: list[tuple[str, str]] | None = None,
    ) -> None:
        if self.busy:
            raise RuntimeError("Морок ещё отвечает")
        if not settings.ready:
            raise ValueError("Сначала включите ИИ и заполните настройки выбранного сервиса")
        message = message.strip()
        if not message:
            raise ValueError("Напишите сообщение")
        url, headers, payload = provider_request(
            settings, message, previous_response_id, history or []
        )
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        for name, value in headers.items():
            request.setRawHeader(name.encode(), value.encode())
        request.setTransferTimeout(120_000 if settings.provider == "ollama" else 90_000)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._cancelled = False
        self._provider = settings.provider
        self._reply = self.manager.post(request, body)
        self._reply.finished.connect(self._finish)

    def _finish(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        data = bytes(reply.readAll())
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        code = int(status) if status is not None else None
        if not self._cancelled:
            if reply.error() != QNetworkReply.NetworkError.NoError or (code and code >= 400):
                self.failed.emit(provider_error(self._provider, data, code, reply.errorString()))
            else:
                try:
                    self.answered.emit(*parse_provider_response(self._provider, data))
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    self.failed.emit(str(error))
        reply.deleteLater()

    def cancel(self) -> None:
        if self._reply is not None:
            self._cancelled = True
            self._reply.abort()
