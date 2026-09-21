"""Shared primitives every domain model is built from.

`debate_core.domain` is the platform's permanent vocabulary. It holds data and invariants only:
no I/O, no HTTP, no AWS SDK, no web framework. Storage and provider access go through the ports
in `debate_core.application` (task v1-e02-t02-ports), so V2 can swap DynamoDB/S3 in behind the
same entities.

This module defines four things the entity modules reuse:

* :class:`DomainModel` — the frozen, `extra="forbid"` Pydantic base, plus :meth:`DomainModel.evolve`
  as the one safe way to produce a changed copy (it revalidates, so invariants cannot be bypassed).
* :class:`DomainEntity` — the persisted-record base: `owner_id`/`organization_id` tenancy
  references, UTC `created_at`/`updated_at`, and the `revision` counter used for optimistic
  concurrency (architecture proposal §7).
* Constrained scalar types: :data:`Ulid`, :data:`UtcDatetime`, :data:`Sha256Hex`, :data:`HttpUrlStr`
  and :data:`NonEmptyText`.
* The injectable id factory (:func:`new_id`, :func:`use_id_factory`) that supplies entity ids.

Only `owner_id` and `organization_id` identify people, and both are opaque ULIDs. Student names
and email addresses are deliberately absent from the domain model (architecture proposal §14,
data minimization).
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints
from ulid import ULID

__all__ = [
    "CROCKFORD_BASE32_ALPHABET",
    "ORGANIZATION_ID_FIELD",
    "OWNER_ID_FIELD",
    "DomainEntity",
    "DomainModel",
    "HttpUrlStr",
    "IdFactory",
    "NonEmptyText",
    "SHA256_HEX_PATTERN",
    "Sha256Hex",
    "ULID_PATTERN",
    "Ulid",
    "UtcDatetime",
    "new_id",
    "use_id_factory",
    "utc_now",
]


# --------------------------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------------------------

#: Crockford base32, the ULID alphabet. `I`, `L`, `O` and `U` are excluded on purpose.
CROCKFORD_BASE32_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: A ULID is 26 Crockford-base32 characters. The 48-bit timestamp caps the first character at `7`.
ULID_PATTERN = r"^[0-7][0-9ABCDEFGHJKMNPQRSTVWXYZ]{25}$"

Ulid = Annotated[
    str,
    StringConstraints(pattern=ULID_PATTERN, min_length=26, max_length=26),
]
"""A ULID in its canonical 26-character textual form.

ULIDs are lexicographically sortable by creation time, which is what makes them a better fit than
UUIDv4 for DynamoDB sort keys in V2. They are carried as strings so that JSON round-trips and
exported schemas stay trivial.
"""

#: The signature of an id factory: no arguments, returns a new :data:`Ulid`.
IdFactory = Callable[[], str]


def generate_ulid() -> str:
    """Return a new ULID string seeded from the current time and the system CSPRNG."""
    return str(ULID())


_id_factory: ContextVar[IdFactory] = ContextVar("debate_core_id_factory", default=generate_ulid)


def new_id() -> str:
    """Return a new entity id from the currently installed factory.

    Every entity's id field defaults to this function, so tests (and any future deterministic
    replay) can make ids predictable with :func:`use_id_factory` without touching the models.
    """
    return _id_factory.get()()


@contextmanager
def use_id_factory(factory: IdFactory) -> Generator[None]:
    """Install `factory` as the id source for the duration of the block.

    The factory is held in a :class:`~contextvars.ContextVar`, so an override is confined to the
    current thread or asyncio task and is always undone on exit.
    """
    token = _id_factory.set(factory)
    try:
        yield
    finally:
        _id_factory.reset(token)


# --------------------------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------------------------


def _require_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalize every aware datetime to UTC."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            "timestamps must be timezone-aware; got a naive datetime. "
            "Use datetime.now(UTC) or attach an explicit tzinfo."
        )
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]
"""A timezone-aware timestamp, always stored in UTC.

