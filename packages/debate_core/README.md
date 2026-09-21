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
| `caselist/` | Disclosed and camp evidence: see below (v1-e30-t02-caselist-domain-model) |
| `debate_files.py` | What reading a debate `.docx` produces: `ParsedDocument`, `FileSection`, `ParsedCard`, `FormattingSpan`, `FontSizeSpan`, `CardCompleteness`, `FileImportProvenance`, `ParseFailure` (v1-e31-t03-debate-docx-parser) |

Things worth knowing before you add a field:

* **Models are frozen.** Produce a changed copy with `model.evolve(**changes)`, which revalidates,
  rather than `model_copy(update=...)`, which does not.
* **Entities declare their own `owner_id`/`organization_id`** instead of inheriting them, because a
  `Card` always belongs to a student while an `Article` describes a public source and may not.
* **`Card.provenance_mode` has no default.** Defaulting it would make the strongest provenance
  claim the platform can make the thing that happens when a caller says nothing.
* **Enum values are a wire format.** State enums are `SCREAMING_SNAKE_CASE`, label enums are
  `lower_snake_case`; both follow the tokens the PlanSpecs use. Changing one is a migration.

### `domain/caselist/` — disclosed and camp evidence (v1-e30-t02-caselist-domain-model)

The vocabulary the E30 importers, the E31 parser and the E32 landscape reports share, kept in its
own subpackage and *not* re-exported from `debate_core.domain`, because names like `Event` and
`Side` are only unambiguous inside it. Import from `debate_core.domain.caselist`.

| Module | Contents |
|---|---|
| `values.py` | `CaselistSlug`, `Season`, `TeamCodeText`, `SnapshotDate`, the `Event`/`Side`/`SourceFormat`/`SourceOrigin`/`Acquisition`/`CompetitionLevel` enums, and `RoundLabel` with its normalization table |
| `entities.py` | `Caselist`, `School`, `TeamCode`, `ArchiveSnapshot`, `SourceDocument`, `Disclosure`, `CampFile` |

Things worth knowing before you add a field:

* **Caselist slugs are data, not an enum.** `hsld26`, `hspolicy26` and `hspf26` are validated
  strings, because every season mints new ones.
* **Identity is natural, so these extend `DomainModel`, not `DomainEntity`.** A source document is
  its SHA-256 and a snapshot is its `(caselist, date)`; there is no ULID, no owner and no revision,
  because an import re-states what a public archive says rather than recording someone's edit.
* **No model may identify a person.** A school name and a disclosed team code are all that is
  stored. `tests/domain/caselist/test_minimization.py` pins every model's field set and bans
  name-shaped field names, so adding one fails CI (architecture proposal §14).
* **Imported evidence is always `ProvenanceMode.FILE_IMPORT`,** enforced on the model rather than
  left to the importer.

### `application/` — ports and errors (v1-e02-t02-ports)

Every boundary the core talks through, as `typing.Protocol` ports, plus the typed errors that
cross them. Full write-up: [docs/architecture/ports-and-adapters.md](../../docs/architecture/ports-and-adapters.md).

| Module | Contents |
|---|---|
| `errors.py` | `DomainError` and the errors a port may raise: `NotFound`, `Conflict` (`AlreadyExists`, `RevisionMismatch`), `InvalidCursor`, `BlobIntegrityError`, `StoreError` (`StoreAccessDenied`, `StoreCredentialsExpired`, `StoreUnavailable`), `InvalidModelOutput`, `ProviderError` (`ProviderUnavailable`, `ProviderRateLimited`) |
| `ports/persistence.py` | `ArticleRepository`, `SnapshotStore`, `CardRepository`, `SearchRepository`, and the `Page` returned by every listing |
| `ports/providers.py` | `SearchProvider`, `ArticleFetcher`, `ContentExtractor`, `ModelRouter`, `Clock`, `IdGenerator`, and the value objects they exchange |
| `ports/caselist.py` | `CaselistRepository`, the boundary the E30 importers, publisher and removal command store through (v1-e30-t02) |
| `ports/debate_files.py` | `DebateFileParser`, the boundary a debate `.docx` is taken apart behind. Synchronous, because parsing waits on nothing, and a file it cannot read comes back as a `ParseFailure` rather than an exception (v1-e31-t03) |
| `ports/evidence_store.py` | `EvidenceObjectStore` and `ObjectInfo`: evidence stored under a *name* rather than a digest — manifests, reports — plus the key validation both its adapters share (v1-e29-t04) |
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
still conform to the Protocols. `InMemoryCaselistRepository` lives there too — built by
`build_fake_caselist_repository()` rather than by `build_fake_ports()`, because a caselist
repository is not one of the ten ports every service takes.

