# Session report: v1-e02-t03-local-repositories

| | |
|---|---|
| Task | `v1-e02-t03-local-repositories` — Local filesystem and SQLite repository implementations |
| Spec | [`plan_specs/v1/e02-domain-core/t03-local-repositories.yaml`](../../plan_specs/v1/e02-domain-core/t03-local-repositories.yaml) |
| Epic / release | `v1-e02-domain-core` / `v1.0` |
| Branch | `task/v1-e02-t03-local-repositories` |
| Session status | COMPLETE |

## Summary

`debate_core.integrations.local` now holds V1's adapters for the four persistence ports, so the
CLI can run with no cloud account. `FsSnapshotStore` keeps snapshot bytes under the SHA-256 of
their own content at `<data_dir>/blobs/sha256/ab/cd/<digest>` — the same key S3 will use in V2 —
written through a temp file and a rename, read-only once written, and re-hashed on every read so a
tampered blob raises `BlobIntegrityError` instead of being returned. `SqliteDatabase.open(data_dir)`
opens `<data_dir>/debate.sqlite3`, applies the pragmas the repositories assume and migrates the
schema; the three repositories share that one database, so there is one connection, one migration
run, and a write spanning two tables is one transaction.

Each entity is stored as the JSON its own Pydantic model produced, revalidated on the way out,
alongside the key columns SQLite needs to find and order it. Nothing reads a value out of a key
column, which is what keeps the local schema the shape DynamoDB can take in V2 without local-only
fields. `SqliteCardRepository.save` applies the optimistic-concurrency check as a single
conditional `UPDATE ... WHERE card_id = ? AND revision = ?`, so there is no window between reading
a revision and writing under it.

