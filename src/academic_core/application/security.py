"""Local security boundaries (Phase 1): no web auth — single-user desktop.

- AppLock: SHA-256 + per-lock salt PIN gate for the local app. The hash lives
  in the JSON config; the PIN never touches SQLite, logs or backups.
- Secrets (tokens, API keys): environment variables / OS credential store
  only. Repositories MUST NOT persist them; BackupService excludes config.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass


@dataclass
class AppLock:
    salt: str = ""
    pin_hash: str = ""

    @classmethod
    def create(cls, pin: str) -> "AppLock":
        salt = secrets.token_hex(16)
        return cls(salt, hashlib.sha256((salt + pin).encode()).hexdigest())

    def verify(self, pin: str) -> bool:
        if not self.salt:
            return True  # no lock configured
        return hashlib.sha256((self.salt + pin).encode()).hexdigest() == self.pin_hash