### `integrations/local/` — the filesystem and SQLite adapters (v1-e02-t03-local-repositories)

V1's implementations of the four persistence ports, so the CLI runs with no cloud account.
Everything lives under one data directory, which each adapter takes as a constructor argument —
they never read settings:

```
<data_dir>/
  blobs/sha256/ab/cd/abcd1234…def0   immutable snapshot bytes, by digest (FsSnapshotStore)
  objects/manifests/hsld26/….jsonl   evidence objects by name (FsEvidenceObjectStore)
  debate.sqlite3                     articles, snapshots, cards, searches (SqliteDatabase)
```

| Module | Contents |
|---|---|
| `fs_blob_store.py` | `FsSnapshotStore`: content-addressed blobs, atomic temp+rename writes, read-only once written, `BlobIntegrityError` on a read whose bytes no longer hash to their key |
| `fs_object_store.py` | `FsEvidenceObjectStore`: named objects under `objects/`, the local side of every `debate-research store sync` (v1-e29-t04) |
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

### `integrations/s3/` — the evidence bucket (v1-e29-t04-s3-blob-store)

The same two evidence ports as `integrations/local/`, against the environment's S3 bucket. **The only
place in the platform that imports boto3**, which an import-linter contract in the workspace root
enforces; boto3 is an optional dependency, so this package needs the `aws` extra:

```bash
uv sync --extra aws        # or: pip install 'debate-core[aws]'
```

| Module | Contents |
|---|---|
| `client.py` | `build_s3_client(region=…, profile=…)` on botocore's standard credential chain, and the multipart thresholds |
| `snapshot_store.py` | `S3SnapshotStore`: keys `<prefix>/sha256/<ab>/<cd>/<digest>`, head-before-put idempotency, SHA-256 additional checksums, the full-object digest in object metadata, verification on read, `put_file`/`get_file` for objects too big to hold in memory |
| `object_store.py` | `S3EvidenceObjectStore`: paginated listing, head, and atomic file transfers for `manifests/` and `reports/` |
| `errors.py` | Where every `ClientError` stops: `NotFound`, `StoreAccessDenied`, `StoreCredentialsExpired` with the `aws sso login` command, `StoreUnavailable` |

```python
client = build_s3_client(region=region, profile=profile)  # profile: the environment's SSO profile
blobs = S3SnapshotStore(bucket=bucket, prefix="raw/caselist/hsld26", client=client)
objects = S3EvidenceObjectStore(bucket=bucket, client=client)
```

Things worth knowing before you use or extend these:

* **No adapter here names a bucket or reads settings.** The bucket name and the KMS key ARN come from
  the environment root's `evidence_bucket_name` and `evidence_kms_key_arn` Terraform outputs, resolved
  per `DEBATE_ENV` by `v1-e29-t05-evidence-sync-cli` and passed to a constructor. A bucket name in
  Python is how dev evidence ends up in prod.
* **A repeat `put` of identical bytes issues no `PutObject`.** The buckets are versioned, and a
  content-addressed key with two versions is a signal that something went wrong, not routine noise.
* **The digest in object metadata is the full-object SHA-256, and S3's `ChecksumSHA256` is not.** For a
  multipart object the latter is a composite of the part digests, so only the metadata entry can be
  compared with a blob key.
* **Blocking calls run in a worker thread** (`asyncio.to_thread`), unlike the local adapters, because
  here the I/O really is a network round trip.
* **Tests use `moto`, never an account.** The fixtures are in `packages/debate_core/tests/conftest.py`
  and the suite runs with `--disable-socket`.
### The debate-file style profile (v1-e31-t02-verbatim-style-profile)

What a pocket, hat, block, tag, cite, analytic and undertag look like in a Word `.docx`, in one
place that the parser (`v1-e31-t03`), the lossless writer (`v1-e33-t02`) and the card format
profiles (`v1-e06-t03`) all read. **No reader or writer keeps its own idea of what `Heading4`
means.**

