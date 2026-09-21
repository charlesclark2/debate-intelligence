# Ports and adapters in `debate_core`

How the domain core reaches storage, the web and a model — and why it is arranged this way.

`debate_core` has to run two ways. In V1 it runs on a student's laptop against SQLite and a
directory of files, with no cloud account at all. In V2 the same use cases run in Lambda and
Fargate against DynamoDB, S3 and Bedrock. That is only affordable if swapping one for the other
changes adapters and not use cases (architecture proposal §2, §6, §17).

So every boundary is a `typing.Protocol` in
[`debate_core.application.ports`](../../packages/debate_core/src/debate_core/application/ports/),
and nothing in `domain/` or `application/` imports `boto3`, `httpx`, `sqlite3`, Typer or FastAPI.
`v1-e02-t06-import-boundary-guard` turns that from a convention into a build failure.

## The ten ports

| Port | Module | Hides | V1 adapter | V2 adapter |
|---|---|---|---|---|
| `ArticleRepository` | `ports.persistence` | Article and snapshot-metadata records | SQLite | DynamoDB |
| `SnapshotStore` | `ports.persistence` | Immutable, content-addressed blobs | Filesystem | S3 |
| `CardRepository` | `ports.persistence` | Cards and their revision checks | SQLite | DynamoDB |
| `SearchRepository` | `ports.persistence` | Searches and ranked results | SQLite | DynamoDB |
| `SearchProvider` | `ports.providers` | One discovery source | OpenAlex, Crossref, RSS … | same |
| `ArticleFetcher` | `ports.providers` | HTTP retrieval | httpx | same |
| `ContentExtractor` | `ports.providers` | Readable-text extraction | trafilatura, pypdf | same |
| `ModelRouter` | `ports.providers` | Every LLM call | Bedrock / replay | Bedrock |
| `Clock` | `ports.providers` | The current time | system clock | system clock |
| `IdGenerator` | `ports.providers` | New entity ids | ULID | ULID |

Concrete adapters land in `debate_core.integrations.<technology>`. `v1-e02-t03-local-repositories`
brought the first of them, in
[`debate_core.integrations.local`](../../packages/debate_core/src/debate_core/integrations/local/):
`FsSnapshotStore` on the filesystem, and the three repositories on one shared `SqliteDatabase`,
which is opened from the data directory and passed to each of them.

## Protocols, not base classes

A port is a `Protocol`, so an adapter conforms **structurally**: it has the right methods and it
never subclasses or imports the port module at runtime. An adapter therefore cannot pull a
dependency of its own back across the boundary, and a third-party object can satisfy a port
without being wrapped.

Conformance is checked statically. In
[`debate_core.testing.fakes`](../../packages/debate_core/src/debate_core/testing/fakes.py),
`build_fake_ports()` assigns each fake to a field of `FakePorts` that is annotated with the
Protocol, so pyright strict fails right there if a fake drifts from its port. Adapters get the
same treatment through the contract suites (`v1-e02-t04-repo-contract-tests`).

## Constructor injection, and nothing else

A service takes the ports it needs as keyword arguments on `__init__`, stores them, and holds no
other state:

```python
class ArticleRegistrationService:
    def __init__(
        self,
        *,
        articles: ArticleRepository,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._articles = articles
        self._clock = clock
        self._id_generator = id_generator
```

The worked example is
[`article_registration.py`](../../packages/debate_core/src/debate_core/application/services/article_registration.py).
Every service in the platform follows the same shape.

**What is not allowed, and why:**

* **No service locator or registry.** `get_repository("cards")` moves a wiring mistake from
  compile time to run time and hides which adapter a use case actually used.
* **No module-level singletons.** A module-level `ARTICLES = SqliteArticleRepository(...)` makes
  two tests share state and makes the data directory a global.
* **No settings object inside a service.** Settings choose adapters; they are read at the
  composition root (`v1-e02-t05-settings-config`), not by the use case.
* **No `datetime.now()` and no `uuid4()` in a service.** Timestamps and ids are what a test
  asserts on and what provenance records; they come from `Clock` and `IdGenerator`.

**The composition root** is the one place that knows which adapters exist: a CLI command, an API
route's dependency, a worker's handler, or a test. It builds the adapters and hands them to the
service. `debate_cli`, `debate_api` and `debate_workers` contain no business logic beyond that.

```python
# In a CLI command (V1)
database = SqliteDatabase.open(settings.storage.data_dir)
service = ArticleRegistrationService(
    articles=SqliteArticleRepository(database),
    clock=SystemClock(),
    id_generator=UlidGenerator(),
)

# In a test
fakes = build_fake_ports(clock=FixedClock(), id_generator=SequentialIdGenerator("ART"))
service = ArticleRegistrationService(
    articles=fakes.article_repository,
    clock=fakes.clock,
    id_generator=fakes.id_generator,
)
```

## Conventions every implementation keeps

**Async where the work is I/O.** Repositories, the blob store, search providers, the fetcher and
the model router are `async`. Extraction (CPU over bytes already in memory), reading the clock and
minting an id are ordinary methods, because making them `async` would buy nothing and would force
every caller to await.

