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

A title, a short subtitle, a sentence or two, a command, and sometimes a hint. **Never** a token, a
credential, a file's contents, card text, a school, a team code, a student's name or a path on the operator's
machine (`docs/policies/caselist-data-use.md` rule 4, and the task specs' forbidden lists). The
text is built from counts, caselist slugs, stage names, error *class* names and error codes — never
from an exception's message, which is the one place a disclosure path could hide — and a hint is
one of this project's own sentences about a fix, which names a directory by what it is for
(`v1-e34-t19`). It is on the caller to keep it that way; the adapters send what they are given.

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

    hint: str | None = None
    """The fix a failed stage gives in the run summary, when it has one that is not a command: a
    permission on this machine's data directory, a grant the profile lacks, a file a person has to
    repair (`v1-e34-t19`). This project's own sentence, naming a directory by its role and never by
    its path; `None` when the command says it all."""

    subtitle: str | None = None
    """A few words under the title, short enough to be shown whole: the run and its environment,
    `Run 20261014T060000Z (prod)` (`v1-e34-t23`). Never the command, which a banner cuts there."""

    @property
    def text(self) -> str:
        """The message, its hint and its fix as one line, for adapters with a single text field."""
        hint = f" {self.hint}" if self.hint else ""
        return f"{self.message}{hint} Fix: {self.fix_command}"

    @property
    def body(self) -> str:
        """The fix first, then the message and its hint: for a banner that shows its first lines.

        On the operator's Mac a banner shows about ten lines of about forty-five characters of its
        body, and the rest only when it is opened (seen 2026-10-15). A fix at the end was cut off,
        so it comes first (`v1-e34-t23`), set apart from the sentence by a dash that no command
        ends with.
        """
        hint = f" {self.hint}" if self.hint else ""
        return f"Fix: {self.fix_command} — {self.message}{hint}"


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
