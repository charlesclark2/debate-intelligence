"""Who a credential is signed in as: the question a takedown asks before it does anything.

The evidence bucket is reached with two credentials, and only one of them may delete
(:mod:`~debate_core.application.ports.evidence_versions`). Which one a profile *is* cannot be told
from what the bucket lets it read: every read the takedown role is granted, the everyday role is
granted too, since `v1-e29-t06` gave it the version listing. The only calls that tell them apart
are the deletes, and a delete is not something to try in order to find out. So the takedown asks
the account who the credential is, which needs no grant and changes nothing, and compares the
answer with the role a takedown runs as
(:func:`~debate_core.application.caselist.removal_service.preflight`, `v1-e29-t08`).

The answer is a role's **name** and nothing else. An implementation never returns, logs or puts in
an error the account the role is in, the role's full identifier or the address the session was
started at: none of them is needed to tell two roles apart, and none of them belongs in a message.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["CallerIdentity"]


@runtime_checkable
class CallerIdentity(Protocol):
    """Says which role a credential is signed in as."""

    async def assumed_role_name(self) -> str | None:
        """The name of the role the credential has assumed, or `None` when it is not a role at all.

        `None` is an answer, not a failure: a user's own long-lived key, or the account itself. A
        credential that cannot be asked — an expired session, an account that did not answer —
        raises the :class:`~debate_core.application.errors.StoreError` that says which.
        """
        ...
