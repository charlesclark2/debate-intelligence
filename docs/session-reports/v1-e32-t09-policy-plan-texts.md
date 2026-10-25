# Session report: v1-e32-t09-policy-plan-texts

| | |
|---|---|
| Task | `v1-e32-t09-policy-plan-texts` — Each Policy affirmative round's plan, counted first, so the landscape names what affs read |
| Spec | [`plan_specs/v1/e32-argument-landscape/t09-policy-plan-texts.yaml`](../../plan_specs/v1/e32-argument-landscape/t09-policy-plan-texts.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t09-policy-plan-texts` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**ac4 and ac2 are built, tested and run on the real store. ac3 waits on the coach.** So the Goal stays
**InProgress**, and the pull request goes `--partial` as the PM ruled on 2026-10-24, so `v1-e32-t05`
can use the assignments for the first report. ac3 lands in a follow-up session.

* **Each affirmative round's aff** (ac4). `AffAssignmentService.aff_assignments(caselist, through)`
  returns `v1-e32-t03`'s `AffAssignment` values, which is the producer t05 asked for. It:
  * reads each affirmative file's plan text from its own bytes, through the parser port, keeping only
    derived fields in a local cache;
  * assigns `PLAN_TEXT` when the paragraph under a plan label names an aff;
  * assigns `TEAM_CARRY` when a team's identified rounds agree, never into a round whose own plan
    text names something else;
  * leaves a round with a placed card to the report's `PLACED_CARD`, and every other round
    unidentified.
* **On hspolicy26 through 2026-10-20:** 1,255 of 2,192 affirmative rounds (57.3%) and 298 of 552 teams
  (54.0%) are identified. Headings alone identify 9.0% of documents.
  * `PLAN_TEXT` 959, `TEAM_CARRY` 226, and `PLACED_CARD` 70 (left to the report);
  * 937 rounds are unidentified, and the guard refused 40 carries
    ([below](#the-real-store-after-the-ruling)).
* **The coach's sheet** (ac2) is written, outside the repository, at
  `~/Documents/debate/landscape-seed/policy-2026-27-nhi-plan-texts.md` with its answers CSV. It was
  rebuilt for the PM's review ruling 1, the condition closed in this session:
  * 959 affirmative documents with a plan text, by 352 teams;
  * all 131 clusters shown, one-team clusters included, by the mechanism words that differ;
  * each cluster's commonest plan text word for word, with how many of its documents hold it exactly;
  * no text that names a school of the caselist (none did).
  * A scan against all 192 schools and 555 team codes of the caselist found none. Its hits were the
    ordinary words `all` and `tag` (below).
* **The normalizer rule** is widened to numbered DAs, CPs and contentions, as ruled. It changes nothing
  in today's hspolicy26 beyond the advantage fix of the 23rd.
* **The spec's ac1** is amended to the affirmative side, with the rulings recorded as a PM-ruling
  comment.

**After the PM review (2026-10-24, accepted with one condition):**
* the condition is closed: the sheet shows plan texts verbatim, every cluster listed, with failing
  tests first, one operator rebuild and a new scan ([below](#the-coachs-sheet));
* `constraints.packages` is amended (ruling 3);
* the rest of this report is brought up to date.

The pull request goes `--partial`; ac3 follows in a resumed session on the coach's answers.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| plan-texts | In progress: ac1, ac2 and ac4 done; ac3 waits on the coach | Counts (2026-10-23), the PM's rulings (2026-10-24), then the normalizer widening, the plan-text reader, the round assignment, the cache, the service, the sheet, the producer and the operator script |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts, on the affirmative side and by teams, of plan-text headings, of the paragraph under them as held in the store (by unit), and of distinct plan texts, sent to the PM with one to three options, before any change | PASS | [The counts](#the-counts-hspolicy26-through-2026-10-20) and [the options](#the-options-for-plan-text-the-store-does-not-keep), sent 2026-10-23 and ruled on 2026-10-24. The spec's ac1 now says the affirmative side (ruling 8). No parser, store or fingerprint was changed |
| ac2: after the ruling, a deterministic extraction of each team's plan text and a review sheet outside the repository grouping them into clusters with team counts, by tests on synthetic sources shown failing first | PASS | Extraction: `plan_text.py` (red 29 failed / 12 passed; then the sheet helpers, 3 failed), `PlanTextService` (10 failed; its words pass, 2 failed). Sheet: `plan_text_sheet.py` (6 failed / 3 passed against hand-written text), `scripts/assign_landscape_affs.py sheet` (5 targeted mutants, each caught). Verbatim texts (review ruling 1): the sheet's tests 6 failed / 6 passed, the read-back 2 failed, the script's 2 failed, then 5 targeted mutants each caught. The real sheet: [below](#the-coachs-sheet) |
| ac3: the coach's mechanisms as child affs of single payer in policy-2026-27-nhi.yaml, with his tag keywords, the taxonomy_version bumped, the config tests passing, and the counts of his decisions in the report | NOT RUN | Waits on the coach's answers to the sheet. A follow-up session applies them (the PM's ruling on order, 2026-10-24) |
| ac4: counts, before any rule, of the affirmative rounds and teams each signal identifies, alone and together, sent to the PM; after the ruling, each identified round carries its aff and the signal that named it, and an unidentified round stays unidentified, by tests on synthetic sources shown failing first | PASS | Counts: [signals alone and together](#signals-alone-and-together) (2026-10-23). After the ruling: `aff_assignment.py` (red 17 failed / 3 passed), `build_aff_assignments` through t03's `LandscapeReportService` (5 failed), the producer (2 of 3 failed), `assign` (failed before the command existed). Real store: [below](#the-real-store-after-the-ruling) |
| plan-texts node: `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS | `.venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape` under `perl -e 'alarm 60'` → 376 passed in 6.70 s. The node itself stays open with ac3 |
| PM brief (3), 2026-10-23: the two normalizer variants fixed with synthetic cases shown failing first; t01's seeding and t02's matcher tests pass; t02's labeled set still placed 100% | PASS | [The normalizer fix](#the-normalizer-fix-pm-brief-3) |
| PM ruling 9, 2026-10-24: the rule widened to numbered DAs, CPs and contentions, failing cases first, guards like the 340B one, a check against the committed aliases, the real-store effect reported | PASS, with contentions reaching no alias | [Widened](#widened-to-numbered-das-cps-and-contentions-pm-ruling-9); Deviations 3 |

The pytest commands were run as `.venv/bin/python -m pytest <files>` with a `perl -e 'alarm N'`
limit on the interpreter (working agreement 10). The branch's commits are relative to `dev` at
`4ba7e4a`, after `scripts/task sync` on 2026-10-24.

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


### Widened to numbered DAs, CPs and contentions (PM ruling 9)

* **The rule** is the advantage rule's, widened to `contention`, `da`, `disad`, `cp` and `counterplan`.
  A number between the word and a name goes from the front of the heading, so `DA 1 Midterms` becomes
  `da midterms`, and `CP 2 States` becomes `cp states`.
* **Numbers are one digit now**, for every kind, advantages included, so `CP 50 State Fiat` keeps the
  number that names it.
* **Shown failing first:**
  * 5 rule cases and 2 checks against the committed aliases (`midterms-da` and `states-cp`) failed, 7
    in all, with 188 passed;
  * the 3 new guards passed before the rule, as guards must: `CP 50 State Fiat`, `CP 1332 Waiver`, and
    `Spending DA 2 Link`, a number further into a heading;
  * a first CP check written as `CP 2: States` passed before the rule, because the colon already split
    it, so it was rewritten as `CP 2 States`, which fails.
  * Green: 195 passed. With the digits widened back to two, the `CP 50 State Fiat` guard fails, so it
    bites.
* **t01's and t02's tests** still pass: 357 passed, 2 skipped, the labeled set placed 100% in all
  three formats.
* **On the real store** (read-only, 58.8 s), measured against the advantage-only rule of the 23rd: it
  changes **0** cards' headings.
  * hspolicy26 has numbered DA headings in 5 documents of 3 teams, all mid-heading, where the rule does
    not reach. It has no numbered CP or contention heading.
  * So the widening is a guard for later files.
* **Contentions reach no alias:** `Contention One: Costs` becomes `contention costs`, and no committed
  position has a `contention` alias (Deviations 3, question 2).

## What was built after the ruling

| Where | What |
|---|---|
| `arguments/landscape/plan_text.py` | Finds each plan text: the paragraph directly under a t01-normalized plan label, or an inline `Plan:` label, in any unit. Reads which aff it names (aliases and tag keywords of aff positions; `medicare for all` and `m4a` name single payer until a position's keywords claim them; a child beats its parent; two unrelated affs conflict). A document's verdict: `NAMES`, `CONFLICTING`, `UNNAMED` (a shaped plan text naming none), `NONE` or `UNREAD`. Keeps derived fields only |
| `arguments/landscape/aff_assignment.py` | The pure round rule over opaque round keys: `PLAN_TEXT`, then `TEAM_CARRY` with the guard, with counts |
| `application/ports/plan_text_store.py`, `integrations/landscape/plan_text_store.py` | The cache, `<data_dir>/landscape/plan_texts/<caselist>.jsonl`, keyed by source digest, parser version and vocabulary digest. No text |
| `application/plan_texts.py` | `PlanTextService`: reads only what the cache lacks, through a `ParseRunner` and the parser port, with `caselist parse`'s blob checks and a placeholder path in place of the disclosure's; `words` reads the sheet's plan texts again in memory, each checked against its cached digest |
| `arguments/landscape/plan_text_sheet.py` | Clusters plan texts by the mechanism words that differ, withholds clusters fewer than two teams read, takes every caselist school out of the words, and renders the sheet and the answers CSV |
| `application/aff_assignment.py` | `build_aff_assignments` (t03's `round_id` and `PLACED_CARD` rule), and `AffAssignmentService` with the `AffAssignmentSource` protocol for t05 |
| `arguments/landscape/render.py` | Labels for `PLAN_TEXT` and `TEAM_CARRY` in the method table, and the note that the caselist's round and cite titles are not read (ruling 4) |
| `scripts/assign_landscape_affs.py` | `plan-texts`, `assign` and `sheet`, printing counts only |
| `docs/guides/landscape-taxonomy.md` | How a round's aff is identified, and how the coach answers the plan-text sheet |

## The real store after the ruling

hspolicy26, parser `2026.10.20-docx-6`, through 2026-10-20. Before each run that I ran, the guards
were checked: no `DEBATE_*` variable set and no `caselist pull` running. Each ran under a 115 s limit
on the interpreter. The first full pass and the sheet were the operator's (below). Counts only.

**Plan texts** (`plan-texts`):

| Verdict | Aff documents | Aff teams |
|---|---|---|
| All affirmative sources | 1,770 | 552 |
| `NAMES` single payer | **767** | **278** |
| `UNNAMED`: a plan text naming no aff | 192 | 86 |
| `NONE`: no plan text | 811 | 284 |
| `CONFLICTING` | 0 | 0 |
| `UNREAD` (refused by the parser, or no readable bytes) | 0 | 0 |

`NAMES` is 767 against the counts' 726, because the rule reads every label's paragraph and the counts
read only the first. `UNNAMED` is the counts' 192 exactly.

**Rounds** (`assign`), by t03's round, so a file read in two rounds counts twice and two files of one
round count once:

| | Aff rounds | Share |
|---|---|---|
| All | 2,192, by 552 teams | |
| `PLAN_TEXT` | 959 | 43.8% |
| `TEAM_CARRY` | 226 | 10.3% |
| Left to the report's `PLACED_CARD` (an aff placed, no plan text naming one) | 70 | 3.2% |
| **Identified** | **1,255** | **57.3%** |
| Unidentified | 937 | 42.7% |
| Of those, the carry refused by the guard (their own plan text names no aff, or a file unread) | 40 | |
| Of those, with conflicting plan texts | 0 | |
| Teams with an identified round | **298 of 552** | **54.0%** |
| Teams whose rounds name two affs | 0 | |

The counts of the 23rd, by document, predicted 55.0% for the same signals with the guard. By t03's
round it is 57.3%.

**Runtimes:**

| Run | By | Wall-clock |
|---|---|---|
| `plan-texts`, first full pass (1,770 sources parsed, 8 workers) | operator | 203.9 s |
| `plan-texts`, cache warm (1,770 hits) | session | 25.5 s |
| `assign` (plan texts cached; t02's classification cached) | session | 36.3 s, and 38.3 s through the service |
| `sheet` (959 sources read again for their words) | operator | 134.3 s |
| `sheet` rebuilt with verbatim texts (review ruling 1) | operator | 130.1 s |

The cache file is 689 KB for 1,770 readings. A grep for `united states`, `federal government`,
`should`, `medicare`, `payer`, `establish` and `school` found none of them in it.

## The coach's sheet

`~/Documents/debate/landscape-seed/policy-2026-27-nhi-plan-texts.md` and `plan-text-answers.csv`,
outside the repository. They were first written on 2026-10-24 by the operator's run (134.3 s), then
rebuilt for the PM's review ruling 1 by one operator block with agreement 11's guards (130.1 s). The
script refuses to replace an answers CSV the coach has begun, and he had not.

| Count | First sheet | Rebuilt sheet |
|---|---|---|
| Affirmative documents with a plan text (`NAMES` or `UNNAMED`) | 959, by 352 teams | 959, by 352 teams |
| Clusters shown | 50 (two or more teams) | **131** (every cluster) |
| Clusters withheld, and their documents | 81, 141 | 0, 0 |
| Clusters with their commonest plan text word for word | none | 131 |
| Plan texts naming a school of the caselist, not shown | not counted | 0 |
| Paragraphs that read differently from their cached reading, and sources unread | 0, 0 | 0, 0 |

The rebuilt sheet is 931 lines, and its answers CSV has 131 rows.

**The scan of the rebuilt files** checked every school of the caselist (192) and every team code (555),
by whole words without case, and each school's first word of four or more letters.
* No school's name and no school's first word is in either file.
* Every team-code hit is the word `all` (as in `medicare for all`), which is also one team's code:
  * in the sheet, 22 table rows, 21 plan texts and the header paragraph, 44 lines;
  * in the CSV, 21 rows.
* The one school hit is `tag`, the whole of one school's normalized name, in the sheet's fixed
  instruction line about "tag keywords" and the CSV's `tag_keywords` header.
* The first sheet's scan found the same two words: `all` on four cluster rows and the header, and
  `tag`.

The scan printed only row labels and the matched word, and no name went into this report.

## Checks shown failing for their reason

* **Red runs**, each against a skeleton that refused nothing, or before the code existed:

  | Suite | Red |
  |---|---|
  | `test_plan_text.py` | 29 failed / 12 passed |
  | `test_aff_assignment.py` (pure) | 17 failed / 3 passed |
  | `test_plan_text_store.py` | 3 failed / 4 passed |
  | `test_plan_texts.py` | 10 failed |
  | `test_plan_text_sheet.py` | 6 failed / 3 passed |
  | `test_aff_assignment.py` (application, seam) | 5 failed |
  | `test_aff_assignment.py` (producer) | 2 failed / 1 passed |
  | `test_render.py` | 2 failed / 13 passed |
  | `test_assign_landscape_affs.py`, `assign` | failed before the command existed |

  A refuse-nothing skeleton passes the cases that assert nothing is found by construction.
* **Written with the code, then shown failing against a stub and restored byte for byte:** the sheet
  helpers (3 failed) and the words pass (2 failed). The words pass's "writes nothing" guard passes a
  stub by construction.
* **18 mutants of `plan_text.py` and `aff_assignment.py`.** Each ran in a fresh process, with bytecode
  writing off and `__pycache__` cleared, and each file was restored byte for byte. No Hypothesis is
  used.
  * First run: 14 caught.
  * Two first runs proved nothing. One mutant failed at collection (a syntax error, not a catch,
    agreement 8) and one did not apply (ruff had reflowed the line). Both were re-aimed and caught: no
    narrowing within a round (1 failed), carried into a round with an unnamed plan text (2 failed).
  * **One survived:** carrying another team's aff into a round no readable team disclosed. My only
    no-team test had no team carrying. `test_a_round_no_readable_team_disclosed_is_not_carried_into_from_another_team`
    was added, and it then caught it (1 failed).
  * One is equivalent: `elif` made `if` where the team is already in the disagreeing set. It is
    control flow, not a check, so there is nothing to remove.
  * Caught, with failures: a conflicting document ignored 2; two affs, first wins 2; unread counted as no
    plan text 1; placed cards not identifying a team 2; a conflicting round no disagreement 2; a placed
    round carried into 4; an inline label not needing a plan's shape 1; a label over a label 1; a
    retired alias with nowhere to go still naming 1; interim words overriding a child 1; words
    matching inside words 1; advantages naming affs 3; unshaped unnamed as `UNNAMED` 1; the digest of
    raw text 3.
* **The verbatim sheet** (review ruling 1). Its tests were red against new fields with no logic:
  * the sheet 6 failed / 6 passed, the 6 passing being behaviour kept (two-team withholding when asked,
    the similarity, the scrub, the frame, the empty sheet);
  * the read-back 2 failed, after a first attempt that failed at import and was redone;
  * the script 2 failed.

  Then 5 targeted mutants, each restored byte for byte, each caught:

  | Mutant | Failed |
  |---|---|
  | A text naming a school shown | 4 |
  | Spacing not collapsed | 5 |
  | One-team clusters withheld by default | 5 |
  | No escaping in the quoted text | 1 |
  | The answers guard removed | 1 |
* **5 mutants of the script, each caught:** no verdict counts printed (1 failed), negative files read
  (2), no school scrub on the sheet (1), the sheet written inside the repository (1), an empty store
  exiting 0 (2).
  * The "inside the repository" mutant wrote its synthetic sheet into the worktree. I inspected the
    stray directory (planted words only) and removed it before anything was committed.

## Before the report (working agreement 10)

* `uv run --frozen scripts/affected_tests.py` listed 63 of 436 test files, from 25 changed files.
  `.venv/bin/python -m pytest -n auto -m "not slow and not live" -p no:randomly <files>` under a
  115 s limit → **2,499 passed, 2 skipped in 64.56 s**. The 2 skips are the overrides-file checks,
  with no overrides file to check. After the review's condition, again: 63 files →
  **2,507 passed, 2 skipped in 73.58 s**.
* `uv run --frozen ruff format --check .` → 1205 files already formatted; `ruff check .` → all checks
  passed.
* `uv run --frozen pyright packages/debate_core` → 0 errors.
* `uv run --frozen lint-imports` → 16 kept, 0 broken.
* `scripts/check_thin_handlers.py` → 47 handlers within 25 statements.
* `scripts/check_command_blocks.py --base origin/dev` → OK; `scripts/check_links.py` → OK;
  `scripts/docs_index.py --check-descriptions` → OK.
* `uv run scripts/validate_specs.py` → OK, 434 files.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.

## Files changed

* **`debate_core.arguments.landscape`:**
  * `headings.py`: the number rule;
  * `plan_text.py`, `aff_assignment.py`, `plan_text_sheet.py` (new);
  * `source_headings.py`: `CaselistNames.without_schools`, the scrub without re-normalizing;
  * `render.py`: the two labels and the note.
* **`debate_core.application`:**
  * `plan_texts.py`, `aff_assignment.py` and `ports/plan_text_store.py` (new).
* **`debate_core.integrations.landscape`:** `plan_text_store.py` (new).
* **`debate_core.testing.landscape_store`:** `PlantedCaselist.source` takes real bytes and writes their
  blob (Deviations 4).
* **`scripts/assign_landscape_affs.py`** (new).
* **Tests:**
  * under `packages/debate_core/tests`: `arguments/landscape/test_headings.py`, `test_plan_text.py`,
    `test_aff_assignment.py`, `test_plan_text_sheet.py` and `test_render.py`;
    `application/test_plan_texts.py` and `test_aff_assignment.py`;
    `integrations/landscape/test_plan_text_store.py`;
  * `tests/scripts/test_assign_landscape_affs.py`.
* **`tests/fixtures/landscape/golden/report.md`:** one line, by hand (Deviations 4).
* **`docs/guides/landscape-taxonomy.md`:** two sections, the sheet's paragraph updated for verbatim
  texts.
* **The spec:** ac1 on the affirmative side and the rulings as a PM-ruling comment. The PM's own
  note of 2026-10-24 arrived with the sync.

## Deviations from the spec

1. **The counts read the raw sources, not only the store** (2026-10-23). The PM's ruling of 2026-10-24
   called it the right call, and ruling 1 made it the method.
2. **Affirmative side only.** ac1 is amended (ruling 8).
3. **Contentions reach no alias.** Ruling 9 asks for a check against the committed aliases. For DAs
   and CPs it is there, shown failing first. Contentions lose their number, but the taxonomy has no
   `contention` alias for them to reach, and hspolicy26 has no numbered contention heading. Question 2
   asks what to do.
4. **Two files outside `constraints.packages`:**
   * `debate_core.testing.landscape_store`: a planted source needs real bytes and a blob for the plan
     text to be read from;
   * `tests/fixtures/landscape/golden/report.md`: ruling 4's note is one line of t03's report, and its
     golden is hand-written, so the line was added by hand.

   Question 3 asks to amend the spec's list.
5. **The sheet predated the PM's note on policy 1.13.** As first written, it showed each cluster's
   mechanism words and withheld a cluster one team reads, as t01's and t02's sheets did. Policy 1.13
   allows plan texts verbatim, a single team's included, never beside a school or team code. Review
   ruling 1 chose that, and the rebuilt sheet shows each cluster's commonest text and every cluster.

## Decisions and assumptions

1. **Every label's paragraph is read**, not only the first, so a 1AC and a later `Plan` block both
   count. This is why `NAMES` is 767, against the counts' 726.
2. **A placed round is left to the report.** A round with a card t02 placed under an aff, and no plan
   text naming one, gets no assignment: t03 counts it as `PLACED_CARD`. It still identifies its team
   for the carry, and is never carried into.
3. **Agreement uses the narrowest aff.** A team whose rounds name single payer and, later, a child aff
   carries the child. Two affs neither of which is the other's ancestor are a disagreement, and so is
   a round with conflicting plan texts.
4. **A file with no reading blocks a carry.** An unread file could hold any plan text. hspolicy26 has
   none.
5. **Two kinds of failure are handled apart.** A parser refusal is cached as unreadable, since it is
   deterministic for one parser version. A missing or corrupt blob, or a worker failure, is not cached,
   so the next run tries it again.
6. **The parser gets a placeholder path**, `plan-text-reading.docx`, so no disclosure path reaches it.
7. **The sheet's frame is the words in at least 80% of plan texts.** At half, two mechanisms each read
   by half the teams became frame and left their clusters wordless, and single payer (about 72% of
   hspolicy26's plan texts) would have vanished from the sheet. Clusters merge into a larger one they
   share three quarters of their words with. A short list of English joining words is dropped first.
8. **The producer reclassifies.** `AffAssignmentService.run` classifies through t02's service, from its
   cache. Like t02's classifier, that may rewrite t02's own cache and review queue under the data
   directory. If t05 classifies too, the second pass is all cache hits.
9. **`assign` reads the newest parsed version** unless `--version` names one, as `classify` does.

## Operator follow-ups

1. **Done, 2026-10-24:** the first full `plan-texts` pass, 203.9 s, output as expected (above).
2. **Done, 2026-10-24:** the coach's sheet, 134.3 s, scanned by the session (above).
3. **The coach** fills `mechanism_name` and `tag_keywords` in
   `~/Documents/debate/landscape-seed/plan-text-answers.csv` (the guide's "The plan-text sheet and
   your mechanisms") of the rebuilt sheet. The resumed session applies them (ac3).
4. **Done, 2026-10-24:** the sheet rebuilt for review ruling 1, 130.1 s, scanned by the session
   (above).
5. **The pull request** (the PM accepted on 2026-10-24), from the task worktree. First:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t09-policy-plan-texts
```

```bash
scripts/task pr v1-e32-t09-policy-plan-texts --partial
```

No whole-selection run is handed over: the pull request's `ci` check runs it.

## Follow-up work

* **Wiring the producer into the CLI's composition root** (`v1-e32-t05`, or this task's follow-up
  session if t05 merges first, by the PM's note of 2026-10-24). `AffAssignmentService` and
  `AffAssignmentSource` are in `debate_core.application.aff_assignment`. Note t05's first dev run: the
  plan-text cache is per machine, so a machine without it parses every affirmative file once (about
  3.5 minutes over 8 workers for hspolicy26).
* **ac3, the coach's mechanisms** (this task's follow-up session): child affs of single payer with
  his tag keywords, a minor `taxonomy_version` bump, `tests/config`, and the counts of his decisions.
  The vocabulary digest changes with them, so the next run reads every affirmative file again.
* **The producer could take classifications** (t05), to skip its second classification pass when the
  run has already classified.
* **Quoting plan texts in the report** under policy 1.13 (t03 or t05). The cache holds no text, so a
  report quoting them reads them again, as the sheet does.

## Questions for the PM

None open. The four below were answered in the PM review of 2026-10-24: (1) (b), done in this
session; (2) (a); (3) yes, amended; (4) yes. Kept as asked:

```text
v1-e32-t09 questions (session, 2026-10-24). ac2 and ac4 pass; ac3 waits on the coach.

1. The coach's sheet shows each cluster's mechanism words and withholds the
   81 clusters (141 documents) one team reads, as t01's and t02's sheets did.
   It was built before your note on policy 1.13, which allows plan texts
   verbatim, a single team's included, never beside a school or team code.
   (a) Keep it as written.
   (b) Add each shown cluster's commonest plan text, verbatim, and list the
       one-team clusters too, with their words. One more operator run (~2.5 min).
   Recommendation: (b). The coach names mechanisms faster from the text itself,
   and the policy now allows it. The sheet stays outside the repository, and
   the scan for schools and codes runs again before he reads it.

2. Contentions lose their number (ruling 9), but no committed position has a
   `contention` alias, so `Contention One: Costs` reaches nothing. hspolicy26
   has no numbered contention heading today.
   (a) Leave it; revisit when contention headings appear.
   (b) Have the normalizer read a leading `contention` as `adv`.
   Recommendation: (a). It is a synonym rule with nothing to measure it on;
   the coach can add `contention ...` aliases if teams write them.

3. Two files outside constraints.packages: debate_core.testing (a planted
   source carries real bytes and a blob) and tests/fixtures/landscape (the
   golden report gains ruling 4's line, by hand). Amend the spec's list?
   Recommendation: yes, as for t01 and t02.

4. The PR goes --partial now (ac3 open), as you ruled. ac3 then lands in a
   follow-up session on the coach's answers. Confirm that the follow-up also
   wires the producer into the composition root if t05 has not merged by then?
   Recommendation: yes, as your note says: whichever merges second wires it.
```

### The questions of 2026-10-23, answered

The PM ruled on 2026-10-24:
* (1) (c), read the raw sources in this task;
* (2) (a), `PLAN_TEXT`;
* (3) (a), `TEAM_CARRY` with the guard;
* (4) (a), no titles this season;
* (5) (a), unidentified and on the sheet;
* (6) yes;
* (7) yes;
* (8) yes;
* (9) widen it here.

They are kept as asked:

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

**Verdict:** ACCEPTED, with one condition closed in-session
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-24

**Notes:**

The task that makes the Policy landscape say what affs read.
* **57.3% of affirmative rounds and 54.0% of teams are now identified,** against 9.0% from
  headings.
* Every method is named: `PLAN_TEXT` 959, `TEAM_CARRY` 226, `PLACED_CARD` 70. The guard refused 40
  carries.
* The cache holds no text, and a grep shows it.
* The red runs are recorded. One surviving mutant (a carry into a round no readable team disclosed)
  got its test.
* The incidents were handled before any count was kept.

**Rulings**

1. **(b).** Add each shown cluster's commonest plan text, verbatim, and list the one-team clusters
   too, with their words and text. Policy 1.13 allows it, never beside a school or team code. The
   sheet stays outside the repository. This is the one condition below.
2. **(a).** Leave contentions until teams write them; the coach can add `contention ...` aliases.
3. **Yes.** Amend `constraints.packages` with `debate_core.testing` and `tests/fixtures/landscape`,
   with a PM-ruling comment.
4. **Yes.** Whichever of t05 and t09's follow-up merges second wires `AffAssignmentService` into the
   CLI's composition root, with a test.

**Deviations 1 to 5 and Decisions 1 to 9 are accepted.** Reading every label's paragraph (767
against the counts' 726) and the 80% frame for the sheet are sound.

**Condition, to close in this session before the PR:**
* Change the sheet renderer for ruling 1, with tests on synthetic sources shown failing first.
* Hand the operator one block to rebuild the sheet (about 2.5 min, working agreement 11's guards).
* Run the school and team-code scan again on the new files, and record the counts.
* Then update the stale parts of this report. No re-review is needed.

**The PR:** opened with `--partial`. ac3 waits on the coach's answers to the rebuilt sheet, and
lands in a follow-up session (`scripts/task resume`) that also wires the producer if t05 has not.

**Follow-up work:**
* Skipping the second classification pass: recorded for t05.
* Quoting plan texts in the report itself: v1-e32-t11's sections and t05's run will read them again,
  as the sheet does.

If anything comes out differently, stop and ask for another review.

## Resumed 2026-10-24: ac3, the coach's answers applied

Session status: **COMPLETE**. Every criterion now passes, so the Goal is **Succeeded**.

### Summary

The coach's answers to the plan-text sheet are final, and the PM's context for ac3 (2026-10-24) said
how to apply them. They are in taxonomy **1.2.0**:
* **nine mechanisms of single payer**, as its children;
* **thirteen other affs**, `nhi-aff` among them.

Each takes the coach's tag keywords and no alias.

* **`nhi-aff`** has no keywords. A shaped plan text that names no aff names it when each of its words
  is a joining word, a frame word or a resolutional word. The two word lists are config,
  [`config/landscape/plan_texts/policy-2026-27-nhi.yaml`](../../config/landscape/plan_texts/policy-2026-27-nhi.yaml),
  built from the sheet's frame and the seven clusters the coach marked `nhi-aff`.
* **A text whose `should` has no federal actor before it is no plan text** (C59's fifty-states
  counterplan).
* **`medicare for all` and `m4a`** now name the Medicare for all child through its keywords. The
  interim words are gone from the code.
* **On hspolicy26 through 2026-10-20** (still the newest snapshot):
  * **1,479 of 2,192 affirmative rounds (67.5%) are identified**, against the first report's 1,252
    (57.1%);
  * 360 of 552 teams (65.2%);
  * `landscape report --dry-run`, without `--publish`, gives the same numbers and wrote nothing.

**Look first at** [the questions](#questions-for-the-pm-resumed-session). There are two Deviations:
* the labels are in sentence case, not exactly as the coach wrote them, because the configuration
  check refuses his Title Case;
* `tests/config` is outside `constraints.packages`.

There are also two conflicts beyond the three the PM named.

### Acceptance criteria (this session)

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac3: the coach's mechanisms as child affs of single payer in policy-2026-27-nhi.yaml, with his tag keywords, the taxonomy_version bumped, the config tests passing, and the counts of his decisions in the report | PASS | 9 children and 13 affs in 1.2.0 (the PM extended ac3 to the affs). `.venv/bin/python -m pytest tests/config` → 52 passed, `test_landscape_released_ids.py` included (the 1.1.0 lock is unchanged). [The coach's decisions](#the-coachs-decisions-counted) |
| plan-texts node: `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS | 483 passed in 2.13 s |
| PM context: the resolutional word set in config, never in Python, and how many unnamed texts and rounds it moves | PASS | [Below](#what-the-change-moves-on-hspolicy26): 41 documents (15 teams), 56 rounds |
| PM context: a text whose actor is not the federal government is not a plan, counted | PASS | 3 documents lose their counterplan paragraph; 0 change verdict ([below](#c59-the-fifty-states-counterplan)) |
| PM context: cards the child keywords move, and cards matching two children | PASS | 86 moved; 0 match two children |
| PM context: the dry run of `landscape report --caselist hspolicy26`, without `--publish` | PASS | 54 s; checksums of every file under `landscape/` and `reports/` unchanged ([below](#the-dry-run)) |

### The coach's decisions, counted

From `plan-text-answers.csv` (131 rows), read where it is and never copied:

| Decision | Clusters | Documents | Positions |
|---|---|---|---|
| A mechanism of single payer (a child) | 41 | 298 | 9 |
| Another aff | 31 | 63 | 12 |
| `nhi-aff` (C16, C20, C28, C48, C127, C128, C130) | 7 | 41 | 1 |
| Blank, so it stays with single payer | 46 | 545 | |
| Blank, `none`: no position (C59, C98, C100) | 3 | 5 | |
| Blank, an accepted conflict (C61, C66, C74) | 3 | 7 | |
| **Total** | **131** | **959** | **22** |

**Ids** follow the PM's rule:
* a child's id is its mechanism name in kebab case plus `-aff`, such as `global-budgets-aff` or
  `medicare-for-all-aff`;
* a top-level aff keeps the id the coach wrote in `aff_named`.

**Keywords:** no row the coach left blank holds keywords. Clusters naming one mechanism repeat the
same list, which is entered once. The coach separated keywords with commas, not the `;` the guide
showed, and each comma-separated phrase is one keyword.

**Aliases:** none. t01's loader does not require one (`Position.aliases` defaults to empty, and
nothing in `tests/config` or the matcher needs one), so the stop for an alias count did not apply.

### What the change moves on hspolicy26

**Plan-text verdicts, by documents.** Before is the cache as it stood under 1.1.0, copied aside
before the operator's run. After is the operator's run under 1.2.0.

| Before → after | Documents |
|---|---|
| NONE → NONE | 811 |
| NAMES single payer → NAMES single payer | 548 |
| NAMES single payer → NAMES a child | 216 |
| UNNAMED → NAMES a child | 82 |
| UNNAMED → NAMES another aff | 62 |
| **UNNAMED → NAMES `nhi-aff`** | **41** |
| UNNAMED → CONFLICTING | 5 |
| NAMES single payer → CONFLICTING | 3 |
| UNNAMED → UNNAMED | 2 |

* **The totals:** NAMES 767 → 949, UNNAMED 192 → 2, CONFLICTING 0 → 8, NONE 811 → 811.
* **The two left UNNAMED** are one document each, as C98 and C100 were. Neither gets an override.

**Rounds**, before from the first report (the same snapshot) and after from the dry run:

| | First report (1.1.0) | **1.2.0** |
|---|---|---|
| Identified affirmative rounds | 1,252 of 2,192 (57.1%) | **1,479 (67.5%)** |
| `PLAN_TEXT` | 959 | 1,171 |
| `TEAM_CARRY` | 226 | 251 |
| `PLACED_CARD` (rounds no plan text or carry names) | 67 | 57 |
| Unidentified | 940 | 713 |

1.2.0 also gives:
* 10 conflicting rounds, 1 refused carry, 73 teams carrying and 27 teams disagreeing;
* **360 of 552 teams identified (65.2%)**, against 298 in this task's run of 2026-10-24.

**`nhi-aff` takes 56 rounds**: 47 by their own plan text and 9 carried. These are the rounds the
resolutional rule moves.

Rounds by aff under 1.2.0 (`PLAN_TEXT` + `TEAM_CARRY`):
* single payer 705 + 133;
* global budgets 114 + 4;
* single public authority 71 + 8;
* value-based reimbursement 61 + 28;
* `nhi-aff` 47 + 9;
* Medicare for all 35 + 5;
* disparate impact enforcement 8 + 33;
* public option 27 + 9;
* lower payment rates 22 + 2;
* degrowth 16;
* ucc 13 + 1;
* indigenous 4 + 10;
* incarceration 7 + 2;
* prescription drug coverage 5 + 6;
* reproductive health, tiered NHI and nanomedicine coverage 8, 8 and 7;
* vouchers 5, ecological NHI 3 + 1, human enhancement 2, and one each for ACA reform, children's
  coverage and Medicaid expansion.

**Cards.** Every card was placed in memory under 1.1.0 and under 1.2.0. This was read-only, and both
caches had the same checksums after. 35.3 s.
* **86 cards move from single payer to a child:** value-based reimbursement 54, global budgets 16,
  Medicare for all 14, degrowth 2. Single payer keeps 2,026 of its 2,112.
* **0 cards hold two children's keywords**, so none falls back to the parent by that rule.
* **Counted cards are unchanged** at 63,494.
* **1,371 cards nothing placed before now have a keyword-only candidate** (`TAG_KEYWORD`, 0.5, t02's
  rule 4). They are below the review threshold, so they are not counted and stay in the review queue,
  whose rows are unchanged at 1,340. The largest group is 356 cards for `indigenous`, mostly in
  negative K files; the next are Medicare for all 174, reproductive health 161, public option 137,
  degrowth 133 and global budgets 133.

#### C59, the fifty-states counterplan

The rule: a text with `should` is a plan text only when a federal actor (`United States federal
government`, `USFG`, or `United States` not after `fifty`) comes before its last `should`, so a
preamble such as "care should be a right, so the USFG should ..." still reads. A text with `should`
and no such actor names nothing and is not shaped.

* **On hspolicy26 it removes one paragraph in each of 3 documents.** These are C59's documents.
* **No document changes verdict.** Each opens with its own federal single-payer plan text, at its
  first plan label. The counterplan is a second "plan" paragraph a few hundred paragraphs further
  on, which is the text the sheet showed for C59. So the three stay single payer from their real
  plan text.
* **No other document had a text the rule removes.**

#### The conflicts

There are 8 CONFLICTING documents (10 rounds). Six are the three the PM named:

| Cluster | The affs its plan texts name | Documents |
|---|---|---|
| C61 | reproductive health and single payer | 2 |
| C66 | public option and value-based reimbursement | 2 |
| C74 | degrowth and single public authority | 2 |
| (new) | incarceration and single payer | 1 |
| (new) | indigenous and `nhi-aff` | 1 |

The last two follow from the keywords as the coach wrote them. They are left as conflicts, as the
PM ruled for the others (question 3).

#### The dry run

`debate-research landscape report --caselist hspolicy26 --dry-run` was run from the task worktree,
without `--publish`.
* **Guards:** no `DEBATE_*` variable, no `caselist pull`.
* **Runtimes:** 54 s, and 50 s with `--json` for the method counts.
* **Nothing written:** every file under `~/.debate-research/dev/landscape/` and `reports/` had the
  same SHA-256 after both runs.

It ran on policy-2026-27-nhi 1.2.0, overrides `e1c2367c…f60ca5`, model mode `none`, 0 model calls,
and the snapshot was current (5 days old, 0 archives awaiting download).

| Count | First report (1.1.0) | **1.2.0 dry run** |
|---|---|---|
| Classification coverage by cards | 63,494 of 126,681 (50.1%) | 63,494 (50.1%) |
| Cards by method | | ALIAS 39,302; INHERITED 21,303; OVERRIDE 2,803; no position 4,888; TAG_KEYWORD 1,457; unplaced 56,928 |
| Classification coverage by rounds | 2,622 of 4,352 (60.2%) | **2,705 (62.2%)** |
| Affirmative rounds with no identified aff | 940 of 2,192 (42.9%) | **713 (32.5%)** |
| How affirmative rounds are identified | plan text 959, team carry 226, placed card 67 | plan text 1,171, team carry 251, placed card 57 |
| Negative rounds with no placed negative position | 1,238 | 1,238 |
| Position-rounds set aside as answers | 4,965 | 4,965 |
| Positions read; top-card rows | 75; 353 | 97; 358 |
| Review queue | 1,340 rows | 1,340 rows |
| Classification cache | | 107,187 lookups, 0 hits (the version bump), nothing written |
| Scan before sharing | 6 hits, accepted | **8 hits, 2 not yet accepted** (digest `81374e646621`) |

**The two new scan hits** are both in `top_cards.csv`, in the rows of the new Medicare for all child.
Each is the ordinary English word that is also a team code, in the card's tag "Medicare for All"; the
first report accepted the same word in another row. Neither names a team. The operator reads and
accepts them at the publish, which the PM coordinates.

**Planned keys:**
* `reports/landscape/hspolicy26/2026-10-20/`: `positions.csv`, `top_cards.csv`, `impact_cards.csv`
  and `report.md`;
* nothing uploaded.

### What was built

| Change | Where |
|---|---|
| The federal-actor rule, the resolutional rule (`ResolutionalPlanWords`, `PlanTextVocabulary.resolutional`) and no interim words | `arguments/landscape/plan_text.py`. The rule version moves to `plan-text-2`, and the vocabulary digest covers the word lists, so a cached reading is read again when either changes. The joining words are shared with the sheet (`JOINING_WORDS`) |
| `plan_texts/<topic id>.yaml`, read and checked with the configuration | `integrations/landscape/yaml_taxonomy_repository.py` (`PLAN_TEXT_DIRECTORY`, `load_plan_text_file`), with `TaxonomyRepository.resolutional_plan_words` in the port |
| The service and the operator script build the vocabulary with it | `application/aff_assignment.py`, `scripts/assign_landscape_affs.py`. The CLI's composition root was wired by t05, which merged after t09, so nothing changes there |
| Taxonomy 1.2.0, the topic map, the word lists | `config/landscape/taxonomies/policy-2026-27-nhi.yaml`, `config/landscape/topics.yaml`, `config/landscape/plan_texts/policy-2026-27-nhi.yaml` |
| The config suite: `plan_texts/` among the allowed files, and its words held to the alias check | `tests/config/test_landscape_taxonomies.py` |
| The coach's guide | `docs/guides/landscape-taxonomy.md`: the plan-text rules, 1.2.0, and the resolutional plan |
| The spec | the PM's ac3 context as a comment above `acceptanceCriteria`, and the Goal `Succeeded` |

**Tests:**
* `test_plan_text.py`;
* `test_plan_text_files.py` (new);
* `test_aff_assignment.py` (application);
* `tests/scripts/test_assign_landscape_affs.py`;
* `tests/config/test_landscape_taxonomies.py`.

### Checks shown failing for their reason

| Check | Red run |
|---|---|
| `test_plan_text.py` against a skeleton (the new model and parameter, no rule) | 12 failed, 54 passed |
| `test_plan_text_files.py` against a skeleton (the constant and a method returning `None`) | 11 failed, 2 passed |
| The producer's resolutional test, before the service passed the words | 1 failed, 8 passed |
| `tests/config` with the new file, before the directory test listed `plan_texts/` | 1 failed (the directory test), 47 passed |
| The coach's Title Case labels against the config's name check | 18 findings over 14 positions (scratch, not committed) |
| 14 targeted mutants, each restored byte for byte from `HEAD` | all 14 caught |

The mutants covered:
* the actor searched in the whole text;
* `fifty United States` read as federal;
* the first `should` instead of the last;
* a non-federal text still naming;
* the resolutional rule without a federal actor;
* joining words, and frame words, left out of the allowed set;
* the digest ignoring the rule;
* any position accepted as the resolutional aff;
* the rule beating a named aff;
* the file not checked against the taxonomy;
* a topic with no taxonomy not refused;
* the service, and the script, dropping the words.

The script's test was written after its code; its mutant fails it.

### Before the report (working agreement 10)

`uv run scripts/affected_tests.py` chose 173 of 449 test files (38.5%) from 16 changed files. They
were run with `.venv/bin/python -m pytest -n auto -m "not slow and not live"` under a 115 s limit:

* **The first run of the whole list stopped at the limit** with 90% done and no failure. Other
  sessions had the load average at 7.8, rising to 30.
* **So the same list was run in seven parts:** 1,930, 1,147, 957, 578, 40, 74 and 104 passed.
  **4,830 passed, 0 failed, 0 skipped.**
* **The rest:**
  * `ruff check .` and `ruff format --check .` OK;
  * `pyright` (the project's configuration) 0 errors;
  * `lint-imports` 16 kept;
  * `check_thin_handlers.py` OK;
  * `validate_specs.py` OK;
  * `check_command_blocks.py --base origin/dev` OK;
  * `docs_index.py --check-descriptions` OK.
* **After the affected set, `dev` moved** to `9ed01f4` (`v1-e32-t04` merged), and `scripts/task sync`
  rebased the branch onto it with no conflict. The landscape tests from every layer were run again
  (`arguments/landscape`, `integrations/landscape`, the application's landscape and plan-text tests,
  the CLI's landscape command, `tests/config`, the script and the landscape smoke test): 804 passed.
  `pyright`, `lint-imports`, `ruff check .` and `validate_specs.py` OK.

### Deviations (resumed session)

1. **The labels are the coach's mechanism names in sentence case** (`Global budgets`, `Single public
   authority`, `Medicare for all`), not exactly as he wrote them.
   * The PM's context said "exactly as he wrote it", but `tests/config`'s personal-data check refuses
     a capital after a label's first word as a person's name. It finds 18 such words in 14 of his 22
     labels.
   * The guide had asked him for sentence case. The ids, which are permanent, are unaffected.
   * Question 1.
2. **`tests/config/test_landscape_taxonomies.py` is outside `constraints.packages`.** ac3 names the
   config tests, and the new file under `config/landscape/` needs the directory test to list it.
   Question 2.
3. **The frame words are fixed in config**, as the sheet of 2026-10-24 printed them, not recomputed
   from each run's plan texts.
   * The cache keeps no words, so a frame recomputed weekly could not be applied per document.
   * A moving frame would also move assignments without any edit.
   * A plan text that writes `USFG` is outside both lists and stays unnamed. Today no UNNAMED document
     would move by adding it: the two left are C98 and C100.

### Decisions and assumptions (resumed session)

1. **For plan texts, two children of single payer conflict** and name nothing, as two unrelated affs
   do. For cards, the matcher's rule 3 keeps the parent. This is the PM's C74 (degrowth and public
   authority) staying CONFLICTING. It applies only to C74's 2 documents, which were UNNAMED under
   1.1.0, so no document identified before loses its aff by it. The 3 documents that went from single
   payer to CONFLICTING name single payer and another top-level aff (reproductive health,
   incarceration).
2. **The actor is read before the last `should`**, so a preamble with its own `should` does not hide
   the federal actor. `fifty United States` is not federal.
3. **The resolutional rule applies only to a shaped plan text that names no aff.** An aff named
   anywhere in the text wins.
4. **The joining words stay in Python**, shared with the sheet that first dropped them. They are
   English, not a list of resolutional words.
5. **`assign` was not run.** It classifies through the cache and rewrites the coach's review queue. The
   round counts come from the CLI's dry run and from a read-only script over the service, with a
   classification store that writes nothing. Both gave the same numbers.

### Operator follow-ups (resumed session)

1. **Done, 2026-10-24:** the plan-text pass under 1.2.0. 1,770 sources parsed, 0 refused, 0 unread,
   and the cache written (derived fields only). The runtime line was not in the pasted output.
2. **The first publish under 1.2.0** (the PM coordinates it):
   * `landscape report --caselist hspolicy26 --publish --dry-run`, then the two new scan hits read and
     accepted;
   * then `scripts/release_landscape_taxonomy.py --topic policy-2026-27-nhi --version 1.2.0` writes
     `released.yaml`, committed by the PM. This session did not touch it.
3. **The pull request**, from the task worktree, without `--partial` now that the Goal is
   `Succeeded`:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t09-policy-plan-texts
```

```bash
scripts/task pr v1-e32-t09-policy-plan-texts
```

### Questions for the PM (resumed session)

```text
v1-e32-t09 questions (resumed session, 2026-10-24). ac3 passes; the Goal is Succeeded.

1. Labels. Your context said the coach's mechanism_name exactly, but the
   config check reads a capital after a label's first word as a person's
   name and refuses 14 of his 22 (e.g. "Global Budgets"). Committed in
   sentence case: "Global budgets", "Medicare for all", "ACA reform".
   (a) Keep sentence case (the guide asked him for it; ids are unaffected).
   (b) Exempt these words from the check, to keep his Title Case.
   Recommendation: (a). The check is the only guard against a person's name
   in a label, and an exemption list grows with every coach edit.

2. tests/config/test_landscape_taxonomies.py is outside constraints.packages.
   ac3 names the config tests, and plan_texts/ had to join the directory test.
   Amend the spec's list with a PM-ruling comment?
   Recommendation: yes, as for ruling 3.

3. Two conflicts beyond C61, C66 and C74: one document whose plan texts name
   incarceration and single payer, one naming indigenous and nhi-aff (1 and
   1 rounds). Both follow from the coach's keywords.
   (a) Leave them CONFLICTING, as ruled for the three.
   (b) Ask the coach.
   Recommendation: (a). Two documents, and your ruling not to bend keywords.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
