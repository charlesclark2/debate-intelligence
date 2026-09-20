# Session report: v1-e02-t02-ports

| | |
|---|---|
| Task | `v1-e02-t02-ports` — Repository and provider port interfaces |
| Spec | [`plan_specs/v1/e02-domain-core/t02-ports.yaml`](../../plan_specs/v1/e02-domain-core/t02-ports.yaml) |
| Epic / release | `v1-e02-domain-core` / `v1.0` |
| Branch | `task/v1-e02-t02-ports` |
| Session status | COMPLETE |

## Summary

Every boundary `debate_core` talks through is now a `typing.Protocol` in
`debate_core.application.ports`: `ArticleRepository`, `SnapshotStore`, `CardRepository` and
`SearchRepository` for storage, and `SearchProvider`, `ArticleFetcher`, `ContentExtractor`,
`ModelRouter`, `Clock` and `IdGenerator` for everything outside the process. They are backed by a
typed error hierarchy in `debate_core.application.errors` — `DomainError` with `NotFound`,
`Conflict` (`AlreadyExists`, `RevisionMismatch`), `InvalidCursor`, `BlobIntegrityError`,
`InvalidModelOutput` and `ProviderError` (`ProviderUnavailable`, `ProviderRateLimited`) — and by a
working in-memory fake of every port in `debate_core.testing.fakes`, which `build_fake_ports()`
assembles into a `FakePorts` whose Protocol-annotated fields are where pyright strict catches a
fake that drifts from its port.

The two rules the epic exists to protect are enforced in the signatures rather than left to
convention. `CardRepository` splits `create(card)` from `save(card, expected_revision=...)`, so
neither a silent overwrite nor an accidental create is expressible and a reprocessing job that
races a student's edit gets a `RevisionMismatch` (§7). `ModelRouter.invoke` takes a task class, a
prompt id and version and a Pydantic output type, returns a validated instance plus the call's
provenance, and its docstring states that a schema may ask a model for paragraph ids and offsets
but never for quoted evidence text (§8).

**Worth the PM's attention first:** three decisions the spec left open — where `SourceSnapshot`
metadata is stored, how strictly to read "only domain types in their signatures", and why the
tests drive coroutines by hand instead of adding an async test plugin — are under *Decisions and
assumptions*. There is also a naming collision between two later specs that should be settled
before t03 is written; it is the first item under *Follow-up work*.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `errors` — Typed port error hierarchy | Done | `application/errors.py`. Added `InvalidCursor` (opaque cursors need a typed rejection) and `BlobIntegrityError` (both t03 and v1-e29-t04 assume a typed integrity error exists) beyond the six the node names; the Goal's ac1 lists the hierarchy as open-ended ("…"). |
| `persistence-ports` — Repository and blob-store ports | Done | `ports/persistence.py`. Snapshot *metadata* is stored through `ArticleRepository`; see Decisions. |
| `provider-ports` — Provider, model and utility ports | Done | `ports/providers.py`, plus the value objects the ports exchange (`ProviderQuery`, `CandidateResult`, `ProviderResponse`, `FetchResult`, `ExtractedContent`, `ModelTaskClass`, `ModelInvocation`). |
| `fakes` — In-memory fakes | Done | `testing/fakes.py`, 100% statement and branch coverage. |
| `injection-pattern` — Constructor-injection pattern and docs | Done | `docs/architecture/ports-and-adapters.md` plus `ArticleRegistrationService` as the worked example; pyright strict clean. |

## Acceptance criteria

