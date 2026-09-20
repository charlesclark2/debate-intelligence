# Session report: v1-e02-t04-repo-contract-tests

| | |
|---|---|
| Task | `v1-e02-t04-repo-contract-tests` — Reusable repository contract test suite |
| Spec | [`plan_specs/v1/e02-domain-core/t04-repo-contract-tests.yaml`](../../plan_specs/v1/e02-domain-core/t04-repo-contract-tests.yaml) |
| Epic / release | `v1-e02-domain-core` / `v1.0` |
| Branch | `task/v1-e02-t04-repo-contract-tests` |
| Session status | COMPLETE |

## Summary

`debate_core.testing.contracts` now holds four implementation-agnostic contract classes, one per
persistence port, and both V1 implementations are bound to all four: the in-memory fakes from
t02 and the filesystem/SQLite adapters from t03. 84 contract tests run twice over, once per
binding, for 168 assertions that neither implementation can drift from the other — which is what
epic criterion ac2 ("local implementations pass a reusable contract-test suite") asks for and
what lets a V2 DynamoDB or S3 adapter be held to the same rules without new test code.

An adapter opts in by subclassing a contract and overriding one fixture, `make_adapter`. That
fixture is a *factory* rather than a single adapter, which is the design decision the PM should
look at first: calling it twice hands back two handles onto the same storage, and that is how the
card contract stages two writers holding the same `expected_revision` — exactly one may win, and
the loser must get `RevisionMismatch` (ac3). A second new module,
`debate_core.testing.builders`, produces complete valid entities from keyword arguments so the
contracts assert on behaviour rather than on model invariants.

Two things outside `debate_core` changed, both in the workspace `pyproject.toml`, and both are
listed under Deviations: pytest now passes `--allow-unix-socket`, and `anyio` is promoted from a
transitive dependency to a declared dev one. The contracts run on a real asyncio event loop
rather than the `coroutine.send(None)` driver the local adapters' own tests use, because a V2
cloud adapter genuinely suspends and a shared contract has to survive that. Network sockets stay
blocked; the suite is still entirely offline.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `harness` — Contract harness and entity factories | Done | `contracts/harness.py` (factory types, `AdapterContract`, `walk_all_pages`) plus `contracts/__init__.py` as the public surface, and `testing/builders.py`. |
| `blob-contract` — SnapshotStore contract | Done | 12 tests: content addressing, dedupe, idempotent put, absence, and tamper detection through an optional `corrupt_blob` fixture. |
| `repo-contracts` — Article, Card and Search repository contracts | Done | 27 + 25 + 20 tests: round-trip, `NotFound`/`None`, upsert and revision semantics, optimistic concurrency, listing order, tie-breaks, cursor paging, `InvalidCursor`. |
| `bind-and-document` — Bind adapters and document opt-in | Done | Four binding modules under `packages/debate_core/tests/contracts/`, a shared `conftest.py`, and `contracts/README.md` with the DynamoDB opt-in example. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1 — contract classes for all four ports, importable from `debate_core.testing.contracts` | PASS | `uv run python -c "from debate_core.testing.contracts import ArticleRepositoryContract, CardRepositoryContract, SearchRepositoryContract, SnapshotStoreContract"` → `imported: SnapshotStoreContract, ArticleRepositoryContract, CardRepositoryContract, SearchRepositoryContract` |
| Goal ac2 — every contract runs against both the fake and the local adapter, all pass | PASS | `uv run pytest packages/debate_core/tests/contracts` → `168 passed in 1.96s`. Collection shows both bindings per port: `TestInMemoryArticleRepository` 27 / `TestSqliteArticleRepository` 27, `TestInMemoryCardRepository` 25 / `TestSqliteCardRepository` 25, `TestInMemorySearchRepository` 20 / `TestSqliteSearchRepository` 20, `TestInMemorySnapshotStore` 12 / `TestFsSnapshotStore` 12. No tests skipped. |
| Goal ac3 — two writers at the same `expected_revision` give one success and one `RevisionMismatch` | PASS | `uv run pytest packages/debate_core/tests/contracts -k two_writers -v` → `2 passed`, `TestInMemoryCardRepository::test_two_writers_at_the_same_revision_produce_one_success_and_one_mismatch PASSED` and `TestSqliteCardRepository::…  PASSED`. The test gathers both writes with `asyncio.gather(..., return_exceptions=True)` and asserts exactly one `Card` and exactly one `RevisionMismatch` carrying `expected_revision == 1` and `actual_revision == 2`, then that the stored card is the winner's. |
| Goal ac4 — a README explains the single-fixture opt-in for a new adapter | PASS | [`packages/debate_core/src/debate_core/testing/contracts/README.md`](../../packages/debate_core/src/debate_core/testing/contracts/README.md) exists; `grep -c make_adapter` → `7`. It gives a complete `TestDynamoDbCardRepository` example, states the three guarantees `make_adapter` must keep, and documents the optional `corrupt_blob` fixture. |
| `harness` — Builders module exists (`artifact_exists`) | PASS | `packages/debate_core/src/debate_core/testing/builders.py` exists (added in commit `8a6eb20`). |
| `blob-contract` — SnapshotStore contract passes for fake and filesystem adapters (`test_passes`) | PASS | `uv run pytest packages/debate_core/tests/contracts -k snapshot_store` → `24 passed in 1.97s` |
| `repo-contracts` — Repository contracts pass for fakes and SQLite adapters (`test_passes`) | PASS | `uv run pytest packages/debate_core/tests/contracts -k "article or card or search"` → `144 passed in 2.05s` |
| `bind-and-document` — Full contract suite passes (`test_passes`) | PASS | `uv run pytest packages/debate_core/tests/contracts` → `168 passed in 1.96s` |
| `bind-and-document` — Opt-in guide exists, matching `make_adapter` (`artifact_exists`) | PASS | `contracts/README.md` present, contains `make_adapter` 7 times. |

