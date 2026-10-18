"""The evidence profiles an installation is configured with: is each defined, and who is it?

`v1-e34-t22`. The evidence bucket is reached through named AWS profiles, and the names live in
settings: the environment's everyday profile (`storage.s3.aws_profile`), and the takedown profile
when `DEBATE_REMOVAL_PROFILE` is set. A setting that names a profile this machine's AWS config does
not define is not found until something tries to use it, and the first thing to use it may be the
weekly pull at six on a Wednesday morning, which then refuses to start (`v1-e29-t07`).

:class:`EvidenceProfileCheck` asks ahead of time. For each configured profile it says whether the
profile is defined and which permission set it is signed in as, through the
:class:`~debate_core.application.ports.caller_identity.CallerIdentity` port the takedown preflight
already asks (`v1-e29-t08`). `debate-research doctor --evidence-profiles` runs it, and so does
`ops/launchd/install.sh --check-launchd`, under launchd with the agent's own environment.

## What fails a check, and what does not

Only a profile that is **not defined** (:attr:`ProfileFinding.defined`). That is the one finding
nothing but an edit cures, and the one that makes a scheduled run refuse to start.

* **An expired session** is reported as expired, with the command that renews it. It is not a
  failure: the weekly run captures and imports without a session and publishes after a login.
* **An account that did not answer** is no verdict on the profile at all.
* **A profile signed in as an unexpected permission set** is said, in the sentence. The takedown
  profile is compared with the permission set a takedown runs as
  (:func:`~debate_core.application.caselist.removal_service.takedown_permission_set`), which is
  the comparison the takedown's own preflight refuses on; here it is advice, given early. An
  everyday profile signed in as the **other environment's** permission set is said to be, since
  this environment's bucket grants that set nothing (`v1-e29-t09`): most likely a profile copied
  from the other environment's block of the AWS config. A takedown profile signed in as the other
  environment's set is told whose set it is in the same words, before it is told what a takedown
  runs as (`v1-e34-t25`).

## What a finding may hold

A profile's name, the name of the setting that holds it, and a **permission set's** name. Never
the role's own name, the account it is in, its full identifier, the address a session was started
at, or where the AWS config is: the port returns none of them but the role's name, and that is
reduced to the permission set here and dropped. A role that is no permission set's is said to be
one, and not named.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from debate_core.application.caselist.removal_service import permission_set_of, takedown_permission_set
from debate_core.application.errors import StoreCredentialsExpired, StoreError, StoreProfileNotConfigured
from debate_core.application.ports.caller_identity import CallerIdentity

__all__ = [
    "ConfiguredProfile",
    "EvidenceProfileCheck",
    "ProfileFinding",
    "ProfileSession",
]

_ASK_AGAIN: Final = "Run the check again when this machine can reach AWS."

#: The two permission sets each environment's bucket module defines, `Debate<Env>EvidenceOperator`
#: and `Debate<Env>EvidenceRemoval` (`infrastructure/modules/evidence_bucket/operator_access.tf`):
#: which environment a set is for, read from its name.
_ENVIRONMENTS_SET: Final = re.compile(r"Debate(?P<environment>[A-Z][a-z]+)Evidence(?:Operator|Removal)")


@dataclass(frozen=True, slots=True)
class ConfiguredProfile:
    """One AWS profile this installation's settings name, and which setting names it."""

    setting: str
    """The setting the name came from, as an operator would look for it:
    `"storage.s3.aws_profile"`, `"DEBATE_REMOVAL_PROFILE"`."""

    name: str
    """The profile's name."""

    for_takedowns: bool = False
    """Whether this is the profile a takedown deletes with, which has one permission set it must be."""


class ProfileSession(StrEnum):
    """What was learnt by asking who a profile is signed in as."""

    SIGNED_IN = "signed_in"
    """AWS answered."""

    EXPIRED = "expired"
    """The profile is defined and its session has expired, or was never started."""

    NOT_DEFINED = "not_defined"
    """The AWS config does not define the profile, so there was nothing to ask."""

    NO_ANSWER = "no_answer"
    """The profile is defined and AWS did not answer: no verdict either way."""


@dataclass(frozen=True, slots=True)
class ProfileFinding:
    """What the check found for one configured profile."""

    setting: str
    profile: str
    session: ProfileSession
    permission_set: str | None
    """The permission set the profile is signed in as, or `None`: when it is not signed in, and
    when what it is signed in as is no permission set's role."""

    summary: str
    """One clause a person reads after the profile's name: `defined, and signed in as …`."""

    hint: str | None = None
    """What to do about it, when there is something: the adapter's fix for a profile that is not
    defined, or the command that renews an expired session."""

    @property
    def defined(self) -> bool:
        """Whether this machine's AWS config defines the profile."""
        return self.session is not ProfileSession.NOT_DEFINED

    def as_json(self) -> dict[str, object]:
        """The finding as `doctor --json` reports it."""
        return {
            "setting": self.setting,
            "profile": self.profile,
            "defined": self.defined,
            "session": str(self.session),
            "permission_set": self.permission_set,
            "summary": self.summary,
            "hint": self.hint,
        }


