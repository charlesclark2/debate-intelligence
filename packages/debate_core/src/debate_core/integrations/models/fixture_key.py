"""The stable key a recorded model answer is filed under, so a test finds the same answer on every run.

The fake router reads `<prompt_id>/<key>.json` from a fixture directory and the replay router reads
a cassette by the same key (v1-e05-t03-fake-replay-models). Both work only if one call has one key:
on every run, on every platform, whatever order a caller happened to build its variables in. So the
key is a SHA-256 over a canonical JSON text, never over Python's `hash()` (which changes per
process) or a `repr` (which follows dict insertion order).

For a `generate_structured` call the key covers exactly four things (acceptance criterion ac2):

* the prompt's id and its version, so a new prompt version needs new fixtures;
* its variables, the call's inputs;
* the output schema's name, which is the dotted path
  :class:`~debate_core.domain.model_contracts.ModelRequest` carries
  (`debate_core.application.cards.CardSelection`), so two schemas that share a class name never
  share a key.

The task class and the per-call parameters are not in it: they change where a call is routed and
how it is sampled, not which answer a fixture holds. The replay router still compares them against
the recorded request before it serves a cassette, so a call that differs only in them is still an
unrecorded call there.

## The canonical text

Hashed as UTF-8, with keys sorted at every depth, no insignificant whitespace, and numbers as
Python's `json` writes them. Two things are refused rather than hashed, because neither can be sent
to a model or written to a cassette: a NaN or infinite number, and text that is not valid Unicode
(a lone surrogate). The text is hashed exactly as given and never normalized: `é` as one code point
and as `e` plus a combining accent are different inputs to a model, and get different keys.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Final

from pydantic import JsonValue

from debate_core.domain.model_contracts import ModelRequest

__all__ = ["FIXTURE_KEY_LENGTH", "canonical_json", "embedding_key", "fixture_key", "rerank_key"]

FIXTURE_KEY_LENGTH: Final = 64
"""Length of every key: a SHA-256 digest in lower-case hex."""


def canonical_json(value: JsonValue) -> str:
    """`value` as the one JSON text every run and platform agrees on.

    Raises `ValueError` for a NaN or infinite number, or for text that is not valid Unicode.
    """
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except ValueError as error:
        raise ValueError(
            f"a fixture key cannot be computed over a NaN or infinite number: {error}"
        ) from error
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(
            f"a fixture key cannot be computed over text that is not valid Unicode: {error.reason} "
            f"at position {error.start}"
        ) from error
    return text


def fixture_key(request: ModelRequest) -> str:
    """The key of one `generate_structured` call: its prompt, version, variables and schema name."""
    return _digest(
        {
            "inputs": request.prompt.variables,
            "prompt_id": request.prompt.prompt_id,
            "prompt_version": request.prompt.prompt_version,
            "schema": request.output_schema,
        }
    )


def embedding_key(texts: Sequence[str]) -> str:
    """The key of one `embed` call: its texts, in order."""
    return _digest({"call": "embed", "texts": list(texts)})


def rerank_key(query: str, documents: Sequence[str]) -> str:
    """The key of one `rerank` call: its query and documents, in order."""
    return _digest({"call": "rerank", "documents": list(documents), "query": query})


def _digest(document: dict[str, JsonValue]) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()