All commands run from the task worktree on `task/v1-e02-t02-ports`, Python 3.12.7, pydantic
2.13.5, pytest 9.1.1, ruff 0.16.8, pyright 1.1.414.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1: all ten ports exist as Protocols, with docstrings stating semantics and only domain types in signatures | PASS | `uv run pytest packages/debate_core/tests/application/test_port_conformance.py` → `14 passed`. The suite asserts there are exactly ten, that each is a runtime-checkable Protocol, that each fake is an instance of it, and that neither port module imports `boto3`, `botocore`, `httpx`, `sqlite3`, `typer` or `fastapi`. Semantics (idempotency, listing order, revision checks, cursors) are documented in each module's header and each method's docstring. See Decisions on "only domain types". |
| Goal ac2: `CardRepository.save` requires `expected_revision` and raises `RevisionMismatch` on conflict | PASS | `expected_revision` is a required keyword-only argument (`ports/persistence.py`); `uv run pytest packages/debate_core/tests/application/test_fakes.py -k two_writers` → `1 passed`. The test stores a card, has a "student edit" and a "reprocessing job" both save at revision 1, and asserts exactly one wins, the other raises `RevisionMismatch` carrying `expected=1, actual=2`, and the stored tag is the student's. |
| Goal ac3: `ModelRouter.invoke` takes task class, prompt_id, prompt_version and a Pydantic output type; returns a validated instance plus invocation metadata | PASS | Signature in `ports/providers.py`; `uv run pytest packages/debate_core/tests/application/test_fakes.py -k router_returns` → `1 passed`, asserting `invocation.output` is the validated instance and `invocation.metadata` carries `model_id`, `prompt_version`, `task_class` and `invoked_at`. `ModelInvocationMetadata` also carries `input_tokens`, `output_tokens`, `latency_ms` and `region`. |
| Goal ac4: in-memory fakes for every port live in `debate_core.testing` and are checked against the Protocols by pyright strict | PASS | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`. The check bites: temporarily renaming `InMemoryCardRepository.save`'s `expected_revision` argument produced `error: Argument of type "InMemoryCardRepository" cannot be assigned to parameter "card_repository" of type "CardRepository"` at the `build_fake_ports()` call site, and the change was reverted. |
| `errors`: artifact_exists `application/errors.py` matching `class RevisionMismatch` | PASS | `grep -c -F "class RevisionMismatch" packages/debate_core/src/debate_core/application/errors.py` → `1` |
| `persistence-ports`: artifact_exists `ports/persistence.py` matching `class SnapshotStore(Protocol)` | PASS | `grep -c -F "class SnapshotStore(Protocol)" packages/debate_core/src/debate_core/application/ports/persistence.py` → `1` |
| `provider-ports`: artifact_exists `ports/providers.py` matching `class ModelRouter(Protocol)` | PASS | `grep -c -F "class ModelRouter(Protocol)" packages/debate_core/src/debate_core/application/ports/providers.py` → `1` |
| `fakes`: test_passes `uv run pytest packages/debate_core/tests/application/test_fakes.py` | PASS | `42 passed in 1.66s`; `testing/fakes.py` at 100% statement and branch coverage |
| `injection-pattern`: command_succeeds `uv run pyright packages/debate_core` | PASS | `0 errors, 0 warnings, 0 informations`; no `type: ignore`, `pyright: ignore` or `noqa` anywhere in `packages/debate_core` (`grep -rn … \| wc -l` → `0`) |
| `injection-pattern`: artifact_exists `docs/architecture/ports-and-adapters.md` | PASS | File present, 216 lines, indexed in `docs/README.md` |

Repo-wide gates, run after the last commit:

| Gate | Status | Evidence |
|---|---|---|
| Full test suite | PASS | `uv run pytest` → `274 passed in 6.23s` (was 198 before this task) |
| Lint | PASS | `uv run ruff check` → `All checks passed!` |
| Format | PASS | `uv run ruff format --check` → `86 files already formatted` |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 261 files, 35 epics, 207 tasks, 19 releases` |

## Files changed

