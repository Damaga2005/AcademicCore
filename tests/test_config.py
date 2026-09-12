"""Unit: config precedence defaults < file < env < overrides; dirs created."""
import json

from academic_core.config import Settings


def test_defaults(tmp_path):
    s = Settings.load()
    assert s.ai.provider == "ollama"
    assert s.ai.model == ""  # auto-detect, never pinned to one model


def test_file_and_overrides(tmp_path, monkeypatch):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"ai": {"provider": "gemini"}}), encoding="utf-8")
    s = Settings.load(cfg, overrides={"ai.model": "qwen3:8b"})
    assert s.ai.provider == "gemini"
    assert s.ai.model == "qwen3:8b"


def test_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("ACORE_AI_PROVIDER", "none")
    assert Settings.load().ai.provider == "none"
