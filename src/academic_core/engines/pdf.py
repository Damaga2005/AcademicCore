"""PDFService abstraction — domain never talks to Stirling directly.

Academic Core -> PDFService/PDFEngine -> StirlingAdapter/runtime (or others).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PDFResult:
    out_hash: str
    pages: int = 0


class PDFService(ABC):
    @abstractmethod
    def merge(self, hashes: list[str]) -> PDFResult: ...
    @abstractmethod
    def split(self, pdf_hash: str, ranges: list[tuple[int, int]]) -> PDFResult: ...
    @abstractmethod
    def compress(self, pdf_hash: str) -> PDFResult: ...
    @abstractmethod
    def ocr(self, pdf_hash: str) -> str: ...


class StirlingAdapter(PDFService):
    """Adapter over a Stirling-PDF runtime (isolated process/service).

    Phase 0: interface + disabled-by-default wiring. No vendored Stirling yet
    (see ADR-0006 for license/runtime decision pending).
    """

    def __init__(self, base_url: str, enabled: bool = False):
        self.base_url = base_url
        self.enabled = enabled

    def _guard(self) -> None:
        if not self.enabled:
            raise RuntimeError("Stirling-PDF runtime not enabled (see ADR-0006)")

    def merge(self, hashes: list[str]) -> PDFResult:
        self._guard()
        raise NotImplementedError

    def split(self, pdf_hash: str, ranges: list[tuple[int, int]]) -> PDFResult:
        self._guard()
        raise NotImplementedError

    def compress(self, pdf_hash: str) -> PDFResult:
        self._guard()
        raise NotImplementedError

    def ocr(self, pdf_hash: str) -> str:
        self._guard()
        raise NotImplementedError
