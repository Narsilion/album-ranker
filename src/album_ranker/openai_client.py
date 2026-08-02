from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_RESPONSES_API_URL = "https://api.openai.com/v1/responses"
OPENAI_MODELS_API_URL = "https://api.openai.com/v1/models"


class AIClientError(RuntimeError):
    pass


class OpenAIClientError(AIClientError):
    pass


def _text_generation_model_ids(items: list[dict[str, object]]) -> list[str]:
    model_ids: list[str] = []
    for item in items:
        model_id = item.get("id")
        if not isinstance(model_id, str):
            continue
        output_modalities = item.get("supported_output_modalities")
        if isinstance(output_modalities, list) and "text" not in output_modalities:
            continue
        if output_modalities is None and any(
            term in model_id
            for term in (
                "audio",
                "computer-use",
                "codex",
                "embedding",
                "image",
                "instruct",
                "realtime",
                "search",
                "transcribe",
                "tts",
                "whisper",
            )
        ):
            continue
        model_ids.append(model_id)
    return sorted(model_ids)


class AlbumWriteupAIClient:
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
        if model.startswith("gpt-5.6"):
            payload["reasoning_effort"] = "medium"
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

    def generate_json_with_web_search(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, object],
    ) -> tuple[dict[str, object], list[dict[str, str]]]:
        if not self.api_key:
            raise OpenAIClientError("OPENAI_API_KEY is not configured")
        payload: dict[str, object] = {
            "model": model,
            "instructions": system_prompt,
            "input": user_prompt,
            "tools": [{"type": "web_search", "search_context_size": "medium"}],
            "tool_choice": "required",
            "max_tool_calls": 3,
            "include": ["web_search_call.action.sources"],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
            "store": False,
        }
        if model.startswith("gpt-5.6"):
            payload["reasoning"] = {"effort": "medium"}
        request = Request(
            OPENAI_RESPONSES_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise OpenAIClientError(f"OpenAI request failed with status {exc.code}: {detail}") from exc
        except URLError as exc:
            raise OpenAIClientError(f"OpenAI request failed: {exc.reason}") from exc

        output = body.get("output") if isinstance(body, dict) else None
        if not isinstance(output, list):
            raise OpenAIClientError(f"Unexpected OpenAI response shape: {body}")
        output_text = ""
        sources: list[dict[str, str]] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "web_search_call":
                action = item.get("action")
                raw_sources = action.get("sources") if isinstance(action, dict) else None
                if isinstance(raw_sources, list):
                    for source in raw_sources:
                        if not isinstance(source, dict):
                            continue
                        url = str(source.get("url") or "").strip()
                        if url:
                            sources.append({"url": url, "title": str(source.get("title") or url).strip()})
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "output_text":
                    continue
                output_text += str(part.get("text") or "")
                annotations = part.get("annotations")
                if isinstance(annotations, list):
                    for annotation in annotations:
                        if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
                            continue
                        url = str(annotation.get("url") or "").strip()
                        if url:
                            sources.append({"url": url, "title": str(annotation.get("title") or url).strip()})
        try:
            data = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise OpenAIClientError(f"OpenAI response was not valid JSON: {output_text}") from exc
        if not isinstance(data, dict):
            raise OpenAIClientError("OpenAI response was not a JSON object")
        unique_sources: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for source in sources:
            if source["url"] in seen_urls:
                continue
            seen_urls.add(source["url"])
            unique_sources.append(source)
        return data, unique_sources

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


OpenAIClient = AlbumWriteupAIClient
