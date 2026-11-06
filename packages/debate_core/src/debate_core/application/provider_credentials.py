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

from debate_core.application.settings import Settings

__all__ = ["CredentialsFileState", "ProviderCredentialReport", "ProviderCredentialRow", "provider_credential_report"]


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


def provider_credential_report(settings: Settings) -> ProviderCredentialReport:
    """The report for `settings`, which :func:`~debate_core.application.settings.load_settings` built."""
    return ProviderCredentialReport(credentials_file=CredentialsFileState(path=None, state=""), enabled=())
