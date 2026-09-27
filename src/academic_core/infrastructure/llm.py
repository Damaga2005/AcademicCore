# SPDX-License-Identifier: MIT
"""F12 LLM provider boundary (infrastructure). Provider-agnostic by design.

``LLMProvider`` is the only contract the application layer depends on;
concrete backends live behind it and the academic domain never imports
one. Adapts the existing Phase-0 ``OllamaBackend`` rather than
duplicating it. No API keys, no cloud provider, no new dependency.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
from dataclasses import dataclass
from typing import Protocol

from academic_core.engines.ai import OllamaBackend

LLM_SCHEMA = "f12-tutor-response/1"
DEFAULT_TIMEOUT_S = 30.0
MAX_CONTEXT_CHARS = 8000
MAX_RESPONSE_CHARS = 4000


@dataclass(frozen=True)
class LLMRequest:
    system_policy: str
    context: str
    task: str
    schema_version: str = LLM_SCHEMA
    max_tokens: int = 800
    timeout_s: float = DEFAULT_TIMEOUT_S

    def __post_init__(self) -> None:
        if len(self.context) > MAX_CONTEXT_CHARS:
            raise ValueError("context exceeds max size")


@dataclass(frozen=True)
class LLMResponse:
    raw_text: str
    provider: str
    model: str
    latency_ms: int
    available: bool = True
    error_code: str = ""  # LLM_UNAVAILABLE | LLM_TIMEOUT | PROVIDER_ERROR


@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    model: str
    available: bool


class LLMProvider(Protocol):
    def generate(self, request: LLMRequest) -> LLMResponse: ...
    def metadata(self) -> ProviderMetadata: ...


class NullProvider:
    """LLM=OFF. Deterministic, no network, always unavailable."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(raw_text="", provider="none", model="",
                            latency_ms=0, available=False,
                            error_code="LLM_UNAVAILABLE")

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider="none", model="", available=False)


class OllamaProvider:
    """Adapter over the existing OllamaBackend. Zero automatic retries."""

    def __init__(self, host: str = "http://127.0.0.1:11434", model: str = ""):
        self._backend = OllamaBackend(host=host, model=model)

    def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = (f"{request.system_policy}\n\n{request.task}\n\n"
                  f"Respond with a single JSON object matching schema "
                  f"{request.schema_version}. No prose outside the JSON.")
        started = time.monotonic()
        try:
            text = self._backend.generate(request.context, prompt,
                                          timeout=request.timeout_s)
        except (socket.timeout, TimeoutError):
            return LLMResponse(raw_text="", provider="ollama",
                                model=self._backend.model, latency_ms=0,
                                available=False, error_code="LLM_TIMEOUT")
        except (urllib.error.URLError, OSError, ValueError,
                json.JSONDecodeError):
            return LLMResponse(raw_text="", provider="ollama",
                                model=self._backend.model, latency_ms=0,
                                available=False, error_code="PROVIDER_ERROR")
        latency_ms = int((time.monotonic() - started) * 1000)
        return LLMResponse(raw_text=text[:MAX_RESPONSE_CHARS], provider="ollama",
                            model=self._backend.model, latency_ms=latency_ms,
                            available=True)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider="ollama", model=self._backend.model,
                                available=True)
