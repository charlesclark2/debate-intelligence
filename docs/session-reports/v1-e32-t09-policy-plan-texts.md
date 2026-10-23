# Session report: v1-e32-t09-policy-plan-texts

| | |
|---|---|
| Task | `v1-e32-t09-policy-plan-texts` — Each Policy affirmative round's plan, counted first, so the landscape names what affs read |
| Spec | [`plan_specs/v1/e32-argument-landscape/t09-policy-plan-texts.yaml`](../../plan_specs/v1/e32-argument-landscape/t09-policy-plan-texts.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t09-policy-plan-texts` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This session did the two parts of the task that needed no ruling, and stopped where the spec and the
PM's brief of 2026-10-23 say to stop. The Goal stays **InProgress**: ac2 to ac4 wait for the PM's
ruling, and ac2 and ac3 then wait for the coach.

* **The counts**, read-only, counts only, over hspolicy26 through 2026-10-20 with v1-e32-t02's reader
  ([below](#the-counts-hspolicy26-through-2026-10-20)). No card text, plan text, team code, school or
  file name is in any output or in this report.
* **The ruled normalizer fix**: `Adv 1 Costs` and `Advantage One: Costs` now reach the
  costs-advantage aliases. Its cases were shown failing first, t01's and t02's tests pass, and t02's
  labeled set is still placed 100%.

**Look first at this: the parsed store holds no plan text.** It keeps cards and leaves out every
other paragraph (`sections`, [parsed-card-store.md](../data/parsed-card-store.md)). A plan text is
almost always an analytic under a block heading `Plan`, with no card under it. So the store shows
the heading in only 33 of 1,770 aff documents, and names the aff in none of them.

Read again from the raw sources, in memory, with the same parser version:
* **1,394 aff documents (78.8%, 448 of 552 teams) have a plan-text label.** In 1,393 of them, the
  store dropped the paragraph under it.
* That paragraph **names single payer or Medicare for All in 726 documents (41.0%; 266 teams,
  48.2%)**, against 159 (9.0%) for the headings today.
* Together with the headings, 789 documents (44.6%) are identified. Carried across each team's own
  rounds, with a guard, that rises to 974 (55.0%; 290 teams, 52.5%).
* **The caselist's own record holds no titles anywhere on this machine.** Round reports and cite
  entries are API resources this project has never fetched, and the data-use policy does not list
  them.

The [questions](#questions-for-the-pm) are one paste-ready block with a recommendation each. The
first is the one everything waits on: **read the raw sources in this task** (my recommendation,
measured at 0.30 s a document), or change the parser in E31 and re-parse.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| plan-texts | In progress: counts done, waiting on the PM's ruling | Counts and options below. The ruled normalizer fix is done and committed (`7b18d8f`). Extraction, the coach's review sheet and the taxonomy edit come after the ruling (spec, forbidden list) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts per side and by teams of plan-text headings, of the paragraph under them as the store holds it (by unit), and of distinct plan texts, sent to the PM with one to three options, before any change | PASS for the affirmative side, sent here | [The counts](#the-counts-hspolicy26-through-2026-10-20) and [the options](#the-options-for-plan-text-the-store-does-not-keep). The negative side is not counted (Deviations 2, question 8). No parser, store or fingerprint was changed |
| ac2: after the ruling, a deterministic extraction of each team's plan text and a review sheet outside the repository, by tests on synthetic sources shown failing first | NOT RUN | Waits for the PM's ruling (spec: "change nothing until the PM rules") |
| ac3: the coach's mechanisms as child affs of single payer with his tag keywords, taxonomy_version bumped, config tests passing | NOT RUN | Waits for the ruling and then for the coach's answers |
| ac4: counts before any rule of the aff rounds and teams each signal identifies, alone and together, sent to the PM; after the ruling, each identified round carries its aff and the signal, an unidentified round stays unidentified, by tests shown failing first | PARTIAL: the counts are done and sent; the rule waits for the ruling | [Signals alone and together](#signals-alone-and-together). The second half is NOT RUN |
| plan-texts node: `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS for the code that exists | `.venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape` under `perl -e 'alarm 60'` → 268 passed in 1.61 s. The node is not done: its extraction is still to build |
| PM brief (3): the two normalizer variants fixed in t01's normalizer, with synthetic cases shown failing first; t01's seeding and t02's matcher tests pass; t02's labeled set still placed 100% | PASS | [The normalizer fix](#the-normalizer-fix-pm-brief-3) |

The pytest commands were run as `.venv/bin/python -m pytest <files>` with a `perl -e 'alarm N'`
limit on the interpreter (working agreement 10).

## The counts (hspolicy26, through 2026-10-20)

**How they were read.** Every pass was read-only. Before each one I checked that no `DEBATE_*`
variable was set and no `caselist pull` was running, and each ran under a 115 s limit on the
interpreter. The scripts were scratch files outside the repository (the scratchpad), and printed
counts only.
* **The sources:** v1-e32-t02's reader (`read_seed_sources`), with `through` 2026-10-20 and parser
  version `2026.10.20-docx-6`. 3,825 sources are on the topic.
* **An aff document** is a source with a live on-topic disclosure on the aff side: 1,770, as in t02.
* **An aff round** is one such disclosure: 2,547. **An aff team** is a disclosing team's identity: 552.
* **A plan-text label** is a paragraph that t01's normalizer reduces to `plan`, `plan text`, `the plan`,
  `pt`, `plantext`, `plan txt`, `plan texts`, `our plan`, `the plan text` or `plan and solvency`.
  It also covers a paragraph that opens `Plan:` or `Plan Text:` and holds the text inline.
* **A plan text's shape** is a paragraph holding the word `should` and a federal actor (`United
  States federal government`, `USFG`, `federal government` or `United States`).
* **An aff alias** is one of single-payer-aff's aliases in policy-2026-27-nhi.yaml 1.0.0, matched as
  words. **A Medicare for All word** is `Medicare for All` or `M4A`, the words t01's affirmative check
  used. No coach-approved list exists yet (question 6).

**Once one pass had shown what the store drops,** a second read the 1,770 aff documents again from
their local blobs. It used the code's parser, which is the store's version, so the stored cards
are reproduced. It ran in memory only, and wrote nothing but per-source flags and plan-text digests
to the scratchpad (no text). All 1,770 aff documents are DOCX; every one had its blob and parsed.

### Plan text in the round's own file

| Count | Aff documents | Aff teams |
|---|---|---|
| All aff documents | 1,770 | 552 |
| **The store** (t02's reader): a plan-text heading over a stored card | 33 | |
| Its paragraph as the store holds it: a card's tag | 11 | |
| Its paragraph as the store holds it: not kept, with a paragraph the store drops between the heading and the card | 21 | |
| Its paragraph as the store holds it: not kept, with nothing between the heading and the card | 1 | |
| Its paragraph names an aff alias or a Medicare for All word | **0** | 0 |
| **The raw sources**: a plan-text label paragraph | **1,394** | **448** |
| The label's unit: block / hat / pocket | 1,158 / 202 / 11 | 379 / 65 / 4 |
| The label's unit: inline (label and text in one analytic, hat or block) | 19 | |
| The label's unit: other (analytic, other, evidence) | 4 | |
| The paragraph under the first label: an **analytic**, not kept by the store | 1,308 | 430 |
| The paragraph under the first label: a block, other, evidence or hat paragraph, not kept | 85 | |
| The paragraph under the first label: inside a stored card (a card's tag) | 1 | 1 |
| The paragraph under the first label: shaped like a plan text | 906 | 340 |
| It carries an **aff alias** | 691 | 255 |
| It carries a **Medicare for All word** | 36 | 13 |
| It carries **either** | **726** | **266** |

So the store keeps the paragraph under a plan heading in 1 aff document of 1,394. The analytic
under it is the plan text, and analytics are not stored.

**A wider net, for comparison only (not a proposed rule):** the first paragraph in the file that is
not evidence and is shaped like a plan text, at most 120 words. It is found in 1,535 aff documents
(481 teams), 1,512 of them not kept by the store. It names the aff in 1,168 (66.0%; 387 teams). It
needs no label, but it is a guess about which paragraph is the plan: a 2AC permutation or a
counterplan answer has the same shape.

**Distinct plan texts.** These are the plan-text-shaped paragraphs under a label, in 959 aff documents
of 352 teams, each digested over its normalized words. A one-word edit is a new digest, so this is an
upper bound on mechanisms, not a count of them.

| Plan texts used by | Distinct plan texts |
|---|---|
| 1 team | 119 |
| 2 teams | 29 |
| 3 to 5 teams | 34 |
| 6 to 10 teams | 7 |
| 11 or more teams | 4 |
| **All** | **193** |

| Teams by how many distinct plan texts their aff documents hold | Teams |
|---|---|
| 1 | 274 |
| 2 | 61 |
| 3 | 15 |
| 4 or more | 2 |

The words in the 192 plan texts (86 teams) that name neither single payer nor Medicare for All. A
document can count under more than one word:

| Word | Documents | Teams |
|---|---|---|
| `national health insurance` | 105 | 55 |
| None of the listed words | 84 | 28 |
| `public option` | 14 | 9 |
| `universal` | 14 | 8 |
| `medicaid` | 5 | 3 |
| `medicare` (not for all) | 4 | 3 |
| `voucher` | 3 | 1 |
| `expansion` | 2 | 2 |
| `affordable care` | 1 | 1 |

`national health insurance` is probably the resolution's own wording used as the plan. Then the
plan text says no more about the mechanism than the topic does (question 5).

Plan texts are short: of the 959, 540 are under 20 words and 402 are 20 to 39.

### The team's other rounds

There is one aff in the taxonomy, so two identified rounds of one team can never name different affs.
"Agree" cannot fail on the aff alone. The plan-text digests are the only disagreement to be seen:
78 of the 352 teams with a plan text hold two or more distinct ones (the table above).

| Carried from | Teams that would identify more rounds | More documents | More rounds | Of those documents, with their own plan text naming neither |
|---|---|---|---|---|
| The headings alone | 37 | 148 | 210 | 18 |
| Headings, plan text under a label (raw) and the caselist record | 75 | 220 | 287 | 35 |

So carrying into a round whose own plan text names something else would assign 35 documents an aff
their own file does not name. The guarded carry in the next table leaves those out.

### The caselist's own record

**Where round and cite-entry titles live: nowhere on this machine.**
* **The manifests** (`objects/manifests/<caselist>/<snapshot>.jsonl`): each row has path, school,
  team code, side, tournament, round and format, and no title.
* **The SQLite disclosure rows** (`caselist_disclosures` in `debate.sqlite3`): the same fields read
  from the path, and `round_label`. No title. `caselist_snapshots` and `caselist_sources` hold
  archive and file metadata.
* **The weekly archives** hold the open-source files only.
* **Round reports and cite entries** (with their titles) are OpenCaselist API resources (`rounds`,
  `cites`). The client does not fetch them: its `rounds` and `cites` modules are V3 work
  (`v3-e24-t02`, Pending). The data-use policy's OpenCaselist row lists what we take, and they are
  not on it (caselist and download listings, archive bytes, OpenEv listings).

**The one per-round record that is local is the disclosure's filename.** I matched the filename's words,
less the team's school and code, against the aliases and the Medicare for All words:
* 1 aff disclosure, of 1 document and 1 team, names the aff that way;
* 0 name Medicare for All.

### Signals alone and together

| Signal | Documents | Share | Rounds | Share | Teams | Share |
|---|---|---|---|---|---|---|
| All aff | 1,770 | | 2,547 | | 552 | |
| Headings (t02's matcher, today) | 159 | 9.0% | 227 | 8.9% | 77 | 13.9% |
| Plan text in the store | 0 | 0.0% | 0 | 0.0% | 0 | 0.0% |
| **Plan text under a label (raw sources)** | **726** | **41.0%** | **1,081** | **42.4%** | **266** | **48.2%** |
| Plan text by shape only (raw; comparison) | 1,168 | 66.0% | 1,691 | 66.4% | 387 | 70.1% |
| The caselist record (filename) | 1 | 0.1% | 1 | 0.0% | 1 | 0.2% |
| Headings + store plan text + record (what the store holds today) | 160 | 9.0% | 228 | 9.0% | 78 | 14.1% |
| **Headings + plan text under a label + record** | **789** | **44.6%** | **1,170** | **45.9%** | **290** | **52.5%** |
| Headings + plan text under a label or by shape + record | 1,189 | 67.2% | 1,718 | 67.5% | 397 | 71.9% |
| Team carry of the headings alone | 307 | 17.3% | 437 | 17.2% | 78 | 14.1% |
| Team carry of what the store holds today | 308 | 17.4% | 438 | 17.2% | 79 | 14.3% |
| Team carry of headings + plan text under a label + record | 1,009 | 57.0% | 1,457 | 57.2% | 290 | 52.5% |
| **The same, never into a round whose own plan text names neither** | **974** | **55.0%** | **1,413** | **55.5%** | **290** | **52.5%** |
| Team carry of everything above, shape included | 1,384 | 78.2% | 1,960 | 77.0% | 397 | 71.9% |

The headings-alone row reproduces v1-e32-t02's 159 documents and 77 teams. The store pass placed
every card with t02's matcher, so the two readings agree.

### Runtimes

| Pass | What it read | Wall-clock |
|---|---|---|
| Plan headings in the store (exploration) | t02's reader, aff documents' heading paths | 32.6 s |
| Tags and full paths in the store (exploration) | every aff document's cards | 38.7 s |
| Raw sample (exploration) | 40 aff documents re-parsed, one process | 40.5 s (parse 0.27 s a document) |
| The store pass | t02's reader and matcher over all 3,825 sources; the stored cards of 1,770 | 47.3 s |
| The raw pass, in four shards of 442 or 443 documents, 8 workers each | 1,770 aff DOCX blobs re-parsed in memory | 46.2, 46.1, 45.6 and 46.9 s (worker time 0.27 to 0.30 s a document; each shard about 25 s of it the reader) |
| The tables and the combine passes | the reader and the flags | 24.2 s and 23.9 s |
| The normalizer's effect | every on-topic source's headings, normalized twice | 53.1 s |

Two incidents, both handled before any count was kept:
* **The first raw run went past the limit.** It was one run of 1,770 documents, building a new
  parser for each. The alarm stopped the parent, which left 9 pool workers running; I found and
  stopped them (my worktree's interpreter, parent gone). After that, each worker kept one parser, the
  work went in shards, and the parent kills its own pool at 100 s.
* **A guard stopped two later runs:** `caselist pull` processes appeared from the v1-e32-t03
  worktree, a few seconds old each, which look like another session's CLI tests. I waited until none
  was running, and checked that the parsed store's index, the manifests and the SQLite database had
  not changed since 2026-10-22.

## The options for plan text the store does not keep

| Option | What it takes | Cost, measured or recorded | What it gives |
|---|---|---|---|
| **Keep what the store holds** | Nothing | None | 0 aff documents named by their plan text. Not worth building |
| **An E31 parser change**: keep the analytic paragraphs under a plan-text heading (or all analytics) in the stored document | A new E31 task. The record gains a field, so `schema_version` 3 and readers that branch on it; a `parser_version` bump; golden fixtures; the policy's account of what `parsed/` holds amended (analytics are the debater's own words, not evidence); a re-parse of every caselist and its publish to dev, then prod at the promotion | The last full re-parse (to `docx-5`) took 714 + 538 + 991 + 180 s, about 40 minutes for the four caselists, hspolicy26 991 s ([caselist-parse-report.md](../data/caselist-parse-report.md)). About 7.5 GB a version directory in the dev bucket, and a third version on this machine until retention | The plan text wherever the store is read, the cloud included, for E33 and E21 as well |
| **Read the raw sources again in this task** | The existing parser behind the application layer's parser port, read-only. No parser, store or fingerprint change. A local cache of what is derived per (source digest, parser version): the label's place, the matched alias or keyword ids and a plan-text digest, never the text | Measured tonight: 0.30 s a document. All 1,770 aff documents took about 185 s over 8 workers, in four shards, about 9 minutes in one process. A weekly run re-parses only new aff sources, a few hundred at most, in under a minute | The same signal as option 2, for the landscape only, and only where the blobs are (this machine; `raw/` in the bucket) |

**Recommendation: read the raw sources in this task.** It needs no parser, store or policy change and
no re-parse. It is measured. And it puts the per-round aff in the first Policy report, or the
second, on 2026-11-07's timeline. Option 2 is the better home in the long run if E33 or E21 come to
need analytics. It can be filed then, and the derived cache would be dropped then.

## The normalizer fix (PM brief 3)

* **The rule:** in t01's normalizer, a number between an advantage's word and its name goes from the
  front of the normalized heading. The number can be digits, a number word to ten or a roman numeral
  to x. So `Adv 1 Costs` → `adv costs` and `Advantage One: Costs` → `advantage costs`.
  * It runs on the joined heading, not a segment, because the colon in `Advantage One: Costs` puts
    the number and the name in different segments.
  * Roman numerals are in because `Advantage I: Costs` missed the same way. The rule is no wider than
    advantages (`DA 1 Midterms` is unchanged; Follow-up work).
* **Shown failing first:** 7 new rule cases, then 2 guards. `Advantage 340B Pricing` keeps its
  number, and so does a number after `advantage` further into the heading.
  * Against the normalizer before the rule: **7 failed, 168 passed**. The 2 guards passed, as guards
    must.
  * Then a check that both headings normalize to one of `costs-advantage`'s aliases in the committed
    Policy file. With the rule taken out: **9 failed, 168 passed**. With it restored byte for byte
    (checked with `cmp`, `__pycache__` cleared): **177 passed**.
* **t01's and t02's tests:** `.venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape
  packages/debate_core/tests/application/test_landscape_seeding.py
  packages/debate_core/tests/application/test_position_classification.py
  tests/scripts/test_seed_landscape_taxonomy.py tests/scripts/test_classify_landscape_positions.py
  tests/config` → **339 passed, 2 skipped**. The 2 skips are t02's overrides-file checks, which have
  no file to check yet.
* **t02's labeled set** is still placed 100%: `test_the_deterministic_stage_places_every_labeled_item_as_labeled`
  passes for POLICY, LD and PF, and so do the answer-heading test and the every-method test.
* **On the real store** (read-only, 53.1 s):
  * the rule changes the headings over 498 cards, in 39 documents of 29 teams;
  * 106 of those cards (13 documents, 13 teams) now sit under a heading that is an alias and was not.
    By position: inequality advantage 63, disease 25, stagnation 11, innovation 4, costs 3.
  * Their cache keys change with their headings, so t02's cache places those items again on the next
    run, and only those.

## Before the report (working agreement 10)

* `uv run --frozen scripts/affected_tests.py` → 42 of 427 test files from 4 changed files, in 5.3 s.
  I ran them with CI's markers: `.venv/bin/python -m pytest -n auto -m "not slow and not live" -p
  no:randomly <files>` under `perl -e 'alarm 115'` → **1,870 passed, 2 skipped in 34.36 s**. The
  2 skips are the overrides-file checks above.
* `uv run --frozen ruff format --check .` → 1179 files already formatted.
* `uv run --frozen ruff check .` → all checks passed.
* `uv run --frozen pyright packages/debate_core` → 0 errors, 0 warnings.
* `uv run --frozen lint-imports` → 16 kept, 0 broken.
* `.venv/bin/python scripts/check_thin_handlers.py` → 47 handlers within 25 statements.
* `uv run scripts/validate_specs.py` → OK, 431 files.
* `scripts/check_command_blocks.py`, `scripts/check_links.py` and `scripts/docs_index.py
  --check-descriptions` → OK, run after this report was written.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.

## Files changed

* **`packages/debate_core/src/debate_core/arguments/landscape/headings.py`**: the advantage-number
  rule and its docstring line.
* **`packages/debate_core/tests/arguments/landscape/test_headings.py`**: 7 rule cases, 2 guards, and
  the check against the committed costs-advantage aliases.
* **This report.** The spec's phase was set to InProgress before the session and is unchanged.

The count scripts are not committed. They were read-only scratch files that print counts. A
committed counting script belongs with the extraction the ruling decides.

## Deviations from the spec

1. **The counts read the raw sources, not only the store.** The spec says to count "for how many the
   paragraph under it is in the parsed store, and in what unit". The store keeps no analytics and
   drops a heading that has no card under it. So the store alone shows 33 plan headings, and cannot
   say what unit the rest are. I re-parsed the aff documents in memory with the store's own parser
   version, which is reading, not a change. Nothing from that run was kept beyond per-source flags and
   digests in the scratchpad. That is what option 3 would do, run once as a measurement, and its
   figures are also option 3's cost. Every store count is given beside it.
2. **Affirmative side only.** ac1 says "per side". A plan heading in a negative file is a counterplan
   text or the aff's plan quoted in a block, and identifies no aff. So the PM's brief counts aff
   documents only, and so did I. Question 8 asks whether to amend ac1.
3. **The caselist record is a filename, not titles.** The titles the spec names exist only behind the
   API and outside the policy ([above](#the-caselists-own-record)). The one local record per round,
   the filename, was counted in their place.

## Decisions and assumptions

1. **The plan-text labels** are the normalized forms listed under [the counts](#the-counts-hspolicy26-through-2026-10-20),
   chosen from an exploration pass. In that pass the store's aff headings holding `plan` or `pt`
   normalized to `plan` (28 documents), `the plan` (2), `plan text` (2) and `plan and solvency` (1).
   Only forms made of debate vocabulary were printed.
2. **Medicare for All words** are `medicare for all` and `m4a`, t01's affirmative check's words. They
   lift the plan-text signal from 691 documents (alias alone) to 726.
3. **A round is a live on-topic aff disclosure**, and its document's signals are its own. So a document
   read in three rounds counts three rounds.
4. **The carry is per team identity**, the opaque school-and-code identity t01's reader builds. With
   one aff in the taxonomy, a team's identified rounds always agree, so the measured guard is the
   target round's own plan text.
5. **No count printed a heading outside debate vocabulary, a tag or a plan text.** Distinct plan texts
   were counted by SHA-256 over normalized words, and the digests stayed in the scratchpad.

## Operator follow-ups

None. Every read ran in the session under the two-minute limit. No whole-selection run is handed
over: the pull request's `ci` check runs it.

## Follow-up work

* **Numbered DAs, CPs and contentions** (E32, for the PM to place). `DA 1 Midterms` → `da 1
  midterms` and `Contention One: Costs` → `contention one costs` miss their aliases the same way the
  advantages did. Not changed here: the ruling named the two advantage forms.
* **Round reports and cite titles** (E34 or V3's `v3-e24-t02`, and a data-use policy question for the
  PM and Charlie). They are the caselist's own statement of each round's aff, and the one signal not
  available tonight.
* **What a team's other rounds can say beyond one aff.** Once the coach names single payer's
  mechanisms as child affs, "agree" can fail for real, and the carry rule should be tested again on
  the children.

## Questions for the PM

```text
v1-e32-t09 questions (session, 2026-10-23). Counts: hspolicy26 through 2026-10-20,
1,770 aff documents, 2,547 aff rounds, 552 aff teams.

1. How do we get plan text the store does not keep? The store keeps cards only.
   Of the 1,394 aff documents with a plan label (1,158 of them a block), the
   paragraph under it is an analytic in 1,308, and the store kept it in 1.
   (a) Keep what the store holds: 0 documents named by plan text.
   (b) E31 parser change (analytics under a plan heading stored), schema_version
       3, parser_version bump, policy wording, re-parse ~40 min + publishes.
   (c) Read the raw sources in this task: the existing parser, read-only, behind
       the application port, with a local cache of derived fields only (label
       place, matched ids, plan-text digest; never text). Measured: 0.30 s a
       document, ~185 s for all 1,770 over 8 workers; weekly runs parse only new
       aff sources.
   Recommendation: (c). No parser, store, fingerprint or policy change, already
   measured, and it can be in the report before 2026-11-07. (b) later if E33 or
   E21 need analytics.

2. Which plan-text rule identifies a round?
   (a) The paragraph directly under a plan-text label (plan, plan text, pt, ...,
       or "Plan:" inline) names an aff alias or a coach word: 726 documents
       (41.0%), 266 teams (48.2%).
   (b) (a), plus the first non-evidence "should + federal actor" paragraph
       anywhere: 1,168 documents (66.0%), 387 teams (70.1%).
   Recommendation: (a), method PLAN_TEXT. (b)'s extra rounds are a guess about
   which paragraph is the plan (a 2AC perm or a CP answer has the same shape),
   and "never a guess" rules them out; they stay unidentified.

3. The team's other rounds. With one aff in the taxonomy a team's identified
   rounds always agree, so the only check is the target round's own plan text:
   35 of the 220 documents a carry would add have a plan text naming neither
   single payer nor Medicare for All. Carry how?
   (a) Carry to every unidentified aff round of a team with an identified one,
       unless that round's own plan text names something else: headings + plan
       text + record + carry = 974 documents (55.0%), 1,413 rounds (55.5%),
       290 teams (52.5%); method TEAM_CARRY, counted apart in the report.
   (b) No carry: 789 documents (44.6%), 290 teams (52.5%).
   Recommendation: (a). It adds 185 documents with no team added, and a
   carried round says so. If the coach finds carried rounds wrong, it is one
   rule to remove.

4. The caselist's own record. Titles live nowhere on this machine: manifests,
   SQLite disclosure rows and archives hold paths and files; round reports and
   cite entries are API resources (rounds, cites) the client does not fetch
   (v3-e24-t02, Pending) and the data-use policy does not list. The one local
   per-round record, the filename, names the aff in 1 aff disclosure.
   (a) Drop the signal this season; the report says so.
   (b) Amend the data-use policy and file a task to fetch round and cite titles.
   Recommendation: (a) now. (b) is yours and Charlie's to weigh (it changes
   what we take from the site); it would be the strongest signal if taken.

5. 192 plan texts (86 teams) name neither single payer nor Medicare for All;
   105 of them (55 teams) say "national health insurance", probably the
   resolution's own wording as the plan. What does such a round count as?
   (a) Unidentified, shown in the report's unidentified share; the coach's
       mechanism sheet (ac2) clusters these texts too, so he can name them.
   (b) A new position now (a resolutional plan).
   Recommendation: (a). A new position is the coach's call, through the sheet.

6. No coach-approved Medicare for All words exist yet. For the rule, may
   "medicare for all" and "m4a" identify single payer (the coach's one aff,
   2026-10-23) until he gives the child aff's tag keywords?
   Recommendation: yes. They add 35 documents; when he names a Medicare for
   All child, the same words move to its tag keywords.

7. Distinct plan texts: 193 digests over 959 documents, 119 used by one team.
   A digest is over the exact words, so one edit makes a new one. For the
   coach's sheet, cluster by the mechanism words that differ (ac2, as the spec
   says), not by digest?
   Recommendation: yes; the digest count is an upper bound, not a mechanism count.

8. ac1 says "per side". A plan heading in a negative file is a CP text or a
   quoted plan and identifies no aff, so only aff documents were counted.
   Amend ac1 to the affirmative side?
   Recommendation: yes.

9. The normalizer fix is done as ruled (adv 1 costs, advantage one costs, and
   roman numerals). "DA 1 Midterms" and "Contention One: Costs" miss their
   aliases the same way. Widen the rule in this task, or file it?
   Recommendation: widen it here after the ruling, with failing cases first.
   It is the same rule on the same normalizer, and contentions are what some
   teams call advantages.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
