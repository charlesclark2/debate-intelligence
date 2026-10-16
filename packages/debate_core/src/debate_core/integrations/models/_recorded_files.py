"""Reading and writing the JSON files the fake and replay routers serve answers from.

Both kinds of file are committed and reviewed in pull requests, so both are written the same way:
pretty-printed, keys sorted, UTF-8 as itself rather than as escapes, one trailing newline. A
reviewer reads a diff of a recorded answer like any other diff.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Final, cast

from debate_core.integrations.models.errors import FixtureFileError

__all__ = ["read_json_object", "safe_directory_name", "write_pretty_json"]

_SAFE_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
"""A prompt id that is also a directory name on every platform: no separators, no leading dot."""


def safe_directory_name(prompt_id: str) -> str:
    """`prompt_id`, which names the directory its answers are filed in, or a `ValueError`."""
    if not _SAFE_NAME.fullmatch(prompt_id):
        raise ValueError(
            f"prompt id {prompt_id!r} cannot name a fixture directory; use letters, digits, '.', '_' "
            "and '-', starting with a letter or digit"
        )
    return prompt_id


def read_json_object(path: Path) -> dict[str, Any] | None:
    """The JSON object in `path`; `None` when there is no such file.

    Raises :class:`FixtureFileError` when the file exists but is not a UTF-8 JSON object.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        raise FixtureFileError(path, f"it could not be read: {error}") from error
    try:
        document: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise FixtureFileError(path, f"it is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise FixtureFileError(path, f"it holds a JSON {type(document).__name__}, not an object")
    return cast(dict[str, Any], document)


def write_pretty_json(path: Path, document: object) -> None:
    """Write `document` to `path` for review, replacing any file already there in one step."""
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, path)