**`packages/debate_core/src/debate_core/application/`** — the new layer.
`errors.py` is the hierarchy every port raises from. `ports/persistence.py` and
`ports/providers.py` hold the ten Protocols and the value objects they exchange; each module's
header states the conventions all implementations keep (async policy, error mapping, who owns
`revision`, newest-first listing order, opaque cursors). `services/article_registration.py` is the
worked example of constructor injection, and the package `__init__` files re-export the public
surface and explain what belongs in the layer.

**`packages/debate_core/src/debate_core/testing/`** — `fakes.py` with an in-memory implementation
of all ten ports, `FixedClock`, `SequentialIdGenerator`, and `build_fake_ports()`/`FakePorts`,
which is also where Protocol conformance is checked statically.

**`packages/debate_core/tests/application/`** — four suites: `test_fakes.py` (the behaviour each
port promises), `test_errors.py` (the hierarchy callers catch on), `test_port_conformance.py`
(ten ports, runtime conformance, no provider imports) and
`test_article_registration_service.py` (the injection pattern, asserting an exact id and
timestamp with no adapter and no patching).

**`docs/architecture/ports-and-adapters.md`** — the page a contributor reads before writing a
service or an adapter. Indexed in `docs/README.md`.

**`packages/debate_core/README.md`** — sections for the new `application/` and `testing/` layers,
matching the existing `domain/` section.

## Deviations from the spec

None. Everything the spec names was built, in the node order it gives. Three choices the spec left
open are recorded below rather than as deviations, and two extra error classes were added inside
the hierarchy the `errors` node owns (`InvalidCursor`, `BlobIntegrityError`) — the Goal's ac1
describes that hierarchy as open-ended.

## Decisions and assumptions

* **Snapshot metadata is stored through `ArticleRepository`.** The spec names exactly ten ports
  and none of them stores `SourceSnapshot` *records* — `SnapshotStore` is explicitly the
  content-addressed blob store, and t03 lists SQLite repositories for articles, cards and searches
  only. Rather than invent an eleventh port, `ArticleRepository` gained `save_snapshot`,
  `get_snapshot` and `list_snapshots`: a snapshot record is article-side metadata (which article,
  when retrieved, under which extractor and normalizer versions, plus the blob keys), so it sits
  beside the article it describes. `save_snapshot` refuses to overwrite, because snapshots are
  immutable. If the PM would rather have a separate `SnapshotRepository`, it is a small move and
  should happen before t03 builds the SQLite side.

* **"Only domain types in their signatures" (ac1) was read as "no provider-specific types".** A
  literal reading is not satisfiable: a `SearchProvider` cannot return
  `domain.SearchResult` (that type needs a `search_id` and a rank, which a provider does not
  produce), and a fetcher has no domain type for an HTTP response. The constraint block's own
  wording — "Ports that leak provider-specific types (e.g. botocore responses, httpx.Response)" —
  is the rule that was enforced. So the ports exchange domain types where one fits
  (`SearchFilters`, `ArticleIdentifiers`, `SourceType`, `AccessStatus`, `Article`, `Card`,
  `Search`, `SourceSnapshot`) and small application-layer value objects where none does
  (`ProviderQuery`, `CandidateResult`, `ProviderResponse`, `FetchResult`, `ExtractedContent`,
  `ModelInvocation`). `test_port_conformance.py` checks that no port module imports a provider
  library. The later specs expect exactly this: v1-e07-t01 says it "finalizes the SearchProvider
  port from v1-e02-t02-ports" and v1-e05-t01 says it finalizes "the ModelRouter port stubbed in
  v1-e02-t02-ports".

* **`CardRepository` splits `create` from `save`.** ac2 says `save` *requires* an
  `expected_revision`. A single upsert taking `expected_revision: int | None` would make "create"
  the meaning of `None`, which is the kind of overload that eventually gets passed `None` by
  accident. Two methods make `expected_revision` genuinely required on the update path and make a
  silent overwrite unexpressible. `delete` is guarded the same way.

