"""`--i-have-lawful-access`: the attestation `fetch --paste` stores a user's copy on.

`fetch` takes it; `cut --from-paste` names it in the hint it gives when no copy is stored
(`v1-e06-t08`). It lived in :mod:`debate_cli.commands.fetch` until then.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ATTESTATION_FLAG"]

ATTESTATION_FLAG: Final = "--i-have-lawful-access"
