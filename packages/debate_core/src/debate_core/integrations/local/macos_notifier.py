"""The operator's Mac notification centre, as a :class:`~debate_core.application.ports.notifier.Notifier`.

`osascript` runs AppleScript's `display notification`, which needs no app bundle, no entitlement
and no third-party package, and is on every Mac.

## Why the text travels as arguments, not inside the script

The obvious form — `osascript -e 'display notification "<message>" with title "<title>"'` — puts
the text inside AppleScript source, so a `"` in it ends the string and whatever follows runs as
AppleScript. Escaping would close that, but only as long as the escaping is right. Here the script
is a fixed constant that reads its text from `argv` (`on run argv`), so the text is never parsed as
source at all and there is nothing to escape. Control characters are still removed, and the text
shortened, because a notification is one glance and not a log: the title and the subtitle to a
line, the body to what holds a failed stage's hint whole.

## What a banner shows (`v1-e34-t23`)

On the operator's Mac, on 2026-10-15, a banner showed its title, a subtitle cut at about forty
characters, and about ten lines of about forty-five characters of its body; the rest is shown when
the notification is opened. The fix command was the subtitle and the end of the body, and was cut
in both. So the subtitle is the notification's own short subtitle, the run and its environment,
and the body starts with the fix (:attr:`~debate_core.application.ports.notifier.Notification.body`).
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
"""The title and the subtitle: one line each."""

_MAX_BODY_CHARACTERS: Final = 1500
"""The body. Long enough for a failed stage's hint whole (`v1-e34-t19`): a hint is the fix, and one
cut off half-way is worse than none. Notification Centre shows the first lines in the banner and
the rest when the notification is opened, so the verdict is in the title and the fix command is
the first thing in the body (`v1-e34-t23`)."""
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
                _clean(notification.body, limit=_MAX_BODY_CHARACTERS),
                _clean(notification.title),
                _clean(notification.subtitle or ""),
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


def _clean(text: str, *, limit: int = _MAX_FIELD_CHARACTERS) -> str:
    """One line of printable text, no longer than `limit`."""
    flattened = "".join(character if character.isprintable() else " " for character in text)
    flattened = " ".join(flattened.split())
    if len(flattened) > limit:
        return flattened[: limit - 1] + "…"
    return flattened
