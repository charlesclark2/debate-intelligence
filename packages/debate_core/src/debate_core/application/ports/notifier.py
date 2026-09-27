"""How an unattended run tells the operator something needs doing (`v1-e34-t03-sync-monitoring`).

The weekly caselist pull runs under launchd with nobody watching. A run that failed, a
caselist_token that expired, or an AWS SSO session that timed out overnight is only fixed if
somebody finds out, and a log file nobody opens is not finding out. So the run posts one
:class:`Notification` per condition, naming the one command that fixes it, through a
:class:`Notifier`.

## Adapters

| Adapter | Where | What it does |
|---|---|---|
| `integrations.local.macos_notifier.MacOsNotifier` | the operator's Mac | `osascript` notification |
| :class:`NullNotifier` | everywhere else, and every CI test | nothing |
| :class:`RecordingNotifier` | tests | keeps what it was given |

`caselist.notifier` in the environment's profile chooses between them; the `test` profile says
`none`, so no test can put a banner on a developer's screen.

## What a notification may say

A title, one sentence, and a command. **Never** a token, a credential, a file's contents, card
text, a school, a team code or a student's name (`docs/policies/caselist-data-use.md` rule 4, and
the task spec's forbidden list). The text is built from counts, caselist slugs, stage names and
error *class* names — never from an exception's message, which is the one place a disclosure path
could hide — and it is on the caller to keep it that way; the adapters send what they are given.

## Delivery is best effort

A notifier that cannot notify must not fail the run it is reporting on: the run record is already
written by the time a notification is sent. Adapters swallow and log their own failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

__all__ = ["Notification", "Notifier", "NullNotifier", "RecordingNotifier"]


@dataclass(frozen=True, slots=True)
class Notification:
    """One thing the operator has to do something about, and the command that does it."""

    title: str
    """Short: which job, and what happened. E.g. `caselist pull failed`."""

    message: str
    """One sentence. Counts, slugs, stage names and error class names only."""

    fix_command: str
    """The one command that fixes it, e.g. `debate-research caselist auth login`."""

    @property
    def text(self) -> str:
        """The message and its fix as one line, for adapters with a single text field."""
        return f"{self.message} Fix: {self.fix_command}"


class Notifier(Protocol):
    """Posts a notification the operator will see without going looking for it."""

    def notify(self, notification: Notification) -> None:
        """Deliver `notification`, best effort. Never raises for a failed delivery."""
        ...


class NullNotifier:
    """Notifies nobody. The default off the operator's Mac, and in every CI test."""

    def notify(self, notification: Notification) -> None:
        return None


@dataclass
class RecordingNotifier:
    """Keeps every notification it is given, so a test can assert on what would have been shown."""

    sent: list[Notification] = field(default_factory=lambda: list[Notification]())

    def notify(self, notification: Notification) -> None:
        self.sent.append(notification)
