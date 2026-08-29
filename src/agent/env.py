"""Minimal .env reader.

Deliberately not a dependency. The file holds a handful of ``KEY=value``
lines and a fifteen-line parser is easier to audit than another package
in requirements.txt - which matters for the one file that handles an API
key.

Values are returned, never logged. Nothing here prints a secret.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Repository root, from this file's location rather than the cwd.
ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / ".env"


class MissingCredentialError(RuntimeError):
    """A required value is absent from both the environment and .env."""


def read_env(path=ENV_PATH):
    """Parse ``KEY=value`` lines into a dict. Missing file yields ``{}``."""
    if not Path(path).exists():
        return {}

    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def get(name, default=None, *, required=False):
    """Look up a setting: real environment first, then .env, then default.

    The process environment wins so CI can override without editing a
    file that is gitignored and therefore absent on other machines.

    Raises:
        MissingCredentialError: ``required`` and nowhere to be found.
    """
    value = os.environ.get(name) or read_env().get(name) or default
    if required and not value:
        raise MissingCredentialError(
            f"{name} is not set. Add it to {ENV_PATH.name} (which is "
            f"gitignored) or export it. The agent layer cannot run without it."
        )
    return value
