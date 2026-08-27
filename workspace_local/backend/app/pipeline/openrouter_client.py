from __future__ import annotations

import re

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class OpenRouterClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def chat_json(self, model: str, messages: list[dict[str, str]]) -> str:
        response = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": model,
                "messages": messages,
                "response_format": {"type": "json_object"},
            },
            timeout=120.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return _JSON_FENCE.sub("", content).strip()
