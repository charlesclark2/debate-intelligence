"""Writing an OPC package whose bytes depend only on its parts.

A built file is reproducible: the same recipe and the same sources give the same bytes (`v1-e33-t02`
ac5). A zip written the ordinary way is not. `ZipFile.writestr` with a bare name stamps the clock, and
an entry records the operating system that wrote it. So every entry here is written in the order
given, dated the DOS epoch, marked as written by MS-DOS, and deflated at one fixed level. Its file
attributes are the constant `writestr` gives an entry that names none (read and write for the
owner, :data:`ENTRY_ATTRIBUTES`).
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from io import BytesIO
from typing import Final

__all__ = ["ENTRY_ATTRIBUTES", "FIXED_ZIP_TIMESTAMP", "write_package"]

#: The DOS epoch, the earliest a zip entry can carry. Any constant would do; the clock would not.
FIXED_ZIP_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)

#: What `ZipFile.writestr` records for an entry that names no attributes: `0o600`, as Unix mode bits.
ENTRY_ATTRIBUTES: Final = 0o600 << 16

_COMPRESS_LEVEL: Final = 6
_CREATED_BY_MS_DOS: Final = 0


def write_package(parts: Sequence[tuple[str, bytes]]) -> bytes:
    """Zip `(name, bytes)` parts in the order given, with nothing in them that depends on when or where."""
    names = [name for name, _ in parts]
    if len(set(names)) != len(names):
        raise ValueError("a package names each part once")
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=_COMPRESS_LEVEL) as archive:
        for name, data in parts:
            entry = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = _CREATED_BY_MS_DOS
            entry.external_attr = ENTRY_ATTRIBUTES
            archive.writestr(entry, data, compresslevel=_COMPRESS_LEVEL)
    return buffer.getvalue()
