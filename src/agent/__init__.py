"""The agent layer: classify and explain, never recompute.

``client.py`` is the only module that imports a provider SDK. Everything
else here works against the :class:`~src.agent.client.LLMClient` protocol.
"""

from .cache import ResponseCache
from .classifier import (
    CONFIRMED,
    OVERRIDDEN,
    OVERRIDE_REJECTED,
    PROMPT_VERSION,
    ROUTED_CONFIDENCE,
    UNPARSEABLE,
    classify,
)
from .client import LLMClient, LLMError, build_client

__all__ = [
    "CONFIRMED",
    "LLMClient",
    "LLMError",
    "OVERRIDDEN",
    "OVERRIDE_REJECTED",
    "PROMPT_VERSION",
    "ROUTED_CONFIDENCE",
    "ResponseCache",
    "UNPARSEABLE",
    "build_client",
    "classify",
]
