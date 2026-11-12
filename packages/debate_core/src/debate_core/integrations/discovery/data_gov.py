"""The api.data.gov key, shared by the government providers that need one (v1-e07-t07).

GovInfo, like every API behind api.data.gov, takes a free key from api.data.gov/signup. The platform
has one setting for it, `providers.api_data_gov_key` (`DEBATE_PROVIDERS__API_DATA_GOV_KEY`, from the
environment or `.env`, never a committed profile). The Federal Register takes no key and never reads it.

:func:`require_api_data_gov_key` is what a factory calls:

* **With a key** it returns the key and registers it with
  :func:`~debate_core.integrations.discovery.redaction.protect_logs`, so no log line on a protected
  logger carries it, httpx's own included. The adapter sends it as the `X-Api-Key` header
  (:data:`API_KEY_HEADER`), one of the ways api.data.gov documents
  (api.data.gov/docs/developer-manual, read 2026-11-02), so it is never in a URL.
* **Without one** (unset, empty or spaces) it raises
  :class:`~debate_core.integrations.discovery.registry.ProviderNotConfigured`, and the registry
  records the provider as not configured instead of building it: a search reports each call to it
  as `not_configured`, with :func:`missing_key_reason`, and nothing fails. api.data.gov's shared
  `DEMO_KEY` (30 requests an hour per address) is never used in its place.

api.data.gov allows a key 1,000 requests an hour by default and answers `429` past that, with no
`Retry-After`; the wrapper then holds the provider for its exponential backoff (v1-e07-t22).
"""

from __future__ import annotations

from typing import Final

from debate_core.application.settings import ProviderSettings
from debate_core.integrations.discovery.redaction import protect_logs
from debate_core.integrations.discovery.registry import ProviderNotConfigured

__all__ = [
    "API_DATA_GOV_KEY_VARIABLE",
    "API_KEY_HEADER",
    "missing_key_reason",
    "require_api_data_gov_key",
]

API_DATA_GOV_KEY_VARIABLE: Final = "DEBATE_PROVIDERS__API_DATA_GOV_KEY"
"""The environment variable that sets `providers.api_data_gov_key`."""

API_KEY_HEADER: Final = "X-Api-Key"
"""The request header api.data.gov reads the key from."""


def missing_key_reason(provider: str) -> str:
    """What a search reports for `provider` when no key is set: the setting to set, never a value."""
    return f"{provider}: no api.data.gov key ({API_DATA_GOV_KEY_VARIABLE})"


def require_api_data_gov_key(settings: ProviderSettings, provider: str) -> str:
    """The configured key, its log protection registered; :class:`ProviderNotConfigured` without one."""
    secret = settings.api_data_gov_key
    key = secret.get_secret_value().strip() if secret is not None else ""
    if not key:
        raise ProviderNotConfigured(provider, missing_key_reason(provider))
    protect_logs((key,))
    return key
