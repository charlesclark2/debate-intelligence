"""Skeleton (red run): an OPC package written the ordinary way."""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from io import BytesIO
from typing import Final

__all__ = ["ENTRY_ATTRIBUTES", "FIXED_ZIP_TIMESTAMP", "write_package"]

FIXED_ZIP_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)
ENTRY_ATTRIBUTES: Final = 0o600 << 16


def write_package(parts: Sequence[tuple[str, bytes]]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts:
            archive.writestr(name, data)
    return buffer.getvalue()
