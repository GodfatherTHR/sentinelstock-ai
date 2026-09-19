from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .fetch import FetchError, request_json

log = logging.getLogger("connectors.openrouter")

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

# Free-tier models, tried in order. Override the first choice with OPENROUTER_MODEL.
DEFAULT_MODELS = (
    "deepseek/deepseek-v4-flash-0731:free",
    "qwen/qwen3.8-27b:free",
    "nvidia/nemotron-3.5-lightning:free",
)


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter cannot answer or the answer is not usable JSON."""


@dataclass
class OpenRouterClient:
    api_key: str
    timeout: int = 120
    referer: str = "https://sentinelstock.local"
    title: str = "SentinelStock AI"

    def chat_json(self, *, model: str, system: str, user: str) -> dict:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": self.referer,
            "X-Title": self.title,
        }
        try:
            response = request_json(CHAT_URL, headers=headers, method="POST", payload=payload, timeout=self.timeout)
        except FetchError as exc:
            raise OpenRouterError(f"{model}: {exc}") from exc
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError(f"{model}: unexpected response {response!r}") from exc
        return _parse_json(content, model)


def _parse_json(content: str, model: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OpenRouterError(f"{model}: model did not return JSON: {text[:200]!r}") from exc
    if not isinstance(parsed, dict):
        raise OpenRouterError(f"{model}: expected a JSON object, got {type(parsed).__name__}")
    return parsed
