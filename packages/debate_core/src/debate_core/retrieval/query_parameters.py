"""Query parameters the canonicalizer strips or must keep (skeleton for the red run)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AMP_QUERY_MARKERS",
    "CONTENT_PARAMETERS",
    "TRACKING_PARAMETERS",
    "AmpQueryMarker",
    "ContentParameter",
    "TrackingParameter",
    "is_amp_marker",
    "is_tracking_parameter",
]


@dataclass(frozen=True, slots=True)
class TrackingParameter:
    name: str
    reason: str
    prefix: bool = False


@dataclass(frozen=True, slots=True)
class ContentParameter:
    name: str
    reason: str


@dataclass(frozen=True, slots=True)
class AmpQueryMarker:
    name: str
    values: frozenset[str | None] | None
    reason: str


TRACKING_PARAMETERS: tuple[TrackingParameter, ...] = ()
CONTENT_PARAMETERS: tuple[ContentParameter, ...] = ()
AMP_QUERY_MARKERS: tuple[AmpQueryMarker, ...] = ()


def is_tracking_parameter(name: str) -> bool:
    return False


def is_amp_marker(name: str, value: str | None) -> bool:
    return False
