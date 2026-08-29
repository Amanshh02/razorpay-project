"""The LLM boundary. **No provider SDK detail leaves this file.**

Everything above this module sees one method::

    client.complete(system=..., user=...) -> str

No message dicts, no content blocks, no provider exception types. Swapping
providers means adding a class here and a branch in :func:`build_client`;
nothing in ``classifier.py`` changes.

The interface deliberately returns plain text rather than a provider's
structured-output object. Structured output is spelled differently by
every vendor, so depending on it here would leak exactly the detail this
boundary exists to contain. The classifier parses JSON out of the text.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from . import env

#: Default model for the Anthropic provider.
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"

#: Enough room for adaptive thinking plus a short JSON answer.
DEFAULT_MAX_TOKENS = 4000


class LLMError(RuntimeError):
    """A provider call failed. Provider exception types never escape."""


@runtime_checkable
class LLMClient(Protocol):
    """What the agent layer needs from a language model. Nothing more."""

    #: Identifies the model in cache keys, so a model change misses cache.
    model: str

    def complete(self, *, system: str, user: str) -> str:
        """Return the model's text response to one system+user exchange."""
        ...


class AnthropicClient:
    """:class:`LLMClient` backed by the Anthropic Messages API.

    The only place ``import anthropic`` appears in the project.
    """

    def __init__(self, api_key=None, model=DEFAULT_ANTHROPIC_MODEL,
                 max_tokens=DEFAULT_MAX_TOKENS):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on install
            raise LLMError(
                "The anthropic package is not installed. "
                "Run: pip install -r requirements.txt"
            ) from exc

        self._anthropic = anthropic
        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(
            api_key=api_key or env.get("ANTHROPIC_API_KEY", required=True)
        )

    def complete(self, *, system, user):
        """One request, one text answer.

        Adaptive thinking is on: the ambiguous cases this layer exists to
        resolve are exactly the ones that benefit from it, and the disk
        cache means each finding is paid for once.
        """
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
            )
        except self._anthropic.APIError as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc

        if response.stop_reason == "refusal":
            raise LLMError("the model declined to answer this request")

        return "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()


def build_client(provider=None, model=None):
    """Construct the configured provider's client.

    Args:
        provider: Overrides ``LLM_PROVIDER``. Defaults to ``anthropic``.
        model: Overrides the provider's default model.

    Raises:
        LLMError: The named provider has no implementation here.
    """
    provider = (provider or env.get("LLM_PROVIDER", "anthropic")).lower()
    if provider == "anthropic":
        return AnthropicClient(model=model or DEFAULT_ANTHROPIC_MODEL)
    raise LLMError(
        f"unknown LLM provider {provider!r}. Implement it in "
        f"src/agent/client.py and add it to build_client()."
    )
