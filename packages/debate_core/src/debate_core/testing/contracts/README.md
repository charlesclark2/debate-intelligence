# Repository contract tests

`debate_core.application.ports.persistence` says in prose what a `SnapshotStore`, an
`ArticleRepository`, a `CardRepository` and a `SearchRepository` do. This package says it in
tests, so that swapping V1's SQLite and filesystem adapters for V2's DynamoDB and S3 ones is a
change of wiring and not a change of behaviour (architecture proposal §16, §17).

There are four contract classes, one per port:

| Contract | Port | Factory type |
|---|---|---|
| `SnapshotStoreContract` | `SnapshotStore` | `SnapshotStoreFactory` |
| `ArticleRepositoryContract` | `ArticleRepository` | `ArticleRepositoryFactory` |
| `CardRepositoryContract` | `CardRepository` | `CardRepositoryFactory` |
| `SearchRepositoryContract` | `SearchRepository` | `SearchRepositoryFactory` |

## Opting a new adapter in

Subclass the contract in a class whose name starts with `Test`, and override one fixture:
`make_adapter`. That is the whole opt-in. Here is what a V2 DynamoDB card repository would add,
in full:

```python
# packages/debate_core/tests/contracts/test_dynamodb_card_repository_contract.py
import pytest

from debate_core.integrations.aws import DynamoDbCardRepository
from debate_core.testing.contracts import CardRepositoryContract, CardRepositoryFactory


class TestDynamoDbCardRepository(CardRepositoryContract):
    @pytest.fixture
    def make_adapter(self, cards_table: str) -> CardRepositoryFactory:
        return lambda: DynamoDbCardRepository(table_name=cards_table)
```

Every test in `CardRepositoryContract` now runs against that adapter, and a failure names the rule
it broke. Nothing else is registered, imported or configured.

### What `make_adapter` has to guarantee

**It returns a handle, not a store.** Calling it twice must give two handles onto *the same*
storage — two repository objects over one database, two clients over one table. That is how the
contracts stage the race the platform actually has to survive: two writers holding the same
`expected_revision` for one card, exactly one of whom may win. For an implementation where one
handle is all there is, returning the same object each time is a correct answer:

```python
    @pytest.fixture
    def make_adapter(self) -> CardRepositoryFactory:
        repository = InMemoryCardRepository()
        return lambda: repository
```

**The storage starts empty in every test.** `make_adapter` is a function-scoped fixture, so
whatever it builds over — a `tmp_path` directory, a per-test table — is fresh. No contract cleans
up after itself, and none of them tolerate leftovers from the test before.

**It reaches nothing real.** A cloud adapter opts in against moto or a local emulator, never an
account. The PR test suite makes no network calls (`docs/process/working-agreements.md`), so an
adapter whose harness cannot run offline is marked `@pytest.mark.slow` or `@pytest.mark.live` and
runs outside the PR path.

### The one optional fixture: `corrupt_blob`

`SnapshotStoreContract` also asks for `corrupt_blob`, and defaults it to `None`. Overriding it
turns on the test that a blob whose bytes no longer hash to its key is refused with
`BlobIntegrityError` rather than served — the property the whole evidence chain rests on
(architecture proposal §8). It cannot be staged through the port, because nothing in production
may rewrite a stored blob, so the binding has to supply the damage:

```python
    @pytest.fixture
    def corrupt_blob(self, make_adapter: SnapshotStoreFactory) -> BlobCorruptor:
        store = make_adapter()
        return lambda key, replacement: store.tamper_for_tests(key, replacement)
```

A binding that leaves it alone skips that one test and runs the rest.

## Running them

```bash
uv run pytest packages/debate_core/tests/contracts            # every binding
uv run pytest packages/debate_core/tests/contracts -k snapshot_store
```

The contracts' tests are `async def` and run on a real asyncio event loop, through the pytest
plugin that ships with `anyio`. The workspace's pytest configuration passes `--allow-unix-socket`
so the loop can build its self-pipe; `AF_INET` sockets stay blocked by `--disable-socket`, and the
suite stays offline. An adapter's *own* tests may keep driving their coroutines with a bare
`coroutine.send(None)` — the local adapters in
`packages/debate_core/tests/integrations/local/` do, to assert that they never suspend — but a
shared contract cannot, because a cloud adapter really does await.

## What the contracts do and do not cover

**They cover** what a use case is entitled to assume from any implementation: round-tripping a
stored entity field for field, `NotFound` from `get_*` against `None` from `find_*`, the
repository owning `revision`, the optimistic-concurrency check on cards, newest-first listing
order with the entity id as tie-break, and a cursor walk that visits every record once and then
stops.

**They deliberately do not cover** anything an adapter is free to decide, and the task spec for
`v1-e02-t04-repo-contract-tests` forbids reaching for it: how a cursor is spelled, which table or
directory a record lands in, what a file looks like on disk, whether a write is one statement or
two. Those belong in the adapter's own test module beside it — see
`packages/debate_core/tests/integrations/local/`, which keeps exactly that half.

Two behaviours are adapter-specific today and are *not* asserted here, because
`ports/persistence.py` does not promise them:

* `SqliteSearchRepository.save_results` rejects a ranking that names one article twice; the
  in-memory fake stores it. The port documents only the two rejections both implement (a result
  whose `search_id` does not match, and two results sharing a rank).
* `SqliteArticleRepository.find_by_canonical_url` returns the oldest match when several articles
  share a canonical URL. The port does not make that URL unique, so it says nothing about which
  one comes back; the contracts only store one article per URL.

## Building entities for a contract

`debate_core.testing.builders` fills in complete, valid entities from a handful of keyword
arguments, with deterministic ids (`readable_id("CARD", 7)`) and timestamps. The contracts use it
throughout, and an adapter's own tests should too rather than restating a `Card`'s invariants.
