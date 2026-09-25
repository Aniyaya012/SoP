"""Small OpenAI-compatible JSON client for reviewer-owned API credentials."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx


def parse_json_object(content: str) -> dict[str, Any]:
    candidate = content.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("Model response must be one JSON object")
    return value


class ChatAPI:
    def __init__(self, base_url: str, model: str, key_environment: str, concurrency: int) -> None:
        key = os.environ.get(key_environment)
        if not key:
            raise ValueError(f"Set {key_environment} before running the method")
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("--api-base-url must be an HTTP(S) URL")
        if not model.strip():
            raise ValueError("--model is required")
        if concurrency < 1:
            raise ValueError("--concurrency must be positive")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.semaphore = asyncio.Semaphore(concurrency)
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(120.0),
            limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
        )

    async def __aenter__(self) -> "ChatAPI":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.client.aclose()

    async def ask(self, messages: list[dict[str, str]], *, max_tokens: int = 1400) -> dict[str, Any]:
        request = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
        last_error: Exception | None = None
        async with self.semaphore:
            for attempt in range(4):
                try:
                    response = await self.client.post(self.url, json=request)
                    if response.status_code in {429, 500, 502, 503, 504}:
                        response.raise_for_status()
                    response.raise_for_status()
                    payload = response.json()
                    content = payload["choices"][0]["message"]["content"]
                    if not isinstance(content, str):
                        raise ValueError("Model response has no text content")
                    return parse_json_object(content)
                except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                    last_error = exc
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {429, 500, 502, 503, 504}:
                        break
                    if attempt < 3:
                        await asyncio.sleep(min(8, 2**attempt))
        raise RuntimeError(f"API request failed after validation/retry: {last_error}")
