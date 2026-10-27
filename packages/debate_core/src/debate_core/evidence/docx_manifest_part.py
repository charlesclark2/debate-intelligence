"""Skeleton for the red run of `v1-e06-t04`: the names, and nothing embedded or found."""

from __future__ import annotations

from pathlib import Path

from debate_core.evidence.manifest import CardManifest

__all__ = ["EmbeddedManifestError", "read_embedded_manifest", "read_embedded_manifest_bytes"]


class EmbeddedManifestError(ValueError):
    pass


def read_embedded_manifest_bytes(path: Path) -> bytes:
    raise EmbeddedManifestError(f"{path.name} holds no embedded manifest")


def read_embedded_manifest(path: Path) -> CardManifest:
    return CardManifest.model_validate_json(read_embedded_manifest_bytes(path))
