"""``isinstance`` for runtime guards on values whose static type already says they pass.

The type checker trusts annotations, but selections arrive from deserialized model output and from
callers outside the checker, which can pass anything. Taking the value as ``object`` keeps strict
pyright from calling these guards unnecessary.
"""

from __future__ import annotations

from types import UnionType
from typing import cast

__all__ = ["is_instance", "is_tuple_of"]


def is_instance(value: object, kind: type | UnionType) -> bool:
    """``isinstance(value, kind)``."""
    return isinstance(value, kind)


def is_tuple_of(value: object, kind: type | UnionType) -> bool:
    """True when ``value`` is a tuple and every item in it is a ``kind``."""
    return isinstance(value, tuple) and all(
        isinstance(item, kind) for item in cast("tuple[object, ...]", value)
    )
