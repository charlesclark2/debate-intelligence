"""What each enabled discovery provider has to search with, for `doctor --providers` (`v1-e41-t22`).

One row per enabled provider: whether its key or the contact email is set, which layer set it, and
what a search does without it. Never a value: a row names a source label such as
`user-env:~/.debate-research/dev.env`, and a blank value counts as missing, as the adapters treat it.
Nothing here fails. A provider without its credential still searches, or is reported as not
configured, and that is a fact about the machine rather than a fault in the installation.

The rows also say whether the per-user credentials file was read, so that a person who wrote one
can see it was found.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import SecretStr

from debate_core.application.settings import (
    ENV_NESTED_DELIMITER,
    ENV_PREFIX,
    SearchProviderName,
    Settings,
    display_user_path,
    user_credentials_file,
)

__all__ = [
    "CredentialsFileState",
    "ProviderCredentialReport",
    "ProviderCredentialRow",
    "missing_credential_cure",
    "provider_credential_report",
]


@dataclass(frozen=True, slots=True)
class ProviderCredentialRow:
    """One enabled provider: its credential's variable, whether it is set and where from, and a sentence."""

    provider: str
    label: str
    credential: str | None
    is_set: bool | None
    source: str | None
    summary: str

    def as_json(self) -> dict[str, str | bool | None]:
        return {
            "provider": self.provider,
            "label": self.label,
            "credential": self.credential,
            "set": self.is_set,
            "source": self.source,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class CredentialsFileState:
    """The per-user credentials file for this environment, as a person reads it, and whether it was read."""

    path: str | None
    state: str

    def as_json(self) -> dict[str, str | None]:
        return {"path": self.path, "state": self.state}


@dataclass(frozen=True, slots=True)
class ProviderCredentialReport:
    """The credentials file's state and one row per enabled provider, in the providers' declared order."""

    credentials_file: CredentialsFileState
    enabled: tuple[ProviderCredentialRow, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "credentials_file": self.credentials_file.as_json(),
            "enabled": [row.as_json() for row in self.enabled],
        }


@dataclass(frozen=True, slots=True)
class _Words:
    """What a provider's row says: its label, its credential's field, and the sentence either way."""

    label: str
    field: str | None = None
    when_set: str = ""
    when_missing: str = ""
    cure: str | None = None
    """What gives the provider its credential, as a search's footer says it after the missing one."""


_KEYLESS: Final = "no key needed"
_NO_ADAPTER: Final = "no adapter in this build"

_WORDS: Final[dict[SearchProviderName, _Words]] = {
    SearchProviderName.OPENALEX: _Words(
        "OpenAlex",
        "openalex_api_key",
        "API key set ({source}): with a key",
        "no OpenAlex key: keyless (a lower daily allowance)",
        "set an OpenAlex key for a higher daily allowance",
    ),
    SearchProviderName.CROSSREF: _Words(
        "Crossref",
        "contact_email",
        "contact email set ({source}): Crossref's polite pool",
        "no contact email: Crossref's public pool",
        "set a contact email for Crossref's polite pool",
    ),
    SearchProviderName.SEMANTIC_SCHOLAR: _Words(
        "Semantic Scholar",
        "semantic_scholar_api_key",
        "API key set ({source})",
        "no Semantic Scholar key: the shared pool, paced at one request a second",
        "set a Semantic Scholar key",
    ),
    SearchProviderName.RSS: _Words("RSS feeds"),
    SearchProviderName.GOOGLE_NEWS: _Words("Google News"),
    SearchProviderName.GDELT: _Words("GDELT"),
    SearchProviderName.FEDERAL_REGISTER: _Words("Federal Register"),
    SearchProviderName.GOVINFO: _Words(
        "GovInfo",
        "api_data_gov_key",
        "api.data.gov key set ({source})",
        "no GovInfo key: GovInfo not asked",
        "get a free key at api.data.gov/signup to ask GovInfo",
    ),
}
"""Every provider's words. The OpenAlex row gives no daily figure: those are OpenAlex's prices, not this
build's (the PM's ruling on `v1-e41-t22`, Q5). Semantic Scholar's row names no limit of its own either: the
adapter keeps one request a second with a key and without (v1-e07-t04)."""

PROVIDERS_WITHOUT_AN_ADAPTER: Final = frozenset({SearchProviderName.GDELT})
"""Names settings accept that this build has no adapter for: the composition root's discovery
factories (`debate_cli.container`) build every other one, and a search refuses these."""


def provider_credential_report(settings: Settings) -> ProviderCredentialReport:
    """The report for `settings`, which :func:`~debate_core.application.settings.load_settings` built.

    Settings that loaded have read the per-user file if it is there, or refused it, so "read" here
    means the file exists; `test` never reads one.
    """
    path = user_credentials_file(settings.environment)
    if path is None:
        credentials_file = CredentialsFileState(path=None, state="not read in the test environment")
    else:
        credentials_file = CredentialsFileState(
            path=display_user_path(path), state="read" if path.is_file() else "not there"
        )
    enabled = set(settings.providers.enabled)
    rows = tuple(_row(settings, name) for name in SearchProviderName if name in enabled)
    return ProviderCredentialReport(credentials_file=credentials_file, enabled=rows)


def _row(settings: Settings, name: SearchProviderName) -> ProviderCredentialRow:
    words = _WORDS[name]
    if name in PROVIDERS_WITHOUT_AN_ADAPTER or words.field is None:
        summary = _NO_ADAPTER if name in PROVIDERS_WITHOUT_AN_ADAPTER else _KEYLESS
        return ProviderCredentialRow(name.value, words.label, None, None, None, summary)
    value = getattr(settings.providers, words.field)
    # Blank is missing, as every adapter strips and treats it.
    is_set = isinstance(value, SecretStr) and bool(value.get_secret_value().strip())
    source = settings.field_sources.get(f"providers.{words.field}", "default")
    variable = f"{ENV_PREFIX}PROVIDERS{ENV_NESTED_DELIMITER}{words.field.upper()}"
    summary = words.when_set.format(source=source) if is_set else words.when_missing
    return ProviderCredentialRow(name.value, words.label, variable, is_set, source, summary)


def missing_credential_cure(provider: str) -> str | None:
    """What a person does to give `provider` the credential it lacks, or None when it needs none.

    `provider` is a settings name; one this build does not know needs nothing. A search names an
    enabled provider that is not configured with these words after its reason (v1-e07-t15).
    """
    try:
        name = SearchProviderName(provider)
    except ValueError:
        return None
    return _WORDS[name].cure
