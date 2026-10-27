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
  parallel. It is also the ledger the budget guard reads, for the run, the day and the month; there
  is no second state file. A file is named by the date in this machine's zone, and the month is
  America/Chicago's (:class:`~debate_core.application.budget.CalendarMonth`), so a month is added
  up from each record's own timestamp, over its files and one either side (v1-e05-t15).

Only calls a real router makes are recorded, in record and live mode. Replay serves cassettes and
the fake router answers from fixtures, so neither costs anything or logs anything.
"""

from __future__ import annotations

import fcntl
import logging
import os
import threading
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta, tzinfo
from pathlib import Path
from typing import Any, Final, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from debate_core.application.budget import CalendarMonth, Spend, UnreadableUsageLog, local_day
from debate_core.application.settings import ConfigurationError
from debate_core.domain.base import UtcDatetime

__all__ = [
    "DOCUMENTS_PER_SEARCH_UNIT",
    "PRICING_FILE_NAME",
    "USAGE_DIRECTORY",
    "ModelPrice",
    "ModelPricing",
    "MonthUsage",
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

MONTH_FILE_MARGIN: Final = timedelta(days=1)
"""How far outside a month's dates its records can be filed. A file is named by the date in this
machine's zone, and no zone's date is more than a day from Chicago's."""

DOCUMENTS_PER_SEARCH_UNIT: Final = 100
"""How many documents one rerank search unit covers: one query over up to 100 documents."""


