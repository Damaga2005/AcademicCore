from academic_core.engines.ai import AIRouter, Answer, Evidence, ModelBackend, OllamaBackend
from academic_core.engines.document_ast import Block, DocMetadata, Document
from academic_core.engines.engineering import Circuit, Component, Experiment, Measurement
from academic_core.engines.pdf import PDFResult, PDFService, StirlingAdapter
from academic_core.engines.providers import (
    GitHubProvider, LocalFilesystemProvider, OneDriveProvider,
    ResourceProvider, SyncResult,
)
from academic_core.engines.resource import IngestResult, ResourceAdapter, ResourceEngine, SUPPORTED_KINDS

__all__ = [
    "Block", "DocMetadata", "Document",
    "SUPPORTED_KINDS", "IngestResult", "ResourceAdapter", "ResourceEngine",
    "PDFResult", "PDFService", "StirlingAdapter",
    "Evidence", "Answer", "ModelBackend", "OllamaBackend", "AIRouter",
    "ResourceProvider", "SyncResult", "LocalFilesystemProvider",
    "OneDriveProvider", "GitHubProvider",
    "Component", "Circuit", "Measurement", "Experiment",
]
