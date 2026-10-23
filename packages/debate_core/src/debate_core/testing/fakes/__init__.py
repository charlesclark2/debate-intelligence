"""In-memory implementations of every port, for tests anywhere in the codebase, one module per port.

These are *fakes*, not mocks: each one really does the job its port describes, in a dictionary.
`InMemoryCardRepository` really refuses a stale write, `InMemorySnapshotStore` really deduplicates
identical bytes and really detects a corrupted blob. A test written against them exercises the
same code paths a test against SQLite would, which is what makes the shared contract suite
(v1-e02-t04-repo-contract-tests) able to run unchanged against both.

They ship in `debate_core` rather than in a test directory because every package's tests need them
— `debate_cli`, `debate_api` and `debate_workers` each wire a service to fakes — and because V2's
cloud adapters are held to the same contracts.

Nothing here touches the filesystem, the network or the clock. `FixedClock` and
`SequentialIdGenerator` exist precisely so that a service's output is byte-identical on every run.

Each module but `clock_and_ids` and `all_ports` fakes the port module of the same name in
`debate_core.application.ports`:

* `clock_and_ids`: `FixedClock`, `SequentialIdGenerator`, `FAKE_EPOCH`. They satisfy `Clock` and
  `IdGenerator` structurally and import no port, so the module nearly every test imports reaches
  almost nothing.
* `persistence`: `InMemoryArticleRepository`, `InMemorySnapshotStore`, `InMemoryCardRepository`,
  `InMemorySearchRepository`.
* `card_edit_log`: `InMemoryCardEditLog`, `build_fake_card_edit_log`.
* `caselist`: `InMemoryCaselistRepository`, `build_fake_caselist_repository`.
* `suppression`: `InMemoryAppendOnlyRecord`, `empty_suppression_list`.
* `providers`: `FakeSearchProvider`, `FakeArticleFetcher`, `FakeContentExtractor`.
* `model_router`: `ScriptedModelRouter`, `ScriptedModelResponse`.
* `debate_files`: `FakeDebateFileParser`, `MisbehavingDebateFileParser`,
  `build_fake_debate_file_parser`.
* `parsed_store`: `InMemoryParsedStore`, `build_fake_parsed_store`.
* `all_ports`: `FakePorts` and `build_fake_ports`, one fake for each of the ten ports every service
  takes; the one module that imports several ports, because assembling them is its job.

**One module per port, and this module imports nothing** (`v1-e01-t30`). Until then every fake was
in one `fakes.py` that imported every port, so a test needing `FixedClock` reached caselist
suppression and the parsed store, and so did every change to them (`scripts/affected_tests.py`).
Import a fake from its own module: `from debate_core.testing.fakes.clock_and_ids import FixedClock`.
`tests/architecture/test_fakes_reach_only_their_port.py` fails when a fakes module imports a port
other than its own, or this module imports anything.
"""