def search_units(documents: int) -> int:
    """The search units a rerank of `documents` documents is billed as: one per started hundred.

    Cohere also splits a document longer than its chunk size into several, each counted; that is
    not known before the call, and is left out.
    """
    return -(-documents // DOCUMENTS_PER_SEARCH_UNIT)


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
        priced = (self.input_usd_per_1k_tokens, self.output_usd_per_1k_tokens, self.usd_per_1k_search_units)
        if any(price is not None for price in priced) and (self.as_of is None or self.source is None):
            raise ValueError("a price needs `as_of` and `source` beside it: the day it was read, and where")
        return self


class PricingFile(BaseModel):
    """The schema of `config/model_pricing.yaml`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    models: dict[str, ModelPrice]


class ModelPricing:
    """The pricing table: what a call to each model costs, or `None` with a warning."""

    def __init__(
        self, prices: Mapping[str, ModelPrice], *, source: str = "config/model_pricing.yaml"
    ) -> None:
        self._prices = dict(prices)
        self.source = source
        """Where the prices were read, for messages."""
        self._warned: set[str] = set()

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read `path`. A missing file prices nothing; an invalid one is a `ConfigurationError`.

        A missing file is not an error because an unpriced model is not one either: every call costs
        `null`, with a warning naming the file, and a run with a budget limit refuses the call.
        """
        source = str(path)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cls({}, source=f"{path} (not found)")
        except OSError as error:
            raise ConfigurationError(f"could not read {path}: {error}", source=source) from error
        try:
            # safe_load: a pricing file is data, and nothing in it may construct a Python object.
            document: Any = yaml.safe_load(text)
        except yaml.YAMLError as error:
            raise ConfigurationError(f"{path} is not valid YAML: {error}", source=source) from error
        try:
            table = PricingFile.model_validate(document)
        except ValidationError as error:
            first = error.errors()[0]
            dotted = ".".join(str(part) for part in first["loc"])
            raise ConfigurationError(
                f"{path}: {dotted or 'the file'}: {first['msg']}", field=dotted or None, source=source
            ) from error
        return cls(table.models, source=source)

    def price_for(self, model_id: str) -> ModelPrice | None:
        """`model_id`'s entry, or `None` when the file has none."""
        return self._prices.get(model_id)

    def structured_cost(
        self, model_id: str, input_tokens: int | None, output_tokens: int | None
    ) -> float | None:
        """A generative call's cost, or `None`, with a warning, when it cannot be priced."""
        price = self._prices.get(model_id)
        if price is None or price.input_usd_per_1k_tokens is None or price.output_usd_per_1k_tokens is None:
            return self._unpriced(model_id, "input and output price per 1K tokens")
        if input_tokens is None or output_tokens is None:
            return None
        return (
            input_tokens * price.input_usd_per_1k_tokens + output_tokens * price.output_usd_per_1k_tokens
        ) / 1000

    def embedding_cost(self, model_id: str, input_tokens: int | None) -> float | None:
        """An embedding call's cost, or `None`, with a warning, when it cannot be priced."""
        price = self._prices.get(model_id)
        if price is None or price.input_usd_per_1k_tokens is None:
            return self._unpriced(model_id, "input price per 1K tokens")
        if input_tokens is None:
            return None
        return input_tokens * price.input_usd_per_1k_tokens / 1000

    def rerank_cost(self, model_id: str, documents: int) -> float | None:
        """A rerank call's cost, or `None`, with a warning, when it cannot be priced."""
        price = self._prices.get(model_id)
        if price is None or price.usd_per_1k_search_units is None:
            return self._unpriced(model_id, "price per 1K search units")
        return search_units(documents) * price.usd_per_1k_search_units / 1000

    def _unpriced(self, model_id: str, needed: str) -> None:
        """No cost, and a warning the first time a model is found without one: never a guess."""
        if model_id not in self._warned:
            self._warned.add(model_id)
            logger.warning(
                "model %s has no %s in %s; its calls are logged with cost null",
                model_id,
                needed,
                self.source,
                extra={"model_id": model_id},
            )
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
        """Every call of the day."""
        return sum(group.calls for group in self.groups)

    @property
    def input_tokens(self) -> int:
        """Every input token reported."""
        return sum(group.input_tokens for group in self.groups)

    @property
    def output_tokens(self) -> int:
        """Every output token reported."""
        return sum(group.output_tokens for group in self.groups)

    @property
    def estimated_cost_usd(self) -> float:
        """The priced calls' cost."""
        return sum((group.estimated_cost_usd for group in self.groups), 0.0)

    @property
    def unpriced_calls(self) -> int:
        """The calls with no cost, which `estimated_cost_usd` leaves out."""
        return sum(group.unpriced_calls for group in self.groups)


@dataclass(frozen=True, slots=True)
class MonthUsage:
    """A calendar month's model usage in America/Chicago, in totals: what the monthly budget counts."""

    month: CalendarMonth
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    """The priced calls' cost; the unpriced calls are counted in `unpriced_calls`, not here."""
    unpriced_calls: int


def summarize(day: date, records: Iterable[UsageRecord]) -> UsageSummary:
    """`records` grouped by prompt id and model id, sorted by them, embed and rerank calls first.

    A token a provider did not report counts as none; a call with no cost is counted apart, in
    `unpriced_calls`, rather than as free.
    """
    totals: dict[tuple[str | None, str], list[float]] = defaultdict(lambda: [0, 0, 0, 0.0, 0])
    for record in records:
        group = totals[(record.prompt_id, record.model_id)]
        group[0] += 1
        group[1] += record.input_tokens or 0
        group[2] += record.output_tokens or 0
        if record.estimated_cost_usd is None:
            group[4] += 1
        else:
            group[3] += record.estimated_cost_usd
    return UsageSummary(
        day=day,
        groups=tuple(
            UsageGroup(
                prompt_id=prompt_id,
                model_id=model_id,
                calls=int(calls),
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                estimated_cost_usd=cost,
                unpriced_calls=int(unpriced),
            )
            for (prompt_id, model_id), (calls, input_tokens, output_tokens, cost, unpriced) in sorted(
                totals.items(), key=lambda item: (item[0][0] or "", item[0][1])
            )
        ),
    )


@dataclass(slots=True)
class _Tail:
    """How far one day file has been read, and what the lines read so far cost."""

    offset: int = 0
    lines: int = 0
    day_usd: float = 0.0
    run_usd: dict[str, float] = field(default_factory=dict[str, float])
    month_usd: dict[CalendarMonth, float] = field(default_factory=dict[CalendarMonth, float])
    """By each record's own month in Chicago, which is not always the month of the file's name."""


class UsageLog:
    """`<data_dir>/usage/YYYY-MM-DD.jsonl`: one line per call, one file per local day."""

    def __init__(self, directory: Path, *, local_zone: tzinfo | None = None) -> None:
        self.directory = directory
        """Where the day files are: `<data_dir>/usage`."""
        self.local_zone = local_zone
        """The zone a record's day is read in; this machine's when `None`."""
        self._lock = threading.Lock()
        self._tails: dict[Path, _Tail] = {}

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
        """Add `record` to its day's file, as one line, safely beside other writers; return the file.

        The line is written with one `write` to a file opened for appending, under an exclusive
        `flock`, so calls in parallel, threads, and other processes on this machine never
        interleave their lines.
        """
        path = self.path_for(self.day_of(record))
        line = (record.model_dump_json() + "\n").encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            written = 0
            while written < len(line):
                written += os.write(descriptor, line[written:])
        finally:
            os.close(descriptor)  # which releases the lock
        return path

    def read(self, day: date) -> tuple[UsageRecord, ...]:
        """Every record of `day`, in the order written; none when there is no file.

        Raises :class:`~debate_core.application.budget.UnreadableUsageLog` naming the file and line
        of a line that is not a record.
        """
        return self._read_path(self.path_for(day))

    def _read_path(self, path: Path) -> tuple[UsageRecord, ...]:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return ()
        except OSError as error:
            raise UnreadableUsageLog(str(path), str(error)) from error
        return tuple(_parsed(path, number, raw) for number, raw in enumerate(data.splitlines(), start=1))

    def summary(self, day: date) -> UsageSummary:
        """`day`'s records, summarized."""
        return summarize(day, self.read(day))

    def month_paths(self, month: CalendarMonth) -> tuple[Path, ...]:
        """Every file a record of `month` can be in: its days' files and the one either side."""
        first = month.first_day - MONTH_FILE_MARGIN
        last = month.last_day + MONTH_FILE_MARGIN
        return tuple(
            self.path_for(first + timedelta(days=offset)) for offset in range((last - first).days + 1)
        )

    def month_usage(self, month: CalendarMonth) -> MonthUsage:
        """Every record whose own time falls in `month` in Chicago, in totals.

        Raises :class:`~debate_core.application.budget.UnreadableUsageLog` as :meth:`read` does.
        """
        records = [
            record
            for path in self.month_paths(month)
            for record in self._read_path(path)
            if CalendarMonth.of(record.recorded_at) == month
        ]
        return MonthUsage(
            month=month,
            calls=len(records),
            input_tokens=sum(record.input_tokens or 0 for record in records),
            output_tokens=sum(record.output_tokens or 0 for record in records),
            estimated_cost_usd=sum((record.estimated_cost_usd or 0.0 for record in records), 0.0),
            unpriced_calls=sum(1 for record in records if record.estimated_cost_usd is None),
        )

    def spent(self, run_id: str, day: date, month: CalendarMonth) -> Spend:
        """What `run_id`, `day` and `month` have spent, from the lines written so far.

        Each file is read once, from where the last read stopped, so a long run does not read its
        day again for every call; lines another process appended since count too. A run's spend is
        every line of it in any file this log has read; a month's is every line whose own time is
        in it, from :meth:`month_paths`; a line with no cost adds nothing. Raises
        :class:`~debate_core.application.budget.UnreadableUsageLog` for a line that is not a record:
        what was spent is then unknown.
        """
        with self._lock:
            path = self.path_for(day)
            for wanted in (path, *self.month_paths(month)):
                self._tails.setdefault(wanted, _Tail())
            for tailed, tail in self._tails.items():
                _catch_up(tailed, tail)
            run_usd = sum((tail.run_usd.get(run_id, 0.0) for tail in self._tails.values()), 0.0)
            month_usd = sum((tail.month_usd.get(month, 0.0) for tail in self._tails.values()), 0.0)
            return Spend(run_usd=run_usd, day_usd=self._tails[path].day_usd, month_usd=month_usd)


def _catch_up(path: Path, tail: _Tail) -> None:
    """Read the whole lines appended to `path` since `tail` last read it, and add up their cost.

    Every new line is parsed before any is counted, so a bad line counts none of them and the
    next read starts from the same place.
    """
    try:
        with path.open("rb") as file:
            file.seek(tail.offset)
            data = file.read()
    except FileNotFoundError:
        return
    except OSError as error:
        raise UnreadableUsageLog(str(path), str(error)) from error
    end = data.rfind(b"\n") + 1  # a line still being written is left for the next read
    records = [
        _parsed(path, tail.lines + number, raw) for number, raw in enumerate(data[:end].splitlines(), start=1)
    ]
    for record in records:
        cost = record.estimated_cost_usd or 0.0
        tail.day_usd += cost
        tail.run_usd[record.run_id] = tail.run_usd.get(record.run_id, 0.0) + cost
        month = CalendarMonth.of(record.recorded_at)
        tail.month_usd[month] = tail.month_usd.get(month, 0.0) + cost
    tail.offset += end
    tail.lines += len(records)


def _parsed(path: Path, number: int, raw: bytes) -> UsageRecord:
    try:
        return UsageRecord.model_validate_json(raw)
    except ValidationError as error:
        reason = error.errors()[0]["msg"]
        raise UnreadableUsageLog(f"{path}, line {number}", f"it is not a usage record ({reason})") from None
