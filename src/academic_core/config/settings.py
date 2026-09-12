"""Configuration system (Phase 0).

Precedence: defaults < config file (TOML/JSON) < env vars (ACORE_*) < explicit overrides.
Covers: storage location, AI provider, Ollama, model, cache, OneDrive, external tools.
No secrets are ever written to disk by this module.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _home() -> Path:
    return Path(os.environ.get("ACORE_HOME", Path.home() / ".academic-core"))


@dataclass
class StorageConfig:
    location: str = str(_home() / "data")
    cas_dir: str = str(_home() / "data" / "cas")
    index_dir: str = str(_home() / "data" / "index")
    cache_dir: str = str(_home() / "data" / "cache")


@dataclass
class AIConfig:
    provider: str = "ollama"  # ollama | gemini | none
    ollama_host: str = "http://127.0.0.1:11434"
    model: str = ""  # empty = auto-detect, never hardcode a single model
    gemini_model: str = "gemini-3.5-flash-lite"


@dataclass
class ProvidersConfig:
    onedrive_enabled: bool = False
    onedrive_folder: str = ""
    github_enabled: bool = False


@dataclass
class ToolsConfig:
    ngspice: str = "ngspice"
    latex: str = "pdflatex"
    stirling_url: str = "http://127.0.0.1:8080"
    stirling_enabled: bool = False


@dataclass
class IngestConfig:
    max_bytes: int = 100 * 1024 * 1024  # 100 MiB per file (F2 default)
    cas_dir: str = ""  # empty = <storage.location>/cas


@dataclass
class Settings:
    storage: StorageConfig = field(default_factory=StorageConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    providers: ProvidersConfig = field(default_factory=ProvidersConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)

    @classmethod
    def load(cls, path: str | os.PathLike | None = None, overrides: dict | None = None) -> "Settings":
        s = cls()
        if path and Path(path).exists():
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            for section in ("storage", "ai", "providers", "tools", "ingest"):
                if section in raw:
                    getattr(s, section).__dict__.update(raw[section])
        env = os.environ
        if env.get("ACORE_DATA_DIR"):
            s.storage.location = env["ACORE_DATA_DIR"]
        if env.get("ACORE_AI_PROVIDER"):
            s.ai.provider = env["ACORE_AI_PROVIDER"]
        if env.get("OLLAMA_HOST"):
            s.ai.ollama_host = env["OLLAMA_HOST"]
        if env.get("ACORE_MODEL"):
            s.ai.model = env["ACORE_MODEL"]
        if env.get("ACORE_ONEDRIVE_FOLDER"):
            s.providers.onedrive_folder = env["ACORE_ONEDRIVE_FOLDER"]
            s.providers.onedrive_enabled = True
        for k, v in (overrides or {}).items():
            if "." in k:
                sec, attr = k.split(".", 1)
                setattr(getattr(s, sec), attr, v)
        return s

    def ensure_dirs(self) -> None:
        for d in (self.storage.location, self.storage.cas_dir,
                  self.storage.index_dir, self.storage.cache_dir):
            Path(d).mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict:
        return asdict(self)
