"""Disk cache for model responses, so re-running the eval does not re-bill.

Keyed by a SHA-256 of everything that could change the answer: the model
id, the prompt version, and the exact prompt text. Edit the prompt and
every entry misses, which is the correct behaviour - a cached answer to a
different question is worse than no cache.

Entries are plain JSON on disk under ``.llm_cache/`` (gitignored). Delete
the directory to force a full re-run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CACHE_DIR = ROOT / ".llm_cache"


class ResponseCache:
    """Content-addressed store of prompt -> response text."""

    def __init__(self, directory=DEFAULT_CACHE_DIR, enabled=True):
        self.directory = Path(directory)
        self.enabled = enabled
        self.hits = 0
        self.misses = 0
        if self.enabled:
            self.directory.mkdir(parents=True, exist_ok=True)

    def key(self, *, model, prompt_version, system, user):
        """Stable digest of everything that determines the answer."""
        digest = hashlib.sha256()
        for part in (model, str(prompt_version), system, user):
            digest.update(part.encode("utf-8"))
            digest.update(b"\x00")
        return digest.hexdigest()

    def _path(self, key):
        return self.directory / f"{key}.json"

    def get(self, key):
        """Cached response text, or None."""
        if not self.enabled:
            return None
        path = self._path(key)
        if not path.exists():
            self.misses += 1
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt entry is a cache miss, never a crash.
            self.misses += 1
            return None
        self.hits += 1
        return payload.get("response")

    def put(self, key, response, *, metadata=None):
        """Store a response. Failure to write is not fatal."""
        if not self.enabled:
            return
        payload = {"response": response, "metadata": metadata or {}}
        try:
            self._path(key).write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
        except OSError:  # pragma: no cover - disk full, permissions
            pass

    def summary(self):
        return f"{self.hits} hit / {self.misses} miss"
