# debate_core

The permanent domain platform: Pydantic entities, application services (use cases),
retrieval, evidence cutting/verification, argument graph, round state machine, and provider
interfaces. **No AWS SDK, Typer, or FastAPI imports** in `domain/` or `application/`.

Planned layout (src layout — see `plan_specs/v1/e02-domain-core/`):

```
src/debate_core/
  domain/        # Pydantic entities and enums
  application/   # use cases / services
  retrieval/     # article + source abstractions
  evidence/      # cutting, spans, verification
  arguments/     # graph extraction and coverage (V3)
  rounds/        # round state machine (V3)
  integrations/  # provider adapters behind ports
```

## Implemented so far

### `domain/` — entities and enums (v1-e02-t01-domain-entities)

The V1 vocabulary as frozen, `extra="forbid"` Pydantic v2 models that already match the cloud data
model in architecture proposal §7, so V2 swaps storage rather than schemas.

| Module | Contents |
|---|---|
| `base.py` | `DomainModel`, `DomainEntity`, the `Ulid`/`UtcDatetime`/`Sha256Hex`/`HttpUrlStr`/`NonEmptyText` scalars, and the injectable id factory (`new_id`, `use_id_factory`) |
| `enums.py` | `AccessStatus`, `VerificationStatus`, `ProvenanceMode`, `SearchStatus`, `SourceType`, `SpanStyle`, `SpanPurpose`, `CitationFieldSource` |
| `article.py` | `Article`, `ArticleIdentifiers`, `SourceSnapshot` |
| `search.py` | `Search`, `SearchFilters`, `SearchResult` |
| `card.py` | `Card`, `CardSpan` |
| `citation.py` | `Citation`, `CitationField[T]` |
| `schema_export.py` | Renders the published JSON Schemas (no I/O; the script writes them) |

Things worth knowing before you add a field:

* **Models are frozen.** Produce a changed copy with `model.evolve(**changes)`, which revalidates,
  rather than `model_copy(update=...)`, which does not.
* **Entities declare their own `owner_id`/`organization_id`** instead of inheriting them, because a
  `Card` always belongs to a student while an `Article` describes a public source and may not.
* **`Card.provenance_mode` has no default.** Defaulting it would make the strongest provenance
  claim the platform can make the thing that happens when a caller says nothing.
* **Enum values are a wire format.** State enums are `SCREAMING_SNAKE_CASE`, label enums are
  `lower_snake_case`; both follow the tokens the PlanSpecs use. Changing one is a migration.

### `application/` — ports and errors (v1-e02-t02-ports)

Every boundary the core talks through, as `typing.Protocol` ports, plus the typed errors that
cross them. Full write-up: [docs/architecture/ports-and-adapters.md](../../docs/architecture/ports-and-adapters.md).

| Module | Contents |
|---|---|
| `errors.py` | `DomainError` and the errors a port may raise: `NotFound`, `Conflict` (`AlreadyExists`, `RevisionMismatch`), `InvalidCursor`, `BlobIntegrityError`, `InvalidModelOutput`, `ProviderError` (`ProviderUnavailable`, `ProviderRateLimited`) |
| `ports/persistence.py` | `ArticleRepository`, `SnapshotStore`, `CardRepository`, `SearchRepository`, and the `Page` returned by every listing |
| `ports/providers.py` | `SearchProvider`, `ArticleFetcher`, `ContentExtractor`, `ModelRouter`, `Clock`, `IdGenerator`, and the value objects they exchange |
| `services/article_registration.py` | The worked example of the constructor-injection pattern every service follows |

Things worth knowing before you write a service:

* **Ports arrive in `__init__`.** No service locator, no module-level singleton, no settings object
  inside a service, and no `datetime.now()` or `uuid4()` — time and ids come from the `Clock` and
  `IdGenerator` ports.
* **Only `application.errors` crosses a port.** An adapter translates `sqlite3`, `botocore` and
  `httpx` failures at its own edge.
* **`CardRepository.save` requires `expected_revision`** and raises `RevisionMismatch`, so model
  reprocessing cannot overwrite a student's edit. Creating is a separate method.
* **Async where the work is I/O.** Extraction, the clock and the id generator are synchronous.

### `testing/` — in-memory fakes (v1-e02-t02-ports)

`debate_core.testing.fakes` has a working in-memory implementation of every port, plus `FixedClock`
and `SequentialIdGenerator`. They enforce what their ports promise — dedupe, blob integrity,
revision conflicts, listing order — so a test against a fake exercises the same rules as the real
adapter. `build_fake_ports()` assembles one of each, and is where pyright checks that the fakes
still conform to the Protocols.

### `integrations/local/` — the filesystem and SQLite adapters (v1-e02-t03-local-repositories)

V1's implementations of the four persistence ports, so the CLI runs with no cloud account.
Everything lives under one data directory, which each adapter takes as a constructor argument —
they never read settings:

```
<data_dir>/
  blobs/sha256/ab/cd/abcd1234…def0   immutable snapshot bytes, by digest (FsSnapshotStore)
  debate.sqlite3                     articles, snapshots, cards, searches (SqliteDatabase)
```

| Module | Contents |
|---|---|
| `fs_blob_store.py` | `FsSnapshotStore`: content-addressed blobs, atomic temp+rename writes, read-only once written, `BlobIntegrityError` on a read whose bytes no longer hash to their key |
| `sqlite_db.py` | `SqliteDatabase.open(data_dir)`: the shared connection, its pragmas, and the migration runner |
| `migrations/` | Numbered `.sql` files, applied in order and exactly once each |
| `sqlite_repos.py` | `SqliteArticleRepository`, `SqliteCardRepository`, `SqliteSearchRepository` |

```python
database = SqliteDatabase.open(settings.storage.data_dir)
service = ArticleRegistrationService(
    articles=SqliteArticleRepository(database),
    clock=SystemClock(),
    id_generator=UlidGenerator(),
)
```

Things worth knowing before you add an adapter or a field:

* **The four repositories share one `SqliteDatabase`.** One connection, one set of pragmas, one
  migration run, and a write spanning two tables is one transaction.
* **An entity is stored as its own JSON, plus key columns for indexing.** Nothing reads a value
  out of a key column, so adding a field to a model needs no migration here — only a new *way of
  finding* records does.
* **These adapters do their I/O synchronously inside `async def`.** On a local disk a read is tens
  of microseconds, and a thread hop per call would cost more than it saved. The port is what makes
  that reversible without a caller changing.
* **Migrations are append-only.** A released migration is never edited; databases already record
  its version. Add the next one.

### `schemas/` — published JSON Schemas

One file per entity, generated and checked in:

```bash
uv run scripts/export_schemas.py          # regenerate after changing a model
uv run scripts/export_schemas.py --check  # exit 1 if a committed schema is stale
```

`tests/domain/test_schemas.py` fails when they drift, so a model change and its schema change
always land in the same commit.