Repository-wide gates, all run in this worktree:

| Gate | Result |
|---|---|
| `uv run pytest` (whole workspace) | `752 passed in 16.32s` |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` (`debate_core` is checked in strict mode) |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `169 files already formatted` |
| `uv run scripts/validate_specs.py` | `OK: 281 files, 38 epics, 223 tasks, 20 releases` |

`lint-imports` was not run: import-linter is not configured yet, and setting it up is
`v1-e02-t06-import-boundary-guard` (still `Pending`). Nothing added here imports boto3, typer,
fastapi or httpx, and nothing was added to `debate_core/domain` or `debate_core/application`.

## Files changed

**`packages/debate_core/src/debate_core/testing/` — the shipped suite**

* `builders.py` (new). Builders for `Article`, `SourceSnapshot`, `Citation`, `CardSpan`, `Card`,
  `Search` and `SearchResult`, plus `readable_id()` and `sha256_of()`. Deterministic: ids are
  legible ULIDs (`0CARD…0007`), timestamps default to `FAKE_EPOCH`, and a snapshot's blob keys and
  digests are computed from the bytes it is given, so one built here can really be stored and read
  back under the keys it claims.
* `contracts/harness.py` (new). The factory type aliases, the `AdapterContract` base that pins the
  async backend, and `walk_all_pages()`, which follows `next_cursor` to the end and checks that
  the walk terminates, takes the expected number of requests and serves no record twice.
* `contracts/snapshot_store.py` (new). `SnapshotStoreContract`, 12 tests.
* `contracts/repositories.py` (new). `ArticleRepositoryContract`, `CardRepositoryContract` and
  `SearchRepositoryContract`, 72 tests between them.
* `contracts/__init__.py` (new). The public surface and the "what this package is" docstring.
* `contracts/README.md` (new). The opt-in guide (ac4).
* `__init__.py` (modified). Re-exports the builders; deliberately does *not* re-export
  `contracts`, which imports pytest and must stay out of a running CLI or API.

**`packages/debate_core/tests/` — the bindings and their own tests**

* `contracts/conftest.py` (new). One migrated, empty `SqliteDatabase` under `tmp_path` per test,
  shared by the three SQLite bindings — which is what makes their factories able to hand out two
  handles onto one store.
* `contracts/test_snapshot_store_contract.py`, `test_article_repository_contract.py`,
  `test_card_repository_contract.py`, `test_search_repository_contract.py` (new). Two bindings
  each, roughly ten lines apiece.
* `testing/test_builders.py` (new). 21 tests that the builders produce valid, self-consistent and
  deterministic entities, and that `readable_id` rejects a label outside the Crockford alphabet.

**`pyproject.toml`, `uv.lock` (modified)** — `--allow-unix-socket` and the `anyio` dev
dependency; see Deviations.

## Deviations from the spec

1. **Two files outside the spec's stated packages were edited.** The spec's
   `constraints.packages` is `[debate_core.testing, debate_core tests]`; the workspace
   `pyproject.toml` (and the `uv.lock` line that follows from it) are outside that.
   * `addopts` gains `--allow-unix-socket`. The contracts must run on a real event loop, an
     asyncio loop builds its self-pipe from `socket.socketpair()`, and `--disable-socket` refuses
     it — verified: without the flag, `asyncio.run` raises
     `pytest_socket.SocketBlockedError`. AF_UNIX sockets cannot reach a network, and a test
     asserting that `socket.socket(AF_INET, SOCK_STREAM)` is still blocked passes with the flag
     on, so the suite remains offline as the working agreements require.
   * `anyio>=4.4` is added to the dev dependency group. Its pytest plugin is what runs the
     `async def` contract tests. It was already installed as a transitive dependency of `httpx`,
     so `uv lock --offline` resolved it with no new download and the lock gained two lines; the
     change makes an existing reliance explicit rather than adding a dependency.

   Neither was avoidable without giving up the ability to hold a genuinely asynchronous cloud
   adapter to the contract, which is the task's stated purpose. Flagging rather than widening the
   spec silently; the PM may want `constraints.packages` amended.

2. **The `harness` node's outputs are split across three files rather than two.** The spec lists
   `contracts/__init__.py` and `testing/builders.py`. The base class, the factory type aliases and
   the paging helper live in `contracts/harness.py`, with `contracts/__init__.py` re-exporting
   them, because the four contract modules have to import the harness and importing it from the
   package `__init__` would be circular. No criterion depends on the file split.

## Decisions and assumptions

* **`make_adapter` returns a factory, not an adapter.** The spec asks for "an adapter factory
  fixture" and names `make_adapter`; the reason it is a factory is ac3. Two handles onto one store
  are what a two-writer race needs, and the same fixture shape serves an implementation where one
  handle is all there is (the fakes return the same object each call). All four contracts use the
  one name, so a V2 implementer learns it once. Documented in the README.

* **The contracts are `async def` on a real loop; the adapters' own tests keep their
  `send(None)` driver.** `tests/integrations/local/` asserts that the local adapters never
  suspend, which is a real property worth keeping and is exactly what a shared contract must not
  assume. The two drivers coexist; the contract module explains why.

* **Tamper detection is an opt-in fixture.** `BlobIntegrityError` is the property the evidence
  chain rests on, but staging it needs damage no production path can do, and the spec forbids
  contracts that reach into adapter internals. So the binding supplies a `corrupt_blob` callable —
  the fake's own `corrupt()` method, and for the filesystem store a rewrite of the blob's file that
  restores its read-only mode afterwards. A binding that omits it skips one test; both bindings
  here supply it, so nothing is skipped.

* **`asyncio.gather(..., return_exceptions=True)` for the two-writer test.** It expresses the race
  honestly and works for an adapter that really suspends, at the cost of pinning the contracts to
  the asyncio backend — which `ASYNC_BACKEND` states and which matches what the CLI, API and
  workers run on.

* **Behaviour the port does not promise is not asserted.** Two divergences between the fake and
  the SQLite adapter were found and deliberately left to the adapters; both are named in the
  README and raised under Follow-up work below.

## Operator follow-ups

None. Every command in this report ran here in a few seconds; the whole workspace suite is
`752 passed in 16.32s`, comfortably inside the 5-minute CI budget.

## Follow-up work

1. **`save_results` disagrees about a ranking that names one article twice** —
   `SqliteSearchRepository` rejects it with a `ValueError` (its schema's primary key would refuse
   the rows, and the adapter checks explicitly so a raw `sqlite3.IntegrityError` never crosses the
   port); `InMemorySearchRepository` stores it. `SearchRepository.save_results` in
   `application/ports/persistence.py` documents only the other two rejections, so the contract
   asserts only those. A use case that passed a duplicate article would pass its fake-backed tests
   and fail in production. The fix is a one-line rule in the port docstring plus a matching check
   in the fake and a contract test — both files this task may touch, but the port docstring belongs
   to `v1-e02-t02-ports`, so it is the PM's call whether that is a spec amendment here or a small
   follow-up task.

2. **`find_by_canonical_url` disagrees when several articles share a URL** —
   `SqliteArticleRepository` returns the oldest match by `created_at`, `article_id`;
   `InMemoryArticleRepository` returns whichever it inserted first. The port does not make the
   canonical URL unique and says nothing about which match comes back, so the contracts store one
   article per URL. Either the port should promise an answer (oldest match, which the SQLite
   adapter already implements and documents) or the repositories should make the URL unique. Worth
   settling before E04's deduplication code relies on one of the two behaviours.

3. **Import-boundary enforcement will need a rule for `debate_core.testing.contracts`** —
   `v1-e02-t06-import-boundary-guard` should allow it to import pytest while keeping pytest out of
   `domain` and `application`. Not a problem today; noting it so the contract written there covers
   this package deliberately rather than by omission.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