* **`ContentExtractor`, `Clock` and `IdGenerator` are synchronous.** The spec says ports are async
  "where I/O-bound". Extraction is CPU work over bytes already in memory, and reading a clock or
  minting an id is immediate; making them `async` would force every caller to await for nothing. A
  caller running many extractions concurrently moves them to a thread or process, which is a
  scheduling decision and not one this port should impose.

* **The tests drive coroutines by hand instead of adding an async test plugin.** The dev
  dependency group has no `pytest-asyncio` or `anyio`, and `asyncio.run` cannot be used because
  the suite runs with pytest-socket's `--disable-socket`, which blocks the `AF_UNIX` socket pair
  asyncio opens for its event-loop self-pipe. Adding a dependency and changing `addopts` in the
  root `pyproject.toml` is tooling owned by v1-e01-t03, so this task did not do it silently.
  Instead each test module has a six-line `run()` helper that does `coroutine.send(None)` and
  fails if the coroutine suspends — which is itself a useful assertion, since a fake that
  suspended would be doing real I/O. See the first follow-up item.

* **The repository owns `revision`; the caller owns `created_at`/`updated_at`.** A write returns
  the entity with `revision` incremented and the caller keeps the returned instance. Timestamps
  are provenance, so they come from the `Clock` port at the service, not from whichever machine an
  adapter happens to run on — which also keeps adapters from needing a clock of their own.

* **Listings are newest first, `created_at` descending then id descending, with an opaque
  cursor.** The tie-break is what makes the order total, and therefore what makes pagination
  reproducible across SQLite, DynamoDB and the fakes; ULIDs make it meaningful. A cursor from
  another listing raises `InvalidCursor` rather than being ignored.

## Operator follow-ups

None. Every command in this session ran in seconds; the longest was the full test suite at about
6 seconds.

## Follow-up work

* **Settle the name of the blob integrity error before t03 is written.**
  `plan_specs/v1/e02-domain-core/t03-local-repositories.yaml` says the filesystem store raises
  `CorruptBlobError`; `plan_specs/v1/e29-cloud-evidence-store/t04-s3-blob-store.yaml` says the S3
  store raises `BlobIntegrityError` and maps "botocore errors to the typed port errors". They are
  the same condition and belong to one class. This task defined `BlobIntegrityError` in
  `application/errors.py` (the E29 spelling, and the one that reads as a condition rather than a
  cause). If the PM prefers `CorruptBlobError`, renaming it now costs one commit; after t03 and
  t04 it costs three. Either way one of the two specs should be edited to match.

* **Add async test support, in v1-e02-t04-repo-contract-tests or a small tooling task.** The
  contract suites will parametrize async adapters across fixtures and will want
  `pytest-asyncio` (or `anyio`) rather than a hand-rolled runner. That task should add the
  dependency to the root dev group and add `--allow-unix-socket` alongside the existing
  `--disable-socket` in `addopts`, which keeps the network blocked while letting asyncio open its
  self-pipe. The `run()` helpers in `packages/debate_core/tests/application/` then go away.

* **`debate_core.testing.builders` is still to come (t04).** Each test module in this task has its
  own small `make_article` / `make_card` / `make_search` helpers. t04 already owns the shared
  builders; these should collapse into them rather than grow.

* **Decide whether the source-removal runbook needs a delete on `SnapshotStore`.** The port has
  `put`, `get` and `exists` and no delete, because v1-e29-t04 forbids "overwriting or deleting an
  existing content-addressed object". `docs/runbooks/caselist-removal.md` therefore has to remove
  blobs as an operator procedure against the bucket or directory. That is a defensible split, but
  it should be a deliberate one rather than a consequence of this port's shape.

* **`ArticleRegistrationService` may be absorbed by v1-e04-t05-article-service.** It is a real use
  case (idempotent registration by canonical URL), but if `ArticleService` ends up owning
  registration, this one should be folded in rather than left beside it, and the docs page
  repointed at whatever the current worked example is.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