class EvidenceProfileCheck:
    """Asks, for each configured evidence profile, whether it is defined and who it is signed in as.

    Args:
        profiles: The profiles this installation's settings name, in the order to report them.
        caller_for: Builds the :class:`CallerIdentity` for one profile. Building it is where a
            profile the AWS config does not define is refused, so it is called here, inside the
            check, and never by whoever builds the check.
        environment: `dev` or `prod`: which environment's takedown permission set the takedown
            profile is compared with.
    """

    def __init__(
        self,
        *,
        profiles: Sequence[ConfiguredProfile],
        caller_for: Callable[[ConfiguredProfile], CallerIdentity],
        environment: str,
    ) -> None:
        self._profiles = tuple(profiles)
        self._caller_for = caller_for
        self._environment = environment

    async def run(self) -> tuple[ProfileFinding, ...]:
        """One finding for each configured profile, in order. One profile's answer never stops
        another being asked."""
        return tuple([await self._find(profile) for profile in self._profiles])

    async def _find(self, profile: ConfiguredProfile) -> ProfileFinding:
        try:
            role_name = await self._caller_for(profile).assumed_role_name()
        except StoreProfileNotConfigured as missing:
            return ProfileFinding(
                setting=profile.setting,
                profile=profile.name,
                session=ProfileSession.NOT_DEFINED,
                permission_set=None,
                summary="not defined in this machine's AWS config",
                hint=missing.hint,
            )
        except StoreCredentialsExpired as expired:
            return ProfileFinding(
                setting=profile.setting,
                profile=profile.name,
                session=ProfileSession.EXPIRED,
                permission_set=None,
                summary=(
                    "defined; its session has expired or was never started, so AWS cannot be asked "
                    "which permission set it is"
                ),
                hint=expired.hint,
            )
        except StoreError:
            # The account did not answer, or refused a question it never refuses. Either way
            # nothing was learnt about the profile, and what the store said is not passed on: it
            # names a bucket, and this finding is about a profile.
            return ProfileFinding(
                setting=profile.setting,
                profile=profile.name,
                session=ProfileSession.NO_ANSWER,
                permission_set=None,
                summary="defined; AWS did not answer when asked which permission set it is signed in as",
                hint=_ASK_AGAIN,
            )
        permission_set = permission_set_of(role_name)
        return ProfileFinding(
            setting=profile.setting,
            profile=profile.name,
            session=ProfileSession.SIGNED_IN,
            permission_set=permission_set,
            summary=self._signed_in(profile, role_name, permission_set),
        )

    def _signed_in(
        self, profile: ConfiguredProfile, role_name: str | None, permission_set: str | None
    ) -> str:
        """The sentence for a profile AWS answered for, with what its permission set means here."""
        if permission_set is not None:
            who = f"defined, and signed in as {permission_set}"
        elif role_name is not None:
            who = "defined, and signed in as a role that is no permission set's"
        else:
            who = "defined, and signed in, but not as a role"
        takedown = takedown_permission_set(self._environment)
        other = _environment_of(permission_set)
        if not profile.for_takedowns and other is not None and other != self._environment:
            this = self._environment
            return (
                f"{who}, which is {other}'s permission set and not {this}'s: {this}'s bucket grants it "
                "nothing, so every command that reaches the bucket will be refused"
            )
        if profile.for_takedowns and permission_set != takedown:
            whose = ""
            if other is not None and other != self._environment:
                kind = (
                    "takedown permission set"
                    if permission_set == takedown_permission_set(other)
                    else "permission set"
                )
                whose = f", which is {other}'s {kind} and not {self._environment}'s"
            return (
                f"{who}{whose}; a takedown runs only as {takedown}, so `caselist remove --execute` will "
                "refuse this profile"
            )
        if not profile.for_takedowns and permission_set == takedown:
            return (
                f"{who}, which is the takedown's permission set; the everyday profile is not meant to hold it"
            )
        return who


def _environment_of(permission_set: str | None) -> str | None:
    """The environment an evidence permission set is for, `dev` or `prod`; `None` for any other set."""
    named = _ENVIRONMENTS_SET.fullmatch(permission_set or "")
    return named.group("environment").lower() if named is not None else None