Two things are worth the PM's attention. First, the adapters do their file and SQLite I/O
synchronously inside `async def` — the reasoning is under **Decisions**, and it is reversible
behind the port. Second, `save_results` rejects two results naming the same article, which the
in-memory fake currently allows; that is a divergence the shared contract suite in
**v1-e02-t04-repo-contract-tests** will have to settle, and it is listed under **Follow-up work**.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `fs-blob-store` — Content-addressed filesystem SnapshotStore | DONE | `fs_blob_store.py`; sharded digest paths, temp+rename writes, read-only blobs, integrity check on read |
| `sqlite-base` — SQLite connection and migrations | DONE | `sqlite_db.py` and `migrations/0001_initial_schema.sql`; WAL, foreign keys, `schema_version`, idempotent migration runner |
| `sqlite-repos` — Article, Card and Search repositories | DONE | `sqlite_repos.py`; JSON documents plus indexed key columns, conditional UPDATE on revision, cursor pagination |
| `quality-gates` — Type check and boundary check | DONE | pyright strict and ruff clean over `debate_core`; no forbidden dependency added |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1 — `FsSnapshotStore` stores bytes under their SHA-256 key, dedupes identical content, writes via temp-file + rename, detects a corrupted blob on read | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_fs_blob_store.py` → `17 passed`. Covering tests: `test_put_returns_the_sha256_of_the_content`, `test_blob_lands_under_the_two_level_sha256_fan_out`, `test_identical_content_is_stored_once` (asserts the inode is unchanged, so nothing was rewritten), `test_a_completed_write_leaves_no_temporary_file`, `test_a_failed_rename_stores_nothing_and_cleans_up`, `test_a_tampered_blob_is_reported_not_returned`, `test_a_truncated_blob_is_reported` |
| Goal ac2 — SQLite repositories implement their ports, persist entities as JSON validated on read, enforce `expected_revision` with a conditional UPDATE | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_sqlite_repos.py` → `41 passed`. `test_each_adapter_satisfies_its_port` binds each adapter to its Protocol (pyright checks it statically, `isinstance` at runtime); `test_a_hand_edited_row_is_reported_rather_than_returned` proves read-time validation; `test_a_stale_write_is_refused_and_changes_nothing` and `test_deleting_a_card_is_guarded_too` prove the revision check |
| Goal ac3 — a versioned migration table creates/upgrades the schema idempotently on first open | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_sqlite_db.py` → `24 passed`. `test_the_schema_is_created_on_first_open`, `test_reopening_applies_nothing_and_keeps_the_data`, `test_applying_migrations_repeatedly_is_a_no_op`, `test_a_fresh_database_records_every_migration_it_ran`, `test_a_migration_that_fails_halfway_is_rolled_back_and_the_run_resumes` |
| Goal ac4 — all adapters live under `debate_core.integrations.local` and are exercised by tests using pytest `tmp_path` only | PASS | Every source file added is under `packages/debate_core/src/debate_core/integrations/local/`; every test takes `tmp_path` and no test names a path outside it. Suite runs with `--disable-socket`, so no network is reachable |
| Node `fs-blob-store` — Blob store tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_fs_blob_store.py` → `17 passed in 1.75s` |
| Node `sqlite-base` — Migration tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_sqlite_db.py` → `24 passed in 1.66s` |
| Node `sqlite-repos` — Repository tests pass including revision conflict | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_sqlite_repos.py` → `41 passed in 1.73s` |
| Node `quality-gates` — pyright passes | PASS | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations` |
| Node `quality-gates` — ruff passes | PASS | `uv run ruff check packages/debate_core` → `All checks passed!` |
| Node `quality-gates` — no forbidden dependencies added | PASS | `grep -rn '^import \(boto3\|botocore\|typer\|fastapi\|httpx\)\|^from \(boto3\|...\)' packages/debate_core/src` → no matches. `grep -rn integrations packages/debate_core/src/debate_core/{domain,application}` → no matches, so the layering still runs one way. Package dependencies unchanged: `sqlite3` is stdlib |
| Whole suite still green | PASS | `uv run pytest` → `563 passed in 16.60s`, well inside the CI budget |
| Specs validate | PASS | `uv run scripts/validate_specs.py` → `OK: 281 files, 38 epics, 223 tasks, 20 releases` |

Coverage of the new modules: `sqlite_repos.py` 100%, `sqlite_db.py` 99%, `fs_blob_store.py` 95%
(the uncovered lines are the `fsync`-on-directory fallbacks for filesystems that refuse it).

## Files changed

**`packages/debate_core/src/debate_core/integrations/`** — new. `__init__.py` states the layering
rule (integrations may import domain and application; neither may import back). `local/__init__.py`
documents the data-directory layout and re-exports the adapters.

**`.../integrations/local/fs_blob_store.py`** — `FsSnapshotStore`: `put`/`get`/`exists`, plus
`path_for`, which is public because the removal runbook and the tests both need to name a blob's
file, and whose key check doubles as the path-traversal guard.

**`.../integrations/local/sqlite_db.py`** and **`.../migrations/`** — `SqliteDatabase.open`, the
pragmas, `build_migrations` (all the validation rules) and `apply_migrations` (the runner), plus
`0001_initial_schema.sql`.

**`.../integrations/local/sqlite_repos.py`** — the three repositories, the shared keyset-pagination
helper, and `CorruptRecordError`.

**`packages/debate_core/tests/integrations/local/`** — new; three test modules, 82 tests, all under
`tmp_path`.

**`packages/debate_core/README.md`** — an `integrations/local/` section in the same form as the
existing ones: the directory layout, a module table, the composition-root snippet and the four
things to know before adding an adapter or a field.

**`docs/architecture/ports-and-adapters.md`** — two small corrections now that the adapters exist,
see **Deviations**.

**`plan_specs/v1/e02-domain-core/t03-local-repositories.yaml`** — Goal `status.phase` → `Succeeded`.

## Deviations from the spec

**None in scope or behaviour.** Two notes on documents the task touched rather than on the spec
itself:

1. `docs/architecture/ports-and-adapters.md` (owned by v1-e02-t02) showed the composition root as
   `SqliteArticleRepository(settings.data_dir)` — one data directory per repository. The
   implementation takes a shared `SqliteDatabase` instead, because four repositories each opening
   the same file would mean four connections, four pragma sets and four racing migration runs. The
   spec's own wording — "the data directory is a constructor argument" — is satisfied by
   `SqliteDatabase.open(data_dir)`. The doc's example and its adapter paragraph were updated to
   match what now exists. Flagging it because the line belongs to another task's document.
2. The spec's node outputs list four paths; the implementation also adds
   `integrations/__init__.py`, `integrations/local/__init__.py` and
   `migrations/__init__.py`, which are the packages those files live in.

## Decisions and assumptions

**The adapters do their I/O synchronously inside `async def`.** The ports are `async` because their
V2 implementations are network-bound, but `sqlite3` and the filesystem are not. A local read is
tens of microseconds, so a thread hop per call would cost more than it saved, and it would force
the SQLite connection to be shared across threads and give up sqlite3's `check_same_thread` guard.
It also makes each call atomic with respect to other tasks on the event loop, because none of them
can interleave at an `await`. If a V1 surface ever fans out enough of these to matter, the fix is a
thread pool inside these adapters and no change anywhere else — which is what the port is for. The
reasoning is in the `integrations/local/__init__.py` docstring, where the next reader will meet it.

**Entities are stored as their own JSON plus key columns.** The alternative — a column per field —
would make every model change in E03 and E04 a migration here and a divergence from DynamoDB, which
the spec's `forbidden` list rules out. Key columns carry only what a lookup or a sort needs, and
nothing reads a value back out of one.

**`canonical_url` is indexed but not unique.** The `ArticleRepository` port does not promise
uniqueness, the in-memory fake does not enforce it, and DynamoDB could not enforce it in V2 without
a transaction on every write. `find_by_canonical_url` therefore returns the *oldest* match, so the
answer stays deterministic when there is more than one; that is stated in the method's docstring
and covered by a test.

**The only foreign key is `search_results` → `searches`.** A result exists only as part of its
search, so `ON DELETE CASCADE` is right there, and it is also what makes `foreign_keys = ON` more
than decoration. No foreign key between entities, because DynamoDB has none and the fakes enforce
none; referential integrity between entities is a service's job.

**Cursors use the same `"<kind>:<id>"` scheme the in-memory fakes mint.** Deliberate, so that
v1-e02-t04's one contract suite can hold the fakes and these adapters to identical behaviour, down
to which cursors are rejected. A cursor whose row has since been deleted is an `InvalidCursor`,
matching the fake.

**Timestamps in sort columns are a fixed-width UTC rendering**
(`YYYY-MM-DDTHH:MM:SS.ffffff`), because `datetime.isoformat()` drops microseconds when they are
zero and two such strings would compare in the wrong order as text. The entity's own ISO 8601
spelling is untouched in the JSON document.

**`MigrationError` is outside the `DomainError` hierarchy** and `CorruptRecordError` is inside it.
A migration failure happens while the composition root is opening the file, before any port exists
to raise it across, so a service catching `DomainError` should not be catching "this build cannot
read this file". A row that no longer validates is reached *through* a port, so it is a
`DomainError` and the CLI's existing handler renders it.

**Tests drive coroutines with `send(None)`, not `asyncio.run`.** Not a preference: the suite runs
with `--disable-socket` and an asyncio event loop builds its self-pipe from `socket.socketpair()`,
which pytest-socket blocks. This is the same driver `tests/application/test_fakes.py` uses, and it
doubles as an assertion that these adapters really do not suspend. When v1-e02-t04 brings an async
test plugin, both can go.

**`STRICT` tables** (SQLite 3.37+, 2021) make a column's declared type a constraint, so an adapter
bug that writes a revision as text fails at the write instead of surfacing as mis-ordered listings
later. `SqliteDatabase.open` checks the linked SQLite version and refuses anything older with a
message that says why.

## Operator follow-ups

None. Every command in this task runs in seconds; the full suite is `563 passed in 16.60s`.

## Follow-up work

1. **`save_results` and duplicate articles — for v1-e02-t04-repo-contract-tests.** The
   `SearchRepository` port names two `ValueError` cases (a result belonging to another search, two
   results sharing a rank). This adapter raises a third: two results naming the same article. The
   domain already states that a search holds at most one result per article, and the schema's
   primary key enforces it, so the alternative was letting a raw `sqlite3.IntegrityError` cross the
   port. `InMemorySearchRepository` currently accepts such a ranking, so the two implementations
   differ. The contract suite should settle it — the recommendation is to add the check to the
   fake and the rule to the port docstring, rather than to relax it here.
2. **An async test plugin — likely v1-e02-t04-repo-contract-tests.** Both this task's `run()`
   helpers and the one in `tests/application/test_fakes.py` exist only because the suite has no way
   to await. `pytest-asyncio` or `anyio` would need `--disable-socket` reconciling with asyncio's
   self-pipe (`--allow-unix-socket` appears to be enough); worth doing once, in the task that first
   needs genuine concurrency.
3. **Nothing yet wires these adapters to settings.** `StorageSettings.data_dir` exists (t05) and
   these constructors take it, but no composition root builds them. That belongs to the first task
   with a command that stores something (E04), not here.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude, project chat), 2026-09-20

**Notes:**

- All criteria pass and the two things this task had to get right are right: content-addressed blob
  keys that match what S3 will use in v1-e29-t04, so the local and cloud stores are the same shape;
  and re-hashing on read so a tampered blob raises BlobIntegrityError instead of being handed back
  as evidence. Checking that the migration .sql actually ships in a built wheel is the kind of
  verification that saves a confusing bug later.
- Synchronous file and SQLite I/O inside `async def` is accepted for V1. It is documented at the
  point of use and reversible behind the port, and the CLI is the only caller. The V2 API must not
  reuse these adapters on an event loop that serves requests; that boundary is already drawn by
  v2-e11 having its own DynamoDB/S3 adapters.
- The `save_results` divergence is a contract question, and your recommendation is the right one:
  rejecting two results for the same article is the correct behaviour, so the fake gets the check
  rather than the adapter losing it. v1-e02-t04 settles it, and its contract suite is the place the
  decision belongs.
- The `docs/architecture/ports-and-adapters.md` fix is accepted although the line belonged to t02.
  Four repositories each opening the same file would mean four connections and four racing
  migration runs; leaving a known-wrong example for the next reader to copy would have been worse
  than the scope deviation.
