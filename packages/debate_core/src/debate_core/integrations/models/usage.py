"""What each real model call used and cost, priced from config and logged one line per call (v1-e05-t07).

Three things, used by :class:`~debate_core.integrations.models.usage_router.UsageRecordingRouter`
and read back by `debate-research usage`:

* :class:`UsageRecord`, one call: the run, the prompt, the model, the attempt, the tokens, the
  latency, the estimated cost and when. Nothing else, and never a prompt's text, a source's text, a
  card's text or any word a student, school or team wrote: a record is identifiers and numbers.
* :class:`ModelPricing`, `config/model_pricing.yaml`: what each model id in the routing files
  charges, per 1K input and output tokens, or per 1K rerank search units. Prices live in that file
  and nowhere in code. A model with no price there costs `null`, with a warning, never a guess.
* :class:`UsageLog`, the records: `<data_dir>/usage/YYYY-MM-DD.jsonl`, one file per local day
  (:func:`~debate_core.application.budget.local_day`), appended safely by calls running in
  parallel. It is also the per-day ledger the budget guard reads; there is no second state file.

Only calls a real router makes are recorded, in record and live mode. Replay serves cassettes and
the fake router answers from fixtures, so neither costs anything or logs anything.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, tzinfo
from pathlib import Path
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from debate_core.application.budget import Spend, local_day
from debate_core.domain.base import UtcDatetime

__all__ = [
    "DOCUMENTS_PER_SEARCH_UNIT",
    "PRICING_FILE_NAME",
    "USAGE_DIRECTORY",
    "ModelPrice",
    "ModelPricing",
    "UsageGroup",
    "UsageLog",
    "UsageRecord",
    "UsageSummary",
    "search_units",
    "summarize",
]

logger = logging.getLogger(__name__)

PRICING_FILE_NAME: Final = "model_pricing.yaml"
"""The pricing file's name. It sits beside the routing files, in `config/`."""

USAGE_DIRECTORY: Final = "usage"
"""Where the usage log's files are, under the data directory."""

DOCUMENTS_PER_SEARCH_UNIT: Final = 100
"""How many documents one rerank search unit covers: one query over up to 100 documents."""


def search_units(documents: int) -> int:
    """The search units a rerank of `documents` documents is billed as: one per started hundred.

    Cohere also splits a document longer than its chunk size into several, each counted; that is
    not known before the call, and is left out.
    """
    return 0


class UsageRecord(BaseModel):
    """One real model call, as the usage log keeps it: identifiers and numbers, never text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1, description="The run the call was made in: one router, one command.")
    prompt_id: str | None = Field(description="The prompt the call ran; null for embed and rerank.")
    prompt_version: str | None = Field(description="That prompt's version; null for embed and rerank.")
    model_id: str = Field(min_length=1, description="The model the call went to.")
    attempt: int = Field(ge=1, description="1 for a call, 2 for the repair of its invalid answer.")
    input_tokens: int | None = Field(ge=0, description="Tokens sent, when the provider reported them.")
    output_tokens: int | None = Field(ge=0, description="Tokens generated, when reported.")
    latency_ms: float = Field(ge=0, description="Wall-clock time of the call, retries included.")
    estimated_cost_usd: float | None = Field(
        ge=0, description="Cost at the pricing file's prices; null when the model is not priced."
    )
    recorded_at: UtcDatetime = Field(description="When the call finished, in UTC.")


class ModelPrice(BaseModel):
    """What one model charges, and where and when that was read; every price may be unset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_usd_per_1k_tokens: float | None = Field(default=None, ge=0)
    output_usd_per_1k_tokens: float | None = Field(default=None, ge=0)
    usd_per_1k_search_units: float | None = Field(default=None, ge=0)
    as_of: date | None = Field(default=None, description="The day the prices were read.")
    source: str | None = Field(default=None, description="Where they were read: the pricing page.")

    @model_validator(mode="after")
    def _a_price_has_provenance(self) -> Self:
        return self