Naive datetimes are rejected rather than assumed to be UTC: an evidence card's retrieval and
publication times are provenance, and a silently mislabelled timezone is a provenance error.
"""


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


# --------------------------------------------------------------------------------------------
# Other constrained scalars
# --------------------------------------------------------------------------------------------

#: Lowercase hex digest of a SHA-256 hash, as written by the evidence-integrity pipeline (§8).
SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"

Sha256Hex = Annotated[
    str,
    StringConstraints(pattern=SHA256_HEX_PATTERN, min_length=64, max_length=64),
]
"""A SHA-256 digest as 64 lowercase hex characters."""

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Text that must carry at least one non-whitespace character; surrounding whitespace is stripped."""


def _require_http_url(value: str) -> str:
    """Accept only absolute http(s) URLs; everything else is a provenance hazard."""
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http or https, got {parts.scheme or 'no'} scheme: {value!r}")
    if not parts.netloc:
        raise ValueError(f"URL must be absolute and include a host: {value!r}")
    if value != value.strip() or any(character.isspace() for character in value):
        raise ValueError(f"URL must not contain whitespace: {value!r}")
    return value


HttpUrlStr = Annotated[str, AfterValidator(_require_http_url)]
"""An absolute `http`/`https` URL kept as a plain string.

Deliberately not `pydantic.HttpUrl`: canonical URLs are compared, hashed and used as dedupe keys
across the platform, so they must survive a round-trip byte for byte rather than being rewritten
by a URL normalizer. Canonicalization is an explicit step in the retrieval layer (E04).
"""


# --------------------------------------------------------------------------------------------
# Model bases
# --------------------------------------------------------------------------------------------


class DomainModel(BaseModel):
    """Base class for every domain model.

    * `frozen=True` — domain objects are values. Changing one means producing a new object with
      :meth:`evolve`, which revalidates and therefore cannot bypass an invariant. Models that
      carry a mapping field (for example `SearchResult.source_quality_features`) are immutable
      but not hashable, because their contents are not.
    * `extra="forbid"` — an unknown key in stored or model-supplied JSON is a bug, not a field to
      keep. Failing loudly here is what stops a renamed provenance field from being silently lost.
    * `validate_default=True` — defaults go through the same validators as supplied values.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        validate_assignment=True,
        arbitrary_types_allowed=False,
    )

    def evolve(self, **changes: object) -> Self:
        """Return a revalidated copy of this model with `changes` applied.

        Unlike :meth:`pydantic.BaseModel.model_copy`, this re-runs every field and model validator,
        so an evolved object cannot end up in a state the constructor would have rejected.
        """
        return type(self).model_validate({**self.__dict__, **changes})


#: Description shared by every entity's `owner_id` field.
OWNER_ID_FIELD = "ULID of the user who owns this record."

#: Description shared by every entity's `organization_id` field.
ORGANIZATION_ID_FIELD = "ULID of the owning organization (school or team); None outside a tenant."


class DomainEntity(DomainModel):
    """Base class for models that are persisted as their own record.

    Subclasses add their own ULID primary key (`article_id`, `card_id`, …) rather than inheriting a
    generic `id`, so the field name stays meaningful in storage, logs and JSON schemas.

    They also declare their own `owner_id` and `organization_id` — see :data:`OWNER_ID_FIELD` —
    because ownership differs by entity: a `Card` belongs to exactly one student, while an
    `Article` is a shared description of a public source that may have no owner at all.

    `revision` is the optimistic-concurrency counter required by architecture proposal §7: a
    repository writes a record only if the stored revision still matches the one it read, so a
    background reprocessing job cannot silently overwrite a student's edit.
    """

    created_at: UtcDatetime = Field(
        default_factory=utc_now,
        description="When this record was first created, in UTC.",
    )
    updated_at: UtcDatetime = Field(
        default_factory=utc_now,
        description="When this record was last written, in UTC.",
    )
    revision: int = Field(
        default=1,
        ge=1,
        description="Optimistic-concurrency counter; incremented by the repository on every write.",
    )
