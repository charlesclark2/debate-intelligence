"""The operator's Mac notification centre, as a :class:`~debate_core.application.ports.notifier.Notifier`.

`osascript` runs AppleScript's `display notification`, which needs no app bundle, no entitlement
and no third-party package, and is on every Mac.

## Why the text travels as arguments, not inside the script

The obvious form — `osascript -e 'display notification "<message>" with title "<title>"'` — puts
the text inside AppleScript source, so a `"` in it ends the string and whatever follows runs as
AppleScript. Escaping would close that, but only as long as the escaping is right. Here the script
is a fixed constant that reads its text from `argv` (`on run argv`), so the text is never parsed as
source at all and there is nothing to escape. Control characters are still removed, and the text
shortened, because a notification is one glance and not a log.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable, Sequence
from typing import Final

from debate_core.application.ports.notifier import Notification

__all__ = ["OSASCRIPT", "MacOsNotifier"]

logger = logging.getLogger(__name__)

OSASCRIPT: Final = "osascript"

_SCRIPT: Final = (
    "on run argv",
    "display notification (item 1 of argv) with title (item 2 of argv) subtitle (item 3 of argv)",
    "end run",
)
"""Fixed AppleScript. The notification's text arrives as `argv`, never as part of this source."""

_MAX_FIELD_CHARACTERS: Final = 240
_TIMEOUT_SECONDS: Final = 10.0

type CommandRunner = Callable[[Sequence[str]], int]
"""Runs one command and returns its exit status. Replaced in tests; nothing real is launched."""


def _run_osascript(command: Sequence[str]) -> int:
    completed = subprocess.run(  # noqa: S603 - a fixed executable and a fixed script; text is argv
        list(command), capture_output=True, timeout=_TIMEOUT_SECONDS, check=False
    )
    return completed.returncode


class MacOsNotifier:
    """Posts to macOS Notification Centre through `osascript`.

    Args:
        run: How the command is run. Defaults to a `subprocess` call; tests pass a recorder.
        executable: The `osascript` to run; found on `PATH` when not given.
    """

    def __init__(self, *, run: CommandRunner | None = None, executable: str | None = None) -> None:
        self._run = run or _run_osascript
        self._executable = executable or shutil.which(OSASCRIPT) or f"/usr/bin/{OSASCRIPT}"

    def command_for(self, notification: Notification) -> list[str]:
        """The exact argv this notifier runs for `notification`."""
        arguments = [self._executable]
        for line in _SCRIPT:
            arguments.extend(("-e", line))
        arguments.extend(
            (
                _clean(notification.text),
                _clean(notification.title),
                _clean(notification.fix_command),
            )
        )
        return arguments

    def notify(self, notification: Notification) -> None:
        """Post `notification`. A failure is logged and swallowed: the run is already recorded."""
        try:
            status = self._run(self.command_for(notification))
        except (OSError, subprocess.SubprocessError) as failed:
            logger.warning("macOS notification could not be shown: %s", type(failed).__name__)
            return
        if status != 0:
            logger.warning("macOS notification could not be shown: osascript exited %d", status)


def _clean(text: str) -> str:
    """One line of printable text, no longer than a notification shows."""
    flattened = "".join(character if character.isprintable() else " " for character in text)
    flattened = " ".join(flattened.split())
    if len(flattened) > _MAX_FIELD_CHARACTERS:
        return flattened[: _MAX_FIELD_CHARACTERS - 1] + "…"
    return flattened