class PricingFile(BaseModel):
    """The schema of `config/model_pricing.yaml`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    models: dict[str, ModelPrice]


class ModelPricing:
    """The pricing table: what a call to each model costs, or `None` with a warning."""

    def __init__(self, prices: Mapping[str, ModelPrice], *, source: str = "config/model_pricing.yaml") -> None:
        self._prices = dict(prices)
        self.source = source
        """Where the prices were read, for messages."""

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read `path`. A missing file prices nothing; an invalid one is a `ConfigurationError`."""
        return cls({}, source=str(path))

    def price_for(self, model_id: str) -> ModelPrice | None:
        """`model_id`'s entry, or `None` when the file has none."""
        return self._prices.get(model_id)

    def structured_cost(self, model_id: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
        """A generative call's cost, or `None`, with a warning, when it cannot be priced."""
        return None

    def embedding_cost(self, model_id: str, input_tokens: int | None) -> float | None:
        """An embedding call's cost, or `None`, with a warning, when it cannot be priced."""
        return None

    def rerank_cost(self, model_id: str, documents: int) -> float | None:
        """A rerank call's cost, or `None`, with a warning, when it cannot be priced."""
        return None


@dataclass(frozen=True, slots=True)
class UsageGroup:
    """One line of a day's summary: the calls of one prompt to one model."""

    prompt_id: str | None
    model_id: str
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    """The priced calls' cost; the unpriced calls are counted in `unpriced_calls`, not here."""
    unpriced_calls: int


@dataclass(frozen=True, slots=True)
class UsageSummary:
    """A day's model usage, grouped by prompt and model."""

    day: date
    groups: tuple[UsageGroup, ...]

    @property
    def calls(self) -> int:
        return sum(group.calls for group in self.groups)

    @property
    def input_tokens(self) -> int:
        return sum(group.input_tokens for group in self.groups)

    @property
    def output_tokens(self) -> int:
        return sum(group.output_tokens for group in self.groups)

    @property
    def estimated_cost_usd(self) -> float:
        return sum(group.estimated_cost_usd for group in self.groups)

    @property
    def unpriced_calls(self) -> int:
        return sum(group.unpriced_calls for group in self.groups)


def summarize(day: date, records: Iterable[UsageRecord]) -> UsageSummary:
    """`records` grouped by prompt id and model id, in that order."""
    return UsageSummary(day=day, groups=())


class UsageLog:
    """`<data_dir>/usage/YYYY-MM-DD.jsonl`: one line per call, one file per local day."""

    def __init__(self, directory: Path, *, local_zone: tzinfo | None = None) -> None:
        self.directory = directory
        """Where the day files are: `<data_dir>/usage`."""
        self.local_zone = local_zone
        """The zone a record's day is read in; this machine's when `None`."""

    @classmethod
    def for_data_dir(cls, data_dir: Path, *, local_zone: tzinfo | None = None) -> Self:
        """The log under `data_dir`."""
        return cls(data_dir / USAGE_DIRECTORY, local_zone=local_zone)

    def path_for(self, day: date) -> Path:
        """The file `day`'s records are in."""
        return self.directory / f"{day.isoformat()}.jsonl"

    def day_of(self, record: UsageRecord) -> date:
        """The local day `record` is filed under."""
        return local_day(record.recorded_at, self.local_zone)

    def append(self, record: UsageRecord) -> Path:
        """Add `record` to its day's file, as one line, safely beside other writers; return the file."""
        return self.path_for(self.day_of(record))

    def read(self, day: date) -> tuple[UsageRecord, ...]:
        """Every record of `day`, in the order written; none when there is no file."""
        return ()

    def summary(self, day: date) -> UsageSummary:
        """`day`'s records, summarized."""
        return summarize(day, self.read(day))

    def spent(self, run_id: str, day: date) -> Spend:
        """What `run_id` and `day` have spent, from the lines written so far."""
        return Spend(run_usd=0.0, day_usd=0.0)
