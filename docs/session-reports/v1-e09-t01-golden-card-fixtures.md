# Session report: v1-e09-t01-golden-card-fixtures

| | |
|---|---|
| Task | `v1-e09-t01-golden-card-fixtures` — Golden card fixtures from team files |
| Spec | [`plan_specs/v1/e09-v1-quality-pilot/t01-golden-card-fixtures.yaml`](../../plan_specs/v1/e09-v1-quality-pilot/t01-golden-card-fixtures.yaml) |
| Epic / release | `v1-e09-v1-quality-pilot` / `v1.5` |
| Branch | `task/v1-e09-t01-golden-card-fixtures` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This session built the tooling that comes before the coach's card selection, as the PM's brief of
2026-11-14 scoped it, and stops there for a partial merge. The Goal stays **InProgress**. ac1, ac2,
ac3 and ac5 are NOT RUN until the resume. ac4's scrub test passes on invented files and on the
committed fixtures, which are none yet; its run over the real corpus is NOT RUN.

`scripts/import_golden_card.py` has four commands:

* `list` reads the three season folders with the platform's own parser and classifies every whole
  card by event, season, source type, length band and omission cut. It writes a balanced shortlist
  of about 45 to a folder outside the repo, keyed by stable candidate IDs, and prints counts only.
* `import --ids` copies each pick into `tests/fixtures/golden_cards/<case_id>/` as a cut-down excerpt
  of its own package, once the coach attests the card. It strips cutter marks and scrubs metadata,
  comments and tracked-change authors through the existing `scrub_docx_fixture.py`, and a roster
  denylist only when `--denylist` names one. It refuses an excerpt that does not re-read as the
  same card.
* `check` fails on any author metadata, comment or tracked-change author it finds, and on a
  denylist entry when one is named.
* `index` rewrites `INDEX.md`, which is committed with no cases.