| Module | Contents |
|---|---|
| `domain/style_profile.py` | `StructuralUnit`, `RunEmphasis`, `StyleMatchSource`, the `StyleProfile` model and the rules that resolve a Word style to a unit or an emphasis |
| `evidence/style_profiles/verbatim.yaml` | The data: styles, aliases, highlight colours, the shrink rule, heuristic thresholds, cite conventions, writer style definitions and the CardMirror mapping |
| `evidence/style_profile_loader.py` | `load_style_profile()` (cached), and `resolve_based_on_chain` for a document's own style table |
| `evidence/style_classifier.py` | `classify_paragraph` / `classify_run` for files that carry no Verbatim styles |

```python
from debate_core.evidence import load_style_profile, resolve_based_on_chain

profile = load_style_profile()
match = profile.resolve_paragraph_style("Heading411", "Heading 411", ("Heading1", "Normal"))
match.unit  # StructuralUnit.TAG
match.rule_id  # 'verbatim-deduplicated:Heading411->Heading4'
match.match_source  # StyleMatchSource.VERBATIM_ALIAS
```

Things worth knowing before you add a style or a rule:

* **Every number in the YAML was measured**, over 2,066 real files. The corpus, the counts and how
  to refresh them are in [docs/data/debate-file-style-survey.md](../../docs/data/debate-file-style-survey.md).
* **`basedOn` is resolved last, and that is deliberate.** `Heading411` appears in 197 files and is
  a Heading 4 that inherits from `Heading1`. Word's numeric de-duplication rule is tried first
  because `basedOn` would get those files wrong.
* **Underline is dual-encoded** — a named character style in body slots, a direct `<w:u>` in
  structural slots, and CardMirror writes both on body runs. A reader must count it once. 63% of
  the corpus has been through CardMirror at least once, so this is the common case, not the edge.
* **`profile_version` is recorded on every parsed card**, so a card can be re-read under the
  profile it was parsed with. Bump it whenever a rule changes, and regenerate the fixtures
  (`uv run python scripts/generate_style_fixtures.py`) — a test fails if they disagree.
* **The profile is not an exported JSON Schema.** `EXPORTED_MODELS` publishes the entities the web
  client and the V2 API read; the profile is configuration this package loads for itself.

### `integrations/docx_parser/` — the debate `.docx` parser (v1-e31-t03-debate-docx-parser)

The V1 `DebateFileParser`. **The only place in the platform that imports lxml**, which an
import-linter contract in the workspace root enforces; lxml is an optional dependency, so this
package needs the `docx` extra:

```bash
uv sync --extra docx       # or: pip install 'debate-core[docx]'
```

| Module | Contents |
|---|---|
| `package.py` | `open_debate_docx`: zip and XML hardening — entry count, uncompressed size, per-part size and compression ratio, and a parser built with entity resolution, DTD loading and network access all off. Refuses PDFs, legacy `.doc`, encrypted and macro-enabled packages by name. `NEVER_READ_PARTS` is what it will not open |
| `runs.py` | Paragraph text and character-offset `FormattingSpan`s, built in one walk so they cannot disagree. Keeps tracked insertions, drops deletions, counts a dual-encoded underline once |
| `parser.py` | `DebateDocxParser`: classification through the t02 style profile, section paths, card assembly and `FILE_IMPORT` provenance |

```python
parser = DebateDocxParser()                      # loads the verbatim style profile
result = parser.parse(content, source, source_path=disclosure.source_path)
if isinstance(result, ParsedDocument):
    ...                                          # otherwise it is a ParseFailure with a reason
```

Things worth knowing before you use or extend this:

* **Evidence text is copied, never produced.** A card's `evidence_text` is the concatenated run
  text, character for character, and every span indexes that exact string. Nothing normalizes,
  corrects or re-flows it.
* **An imported card is `UNVERIFIED` and cannot say otherwise.** It is deliberately not a `Card`.
* **A refusal is a return value.** A bulk import of twelve thousand files needs a row it can
  count, not an exception that stops the run.
* **Nothing reads `docProps`, comments, `people.xml` or `settings.xml`.** The opened package
  records every part it did read, and a test asserts that list.
* **A card reports the weakest match that built it**, which for an ordinary Verbatim card is a
  heuristic: Verbatim gives a card body no paragraph style, so the body is found by its markup.
  `rule_ids` is where the detail is.

### `schemas/` — published JSON Schemas

One file per entity, generated and checked in:

```bash
uv run scripts/export_schemas.py          # regenerate after changing a model
uv run scripts/export_schemas.py --check  # exit 1 if a committed schema is stale
```

`tests/domain/test_schemas.py` fails when they drift, so a model change and its schema change
always land in the same commit.
