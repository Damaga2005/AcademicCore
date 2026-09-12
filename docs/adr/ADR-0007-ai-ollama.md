# ADR-0007 — AI Engine: Ollama runtime + evidence-gated router

Date: 2026-09-12 · Status: Accepted

## Decision
- Local runtime = **Ollama** (runtime, not model). Models interchangeable;
  benchmark Qwen / Gemma / Llama before pinning defaults — no single model fixed.
- Architecture: `Knowledge/Retrieval → Evidence → Context → Model → Answer`.
  `AIRouter` abstains (`No trobo suport suficient...`) when evidence is empty.
- Cloud (Gemini `gemini-3.5-flash-lite`) is an opt-in provider behind the same
  `ModelBackend` interface; fallback extractive provider for offline use.

## Rationale
Sistemes audit: grounding (EvidencePack + abstention + formula_check) is the
asset; the LLM must never invent formulas. Ollama keeps data local and fits the
RTX 2060 as optional acceleration (CPU fallback mandatory).

## Consequences
- RAM: models load on demand, one at a time; quantization preferred; context
  built from top-k evidence, never whole KB.
- Benchmark harness in Phase 10 measures quality/latency/RAM per model.
