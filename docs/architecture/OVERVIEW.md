# Architecture Overview (Phase 0)

Modular monolith, Windows-native (PySide6/Qt), Python throughout.

```
┌─────────────────────────────────────────────────────────┐
│ Native UI (Qt): windows, tabs, dockables, workers       │  ADR-0001
├─────────────────────────────────────────────────────────┤
│ Application Layer (use-cases, orchestration)            │  Phase 1+
├─────────────────────────────────────────────────────────┤
│ Domain Layer (academic model, identities, status)       │  done v0
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│ Academic │ Engineer │ Simul.   │ Document │ AI Engine   │  interfaces done
│ Engines  │ ing Core │ Engine   │ +PDF Eng │ (Ollama)    │
├──────────┴──────────┴──────────┴──────────┴─────────────┤
│ Data Layer: SQLite + CAS filesystem + FTS5/TF-IDF index │  ADR-0003
├─────────────────────────────────────────────────────────┤
│ Integrations: LocalFS | OneDrive | GitHub | Stirling |  │  adapters, opt-in
│ Ollama | ngspice | LaTeX (all as external processes)    │
└─────────────────────────────────────────────────────────┘
```

Data flow (read path): UI → Application → Retrieval (FTS5/TF-IDF/RRF) →
EvidencePack → Context → AIRouter/Ollama → Answer + citations.
Write path: Source → ResourceEngine pipeline → Document AST + CAS →
SQLite entities + incremental index (background thread, never whole KB in RAM).
