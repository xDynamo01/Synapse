from __future__ import annotations

import json
from typing import Iterable

from synapse.providers.base import BaseProvider, ChatRequest, ProviderError


class OpenAICompatibleProvider(BaseProvider):
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = self.config.resolved_api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _url(self) -> str:
        return self.config.base_url.rstrip("/") + "/chat/completions"

    def _body(self, request: ChatRequest, stream: bool) -> dict:
        return {
            "model": request.model or self.config.model,
            "messages": request.messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": stream,
        }

    def chat(self, request: ChatRequest) -> str:
        try:
            import requests

            response = requests.post(
                self._url(),
                headers=self._headers(),
                json=self._body(request, stream=False),
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            raise ProviderError(f"{self.config.name} failed: {exc}") from exc

    def stream(self, request: ChatRequest) -> Iterable[str]:
        try:
            import requests

            with requests.post(
                self._url(),
                headers=self._headers(),
                json=self._body(request, stream=True),
                stream=True,
                timeout=self.config.timeout_seconds,
            ) as response:
                response.raise_for_status()
                for raw in response.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    line = raw[6:] if raw.startswith("data: ") else raw
                    if line.strip() == "[DONE]":
                        break
                    data = json.loads(line)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        yield token
        except Exception as exc:
            raise ProviderError(f"{self.config.name} stream failed: {exc}") from exc

    def health_check(self) -> bool:
        try:
            import requests

            response = requests.get(self.config.base_url.rstrip("/") + "/models", headers=self._headers(), timeout=5)
            return response.status_code < 500
        except Exception:
            return False