**The PM ruled on Deviations 1 to 3 on 2026-11-14,** and the same session carried the ruling
into the tooling (section *After the PM's rulings*, below). The operator then confirmed the
repository is public, and a replacement ruling made Q2 B: no source snapshot enters the repository.

* `import` asks the coach about each pick and refuses a card without the attestation (Q1), shown
  failing first;
* the corpus's `README.md` states what the corpus keeps (attested, scrubbed card excerpts) and
  what it never does (source pages, which stay in a local folder outside the repository);
* the snapshot half (digests in `case.json`, the local copy, `check`'s integrity run) is the
  resume's.

A third ruling of the same day, by the product owner, replaced the roster denylist
(`8561c0f`, Decisions):
* the corpus takes only cards the coach cut or re-cut;
* the attestation is now "cut or re-cut by the coach, and reviewed by the coach for names", and it
  is the control on names in place of the denylist;
* `--denylist` is optional and off by default, and its tests stay, on invented lists;
* the metadata, comment and tracked-change scrub and the cutter-mark rule run on every import.

Nothing real has been committed. The import can run now.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `select-and-copy` | Tooling done; selection and import NOT RUN | Lister, importer (with the coach's per-card attestation), checker and index built and tested (84 tests in `tests/golden`). The node's criterion (`INDEX.md` exists) passes, with 0 cases. The coach's selection and the import are the resume's. |
| `record-sources` | NOT RUN | A network call, the operator's at the resume. No E04 recorder exists (Deviation 2): the operator runs `debate-research fetch`, then the resume's copy script copies each snapshot to a local folder outside the repository, and `case.json` records its digests, URL, fetch date and access status (ruling, Q2 B). The PM amends this node in the next batch. |
| `label-offsets` | NOT RUN | Resume. The offsets go into `case.json`; the PM amends this node in the next batch. |
| `expected-renders` | NOT RUN | Resume. |
| `scrub-and-signoff` | Scrub test PASS on invented files and committed fixtures (none); coach sign-off NOT RUN | `tests/golden/test_fixture_scrubbed.py`, shown red first and checked by mutants (below). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: at least 24 cases, balanced Policy/LD/PF, `INDEX.md` with case id, event, season, source type and research need | NOT RUN | Index exists with those columns and 0 cases. Waits on the coach's picks and the import; Deviation 1 is ruled (Q1: A). The PM amends ac1 for Q2 B in the next batch. |
| ac2: each case's offsets reproduce the team card's evidence from the recorded snapshot (fixture-integrity test) | NOT RUN | No snapshots or labels yet (resume). By the ruling (Q2 B) this becomes the operator's `import_golden_card.py check` over the local folder, not a test; the PM amends ac2 in the next batch. |
| ac3: coach-authored span labels per case | NOT RUN | Resume. |
| ac4, as the product owner's ruling restates it: a scrub test confirms no fixture DOCX carries author or lastModifiedBy metadata, comments or tracked-change authors, and every case carries the coach's attestation (the spec's text, still naming a roster denylist, is amended in the next batch) | PASS on invented files and the committed fixtures (none yet); over real cases it runs in CI once they are imported | `uv run pytest tests/golden/test_fixture_scrubbed.py` → `19 passed in 6.48s` (`-n 0`). Red first, each time the rules changed, and checked by mutants (below), including the two the PM named and six for the optional denylist. |
| ac5: coach signs off the corpus | NOT RUN | Resume. |
| Node `select-and-copy`: `tests/fixtures/golden_cards/INDEX.md` exists | PASS | `test -f tests/fixtures/golden_cards/INDEX.md` → exists, last line `0 cases.` |
| Node `record-sources`: `tests/fixtures/golden_cards/policy-001/snapshot.normalized.txt` exists | NOT RUN | No cases yet. |
| Node `label-offsets`: `uv run pytest tests/golden/test_fixture_integrity.py` | NOT RUN | The file is the resume's. |
| Node `expected-renders`: `uv run scripts/label_golden_card.py --render-expected --check` | NOT RUN | The script is the resume's. |
| Node `scrub-and-signoff`: `uv run pytest tests/golden/test_fixture_scrubbed.py` | PASS | `19 passed in 6.48s` |
| Node `scrub-and-signoff`: coach approves the corpus | NOT RUN | Resume. |

### Red run, then green

The tests were written against a skeleton with the real signatures whose every behaviour refuses
nothing, and that state was committed (`1788c90`):

* **Red, `tests/golden` at `-n 0`:** 50 failed, 4 errors, 15 passed.
* **The 4 errors** are the `imported` fixture's own assertion (`assert 0 == 6`): the skeleton lister
  finds no candidate. That is an assertion failure, not a collection error.
* **The 15 passes:**
  * must-not cases: two unknown source types, a cite with no link, seven cites that keep their own
    endings, a body with no cut;
  * the two committed-fixture checks, over a corpus that is empty today;
  * the two `list` guards that live in `main`, which the skeleton kept (refusing an output folder
    inside the repo, and stopping with no digest key).
* **Green after the implementation** (`eca18c3`): 68 passed, 1 failed. The failure was a real gap:
  capitals after the cite's closing bracket (`...] MQ`) were not read as a cutter mark. The rule was
  widened to match, then 69 passed. With the tests added since, **72 passed** (`-n 0`, and under
  xdist in 2.30 s).

### Mutants

21 mutants, each applied to the committed tree and run over `tests/golden` at `-n 0`, with
`PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared. Each file was restored with
`git checkout HEAD --`, and the tree was clean after the runs. No Hypothesis property is involved.

| Mutant | Result | Caught by |
|---|---|---|
| **Skip the docProps scrub** (`_blank_core_properties` not called, in `scrub_docx_fixture.py`) | CAUGHT, 1 failed | `test_imported_excerpts_carry_no_author_metadata`. The author is deliberately not on the denylist, so only the metadata check sees it. |
| **Skip the denylist** (the importer scrubs with an empty list) | CAUGHT, 1 failed | `test_no_roster_name_survives_the_import`, through `check_fixtures` with the real tmp denylist. Since `8561c0f` this covers a denylist named with `--denylist`. |
| Checker ignores `dc:creator` | CAUGHT | `test_the_checker_flags_a_team_file_that_was_never_scrubbed` |
| Checker skips text files | CAUGHT | `test_the_checker_finds_a_roster_name_in_a_text_file` |
| A missing denylist read as an empty list | CAUGHT, 2 failed | `test_a_missing_denylist_is_a_hard_failure[check]`, `[import]`, since renamed `test_a_denylist_named_but_missing_is_an_error` |
| An empty denylist accepted | CAUGHT | `test_an_empty_denylist_is_refused` |
| Excerpt keeps the header relationship | CAUGHT | `test_the_excerpt_rereads_as_the_card_and_keeps_only_what_the_card_needs` |
| Excerpt keeps the template link and document variables | CAUGHT | same |
| Cutter marks not stripped from the excerpt | CAUGHT | `test_every_imported_cite_has_lost_its_cutter_mark` |
| No re-read check | CAUGHT | `test_an_excerpt_that_does_not_reread_as_the_card_is_refused` |
| No refusal of a denylisted name in a body | CAUGHT | `test_a_card_whose_body_names_someone_on_the_roster_is_refused` |
| No changed-file refusal | CAUGHT | `test_import_refuses_an_unknown_id_a_repeat_and_a_changed_file` |
| Research need written unscrubbed | CAUGHT, 2 failed | `test_no_roster_name_survives_the_import`, `test_the_research_need_is_the_tag_with_the_roster_name_removed` |
| Cite words before the host | CAUGHT, 11 failed | source-type table, host-outranks-words test, import index test |
| Acronyms (`[PDF]`, `(AP)`) read as cutter marks | CAUGHT, 3 failed | the kept-cite table |
| Shortlist ignores files already used | CAUGHT, 2 failed | both shortlist tests |
| Shortlist does not alternate cuts | CAUGHT, 2 failed | both shortlist tests |
| Copier refusal ignored | CAUGHT, 3 failed | lister classification, ID and `list` tests |
| Abbreviated cards kept | CAUGHT | `test_the_lister_classifies_every_whole_card_and_counts_the_rest` |
| `write_shortlist` writes inside the repo | SURVIVED, then CAUGHT | `main` refuses first, so its guard masked this one. Added `test_the_shortlist_writer_itself_refuses_a_folder_inside_the_repository`. |
| `main` lets the shortlist go inside the repo | CAUGHT | `test_list_refuses_to_write_the_shortlist_inside_the_repository`, after it was given a scratch digest key so a mutant cannot read the operator's |

Two of the mutants did what they were meant to do and wrote an empty test shortlist (`[]`) into the
worktree. Both times I deleted it. Since then, the refusal test uses a scratch digest key.

### After the PM's rulings (2026-11-14)

Two rulings came back in the same session, before the pull request. The first (Q1: A, Q2: A on
three conditions, Q3: yes) was carried out in `01045ec`. The operator then confirmed the repository
is public, and the second ruling replaced Q2 with B; `ce36398` carried that out. Q1 and Q3 stand.

* **The coach attests each pick (Q1).** `import` asks about each known, not yet imported ID before
  it reads the file. It asks in the terminal, by ID only: "did the team cut this card itself, not
  copy it from another program, the caselist or a camp file? Type yes to import it". Only `yes`
  imports the card. Any other answer refuses the pick (`REFUSED_NOT_ATTESTED`), and so does stdin
  that is not a terminal, where nothing is asked. `case.json` records `coach_attests_team_cut:
  true`, and a committed case without it fails
  `test_every_committed_case_carries_the_coachs_attestation`. The shortlist's instructions say the
  same.
  * *Why a question, not a flag:* a flag holding the same IDs as `--ids` would attest every pick
    in one stroke. The question is asked once per card, and the import cannot pass it silently.
* **What the corpus keeps (Q1, Q2 B).** `tests/fixtures/golden_cards/README.md` says:
  * one scrubbed excerpt per card the coach attests the team cut, never a whole file;
  * no source page or snapshot enters the repository;
  * `case.json` records the snapshot's raw and normalized SHA-256, URL, fetch date, access status
    and the card's offsets, and the snapshots stay in a local folder outside the repository;
  * a paywalled, private or robots-disallowed source is dropped, not kept as a local case;
  * v1-e04-t06's and v1-e04-t07's rules hold here as everywhere.

  `INDEX.md`'s header and `tests/README.md` point to it. `tests/README.md` had said no excerpt is
  committed anywhere, so it now names this one exception and says no page is committed.
* **The reader guard is withdrawn.** For the first Q2, `01045ec` added
  `tests/golden/test_corpus_readers.py`, which failed when anything but the corpus's own tooling
  named the corpus folder ("no other part of the repository may read them"). That condition
  protected committed pages, and under Q2 B there are none. Kept, it would also have failed
  v2-e14-t05's planned tests over these cards. `ce36398` removes it; it can come back from
  `01045ec` (pre-rewrite, local only) if the PM wants the excerpts guarded too. Its red run, planted break and two mutants
  are below for the record.

**Red run of the attestation** against a skeleton that refuses nothing (`ask` returns yes and prints nothing, `import`
never asks, `case.json` without the key): **10 failed, 74 passed.** The failures were the 8
terminal-question cases, the refusal test, the no-terminal import and the `case.json` dict, each an
assertion. The committed-case test and the real-repository reader test pass on today's tree, so
each got a planted break:

* an untracked `packages/debate_core/src/debate_core/golden_probe.py` naming the corpus →
  `test_only_the_corpus_tooling_names_the_corpus` failed (`assert ['packages/de...den_probe.py'] == []`);
* a planted `policy-999/case.json` with `coach_attests_team_cut: false` →
  `test_every_committed_case_carries_the_coachs_attestation` failed (`assert ['policy-999'] == []`).

Both plants were removed, and the tree was clean after. (The first plant tested the reader guard,
since withdrawn.)

**Mutants**, 7, each applied to the committed tree and restored, over `tests/golden` at `-n 0`:

| Mutant | Result | Caught by |
|---|---|---|
| `y` also attests | CAUGHT | `test_only_yes_at_the_terminal_attests[y\n-False]` |
| No terminal check (piped stdin is asked) | CAUGHT, 2 failed | the no-terminal unit test and the no-terminal import |
| The question is not printed | CAUGHT, 6 failed | the terminal-question cases |
| Asked before the unknown and repeat checks | CAUGHT | `test_a_pick_the_coach_does_not_attest_is_refused_before_its_file_is_read` (who was asked) |
| `main` ignores its `attest` argument | CAUGHT | `test_import_takes_ids_space_or_comma_separated` |
| Guard ignores untracked files (guard since withdrawn) | CAUGHT | `test_the_check_finds_a_reader_outside_the_tooling` |
| Guard allows all of `tests/` (guard since withdrawn) | CAUGHT | same |

The refusal test also deletes the unattested card's file, so a check moved after the file read
would refuse it as `the file is no longer where the listing found it` and fail the test.

### After the product owner's ruling (2026-11-14)

The ruling replaced the roster denylist with the coach's attestation (Decisions). Commit `8561c0f`:

* **The attestation** is now asked as "did the coach cut or re-cut this card, and review it for
  names? Type yes to import it" and recorded as `coach_cut_and_reviewed_for_names: true`. A card
  without it is refused (`REFUSED_NOT_ATTESTED`, reworded to match). The shortlist tells the coach
  to pick only cards the coach cut or re-cut, never a debater's own cut, and to read each pick for
  names. No case was ever imported under the old key, so nothing needed migrating.
* **`--denylist` is optional and off by default** for `import` and `check`. With none given, the
  importer uses `NO_DENYLIST` (no entries), reads no file, and refuses, replaces and reports no
  name. `check` prints `denylist: off`. A denylist named explicitly is still refused when missing,
  empty or inside the repository: asking for a check and getting none would pass everything. The
  default path `DEFAULT_DENYLIST` is gone, so nothing reads `~/.debate-intelligence/` unasked.
* **Unchanged on every import and check:** the docProps, comment and tracked-change-author scrub
  and the cutter-mark rule. `check` fails on any metadata whether or not a denylist is named.
* The denylist tests stay, on invented lists. Two tests are new: import and check without a
  denylist (they must read none, the excerpts must carry no metadata, and `check` must pass), and
  check without a denylist failing on an unscrubbed file.
* The corpus `README.md`, the `INDEX.md` header, `tests/README.md` and the script's docstring say
  the same.

**Red run:** the new and changed tests against the unchanged importer (`ce36398`): **9 failed, 75
passed.**
* The no-denylist import read a denylist when none was given (`AssertionError: a denylist was
  read with none given`).
* The no-denylist check stopped for want of one.
* The `case.json` dict and the 6 terminal-question cases failed on the old wording.

In that red run, the old default made `check` try the operator's default denylist path. It
printed nothing, and with the new default nothing reads that path.

**Mutants**, 6, each applied to the committed tree and restored, over `tests/golden` at `-n 0`:

| Mutant | Result | Caught by |
|---|---|---|
| docProps scrub only with a denylist (`scrub_docx_fixture.py`) | CAUGHT | `test_import_and_check_run_without_a_denylist_and_still_strip_the_metadata` |
| Tracked-change authors redacted only with a denylist | CAUGHT | same |
| With none given, a default path is read | CAUGHT, 2 failed | both no-denylist tests (`a denylist was read with none given`) |
| `check` skips metadata without a denylist | CAUGHT | `test_check_without_a_denylist_still_fails_on_metadata` |
| No `denylist: off` line | CAUGHT, 2 failed | both no-denylist tests |
| A named but missing denylist read as off | CAUGHT, 3 failed | `test_a_denylist_named_but_missing_is_an_error[check]` and the in-repository refusal on assertions. The `[import]` case ends in a FileNotFoundError on its missing shortlist, a crash rather than a catch. |

### Before the report

| Check | Result |
|---|---|
| After the product owner's ruling (`8561c0f`), affected set (60 files: the same set less the withdrawn guard) | Two halves, CI's markers, each under `hard_stop.py 115`: **765 passed in 39.32s** and **1823 passed in 74.50s**, 2588 in all (load 12 to 23). `tests/golden` at `-n 0`: 84 passed (19 + 65). `ruff format --check .` 2119 files formatted, `ruff check .` clean, `pyright` 0 errors, `lint-imports` 20 kept, `validate_specs.py` OK, `check_links.py` OK. |
| After the replacement ruling (`ce36398`: README, INDEX header, `tests/README.md`, the guard removed) | `tests/golden` at `-n 0`: **82 passed in 0.65s** (84 less the guard's 2). `pyright` 0 errors; `ruff format --check` and `ruff check` on the changed Python clean; `check_links.py` OK, 3875 links. The affected set was not re-run: the change since the run below is the INDEX header string, prose and a deleted test file, all inside what `tests/golden` covers. |
| Affected set, after the first ruling's changes (61 files) | `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` stopped at its 115-second limit at about 99% (load 3.4). Re-run as two halves of the same 61 files, CI's markers (`-m "not slow and not live"`, `-n auto`): **765 passed in 42.05s** and **1823 passed in 74.03s**, 2588 in all (the 2576 below plus the 12 new tests). The slow tier reaches only validate-dev's planted-break file, as before. |
| `ruff format --check .` / `ruff check .`, after the ruling | 2120 files already formatted / All checks passed |
| `pyright` (whole project), after the ruling | 0 errors, 0 warnings, 0 informations |
| `lint-imports` / `validate_specs.py` / `check_command_blocks.py` / `check_links.py`, after the ruling | 20 kept, 0 broken / OK: 685 files, 41 epics, 622 tasks, 22 releases / OK, 703 blocks / OK, 3875 links |
| `uv run scripts/affected_tests.py --run --slow`, before the ruling | Stopped by `hard_stop.py` at its 115-second limit at about 98% of the fast tier (load 2.4). Re-run as the fast tier alone over the same 60 files: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -m "not slow and not live" <the 60 files>` → **2576 passed in 86.60s** (load 5.5 to 7.3). The only slow file the set reaches is `tests/scripts/test_affected_tests_planted_breaks.py`, which is validate-dev's alone (agreement 10). So the slow tier has nothing to run here, and the pull request's `slow-tests` job leaves it to validate-dev too. |
| `ruff format --check .` / `ruff check .` | 2118 files already formatted / All checks passed |
| `pyright` (whole project, as CI) | 0 errors, 0 warnings (28.9 s). `pyright scripts/import_golden_card.py tests/golden` also 0 errors; the project's `include` covers neither. |
| `lint-imports` | Contracts: 20 kept, 0 broken |
| `uv run scripts/validate_specs.py` | OK: 685 files, 41 epics, 622 tasks, 22 releases |

## Files changed

* **`scripts/import_golden_card.py`** (new): the lister, importer, checker and index writer. It
  reuses:
  * `DebateDocxParser` and `body_paragraphs`, the parser's own Verbatim reading;
  * `copy_card`, the lossless writer's check that a card can be copied;
  * `select_files` from `analyze_team_formatting.py` (v1-e06-t03), its file choice;
  * `infer_format` and `infer_season` from `select_eval_files.py`;
  * the parser evaluation's keyed digest;
  * `scrub_package` from `scrub_docx_fixture.py`, its scrub and verification.
* **`tests/golden/test_fixture_scrubbed.py`** (new): ac4's scrub test.
* **`tests/golden/test_import_golden_card.py`** (new): the lister, shortlist, import and excerpt tests.
* **`tests/golden/synthetic_team_files.py`** (new): invented Verbatim-style team files. They hide an
  invented roster name everywhere Word hides one: docProps, comments, `people.xml`, a header, the
  template link, a document variable, a tracked-change author, a tag and a cite tail. They also carry
  a docProps author who is not on the denylist. `coach_attests` is the "yes" answer for tests that
  are not about the attestation.
* **`tests/fixtures/golden_cards/INDEX.md`** (new): written by `import_golden_card.py index`, 0 cases.
* **`tests/fixtures/golden_cards/README.md`** (new, after the rulings): what the corpus keeps and
  what it never does.
* **`tests/README.md`**: names the golden corpus as the one exception to "no real excerpt is
  committed", and says no source page is.

## Deviations from the spec

1. **Committing team-card excerpts conflicts with an earlier PM ruling.** *Ruled 2026-11-14, Q1: A.*
   Import requires a per-card attestation (since the product owner's ruling: "cut or re-cut by the
   coach, and reviewed by the coach for names", `coach_cut_and_reviewed_for_names`), recorded in
   `case.json`, and refuses a card without it. Opencaselist and Camp Files stay excluded. The
   2026-10-26 rule against whole files stands. The replacement ruling keeps Q1 at A: the excerpts are
   the team's own scrubbed cuts, and the team's files are already disclosed on the caselist. Done in
   `01045ec`, the attestation's tests shown failing first (section *After the PM's rulings*). The
   background as raised:
   * *What asks for it:* the spec, and the brief's item 2, put "the original team card as a
     scrubbed DOCX excerpt" in each case.
   * *What forbids it:*
     * v1-e06-t03's amendment of 2026-10-26 (its ac1): "no team file is copied into the repository
       in any form", because "a team file routinely carries cards another program cut, so
       scrubbing does not make it committable" (`tests/fixtures/team_samples/MANIFEST.md`). The
       same ruling stands behind v1-e31-t02 and v1-e31-t03.
     * Prohibition 9 of `docs/policies/caselist-data-use.md`.
   * *What allows it:* the policy puts "the team's own cut cards, files and uploads" out of scope as
     team work product. So an excerpt of a card the team itself cut may be allowed, where a whole
     team file is not.
   * *What the tooling does about it:*
     * the shortlist asks the coach to pick only cards the coach cut or re-cut;
     * the default exclusions leave out `Opencaselist` and `Camp Files`;
     * `--fixtures` can point the import at a folder outside the repo. Under Q2 B that is where the
       snapshots go, not the excerpts.
   * *What waited:* the import, now unblocked.
2. **No "E04 fixture recorder" exists, and committing real source pages conflicts with an earlier
   PM ruling.** *Ruled 2026-11-14, Q2: B* (a replacement ruling, after the operator confirmed the
   repository is public; the same day's Q2 A, which needed a private repository, no longer applies):
   * **A source snapshot never enters the repository.** `case.json` records the snapshot's SHA-256
     (raw and normalized), its URL, the fetch date and access status, and the card's offsets.
   * At the resume the operator runs `debate-research fetch URL --json`. The copy script then copies
     each snapshot from the dev store into a local fixtures folder outside the repository (the
     existing `--fixtures <local folder>` path), never into `tests/`.
   * **ac2's integrity check is the operator's `import_golden_card.py check`**, given that folder.
     It verifies each SHA-256, then reproduces the evidence from the offsets under the current
     normalizer, and fails outright when a snapshot is missing or its digest differs. It is not a
     test, because a test may not read a path outside the repository.
   * CI runs a structure test that every case has its digests, URL, offsets and attestation, the
     metadata scrub over the committed DOCX files, and the tooling tests on invented files.
   * Paywalled, private or robots-disallowed sources are dropped, not kept locally as cases.
   * The PM amends ac1, ac2, the record-sources and label-offsets nodes, and v1-e09-t02, t03 and
     t04 (golden evaluation run locally against that folder) in the next batch.

   This session changed only what the first Q2 had put in place (`ce36398`): the README and
   `tests/README.md` say no page is committed, and the reader guard is withdrawn. The snapshot
   half is the resume's. The background as raised:
   * *What E04 has:* every cassette is synthetic, by the PM's amendment of 2026-10-25 to v1-e04-t06
     (`tests/fixtures/http/README.md`): "a real article is someone else's text".
   * *What forbids it:* v1-e04-t07 forbids "a real page, PDF or its text committed to the
     repository".
   * *What does exist for real pages:* `debate-research fetch URL --json`. It stores the snapshot in
     the local store and prints no page text.
   * *What the resume needs:* that fetch, plus a script that copies a stored snapshot into the local
     folder and records its digests in the case.
   * *Seeding from v1-e06-t03's samples* (brief item 4): **they cannot seed any case.**
     * `tests/fixtures/team_samples/` holds only a manifest of 314 keyed digests: every team file,
       chosen by rule, with no card-level information. Being listed says nothing about a card.
     * The synthetic `team_format` tree is invented text with no public source.
     * What the task did reuse from v1-e06-t03 is its file-selection rule.
3. **ac4's denylist half cannot run in CI.** The denylist lives only on the operator's machine. So
   the in-repo test does two things:
   * it checks the committed fixtures' metadata on every run;
   * it proves the checker and the importer on invented files.

   The check against the real denylist is `import_golden_card.py check`, run by the operator, and
   it fails outright when the denylist is missing. *Ruled 2026-11-14, Q3: yes, confirmed by the
   replacement ruling.* *Then superseded in part by the product owner's ruling:* the denylist is no
   longer required, so ac4 has no operator half. ac4 is now the CI scrub test (no metadata,
   comments or tracked-change authors, every case attested). The operator's `check` keeps the
   snapshot half (ac2, Q2 B) and, with `--denylist`, an optional name check. The PM amends ac4 and
   the scrub-and-signoff node in the next batch.
4. **Files outside `constraints.packages`.** The spec's own criteria name
   `tests/golden/test_fixture_scrubbed.py` (and, later, `test_fixture_integrity.py`). But
   `constraints.packages` lists only `tests/fixtures/golden_cards` and `scripts`. The tests and their
   helper are in `tests/golden/`. *Accepted 2026-11-14; the PM adds `tests/golden` to the packages
   in the next batch.*
5. **The research need is the card's tag.** `INDEX.md` and `case.json` record the tag, scrubbed
   through the denylist, as the research need. Nothing in the team file states a need separately.
   The coach may rewrite it when labelling (ac3). *Accepted 2026-11-14.*

## Decisions and assumptions

* **Event** comes from the outermost folder naming LD, PF or Policy, and **season** from the
  nearest `20YY-20YY` folder (`select_eval_files.py`'s rules).
  * *What it cannot tell:* a file in a folder that names no event is skipped and counted. A file
    filed under one event but written for another is read as the folder's event. A folder naming
    two events is read by the first rule that matches (LD, then PF, then Policy).
* **Source type** comes from the cite's link host first: tables of news, think-tank, journal and
  government hosts, plus `.gov`, `.mil` and national-government suffixes. If the host says nothing,
  it comes from words in the cite, in this order:
  * news organisations' names, then government words, then think-tank words, then journal words;
  * last, the generic words newspaper titles are made of (`Times`, `News`, `Daily`).

  An intergovernmental body (UN, WHO, IMF, World Bank, OECD, NATO) counts as government. A
  university page, a blog or a company site is *unknown*. Known limits: *Institute* in a
  university's name reads as think tank, and an ellipsis the author printed reads as an omission
  cut.
* **Candidates** are whole cards (`FULL`) with a tag, a cite, at least 20 body words, a link or DOI
  in the cite (the source has to be fetched again), and nothing the lossless copier refuses (table,
  picture, text box, footnote). Every card left out is counted by its first reason.
* **Shortlist:** a third per event. Within an event it goes round the ten source-type × length
  buckets, alternating cut and uncut, one card per file until no other file is left, taken in
  candidate-ID order. Deterministic.
* **Candidate IDs** are `<event>-<10 hex>`: an HMAC under the parser evaluation's existing digest
  key, over the file's bytes and the card's first paragraph index. They are stable across runs and
  join to nothing without the key, so an ID can be pasted into a command or a report. The lister
  stops if the key is missing.
* **The excerpt** is the source package cut down to the card's paragraphs.
  * *What it keeps:* the source's own styles, numbering, theme and settings, so it looks as the
    team cut it.
  * *What it leaves behind:* headers and footers, comments, `people.xml`, custom XML, footnotes,
    media, `docProps/app.xml`, and the settings' template link, document variables and mail merge.
  * *Then the scrub:* `scrub_package` blanks the docProps author, last editor and title, removes
    comment markup and rewrites every `w:author` as `Redacted`. With a named denylist it also
    replaces the denylist's entries, verifies itself and deletes its output if any entry survives.
  * *Last, a re-read:* the excerpt must parse as one card with the source card's body text and
    formatting spans exactly.
* **The coach's attestation replaces the roster denylist** (the product owner's ruling of
  2026-11-14, which replaces the denylist parts of Q3 and the brief).
  * The corpus takes only cards the coach cut or re-cut; debaters' own cuts are not picked.
  * The per-card attestation is "cut or re-cut by the coach, and reviewed by the coach for names",
    recorded as `coach_cut_and_reviewed_for_names`. `import` refuses a card without it. This is the
    control on names in place of the denylist.
  * The denylist is no longer required. `import` and `check` run without one, and a missing
    denylist is not an error.
  * `--denylist` is optional and off by default. The built and tested denylist code stays, and its
    tests use invented lists.
  * The docProps, comment and tracked-change-author scrub and the cutter-mark rule run on every
    import and check, and `check` fails on any metadata it finds.
  * One call of mine inside the ruling: a denylist *named* with `--denylist` that is missing,
    empty or inside the repository is still an error. The ruling makes the denylist optional; it
    does not say a requested check may silently check nothing.
* **The denylist, when named,** is plain text, one entry per line, at a path the operator gives
  (no default path; `~/.debate-intelligence/` is no longer read unasked). A missing file, an empty
  file or a path inside the repo is refused. Entries of four characters or fewer match only as whole words (the scrub script's rule).
* **Cutter marks** are initials or a code at the very end of a cite: after `//` or `\\`, in brackets
  or parentheses of capitals, after a dash following the closing bracket, or two to four capitals
  after the closing link or bracket. A list of file types, wires, countries and agencies (`PDF`,
  `AP`, `UN`, `GAO`, …) is never read as a mark.
* **The attestation is a question per card, not a flag** (Q1, reworded by the product owner's ruling). A flag repeating the `--ids` list
  would attest every pick in one stroke. The question names only the ID, refuses anything but `yes`,
  and is never asked, so never passed, when stdin is not a terminal. `case.json` records
  `coach_cut_and_reviewed_for_names: true`, and a committed case without it fails in CI.
* **The reader guard is withdrawn** (Q2 B). It enforced the first Q2's "no other part of the
  repository may read them", which protected committed pages. Under Q2 B no page is committed, and
  the guard would have failed v2-e14-t05's planned tests over these cards. It is in `01045ec` if
  the PM wants the excerpts guarded too.
* **The CI structure test is only partly built.** Today it checks that every committed case is
  attested, a directory per `case.json` and an `INDEX.md` the importer would write. Digests, URL,
  fetch date, access status and offsets come from the record-sources and label-offsets nodes, so
  their part of the structure test is the resume's, as is `check`'s snapshot half and the copy
  script.
* **Screening the invented names.** The names the tests commit were screened read-only against the
  dev store's `hspolicy26`, `hsld26` and `hspf26` disclosures (`caselist_words` and `is_withheld`;
  counts only).
  * The first invented author's first name matched one caselist's school and team words, so it was
    replaced; the replacement matches none.
  * The earlier name was in this branch's history (`1788c90`..`501e0cc`) until the rewrite below,
    which removed it before any push.
  * Per the PM's note of 2026-11-14, later screening of that kind is the operator's to run, and a
    session gets only pass or fail.
* **The branch was rewritten before any push** (PM review, 2026-11-14). The repository is public,
  and a pull request's commits stay reachable on GitHub after a squash merge.
  * The PM's review edit was committed first (`c8b7097`, the pre-rewrite head).
  * Then `git reset --soft` to the merge base with `dev` (`c6b9fe4`) and one commit, `f4c8973`. Its
    tree is byte-identical to the pre-rewrite head: `git diff c8b7097 f4c8973` prints 0 lines.
  * The count, by a scratch script that reads the replaced first name from the commit that replaced
    it and prints only counts:
    * over `git log -p c6b9fe4..c8b7097`, before the rewrite: **2**, the line that added it and the
      line that removed it, so the count can fail;
    * over `git log -p c6b9fe4..HEAD` after the rewrite, messages and authors included: **0**,
      whole word and ignoring case alike;
    * after this report's own commit on top: **0** again (recounted below the PM review).
  * The commit hashes cited elsewhere in this report (`1788c90`, `eca18c3`, `501e0cc`, `01045ec`,
    `ce36398`, `8561c0f`) are pre-rewrite commits. Their content is all in `f4c8973`, and none was
    pushed. They remain in this machine's object store until the reflog expires.
  * The store's `.sqlite3` file is byte-identical (mtime unchanged); its `-shm` and `-wal` sidecars
    moved.

## Questions for the PM

Deviations 1, 2 and 3 went to the PM as one relay prompt and were ruled on 2026-11-14, Q2 twice
(above). None is open. One point for the PM's review: the reader guard was withdrawn with the first
Q2 (Decisions). Restoring it for the excerpts alone is a one-commit change.

## Operator follow-ups

**Done.** Two steps of earlier drafts are gone. The repository-visibility check went because the
operator confirmed the repository is public, so Q2 is B. Creating a denylist went because the
product owner's ruling made it unnecessary.

*1. List the candidates*: **done.** The operator ran it, and 45 were shortlisted, 15 per event. The
command, for a re-run (read-only, 1 to 3 minutes):

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e09-t01-golden-card-fixtures
uv run python scripts/import_golden_card.py list ~/Documents/debate/2024-2025 ~/Documents/debate/2025-2026 ~/Documents/debate/2026-2027 --output ~/golden-card-shortlist
```

Success looks like this:

* `files read:` above zero (the t03 survey counted 314 files by the same rule);
* `candidates:` above zero;
* `shortlist: 45`, or fewer, with the per-event counts saying where the shortfall is;
* `~/golden-card-shortlist/shortlist.md` exists.

The terminal output is counts only. Paste it back. Never paste `shortlist.md` or `candidates.json`:
they hold tags, cites and file paths.

Then the coach opens the shortlist and picks 24 to 30 IDs. Pick about a third per event, every
source type, short and multi-paragraph cards, some with an omission cut, and only cards the coach
cut or re-cut, never a debater's own cut, whose source is still free to read. The coach reads each
pick for names before importing it:

```bash
open ~/golden-card-shortlist/shortlist.md
```

**At the resume.** The import waits for the resume (PM review). Before the pull request, an import
into this worktree would put real excerpts on a branch that is about to be pushed, outside the
reviewed state.

*2. Import the picks and check them*, in the resumed task's worktree (seconds per card). Run it in
a terminal with the coach present. The import asks about each ID: "did the coach cut or re-cut this
card, and review it for names? Type yes to import it". The coach checks the ID in `shortlist.md`
and types `yes` only for a card the coach cut or re-cut and has reviewed for names. Any other
answer refuses that card. Replace `PICKED-IDS-HERE` with the coach's IDs, separated by spaces or
commas. An ID that is not in the shortlist is refused, so the
placeholder imports nothing:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e09-t01-golden-card-fixtures
uv run python scripts/import_golden_card.py import --shortlist ~/golden-card-shortlist --ids PICKED-IDS-HERE
```

Success:

* one line of removal counts per case;
* `imported N, refused 0`, with N the number of picks;
* a refusal names an ID and a reason, never the card. Send those back and the coach picks a
  replacement. A card the coach answered no to is refused as `the coach did not confirm cutting or
  re-cutting this card and reviewing it for names`. The coach picks another.

Then:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e09-t01-golden-card-fixtures
uv run python scripts/import_golden_card.py check
```

Success: `docx checked:` equal to N, then `denylist: off`, and the last line `clean`.

*3. Record the sources*, after the import (a network call;
about 5 to 10 seconds per case under the fetcher's politeness limits). It fetches each case's
source link into the dev store, with the profile pinned and any leftover data-directory override
cleared. It keeps the JSON reports, which hold no page text, outside the repo:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e09-t01-golden-card-fixtures
mkdir -p ~/golden-card-fetches
for case in tests/fixtures/golden_cards/*/case.json; do id="$(basename "$(dirname "$case")")"; link="$(.venv/bin/python -c 'import json, sys; print(json.load(open(sys.argv[1]))["source_link"])' "$case")"; env -u DEBATE_STORAGE__DATA_DIR DEBATE_ENV=dev uv run debate-research fetch "$link" --json > ~/golden-card-fetches/"$id".json; echo "$id exit $?"; done
```

Each case should print `exit 0`. `exit 3` means the source is no longer accessible (paywalled,
blocked, gone), and that card is dropped from the corpus, not kept as a local case. The resume's
copy script then copies each stored snapshot to a local folder outside the repository and records
its digests in the case; it also drops any page that needed a login or was cut short by a paywall.
Send back this count of outcomes, and nothing else from those files:

```bash
grep -ho '"access_status": *"[A-Z_]*"' ~/golden-card-fetches/*.json | sort | uniq -c
```

## Follow-up work

* **Resume of this task** (`scripts/task resume`), after the PM's amendments:
  * the import (operator, with the coach);
  * the copy script: each stored snapshot into a local fixtures folder outside the repository,
    its raw and normalized SHA-256, URL, fetch date and access status into `case.json`, and every
    paywalled, private or robots-disallowed case dropped (Q2 B);
  * `check`'s snapshot half: given the local folder, verify each digest and reproduce the evidence
    from the offsets under the current normalizer, failing outright on a missing snapshot or a
    changed digest (ac2);
  * the CI structure test's remaining fields (digests, URL, offsets);
  * the offsets and labels, the expected renders and the coach's sign-off.
* **PM, next batch** (per the rulings):
  * amend ac1, ac2, the record-sources and label-offsets nodes (Q2 B);
  * amend ac4 and the scrub-and-signoff node to the product owner's wording: no metadata, comments
    or tracked-change authors, and every case attested; no roster denylist;
  * add `tests/golden` to `constraints.packages`;
  * amend v1-e09-t02, t03 and t04 to run their golden evaluation locally against the local folder.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** CHANGES_REQUESTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-14

**Notes:**

The work is accepted as built. Two changes are needed before the partial pull request, and both are
small.

1. **The earlier invented name must not reach GitHub.** Decisions says the first invented author's
   first name matched a real caselist's school and team words, and that it stays in this branch's
   history (`1788c90`..`501e0cc`) because "the squash merge leaves it out of dev". The repository
   is public, though. `scripts/task pr` pushes the branch, and a pull request's commits stay
   reachable on GitHub (`refs/pull/<n>/head`) after the squash and after the branch is deleted. So
   a word from a real school name or team code would be public for good, against prohibition 9.
   * The branch is not yet on the remote. Rewrite it so that no commit carries that name: a soft
     reset to the merge base and one commit, or an interactive-free rebase that rewrites the
     commits that hold it.
   * Then confirm with a count over `git log -p <merge-base>..HEAD` for the name, printing only the
     count, which must be 0.
   * Record the rewrite and the count in Decisions. Commit hashes cited elsewhere in the report may
     be replaced by the new one.
2. **The import moves to the resume.** Operator follow-up 2 is written as "Now", but an import into
   this worktree before the pull request would leave real excerpts in a branch that is about to be
   pushed, outside the reviewed state. Move step 2 (import and check) under "At the resume", ahead
   of the record step. Step 1 (list) stays "Now". The operator has already run it, with 45 shortlisted
   (15 per event).

For the record, what is accepted:

* **The tooling.**
  * The lister reuses the parser, the copier's check, v1-e06-t03's file rule, the season and event
    rules and the parser evaluation's keyed digest.
  * The excerpt keeps the card's own styles and leaves headers, comments, `people.xml`, custom XML,
    footnotes, media and the template link behind. It is scrubbed, then re-read as the same card.
* **The attestation as a per-card terminal question,** never a flag and never passed when stdin is
  not a terminal. It is recorded in `case.json` and required in CI. This is the right design.
* **The product owner's ruling as built.**
  * `--denylist` is optional, and the metadata, comment and tracked-change scrub runs on every import
    and check.
  * The session's one call inside the ruling, that a denylist *named* but missing, empty or inside
    the repository is still an error, is accepted.
* **The evidence.**
  * The red run, then green (the cutter-mark gap after `]` was found and closed).
  * 21 mutants, then 7 and 6 more, all caught; the one survivor, the shortlist writer's own guard,
    gained its test.
* **The reader guard withdrawn under Q2 B:** accepted. It protected committed pages, and none are
  committed. The excerpts need no guard of their own.
* **Deviations 1 to 5:** accepted as ruled. In the next batch the PM amends:
  * ac1, ac2 and ac4;
  * the record-sources, label-offsets and scrub-and-signoff nodes;
  * the packages (`tests/golden`);
  * v1-e09-t02, t03 and t04.
* **One note for later sessions.** The screening of invented names against the dev store was read
  with counts only, but a match still tells a session that a word is a real school or team word.
  Future screening of that kind is the operator's to run, and a session gets pass or fail.

Append the two changes and a line under this review. The PM then appends an `ACCEPTED` review with
the merge line `scripts/task pr --partial`.

**Session, 2026-11-14: both changes are done.** (1) The branch was rewritten before any push: a soft
reset to the merge base `c6b9fe4` and one commit, `f4c8973`, whose tree is byte-identical to the
pre-rewrite head. The name counts 0 over `git log -p c6b9fe4..HEAD` (2 before the rewrite),
recorded in Decisions. (2) Operator follow-up 2 (import and check) is under "At the resume", ahead of
the record step; step 1 is marked done, with 45 shortlisted, 15 per event.

## Criteria still open after the changes (2026-11-14)

Recorded by the PM from this session's acceptance-criteria table above, unchanged by the two
changes, so that `scripts/task pr --partial` reads them after the first review:

| Criterion | Status |
|---|---|
| ac1: at least 24 cases, balanced, `INDEX.md` | NOT RUN (the import is the resume's; the coach's 26 picks are held locally) |
| ac2: offsets reproduce the evidence from the recorded snapshot | NOT RUN (resume; the operator's `check` over the local folder under Q2 B) |
| ac3: coach-authored span labels per case | NOT RUN (resume) |
| ac4: no metadata, comments or tracked-change authors, every case attested | PASS on invented files and the committed fixtures (none yet); over real cases at the resume |
| ac5: coach sign-off | NOT RUN (resume) |

## PM review (2026-11-14, second)

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-14

**Notes:**

Accepted for a partial merge. Both changes are done, and the Goal stays `InProgress`.

* **The rewrite was checked by the PM, read-only.**
  * `origin/dev..HEAD` is two commits, `f4c8973` (the tooling, on the merge base `c6b9fe4`) and
    `afd06d9` (this report).
  * The worktree is clean.
  * The count method is sound: 2 before the rewrite, so it could fail, then 0 after, messages and
    authors included.
  * The pre-rewrite commits are only in this machine's object store, and a push sends only what the
    branch reaches.
* **The import is under "At the resume",** and the list step is marked done. One stale sentence in
  the Summary, "The import can run now", is superseded by Operator follow-ups and needs no further
  edit.
* **The coach's picks are in, held locally:** 26 cards (Policy 8, LD 9, PF 9), which meets ac1's 24
  with room for two drops at the record step.
* **The resume follows the PM batch** that amends ac1, ac2, ac4, the record-sources, label-offsets
  and scrub-and-signoff nodes, the packages, and v1-e09-t02 to t04.

`scripts/task pr --partial`

## Resumed 2026-11-15 to 2026-11-25: the corpus, its snapshots, labels and renders

Session status: **PARTIAL.** The Goal stays **InProgress**: ac1 to ac4 pass, and ac5, the coach's
sign-off, is the one criterion left. This section names cases only by ID and counts, never a card's
text, a tag, a school or a student.

### Summary

* **The corpus is committed: 31 cases**, Policy 8, LD 9, PF 14. By source type: news 6, think tank
  14, government 2, journal 2, unknown 7. Each case holds `case.json` (with its snapshot record),
  `team-card.docx`, `expected.json` and `expected.docx`. No source page or snapshot is in the
  repository.
* **The tooling the resume added:**
  * `record` copies each case's snapshot from the dev store to the local folder
    `~/.debate-intelligence/golden-snapshots/<case_id>/` and records its digests in `case.json`;
  * `check --snapshots` is ac2's operator check;
  * `label_golden_card.py` writes `expected.json` from the coach's own underline, highlight and
    Emphasis runs, and `--render-expected` writes `expected.docx`;
  * `retire` takes out a case that does not label;
  * `review` writes the coach's sign-off sheet, one row per case and a sign-off line, outside
    the repository.
* **Three pick rounds**, all run by the operator with the coach answering each attestation:

  | Round | List | Picked | Imported | Dropped at record | Labelled | Retired for not labelling |
  |---|---|---|---|---|---|---|
  | 1 | 45 | 26 | 25 (1 not attested) | 11, then 1 more after its retry | | |
  | 2 | 90 | 30 | 29 (1 already imported) | 10 more (4 after their one retry) | | |
  | 1 and 2 together | | | 54 | 22 | 24 of 32 | 8 |
  | 3 (PF) | 150 (98 new) | 17 | 17 | 5 | 7 of 12 | 5 |
  | **All** | | **73** | **71** | **27** | **31** | **13** |

  71 imported, less 27 dropped and 13 retired, is the 31 cases. The 40 retired IDs are on
  `INDEX.md`'s last line.
* **The PM's rulings of 2026-11-16, 2026-11-19 and 2026-11-20 are built in**, and listed under
  Deviations below.

### Plan nodes

| Node | Status | Notes |
|---|---|---|
| `select-and-copy` | Done | 71 imported over three rounds; 31 remain. |
| `record-sources` | Done; PASS on the amended criterion (PM ruling of 2026-11-25) | `record` built and run by the operator. The spec's artifact, `policy-001/case.json`, no longer exists: `policy-001`'s source was dropped (Deviation 7). |
| `label-offsets` | Done | 31 of 31 labelled; operator's check clean. |
| `expected-renders` | Done | 31 renders, byte-identical on every run. |
| `scrub-and-signoff` | Scrub done; sign-off NOT RUN | The review sheet is built as the PM ruled on 2026-11-25; the coach's reading of it is the next operator step. |

### Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: at least 24 cases, balanced across Policy, LD and PF, `INDEX.md` with case id, event, season, source type and research need | PASS, read as the PM's floor of 2026-11-20 (at least 24 in all, at least 8 per event) | `uv run pytest tests/golden/test_corpus_structure.py` → `38 passed`, including `test_the_committed_corpus_meets_the_floor_and_its_index_counts_it`, which failed at 24 cases (PF 7) and passes at 31 (Policy 8, LD 9, PF 14). `INDEX.md` has the five columns, the counts by event and source type, and the retired line. The spec's "24-30" and "balanced" await the PM's amendment (Questions). |
| ac2: each case's offsets reproduce the team card's evidence from the recorded snapshot, and each snapshot's SHA-256 is verified, by the operator's check | PASS, in the matching form of the PM's ruling of 2026-11-20 | Operator, 2026-11-25: `uv run python scripts/import_golden_card.py check --snapshots ~/.debate-intelligence/golden-snapshots` → `docx checked: 62, other files checked: 64`, `denylist: off`, `snapshots verified: 31 of 31`, `evidence reproduced: 31 of 31`, `clean`. |
| ac3: a coach-authored span label set per case (underline and highlight ranges with purpose) from the team's original markup | PASS, with every purpose null (PM rulings of 2026-11-16 and 2026-11-19) | `uv run scripts/label_golden_card.py --snapshots ~/.debate-intelligence/golden-snapshots` (session, 2026-11-25) → `labelled 31, not labelled 5`, the 5 then retired. Every `expected.json` passes the structure test: offsets only, spans inside one segment, highlights inside the underlining. |
| ac4: no fixture DOCX carries author or lastModifiedBy metadata, comments or tracked-change authors, and every case carries the coach's attestation | PASS | `uv run pytest tests/golden/test_fixture_scrubbed.py` → `19 passed`. `uv run python scripts/import_golden_card.py check` → `docx checked: 62`, `clean`. The renderer's own name and its 3 manifest parts are allowed in `expected.docx` only (PM ruling of 2026-11-16). |
| ac5: the coach signs off that the corpus is representative | NOT RUN | The task merges as a partial on ac5 (PM ruling of 2026-11-25). The review sheet, one row per case and a sign-off line, is written to a local file outside the repository by the operator's command (Operator follow-ups); nothing from it goes into this report or the repository. |
| Node `select-and-copy`: `INDEX.md` exists | PASS | `test -f tests/fixtures/golden_cards/INDEX.md` → exists. |
| Node `record-sources`: amended to `tests/golden/test_corpus_structure.py` (PM rulings of 2026-11-19 and 2026-11-25; the spec's text, `policy-001/case.json`, is amended in the next PM batch) | PASS on the amended criterion | `uv run pytest tests/golden/test_corpus_structure.py` → `38 passed`; it requires every case's whole snapshot record. The spec's artifact as still written is absent (`test -f` exits 1): `policy-001` was dropped at record (Deviation 7). |
| Node `label-offsets`: `uv run pytest tests/golden` | PASS | `211 passed in 3.07s` |
| Node `label-offsets`: the operator's integrity check is clean | PASS | as ac2 |
| Node `expected-renders`: `uv run scripts/label_golden_card.py --render-expected --check` | PASS | `rendered and compared 31, differ 0, not rendered 0`, exit 0 |
| Node `scrub-and-signoff`: `uv run pytest tests/golden/test_fixture_scrubbed.py` | PASS | `19 passed in 2.11s` |
| Node `scrub-and-signoff`: the coach approves the corpus | NOT RUN | as ac5 |

### The labels, in counts

* **Segments:** 31 cases. 7 unmarked cuts (cuts made with no marker) in 4 cases: `ld-009`,
  `ld-017`, `pf-003` and `pf-014`.
* **Highlights cut back to the underlining:** 69 characters in 17 cases. A highlight outside the
  underlining cannot be stored (the card model requires every highlight inside it), so those
  characters are cut back.
* **Why cards did not label** (13 in all, every one retired):
  * Rounds 1 and 2 (8 cases), diagnosed by a class-only comparison that printed no text:
    * 5 hold text the page does not (a changed page or the cutter's own words);
    * 2 carry PDF footnote digits;
    * 1, `pf-017`, recorded a page that is not the article.
  * Round 3 (5 cases): a stretch of the card is not in the snapshot. Characters found:
    * `pf-025`: 1090 of 1224;
    * `pf-028`: 2024 of 3282;
    * `pf-029`: 0 of 1627;
    * `pf-032`: 205 of 2891;
    * `pf-036`: 553 of 3761.

    These were not diagnosed further, since the corpus is over its floor without them.

### Evidence: red runs and mutants

Each mutant was applied to the committed tree and its tests run at `-n 0`, and the file was
restored afterwards (`git checkout HEAD --`). The tree was clean after each set.

**The 2026-11-15 tooling** (`record`, `check --snapshots`, labels, renders). No red run against a
do-nothing skeleton was recorded for this part, which is a gap against the PM's red-run-first
practice; the tests were checked by mutants only.

* **Snapshot half, 18 mutants, all CAUGHT:**
  * the snapshot's digests and size: raw digest, raw size, document key, text digest;
  * the comparison: normalizer idempotence, case folding, team markers, segment join, no offsets
    counted as reproduced;
  * fetch reports: another link, PAYWALLED;
  * the store and folders: the WAL read, worktrees, dry-run deletes;
  * the structure rules: access status, text keys, highlight outside the underlining, a span
    across segments.
* **Label half, 18 mutants:**
  * **CAUGHT (13):** no unmarked search, one word enough, short tail, edge spaces, raw offsets,
    Emphasis, highlight cut-back, cut-back count, span ids, render check writes, parts allowance,
    author everywhere, and a marker that omits nothing accepted.
  * **SURVIVED, then the code changed (3):**
    * the label's own markup check and its reproduction check could never fire, so both were
      removed;
    * the touching-segment merge was replaced by a refusal (`NOTHING_OMITTED`), which its mutant
      fails.
  * **Equivalent (1):** "render not verified" (`verify` for `verify_and_record`). No citation field
    is verified, so the card is UNVERIFIED either way.
  * **Crashed (1):** "render skips markup" crashed rather than failing an assertion, so it is not
    counted as a catch.
* **Three bugs the tests found:**
  * the dry run left SQLite side files in the store (now opened `immutable=1` when there is no
    `-wal`);
  * two stray words from a later paragraph could finish a card (the four-word minimum now applies
    on both sides of an unmarked cut);
  * an omission marker inside a word was merged away.

**2026-11-19 and 2026-11-20 changes:**

| Change | Shown failing | Mutants |
|---|---|---|
| The renderer's name and parts fail in `team-card.docx` (ruling 3 of 2026-11-16) | The new test failed with `check` changed to accept the name in every file | |
| `record` counts by source type and access status | The test failed with a counter that lists only the types seen | 1, CAUGHT |
| `--drop-errors` | | 2, both CAUGHT: the option doing nothing, and the option dropping every unrecorded case |
| ac1's floor and `INDEX.md`'s counts | On a copy of the committed tree, the floor test failed with `0 cases, fewer than 24` | 4, all CAUGHT: a per-event floor of 6, a floor growing with the corpus, no check on the total, a source type with no case left out |
| The matching form (ruling 1 of 2026-11-20) | Before the change, the label refused 6 cards over typography only, from the class-only diagnosis; the 18 earlier labels came out byte-identical after it | 8, all CAUGHT by assertion failures: no matching normalization (9 failed), no line-end hyphen rule (6), pilcrow compared (5), a hyphen after any character (1), a hyphen before any character (2), whitespace compared (21), segments joined with a space (3), a ligature's second letter unpositioned (1). Four of them (no matching normalization, no line-end hyphen rule, pilcrow compared, whitespace compared) also had 7 setup errors each, where a world's labelling broke. The first run showed the typeset card's test reading a missing `expected.json` (a crash), so it now asserts its label line first (`a8c7702`). |
| The review sheet (PM ruling of 2026-11-25): one row per case with ID, event, season, source type, research need and tag, then a sign-off line | The rewritten test failed against the old sheet on its header assertion (`'\| Case \| Event \| Season \| Source type \| Research need \| Tag \|...' in ...`) | 4, all CAUGHT on assertions: the tag column filled from the research need (the test rewrites one case's need so the two differ), no sign-off line, the first case left out, the research-need column left out |
| Numbers never reused (ruling 3 of 2026-11-20) | **7 of 8 new tests failed** against the old importer; the eighth, existing IDs kept, passes as it should. A probe printed `dropped policy-001 -> late card numbered policy-001`, and the first test failed on `'policy-001' == 'policy-003'` | 6. **CAUGHT (5):** record retires nothing (3 failed), a rewrite forgets the listed IDs (3), the retire dry run writes (1), a present case may be retired (1), and retired IDs not counted as taken (1, through `write_index`'s own refusal `policy-002 is a case in the corpus, not retired`, a deliberate refusal rather than a crash). **SURVIVED, then CAUGHT (1):** the first free number was equivalent while every departure is retired. `test_a_number_below_the_highest_is_not_given_again_even_with_no_retired_line` (a folder removed by hand) now catches it (`79c625c`). |

### Before the report (2026-11-25)

| Check | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | 71 test files, **2720 passed in 64.21s**, exit 0 (load 2.9) |
| the same, again after the review sheet's change and this report's edits | 76 test files, **3623 passed in 86.73s**, exit 0 (load 3.2); then `ruff format --check`, `ruff check`, `lint-imports`, `check_links.py`, `check_command_blocks.py` and `validate_specs.py` clean as below. `pyright` (whole project) was run after the sheet's last format: 0 errors. `tests/golden`: 211 passed. |
| the same with `--slow` | fast tier as above; slow tier 5 test files, **13 passed in 13.11s** |
| `uv run --frozen ruff format --check .` / `ruff check .` | 2140 files already formatted / All checks passed |
| `uv run --frozen pyright` (whole project, after the last format) | 0 errors, 0 warnings, 0 informations |
| `lint-imports` / `check_thin_handlers.py` | 20 kept, 0 broken / 74 handlers within 25 statements |
| `docs_index.py --check-descriptions` / `check_links.py` / `check_command_blocks.py --base origin/dev` | 72 documents described / 3902 links OK / no `#` comments in 721 blocks |
| `pre-commit run check-merge-conflict --all-files` | Passed |
| `uv run scripts/validate_specs.py` (phase left InProgress) | OK: 690 files, 41 epics, 627 tasks, 22 releases |
| Branch history | The case folders in `merge-base..HEAD` are exactly the 31 present cases; none of the 40 retired IDs appears in any commit. |

The README correction of this section's commit (offsets are in `expected.json`, not `case.json`)
is prose only. After it, `tests/golden` and `check_links.py` were run again.

### Files changed (resume)

* **`scripts/golden_snapshots.py`** (new): fetch-report reading, the read-only store loader, the
  local snapshot copy, the snapshot checks, the matching form (`comparison_view`) and the
  structure validators.
* **`scripts/import_golden_card.py`**: the `record`, `check --snapshots`, `retire` and `review`
  commands. Also `--drop-errors`, the source-type counts, ac1's floor, `INDEX.md`'s counts and
  retired line, never-reused numbering, and the renderer allowance in `metadata_problems`.
* **`scripts/label_golden_card.py`** (new): labels and renders.
* **Tests:**
  * `tests/golden/snapshot_world.py` (new): an invented store, pages and fetch reports;
  * `test_golden_snapshots.py`, `test_label_golden_card.py`, `test_corpus_structure.py` and
    `test_case_numbers.py` (new);
  * `test_fixture_scrubbed.py`, `test_import_golden_card.py` and `synthetic_team_files.py`
    (changed).
* **`tests/fixtures/golden_cards/`**: 31 case folders, `INDEX.md`, and `README.md`, which covers
  each case's files, the renderer allowance, the purpose rule, the UNVERIFIED verdict, what
  "reproduce" means and the never-reused IDs.

### Deviations from the spec (resume)

Numbered on from the first session's five.

6. **The offsets are in `expected.json`, not `case.json`.** The amendment of 2026-11-14 puts "the
   card's offsets" in `case.json`. They sit with the spans they belong to, in `expected.json`,
   which the spec's description names. `case.json` holds the snapshot record. The corpus README's
   first section said `case.json`, and this section's commit corrects it.
7. **`record-sources`'s artifact is `policy-001/case.json`, a case that no longer exists.**
   `policy-001`'s source was dropped at record, and numbers are never reused. *Ruled 2026-11-19:*
   the node is checked by `tests/golden/test_corpus_structure.py`; the PM amends the node.
8. **BLOCKED is dropped, and ERROR gets one retry.** *Ruled 2026-11-19.* `--drop-errors` drops a
   case still ERROR after its one retry and changes nothing else.
9. **Corpus size: a floor, not "24-30" or a share.** *Ruled 2026-11-20:* every case that labels and
   checks clean is kept, and the CI test requires at least 24 in all and 8 per event. The PM
   amends "24 to 30" and "balanced". Today: 31 cases, Policy 8, LD 9, PF 14.
10. **ac2's "exactly" is the matching form.** *Ruled 2026-11-20:* card and snapshot are compared
    under `debate_core.evidence.fingerprints.normalize_for_matching` (NFKC, casefold, quotes,
    dashes, invisibles). Whitespace, the pilcrow and a line-end hyphen are not compared. Offsets
    point only into the snapshot, and the evidence is the snapshot's own characters.
11. **Every span purpose is null.** *Ruled 2026-11-16 (2A) and 2026-11-19 (A):* no format profile
    maps a markup kind to claim, warrant, internal link or impact. A "read aloud" value would be a
    later task's change to the card model, and the script then regenerates the expected files.
12. **Every render is UNVERIFIED (`CITATION_UNVERIFIED`).** *Ruled 2026-11-16 (1A):* the cite is the
    team's, typed by hand, so no citation field verifies. Harvesting citations is on the V1.x list,
    and renders are regenerated, never edited.
13. **The renderer's name and 3 manifest parts are allowed in `expected.docx` only.** *Ruled
    2026-11-16 (3)*, named in the README and pinned by a test both ways.
14. **Case IDs are never reused; INDEX.md keeps a retired line.** *Ruled 2026-11-20 (3).* `retire`
    takes out a case that does not label, as a dry run until `--execute`. The 8 cases removed in
    round 2 were deleted by hand, before `retire` existed. Their IDs went on the retired line when
    it was introduced, and none of them was ever committed.
15. **Journal sources: 2, both PF**, from the coach's round-3 picks (ruling 2A of 2026-11-20). The
    description keeps "journal", and no amendment is needed.
16. **A script uses `debate_core.testing` fakes.** `render_case` verifies each card with the real
    `EvidenceVerifier` over `InMemoryArticleRepository` and `InMemorySnapshotStore`, so the render
    carries the verifier's real verdict without a store. Nothing in `debate_core` changed.
17. **The session ran the label and render steps itself** after the operator's first run in round
    2: after the comparison change, and for round 3. They read the local
    snapshot folder outside the repository and make no network or model call, and only counts and
    IDs were printed. The PM's rule is that a *test* reads no path outside the repository; no test
    does.

### Decisions and slips

* **Unmarked cuts are allowed and counted.** A stretch the page does not hold whole is matched by
  its longest prefix of at least 4 words, and the rest after a cut of at least 4 words. A card
  that still does not fit is refused, never guessed.
* **Highlights are cut back to the underlining** and the characters counted (69, above).
* **Round 3's list was filtered for the coach.** The importer refuses a card whose case is
  present, but a retired case's folder is gone, so it would take a re-picked retired card under a
  new number. 52 of the 150 cards were in the corpus or picked before. The session wrote a copy of
  `shortlist.md` without them in the list's own folder outside the repository (98 cards), and
  checked the 17 picks against the list and earlier rounds by ID before the import.
* **Slip, 2026-11-20:** a `git add -A` swept the 25 imported case folders into a wip commit. It was
  undone with a soft reset before anything left the machine. Since then, commits stage named paths
  only, and the branch history holds only the 31 present cases (above).
* **Slip, 2026-11-25:** the session ran `git fetch origin dev` to compare the spec with dev, a
  network call that is the operator's under the PM's rule. It fetched refs from the project's own
  remote, no page and no model, and it changed nothing in the worktree. The spec is unchanged on
  dev, and dev has moved past the branch's base, so the sync before the PR is the operator's.
  *Noted by the PM on 2026-11-25:* it stays in this report, and later sessions leave fetches to the
  operator.

### Questions for the PM

Both were ruled on 2026-11-25, and none is open.

1. **The spec amendments are the PM's, in the next PM batch:**
   * the description's "24-30" and "roughly a third each" become the floor (24 in all, at least 8
     per event);
   * ac2's "exactly" becomes the card-fingerprint matching form;
   * ac3 holds with purpose null;
   * ac4 gains the renderer allowance in `expected.docx` only;
   * `record-sources`' artifact becomes `tests/golden/test_corpus_structure.py`.

   Until that batch merges, `record-sources` is recorded as passing on the amended criterion,
   citing the ruling (above).
2. **A retired card can be picked again:** *ruled A.* The filtered-list practice stays. The corpus
   is complete at 31 and no further round is planned. Option B, a local file of every candidate ID
   imported, is a small follow-up if a round is ever needed.

### Operator follow-ups (resume)

* **The coach's review sheet (ac5).** Writes `review.md` to a local folder outside the repository
  and opens it, a few seconds. One row per case (ID, event, season, source type, research need,
  tag), then the sign-off line. The coach opens each case's `team-card.docx` beside its
  `expected.docx` and signs the line:

  ```bash
  cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e09-t01-golden-card-fixtures
  uv run python scripts/import_golden_card.py review --output ~/golden-card-shortlist/review.md && open ~/golden-card-shortlist/review.md
  ```

  Success: `review sheet: 31 cases`, and the sheet opens. Send back only whether the coach signs
  off, and the IDs of any cases he wants changed. Never paste the sheet: it holds the cards'
  tags.
* **Sync before the PR.** Dev has moved since the branch's base. `scripts/task sync` is the
  operator's.

### Follow-up work

* The coach's sign-off (ac5), after this partial merge. The Goal goes to `Succeeded` after it
  and the PM's amendments.
* If a pick round is ever needed again: a local file of every candidate ID imported, read by the
  importer (ruling 2B of 2026-11-25).
* V1.x: harvest citations from the snapshots, so cards whose metadata verifies render VERIFIED
  (ruling 1B of 2026-11-16).
* A later card-model task, if wanted: a "read aloud" span purpose; then regenerate the expected
  files.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-25

**Notes:**

Accepted for a partial merge. ac1 to ac4 and every node but the sign-off pass. ac5, the coach's
sign-off, is open, so the Goal stays `InProgress`.

* **The corpus is complete and meets the floor:** 31 cases (Policy 8, LD 9, PF 14). By source:
  think tank 14, unknown 7, news 6, government 2, journal 2. Every case is coach-attested, scrubbed
  and labelled.
* **The operator's checks are clean:**
  * `check --snapshots`: 31 of 31 snapshots verified, 31 of 31 evidence reproduced;
  * `check`: 62 DOCX files clean;
  * the renders: byte-identical on every run.
* **Every ruling of 2026-11-14 to 2026-11-25 is built as given** (Deviations 6 to 17):
  * the public-repository rule (no snapshot committed);
  * the attestation in place of the denylist;
  * the matching form;
  * purpose null, and the real UNVERIFIED verdict;
  * the renderer allowance in `expected.docx` only;
  * numbers never reused, with the retired line;
  * the per-event floor.
* **The evidence, with its gaps stated.**
  * The 2026-11-15 tooling (`record`, `check --snapshots`, labels, renders) has no recorded red run
    against a skeleton. That is a gap against the practice, accepted because 36 mutants cover it, of
    which 3 survivors led to code changes and none is open.
  * One mutant crashed rather than failing an assertion; it is not counted as a catch, and that is
    the right way to report it.
  * Every change from 2026-11-19 on was shown failing first.
* **The two slips are handled.**
  * The `git add -A` that swept case folders into a commit was undone before anything left the
    machine. The branch history now holds exactly the 31 present cases, and none of the 40 retired
    IDs appears in any commit. That matters in a public repository.
  * The `git fetch` is noted; later sessions leave it to the operator.
* **Labelling the cards in the session (Deviation 17) is accepted.** It read only public article
  snapshots in the local folder, printed counts and IDs only, and no test reads a path outside the
  repository.
* **The checks.** The affected set ran in full within the bound (76 files, 3,623 passed) and so did
  its slow tier (13 passed). Pyright, the import contracts and the spec validator are clean. **Dev
  has moved, so `scripts/task sync` before the PR.**
* **Next.**
  * ac5: the coach reads the review sheet and signs, or names case IDs to change.
  * The PM's batch amends the description's size, ac2's matching form, ac3's null purpose, ac4's
    allowance and record-sources' artifact.
  * Then the Goal is `Succeeded`.
* **Follow-ups:** citation harvesting stays on the V1.x list. A "read aloud" purpose and a file of
  imported candidate IDs are filed only if wanted.

`scripts/task pr --partial`

## Operator records (recorded by the PM, 2026-11-25)

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac5: the coach signs off that the corpus is representative | NOT RUN | PASS | 2026-11-25: the coach read the review sheet (31 cases: Policy 8, LD 9, PF 14) and signed off, with no case changed |
| Node `scrub-and-signoff`: the coach approves the corpus | NOT RUN | PASS | as ac5 |

Every criterion passes, so the Goal is `Succeeded`. The PM batch of 2026-11-25 amends the description's size,
ac1's floor, ac2's matching form, ac3's null purpose, ac4's renderer allowance and `record-sources`' artifact,
as the rulings of 2026-11-16 to 2026-11-20 say.