**Only errors from [`application.errors`](../../packages/debate_core/src/debate_core/application/errors.py)
cross a port.** An adapter translates its library's failures at its own edge; a `sqlite3` or
`botocore` exception reaching a service is an adapter bug.

```
DomainError
├── NotFound                  a get by key found nothing (find_* returns None instead)
├── Conflict
│   ├── AlreadyExists         a create would overwrite
│   └── RevisionMismatch      the stored revision moved since it was read
├── InvalidCursor             a cursor this repository did not mint
├── BlobIntegrityError        stored bytes do not hash to their key
├── InvalidModelOutput        a model's answer does not fit the requested schema
└── ProviderError
    ├── ProviderUnavailable   unreachable, timed out, server error
    └── ProviderRateLimited   over the limit; carries retry_after_seconds
```

**The repository owns `revision`; the caller owns `created_at`/`updated_at`.** A successful write
returns the entity with `revision` incremented, and the caller keeps the returned instance.
Timestamps are provenance, so they come from the `Clock` port rather than from whichever machine
the adapter happens to run on.

**Cards are written under an optimistic-concurrency check.** `CardRepository.save` requires the
`expected_revision` the caller read and raises `RevisionMismatch` if the stored revision moved, so
a reprocessing job cannot silently overwrite a student's edit (architecture proposal §7). Creating
is a separate method, so neither a silent overwrite nor an accidental create is expressible:

```python
stored = await cards.get(card_id)
edited = stored.evolve(tag="Warming is anthropogenic")
try:
    saved = await cards.save(edited, expected_revision=stored.revision)
except RevisionMismatch:
    ...  # re-read, re-apply, or tell the user their copy is stale
```

**Listings are newest first** — `created_at` descending, then id descending — and paginate with an
opaque cursor. The tie-break is what makes the order total, and therefore what makes pagination
reproducible across SQLite, DynamoDB and the fakes.

**Snapshots are immutable.** `SnapshotStore` has `put`, `get` and `exists` and no delete or
overwrite; re-retrieving a source produces a new snapshot. A read whose bytes do not hash to their
key fails with `BlobIntegrityError` rather than returning text a card would then be "verified"
against.

**A model never supplies evidence text.** `ModelRouter.invoke` takes a `ModelTaskClass`, a
`prompt_id` and `prompt_version`, and a Pydantic output type, and returns a validated instance
plus the call's provenance (model id, tokens, latency). A schema may ask a model for paragraph
ids, offsets, labels and explanations — *which* passage to cut and *why*. The quotation itself is
always sliced out of the stored snapshot afterwards (architecture proposal §8).

```python
invocation = await router.invoke(
    task_class=ModelTaskClass.COMPLEX_REASONING,
    prompt_id="select-passage",
    prompt_version="1.2.0",
    output_type=PassageChoice,
    variables={"tag": tag, "paragraphs": numbered_paragraphs},
)
choice = invocation.output  # a validated PassageChoice
model_id = invocation.metadata.model_id
```

## Testing against the fakes

[`debate_core.testing`](../../packages/debate_core/src/debate_core/testing/) ships an in-memory
implementation of every port. They are fakes, not mocks: each one really enforces what its port
promises, so a test that passes against a fake is testing the same rules the real adapter is held
to.

```python
articles = InMemoryArticleRepository()
service = ArticleRegistrationService(
    articles=articles,
    clock=FixedClock(step=timedelta(minutes=1)),
    id_generator=SequentialIdGenerator("ART"),
)
article = await service.register(canonical_url=url, title=title)
assert article.article_id == "0ART0000000000000000000001"
```

`FakeSearchProvider`, `FakeArticleFetcher`, `FakeContentExtractor` and `FakeModelRouter` are
scripted: give them the answers the test needs, including failures, and assert on what they were
asked. `FakeModelRouter` records every call, so a test can check that a use case routed to the
right task class and prompt version.

Two fakes expose test-only helpers that are deliberately *not* on their ports, because no
production code may do these things: `InMemorySnapshotStore.corrupt()` tampers with a stored blob
to prove the integrity check fires, and `FakeArticleFetcher.add()` registers a canned response.

## Adding an adapter

1. Write the class in `debate_core.integrations.<technology>`. Take its configuration — a data
   directory, a bucket, a client — as constructor arguments. Do not import settings.
2. Implement the port's methods with exactly the port's names and signatures. Do not subclass the
   Protocol.
3. Translate every library failure into a `DomainError` at the adapter's edge.
4. Bind it to the shared contract suite (`v1-e02-t04-repo-contract-tests`) with one fixture. The
   contracts are what prove the swap is safe; they never reach into an adapter's internals.
5. Wire it at the composition root, behind whatever setting selects it.

## Related documents

* [architecture_proposal.md](architecture_proposal.md) — §2 principles, §6 boundaries, §7 data
  architecture, §10 the ModelRouter, §17 deployment and evolution.
* [`plan_specs/v1/e02-domain-core/`](../../plan_specs/v1/e02-domain-core/) — the specs for the
  ports (t02), the local adapters (t03), the contract suites (t04) and the import guard (t06).
* [`packages/debate_core/README.md`](../../packages/debate_core/README.md) — package layout.
