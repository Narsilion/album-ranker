from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODELS_API_URL = "https://api.openai.com/v1/models"
GITHUB_MODELS_API_URL = "https://models.github.ai/inference/chat/completions"
GITHUB_MODELS_CATALOG_API_URL = "https://models.github.ai/catalog/models"
GITHUB_MODELS_API_VERSION = "2022-11-28"


class OpenAIClientError(RuntimeError):
    pass


AIClientError = OpenAIClientError


def _text_generation_model_ids(items: list[dict[str, object]]) -> list[str]:
    model_ids: list[str] = []
    for item in items:
        model_id = item.get("id")
        if not isinstance(model_id, str):
            continue
        output_modalities = item.get("supported_output_modalities")
        if isinstance(output_modalities, list) and "text" not in output_modalities:
            continue
        if output_modalities is None and any(term in model_id for term in ("embedding", "whisper", "tts")):
            continue
        model_ids.append(model_id)
    return sorted(model_ids)


class OpenAIClient:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    def generate_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, object],
    ) -> dict[str, object]:
        if not self.api_key:
            raise OpenAIClientError("OPENAI_API_KEY is not configured")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_prompt
                    + "\n\nReturn valid JSON only. Do not include markdown fences or prose outside the JSON object.",
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        request = Request(
            OPENAI_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise OpenAIClientError(f"OpenAI request failed with status {exc.code}: {detail}") from exc
        except URLError as exc:
            raise OpenAIClientError(f"OpenAI request failed: {exc.reason}") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenAIClientError(f"Unexpected OpenAI response shape: {body}") from exc
        data = json.loads(content)
        if not isinstance(data, dict):
            raise OpenAIClientError("OpenAI response was not a JSON object")
        return data

    def list_models(self) -> list[str]:
        if not self.api_key:
            raise OpenAIClientError("OPENAI_API_KEY is not configured")
        request = Request(
            OPENAI_MODELS_API_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise OpenAIClientError(f"OpenAI models request failed with status {exc.code}: {detail}") from exc
        except URLError as exc:
            raise OpenAIClientError(f"OpenAI models request failed: {exc.reason}") from exc
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise OpenAIClientError(f"Unexpected OpenAI models response shape: {body}")
        return _text_generation_model_ids([item for item in data if isinstance(item, dict)])


class GitHubModelsClient:
    def __init__(self, token: str | None) -> None:
        self.token = token

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise OpenAIClientError("GITHUB_MODELS_TOKEN is not configured")
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_MODELS_API_VERSION,
        }

    def generate_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, object],
    ) -> dict[str, object]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_prompt
                    + "\n\nReturn valid JSON only. Do not include markdown fences or prose outside the JSON object.",
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        request = Request(
            GITHUB_MODELS_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise OpenAIClientError(f"GitHub Models request failed with status {exc.code}: {detail}") from exc
        except URLError as exc:
            raise OpenAIClientError(f"GitHub Models request failed: {exc.reason}") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenAIClientError(f"Unexpected GitHub Models response shape: {body}") from exc
        data = json.loads(content)
        if not isinstance(data, dict):
            raise OpenAIClientError("GitHub Models response was not a JSON object")
        return data

    def list_models(self) -> list[str]:
        request = Request(
            GITHUB_MODELS_CATALOG_API_URL,
            headers=self._headers(),
            method="GET",
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise OpenAIClientError(f"GitHub Models catalog request failed with status {exc.code}: {detail}") from exc
        except URLError as exc:
            raise OpenAIClientError(f"GitHub Models catalog request failed: {exc.reason}") from exc
        if not isinstance(body, list):
            raise OpenAIClientError(f"Unexpected GitHub Models catalog response shape: {body}")
        return _text_generation_model_ids([item for item in body if isinstance(item, dict)])
