# SPDX-License-Identifier: MIT
"""Deterministic batch conversion (F3.1 §43): sorted order, structured
errors/warnings, optional cache + cancellation + progress. No hidden FS."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BatchItem:
    name: str
    ok: bool
    warnings: tuple = ()
    error: str = ""


@dataclass
class BatchResult:
    items: list[BatchItem] = field(default_factory=list)
    truncated: bool = False

    @property
    def converted(self) -> int:
        return sum(1 for i in self.items if i.ok)

    @property
    def failed(self) -> int:
        return sum(1 for i in self.items if not i.ok)


def convert_batch(files: dict[str, bytes], convert, *, progress=None,
                  cancel=None, cache: dict | None = None,
                  max_files: int = 1_000) -> BatchResult:
    """`files`: {name: bytes}; `convert(name, data) -> (doc, warnings)`.

    Iterates in `sorted(files)` order. Errors are captured per file, never
    raised, never hidden: each failure yields `BatchItem(ok=False, error=...)`.
    `cache` maps name → digest/etag and skips unchanged inputs when the caller
    supplies `cache_get(name, data)`? Kept minimal: if `cache` contains
    `name` with value `len(data)`, the file is skipped as unchanged and
    reported ok with warning `cached`.
    """
    result = BatchResult()
    names = sorted(files)
    if len(names) > max_files:
        result.truncated = True
        names = names[:max_files]
    for idx, name in enumerate(names):
        if cancel is not None and cancel():
            result.truncated = True
            break
        data = files[name]
        if cache is not None and cache.get(name) == len(data):
            result.items.append(BatchItem(name, True, ("cached",)))
            continue
        try:
            _, warnings = convert(name, data)
            result.items.append(BatchItem(name, True, tuple(warnings)))
        except Exception as e:  # captured, never hidden
            result.items.append(BatchItem(name, False, (), f"{type(e).__name__}: {e}"))
        if progress is not None:
            progress(idx + 1, len(names), name)
        if cache is not None:
            cache[name] = len(data)
    return result
