from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from album_ranker import openai_client
from album_ranker.openai_client import AIClientError, AlbumWriteupAIClient, OpenAIClient


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakeErrorBody:
    def read(self) -> bytes:
        return b'{"message":"rate limited"}'

    def close(self) -> None:
        return None


def test_album_writeup_ai_client_sends_json_schema_request(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"choices": [{"message": {"content": '{"overview":"Wyrd"}'}}]})

    monkeypatch.setattr(openai_client, "urlopen", fake_urlopen)

    result = AlbumWriteupAIClient("openai-token").generate_json(
        model="gpt-5-mini",
        system_prompt="System",
        user_prompt="User",
        schema_name="album_writeup",
        schema={"type": "object", "properties": {"overview": {"type": "string"}}, "required": ["overview"]},
    )

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    assert result == {"overview": "Wyrd"}
    assert captured["timeout"] == 90
    assert request.full_url == openai_client.OPENAI_API_URL
    assert request.get_header("Authorization") == "Bearer openai-token"
    assert body["model"] == "gpt-5-mini"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "album_writeup"


def test_album_writeup_ai_client_requires_api_key() -> None:
    with pytest.raises(AIClientError, match="OPENAI_API_KEY is not configured"):
        AlbumWriteupAIClient(None).generate_json(
            model="gpt-5-mini",
            system_prompt="System",
            user_prompt="User",
            schema_name="result",
            schema={"type": "object", "properties": {}, "required": []},
        )


def test_openai_client_aliases_album_writeup_ai_client() -> None:
    assert OpenAIClient is AlbumWriteupAIClient


def test_album_writeup_ai_client_lists_text_generation_models(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "data": [
                    {"id": "gpt-5"},
                    {"id": "gpt-4.1-mini"},
                    {"id": "text-embedding-3-small"},
                    {"id": "whisper-1"},
                    {"id": "o3-mini"},
                ]
            }
        )

    monkeypatch.setattr(openai_client, "urlopen", fake_urlopen)

    models = AlbumWriteupAIClient("openai-token").list_models()

    request = captured["request"]
    assert models == ["gpt-4.1-mini", "gpt-5", "o3-mini"]
    assert captured["timeout"] == 30
    assert request.full_url == openai_client.OPENAI_MODELS_API_URL
    assert request.get_header("Authorization") == "Bearer openai-token"


def test_album_writeup_ai_client_reports_http_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        raise HTTPError(request.full_url, 429, "Too Many Requests", hdrs=None, fp=FakeErrorBody())

    monkeypatch.setattr(openai_client, "urlopen", fake_urlopen)

    with pytest.raises(AIClientError, match="OpenAI request failed with status 429"):
        AlbumWriteupAIClient("openai-token").generate_json(
            model="gpt-5-mini",
            system_prompt="System",
            user_prompt="User",
            schema_name="result",
            schema={"type": "object", "properties": {}, "required": []},
        )


def test_album_writeup_ai_client_reports_network_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        raise URLError("offline")

    monkeypatch.setattr(openai_client, "urlopen", fake_urlopen)

    with pytest.raises(AIClientError, match="OpenAI request failed"):
        AlbumWriteupAIClient("openai-token").generate_json(
            model="gpt-5-mini",
            system_prompt="System",
            user_prompt="User",
            schema_name="result",
            schema={"type": "object", "properties": {}, "required": []},
        )
