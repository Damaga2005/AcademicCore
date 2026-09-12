"""AI Engine: Knowledge/Retrieval -> Evidence -> Context -> Model -> Answer.

The model is NEVER the source of truth. Local runtime = Ollama (runtime, not model).
Models (Qwen/Gemma/Llama/...) are interchangeable; benchmark before pinning.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Evidence:
    items: list[dict] = field(default_factory=list)
    abstained: bool = False
    reason: str = ""


@dataclass
class Answer:
    text: str
    evidence: Evidence
    model: str


class ModelBackend(ABC):
    name: str = ""

    @abstractmethod
    def generate(self, context: str, prompt: str) -> str: ...

    @abstractmethod
    def list_models(self) -> list[str]: ...


class OllamaBackend(ModelBackend):
    name = "ollama"

    def __init__(self, host: str = "http://127.0.0.1:11434", model: str = ""):
        self.host = host
        self.model = model

    def list_models(self) -> list[str]:
        # Phase 0: live listing happens in Phase 10; keep stdlib-only here.
        import json
        import urllib.request
        with urllib.request.urlopen(self.host + "/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m["name"] for m in data.get("models", [])]

    def generate(self, context: str, prompt: str) -> str:
        import json
        import urllib.request
        payload = json.dumps({
            "model": self.model, "stream": False,
            "prompt": f"Context (do not invent beyond it):\n{context}\n\nQ: {prompt}",
        }).encode()
        req = urllib.request.Request(self.host + "/api/generate", data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8")).get("response", "")


class AIRouter:
    """Routes to local Ollama or cloud providers. Evidence-gated."""

    def __init__(self, backend: ModelBackend):
        self.backend = backend

    def ask(self, evidence: Evidence, question: str) -> Answer:
        if evidence.abstained or not evidence.items:
            return Answer(text="No trobo suport suficient a la base de coneixement.",
                          evidence=evidence, model=self.backend.name)
        context = "\n".join(str(i) for i in evidence.items)
        return Answer(text=self.backend.generate(context, question),
                      evidence=evidence, model=self.backend.name)
