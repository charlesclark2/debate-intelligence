"""The environments a command may write a bucket in, and the flag a write to production needs.

Shared by `store`, the `caselist` commands and `landscape`, so each spells and checks them alike.
They lived in :mod:`debate_cli.commands.store` until v1-e01-t32, and every command that needed them
imported that command's module, and with it everything `store` imports.
"""

from __future__ import annotations

from debate_core.application.settings import Environment

__all__ = ["CONFIRM_PROD_FLAG", "SYNCABLE_ENVIRONMENTS"]

#: The environments that name a real bucket. `test` is deliberately not one of them.
SYNCABLE_ENVIRONMENTS = (Environment.DEV, Environment.PROD)

#: Confirmation a push to production needs, spelled the way the rest of the CLI spells one.
CONFIRM_PROD_FLAG = "--confirm-prod"
