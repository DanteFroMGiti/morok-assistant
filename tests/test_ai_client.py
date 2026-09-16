import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from morok_assistant.ai.client import (
    AIConnector,
    api_error,
    parse_provider_response,
    parse_response,
    provider_request,
    response_payload,
)
from morok_assistant.ai.settings import AISettings


def test_response_parser_skips_reasoning_and_collects_all_text() -> None:
    raw = {
        "id": "resp_1",
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Первая часть."},
                    {"type": "output_text", "text": "Вторая часть."},
                ],
            },
        ],
    }
    assert parse_response(json.dumps(raw).encode()) == ("Первая часть.\nВторая часть.", "resp_1")
    assert response_payload("gpt-5-mini", "Привет", "resp_1")["previous_response_id"] == "resp_1"


def test_429_error_distinguishes_exhausted_credits_from_rate_limit() -> None:
    credits = json.dumps(
        {"error": {"type": "insufficient_quota", "code": "credit_balance_exhausted"}}
    ).encode()
    rate = json.dumps(
        {"error": {"type": "rate_limit_error", "code": "rate_limit_exceeded"}}
    ).encode()
    assert "пополните кредиты" in api_error(credits, 429, "fallback")
    assert "Подождите и повторите" in api_error(rate, 429, "fallback")


def test_provider_requests_keep_history_and_use_each_api_format() -> None:
    history = [("user", "Привет"), ("assistant", "Здравствуйте")]
    claude = AISettings(enabled=True, provider="anthropic", model="claude-sonnet-5", api_key="key")
    url, headers, body = provider_request(claude, "Как дела?", None, history)
    assert url.endswith("/v1/messages")
    assert headers["x-api-key"] == "key"
    assert body["messages"][-1] == {"role": "user", "content": "Как дела?"}
    assert body["messages"][1] == {"role": "assistant", "content": "Здравствуйте"}

    gemini = AISettings(enabled=True, provider="gemini", model="gemini-3.8-flash", api_key="key")
    url, headers, body = provider_request(gemini, "Как дела?", None, history)
    assert url.endswith("/gemini-3.8-flash:generateContent")
    assert headers["x-goog-api-key"] == "key"
    assert [item["role"] for item in body["contents"]] == ["user", "model", "user"]

    llama = AISettings(
        enabled=True,
        provider="openrouter",
        model="meta-llama/llama-4-maverick",
        api_key="key",
    )
    url, headers, body = provider_request(llama, "Как дела?", None, history)
    assert url.endswith("/chat/completions")
    assert headers["Authorization"] == "Bearer key"
    assert [item["role"] for item in body["messages"]] == ["system", "user", "assistant", "user"]

    local = AISettings(enabled=True, provider="ollama", model="qwen2.5-coder:3b")
    url, headers, body = provider_request(local, "Как дела?", None, history)
    assert url == "http://127.0.0.1:11434/api/chat"
    assert headers == {} and body["stream"] is False


def test_provider_responses_extract_text() -> None:
    examples = {
        "anthropic": {"content": [{"type": "text", "text": "Ответ Claude"}]},
        "gemini": {"candidates": [{"content": {"parts": [{"text": "Ответ Gemini"}]}}]},
        "openrouter": {"choices": [{"message": {"content": "Ответ Llama"}}]},
        "ollama": {"message": {"content": "Локальный ответ"}},
    }
    for provider, response in examples.items():
        answer, response_id = parse_provider_response(provider, json.dumps(response).encode())
        assert answer.startswith("Ответ") or answer == "Локальный ответ"
        assert response_id == ""


def test_connector_sends_model_key_and_previous_response_id(monkeypatch) -> None:
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append(
                {
                    "path": self.path,
                    "authorization": self.headers["Authorization"],
                    "body": json.loads(body),
                }
            )
            reply = {
                "id": f"resp_{len(received)}",
                "status": "completed",
                "output": [
                    {"type": "reasoning"},
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Ответ Морока"}],
                    },
                ],
            }
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, _format: str, *args) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        "morok_assistant.ai.client.RESPONSES_URL",
        f"http://127.0.0.1:{server.server_port}/v1/responses",
    )
    app = QCoreApplication.instance() or QCoreApplication([])
    connector = AIConnector()
    answers: list[tuple[str, str]] = []
    errors: list[str] = []
    loop = QEventLoop()
    connector.answered.connect(
        lambda text, identifier: (answers.append((text, identifier)), loop.quit())
    )
    connector.failed.connect(lambda message: (errors.append(message), loop.quit()))
    settings = AISettings(enabled=True, model="gpt-5-mini", api_key="test-key")

    try:
        for message, previous in (("Привет", None), ("Как дела?", "resp_1")):
            connector.send(settings, message, previous)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
        assert not errors
        assert answers == [("Ответ Морока", "resp_1"), ("Ответ Морока", "resp_2")]
        assert [item["path"] for item in received] == ["/v1/responses"] * 2
        assert [item["authorization"] for item in received] == ["Bearer test-key"] * 2
        assert received[0]["body"]["model"] == "gpt-5-mini"
        assert received[0]["body"]["input"] == "Привет"
        assert "previous_response_id" not in received[0]["body"]
        assert received[1]["body"]["previous_response_id"] == "resp_1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert app is not None
