from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from album_ranker import openai_client
from album_ranker.openai_client import AIClientError, GitHubModelsClient, OpenAIClient


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


def test_github_models_client_sends_json_schema_request(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"choices": [{"message": {"content": '{"name":"Wyrd"}'}}]})

    monkeypatch.setattr(openai_client, "urlopen", fake_urlopen)

    result = GitHubModelsClient("gh-token").generate_json(
        model="openai/gpt-4.1",
        system_prompt="System",
        user_prompt="User",
        schema_name="album_draft",
        schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    assert result == {"name": "Wyrd"}
    assert captured["timeout"] == 90
    assert request.full_url == openai_client.GITHUB_MODELS_API_URL
    assert request.get_header("Authorization") == "Bearer gh-token"
    assert request.get_header("Accept") == "application/vnd.github+json"
    assert request.get_header("X-github-api-version") == openai_client.GITHUB_MODELS_API_VERSION
    assert body["model"] == "openai/gpt-4.1"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "album_draft"


def test_github_models_client_requires_token() -> None:
    with pytest.raises(AIClientError, match="GITHUB_MODELS_TOKEN is not configured"):
        GitHubModelsClient(None).generate_json(
            model="openai/gpt-4.1",
            system_prompt="System",
            user_prompt="User",
            schema_name="result",
            schema={"type": "object", "properties": {}, "required": []},
        )


def test_github_models_client_lists_text_generation_models(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(
            [
                {
                    "id": "openai/gpt-5",
                    "supported_input_modalities": ["text", "image"],
                    "supported_output_modalities": ["text"],
                },
                {
                    "id": "openai/text-embedding-3-small",
                    "supported_input_modalities": ["text"],
                    "supported_output_modalities": ["embeddings"],
                },
                {
                    "id": "meta/llama-3.3-70b-instruct",
                    "supported_input_modalities": ["text"],
                    "supported_output_modalities": ["text"],
                },
            ]
        )

    monkeypatch.setattr(openai_client, "urlopen", fake_urlopen)

    models = GitHubModelsClient("gh-token").list_models()

    request = captured["request"]
    assert models == ["meta/llama-3.3-70b-instruct", "openai/gpt-5"]
    assert captured["timeout"] == 30
    assert request.full_url == openai_client.GITHUB_MODELS_CATALOG_API_URL
    assert request.get_header("Authorization") == "Bearer gh-token"
    assert request.get_header("Accept") == "application/vnd.github+json"
    assert request.get_header("X-github-api-version") == openai_client.GITHUB_MODELS_API_VERSION


def test_openai_client_lists_text_generation_models(monkeypatch) -> None:
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

    models = OpenAIClient("openai-token").list_models()

    request = captured["request"]
    assert models == ["gpt-4.1-mini", "gpt-5", "o3-mini"]
    assert captured["timeout"] == 30
    assert request.full_url == openai_client.OPENAI_MODELS_API_URL
    assert request.get_header("Authorization") == "Bearer openai-token"


def test_github_models_client_reports_http_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        raise HTTPError(request.full_url, 429, "Too Many Requests", hdrs=None, fp=FakeErrorBody())

    monkeypatch.setattr(openai_client, "urlopen", fake_urlopen)

    with pytest.raises(AIClientError, match="GitHub Models request failed with status 429"):
        GitHubModelsClient("gh-token").generate_json(
            model="openai/gpt-4.1",
            system_prompt="System",
            user_prompt="User",
            schema_name="result",
            schema={"type": "object", "properties": {}, "required": []},
        )


def test_github_models_client_reports_network_errors(monkeypatch) -> None:
    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        raise URLError("offline")

    monkeypatch.setattr(openai_client, "urlopen", fake_urlopen)

    with pytest.raises(AIClientError, match="GitHub Models request failed"):
        GitHubModelsClient("gh-token").generate_json(
            model="openai/gpt-4.1",
            system_prompt="System",
            user_prompt="User",
            schema_name="result",
            schema={"type": "object", "properties": {}, "required": []},
        )
