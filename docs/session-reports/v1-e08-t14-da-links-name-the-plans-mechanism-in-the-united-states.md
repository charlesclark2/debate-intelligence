# Session report: v1-e08-t14-da-links-name-the-plans-mechanism-in-the-united-states

| | |
|---|---|
| Task | `v1-e08-t14-da-links-name-the-plans-mechanism-in-the-united-states` — A disadvantage's link queries name the plan's mechanism and the United States |
| Spec | [`plan_specs/v1/e08-research-workflows/t14-da-links-name-the-plans-mechanism-in-the-united-states.yaml`](../../plan_specs/v1/e08-research-workflows/t14-da-links-name-the-plans-mechanism-in-the-united-states.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t14-da-links-name-the-plans-mechanism-in-the-united-states` |
| Session status | COMPLETE: the Goal stays `InProgress` for the coach's review (ac1) and the operator's search (ac3) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A DA's link search on the NHI topic now names the plan's mechanisms and the United States. It does
this for all five DAs, built as proposed and ruled on 2026-11-04.

How it works:
- **The reviewed queries are unchanged.** The coach's link templates are asked as they are, first.
- **Up to five queries are added.** They come from the DA's first link template that names only
  `{query}` and `{topic}`. One is on the resolution's words and one is on each of the preset's four
  mechanisms. Each ends with "United States" unless it already names it.
- **Where the words live.** The mechanisms, their phrases and the country are in the NHI topic preset
  of `config/argument_taxonomy.yaml` (taxonomy 1.3.0), which awaits the coach's review. No argument
  entry changed, so the coach-reviewed guard is untouched.
- **What the loader refuses:** a preset with more than four mechanisms, two mechanisms with the same
  landscape id or the same phrase, a digit in a phrase, or no `topic` and `country` to build the
  queries on.

The politics DA's link search goes from 7 queries to 12, and the CLI test shows OpenAlex asked
exactly those 12.

ac2 and the node criterion pass. The tests failed first against the skeleton: 23 failed, all at
assertions. 23 mutants were all caught.

**ac1's coach review and ac3's repeated search are the operator's, so the Goal stays
`InProgress`.** The coach's review sheet and the ac3 blocks are below.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `da-links-name-the-plans-mechanism-in-the`: Mechanism links | Done | Proposal, then the PM's ruling. Tests written first and run red against a skeleton with the fan-out off. Then the preset's rules and the fan-out, then 23 mutants. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 (part): the PM rules on the proposal before any code | PASS | Proposal committed in `f56bde1` with no code. The PM ruled on 2026-11-04 (summarised [below](#the-pms-ruling-2026-11-04)), and the first code commit is `79b86ed`, after the ruling. |
| ac1 (part): the coach reviews the new templates (operator) | NOT RUN | The coach's. The sheet is [below](#review-sheet-for-the-coach). The NHI preset says `review: awaiting_coach_review`. |
| ac2: a DA's link need expands over the topic's plan mechanisms and names the United States, with the resolution's words kept as one query, by expansion tests on the recorded fixtures shown failing first | PASS | See the red run below. The green run of `test_query_expansion.py` and `test_search_command.py` gives `165 passed in 4.67s`. The tests, all with expected queries written by hand: the politics DA's whole 12-query expansion on NHI; the other four DAs' 7 queries each; the reviewed queries first and unchanged, with exactly 5 added, for each DA; the resolution query on "national health insurance" when "Medicare for All" is typed; no fan-out for other needs, an advantage, a kritik, a counterplan, no topic, or a preset with no mechanisms; the first template that always renders, its own window, and a phrase already naming the country; the search's own `since`; the stored search on both repositories; the CLI asking OpenAlex the 12 queries; six loader refusals; the committed preset against the landscape file. |
| ac3: the operator repeats v1-e08-t05's Policy search and the coach labels it blind; the PM records nDCG@10 and the relevant count against ac6's (3 of 20, 0.746) | NOT RUN | The operator's, after the merge, on an installed build the PM schedules (after Thursday's v1-e31-t32 copy). The blocks are under [Operator follow-ups](#operator-follow-ups). |
| Node: `uv run pytest packages/debate_core/tests/application/test_query_expansion.py` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/application/test_query_expansion.py`: `114 passed in 2.31s` |

### Red run

The skeleton was commit `79b86ed`, "Mechanism link tests, written first against a skeleton with the
fan-out off". It had:
- the preset's new fields (`review`, `mechanisms`), accepted with no rule on them;
- the 1.3.0 file;
- no fan-out.

```
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -q -p no:randomly --tb=line packages/debate_core/tests/application/test_query_expansion.py packages/debate_cli/tests/test_search_command.py
```

That gave `23 failed, 142 passed in 4.88s`, every failure at an assertion:

| Count | Failure | Tests |
|---|---|---|
| 6 | `DID NOT RAISE InvalidArgumentTaxonomy` | five mechanisms; mechanisms and no country; mechanisms and no topic; one landscape id twice; one phrase twice; a digit in a phrase |
| 16 | The expected queries are missing, or the count is short (`assert 7 == (7 + 5)`, `assert 7 == 12`, `assert [] == [...]`) | the politics expansion; the other four DAs; reviewed-first for each of the five DAs; the resolution's words when a mechanism is typed; only-a-DA's-link; the first template that always renders; the search's own `since`; the stored search on both repositories |
| 1 | The OpenAlex query list is short | the CLI's 12 queries |

The first attempt, before `79b86ed`, failed two older tests for reasons of their own, so I corrected
them before recording the run above:
- the committed-taxonomy test pins the version, and it moved from `1.2.1` to `1.3.0`;
- the "a topic setting query" refusal was being refused for its missing `review` instead of its own
  rule. It now carries a `review`.

**What the red run cannot show.** Three checks passed on the skeleton:
- the committed-content test (the four mechanisms, their landscape ids, labels and phrases, and the
  preset's review status);
- the missing-review refusal, because the skeleton already required the field;
- the negative lines of the only-a-DA's-link test, which carries a positive control so that it failed
  red.

Each is proven by the mutants below instead.

### Mutants

Each mutant was applied to the committed tree and run against the two test files with
`-n 0 -p no:randomly --tb=line` under `hard_stop.py 115`. The file was then restored with
`git checkout HEAD --`. There are 23 mutants: 20 in one script (kept in the scratchpad, not committed),
two of the landscape file, and one for the retired-position check added after them. Every one was
caught at an assertion, with no crash and no collection error. No test here uses Hypothesis, so
agreement 8's database does not apply.

| Mutant | Caught by |
|---|---|
| Fan-out on every need of a DA | only-a-DA's-link: `('politics-da', 'uniqueness')` |
| Fan-out for every kind of argument | only-a-DA's-link: `('economy-advantage', 'link')` |
| The country never added | 16 tests: the politics expansion, the other DAs, the CLI's 12 |
| The country added even when the phrase names it | first-template test (`beta plan in Testland link`) |
| The last renderable template instead of the first | 11 tests, including the CLI's |
| The resolution's query dropped (the forbidden entry) | 17 tests (`assert 11 == (7 + 5)`) |
| The resolution's query built on something other than the topic's words | first-template test |
| Added queries asked before the reviewed ones | 15 tests, including the CLI's |
| The template's own window ignored for added queries | first-template test |
| An added query's id without `/resolution` or the mechanism | 10 tests, including the CLI's template ids |
| The cap of four off by one | the refusal `five plan mechanisms` (DID NOT RAISE) |
| No check for the country | the refusal `plan mechanisms and no country` |
| A repeated landscape id accepted | the refusal `two plan mechanisms with one landscape id` |
| Phrases compared as written, not folded | the refusal `two plan mechanisms with one phrase` |
| A digit in a phrase accepted | the refusal `a plan mechanism phrase with a digit` |
| YAML: a mechanism that is a DA (`politics-da`) | 9 tests, among them the committed-content test |
| YAML: a label unlike the landscape's (`Public options`) | the committed-content test, at the landscape comparison |
| YAML: a phrase that is no landscape word (`Obamacare`) | 10 tests |
| YAML: the preset marked `coach_reviewed` | the committed-content test |
| YAML: a mechanism dropped | 16 tests |
| Landscape file: `aca-reform-aff` made a negative CP | the committed-content test: `('cp', 'neg', 'ACA reform') == ('aff', 'aff', 'ACA reform')` |
| Landscape file: `aca-reform-aff` renamed | the committed-content test: `AssertionError: aca-reform-aff` |
| Landscape file: `aca-reform-aff` retired (`deprecated: true`) | the committed-content test, at the check added for it (`270d116`) |

### Checks before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 275 test files: the domain model and the CLI test file reach the CLI. |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | Stopped at its 115-second limit (exit 124), at a load average near 3. **Over two minutes, so under agreement 10 the affected set is left to the pull request's `ci` check, not handed over.** |
| Every test file that reads the taxonomy or the expansion module, plus the changed areas and the always-run list: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n auto -m "not slow and not live"` over `test_search_command.py`, `test_query_expansion.py`, `test_federated_search.py`, `integrations/discovery/test_government.py`, `tests/scripts/test_stamp_build.py`, `tests/smoke/test_search_smoke.py`, `packages/debate_core/tests/domain`, `tests/architecture`, `tests/specs`, `tests/config`, and the CLI's `test_app.py`, `test_help_rendering.py` and `test_container_factories.py` | `2088 passed in 22.88s` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1919 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli tests/smoke` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 72 CLI command and API route handlers within 25 statements` |
| `scripts/export_schemas.py --check` | `OK: 10 schemas in packages/debate_core/schemas are up to date`: no schema changed (ruling 5a) |
| `uv run scripts/validate_specs.py`, docs checks | See [Final checks](#final-checks) |

## Proposal for the PM's ruling

As sent to the PM on 2026-11-04, before any code (`f56bde1`). The ruling is [below](#the-pms-ruling-2026-11-04); where it differs (5a, no `ExpandedQuery` field), the ruling is what was built.

What I measured, all offline, with scripts kept in the session scratchpad:
- `config/argument_taxonomy.yaml` 1.2.1, loaded by the real loader;
- the courier feed fixture, run through the feeds provider's own `query_terms` and `matches_terms`;
- `git diff HEAD origin/dev`, which showed no amendment to this spec.

I quote card text from no file, and every mechanism word below is a landscape label or the coach's
tag keyword.

### 1. Where the mechanisms come from

**Recommendation: the NHI topic preset in `config/argument_taxonomy.yaml` lists them.** Each entry
names the landscape's aff position by `landscape_id`. A test checks every id against
`config/landscape/taxonomies/policy-2026-27-nhi.yaml`: it must be a position there with `side: aff`.
The code never reads the landscape file, which is the rule v1-e08-t04 set.

Why not read the landscape's aff positions directly:
- **Too many positions.** The landscape has 24 aff positions, including `kritikal-aff` (no plan text),
  `nhi-aff` (the resolution itself), `degrowth-aff` and `nanomedicine-coverage-aff`. A fan-out needs a
  short ordered choice of them anyway.
- **Labels search badly.** The labels are heading names, such as "UCC", "Indigenous", "Resolutional
  NHI" and "ACA reform". Each mechanism needs a search phrase, which the coach edits.
- **Separate versions.** The landscape is versioned for counting. A landscape bump would otherwise
  change search queries without anyone reviewing them.

The NHI list I propose follows the spec's own four, in its order:

| Order | Landscape id | Landscape label | Search phrase | Where the phrase comes from |
|---|---|---|---|---|
| 1 | `single-payer-aff` | Single payer | `single payer` | The label |
| 2 | `medicare-for-all-aff` | Medicare for all | `Medicare for All` | The label, and the coach's tag keyword |
| 3 | `public-option-aff` | Public option | `public option` | The label, and the coach's tag keyword |
| 4 | `aca-reform-aff` | ACA reform | `Affordable Care Act` | The coach's tag keyword. The label's "ACA" is an acronym that also names other things. |

**Mechanisms the cap leaves out, for the coach to swap in:**
- single payer's other eight children: `global-budgets-aff`, `single-public-authority-aff`,
  `lower-payment-rates-aff`, `value-based-reimbursement-aff`, `disparate-impact-enforcement-aff`,
  `degrowth-aff`, `prescription-drug-coverage-aff` and `nanomedicine-coverage-aff`
  (`medicare-for-all-aff` is the ninth);
- the other affs, such as `medicaid-expansion-aff`, `ucc-aff` and `tiered-nhi-aff`.

`nhi-aff` is covered by the resolution's own queries. `kritikal-aff` has no plan text to link to.

The phrases follow two rules: no digits, so the coach's `3069` keyword is out, and no card text.

### 2. How the United States is anchored

**Recommendation: a word in the query, on the added queries only. No provider filter.**

The resolution is "The United States federal government should establish national health insurance in
the United States." The preset gains `country: United States` as a variable. The existing test checks
every preset variable word for word against `topics.yaml`'s resolution, so it covers this one too.

Every added query ends with the country, unless it already names it. The reviewed queries are asked
exactly as today, without it.

What each choice does to recall on the recorded fixtures:
- **A word on every query, the reviewed ones included, costs feed recall.** The feeds provider keeps
  an entry only when every query word is in its title or snippet. On `courier_politics.xml`, the
  politics DA's seven link queries for `health insurance` match one item today ("Health insurance
  fight costs the president political capital"). With `United States` appended they match none.
  Anchoring only the added queries keeps that one item, because the reviewed seven are unchanged. The
  added queries match no fixture item with the anchor or without it.
- **A word in an OpenAlex query: the fixtures cannot measure it.** The recorded OpenAlex transport
  answers every `/works` request with the same body, whatever the query. The recall change can only
  be measured live, which is ac3. I have not checked how OpenAlex's `search=` combines words. That
  would be a live documentation read, which goes to the operator, and the coach's labels answer the
  question that matters anyway.
- **An OpenAlex filter: not recommended for this task.** The filter would be by author country,
  something like `authorships.countries:US` (the exact name is unverified, for the same reason).
  - It filters by where the authors work, not by what the work is about. It would drop a Canadian
  scholar on US single payer and keep a US author on South Africa's NHI.
  - It needs a new `SearchFilters` field, which changes the stored `Search` schema.
  - It needs an adapter change in `debate_core.integrations`, outside this task's packages.
  - It does nothing for feeds.
  - The fixtures cannot show what it drops, because the server applies it.

  If ac3 still shows foreign NHI, the filter is a follow-up for E07.

### 3. The fan-out's size

**Recommendation: the preset names at most 4 mechanisms, and the loader refuses more.** A DA's link
search adds, in order:
1. one query on the resolution's words: the DA's first link template that renders on `{query}` and
   `{topic}`, filled with the topic's value, plus the country;
2. one query per mechanism, from the same template with `{query}` and `{topic}` filled with the
   mechanism's phrase, plus the country.

That is at most five added queries. Every DA's first link template renders on `{query}` and `{topic}`
alone today. Each added query uses the need's window (link: 1,826 days).

Queries per search, with `--topic policy-2026-27-nhi`, and OpenAlex searches a day without a key. The
daily figures use v1-e08-t05's estimate of about 100 OpenAlex requests a day, one request per query
until v1-e08-t10 lands.

| DA link search | Today | Recommended (first template) | First two templates | Every link template |
|---|---|---|---|---|
| `politics-da` (7 link templates) | 7, ~14 a day | **12, ~8 a day** | 17, ~5 a day | 42, ~2 a day |
| `midterms-da`, `economy-da`, `spending-da`, `federalism-da` (2 each) | 2, ~50 a day | **7, ~14 a day** | 12, ~8 a day | 12, ~8 a day |

The figures are 100 divided by the query count, rounded down: 100/7, 100/12, 100/17, 100/42, 100/2 and
100/7.

A search without `--topic`, or on a preset with no mechanisms, adds nothing. So does a need other
than link, or an argument that is not a DA (advantages, kritiks). Every search except a DA's link
search on a preset with mechanisms is therefore unchanged.

**What the ac6 search would ask** (`"national health insurance" --argument politics-da --need link
--topic policy-2026-27-nhi`), recommended option:

| Queries | Text |
|---|---|
| The reviewed 7, unchanged | `national health insurance political capital`, `… partisan fight Congress`, `… unpopular with voters`, `… popular with Republicans`, `… unpopular with Republicans`, `… popular with Democrats`, `… unpopular with Democrats` |
| Added 5 | `national health insurance political capital United States`, `single payer political capital United States`, `Medicare for All political capital United States`, `public option political capital United States`, `Affordable Care Act political capital United States` |

The first-template choice puts the politics DA's mechanism links on political capital alone. The
party-popularity links ("unpopular with Republicans") are not crossed with the mechanisms. That is
the price of the cap, and the coach's review is where to change it. Moving another template first
would change a reviewed entry, which puts it back to `awaiting_coach_review`.

### 4. The coach-reviewed guard

**Recommendation: the fan-out runs at expansion time, and no reviewed entry changes.**

The guard is `test_the_committed_taxonomy_keeps_every_coach_reviewed_entry_as_he_reviewed_it`. It
compares each reviewed argument entry whole, and the DA family's needs, with
`coach_reviewed_1_2_1.yaml`. It does not read the topic presets.

The new text lives in the NHI preset: `country` and the `mechanisms` list. The preset gets
`review: awaiting_coach_review` of its own, so the coach's sign-off is recorded in the file as it is
for arguments.

Why not the other route:
- **It would need new templates on the DA entries.** That means a `{mechanism}` variable on politics,
  midterms, economy, spending and federalism.
- **Those five entries would go back to `awaiting_coach_review` whole.** Their reviewed uniqueness,
  internal link, impact and answers templates would lose the guard until he reviews again.
- **He would review five sets of near-duplicate templates.** Here he reviews one list and one rule.

The 17 entries awaiting his review from v1-e08-t08 are untouched. The taxonomy goes from 1.2.1 to
1.3.0, a minor bump, because the preset gains new fields.

The guard's fixture is refreshed only after the coach reviews. The preset is not guarded until then.

### 5. The resolution's words stay a query

Both ways the forbidden entry could be read are met:
- The reviewed queries are asked as today, built on what the debater typed. In ac6 that was the
  resolution's words.
- The added resolution query is built on the topic's value ("national health insurance") whatever was
  typed. A test pins that one query holds the topic's value word for word.

### What the build would change (after the ruling)

- **`domain/argument_taxonomy.py`:** `TopicPreset` gains `mechanisms` (id, label, phrase, at most 4,
  no digits, unique) and `review`, and the taxonomy declares the `country` variable.
- **`application/query_expansion.py`:** the fan-out in `expand_with_templates`. Added queries are
  recorded with template ids such as `politics-da/link/1/medicare-for-all-aff` and
  `politics-da/link/1/resolution`.
- **`domain/search.py`:** an optional `ExpandedQuery.mechanism` (the landscape id), left out of the
  JSON when it is unset, so every other search serializes as before. This changes
  `schemas/search.schema.json`, which is outside the listed packages, as in v1-e08-t04.
  The alternative is to keep the mechanism in the template id alone, with no schema change.
- **`config/argument_taxonomy.yaml`:** the NHI preset's new fields and 1.3.0. The ac2 example test
  pins the taxonomy version, so that pin moves.
- **Tests, shown failing first against a skeleton with the fan-out off:**
  - every DA's link need on the NHI preset, with expected queries written by hand;
  - the reviewed queries unchanged;
  - no fan-out without a preset, for an advantage or a kritik, or for any other need;
  - the cap refusal;
  - the landscape-id check;
  - the stored search's record;
  - a CLI test that OpenAlex is asked the 12 queries.
- **Not touched:** `commands/search.py` (v1-e08-t06's), and the 17 entries still awaiting review.

## Questions for the PM

```text
v1-e08-t14 proposal (session of 2026-11-04). No code yet; the build starts on your ruling.

1. Where the mechanisms come from.
   A. The NHI topic preset in config/argument_taxonomy.yaml lists them, each with the landscape aff
      id it stands for (checked by a test against config/landscape/taxonomies/policy-2026-27-nhi.yaml,
      side aff) and a search phrase (recommended). The code still never reads a landscape file; the
      landscape has 24 aff positions whose labels are headings ("UCC", "Resolutional NHI"), so a short
      ordered list with search phrases is needed either way, and a landscape bump cannot silently move
      search queries.
   B. Read every aff position from the landscape file at expansion time, label as phrase: 24 positions,
      including kritikal-aff and nhi-aff, so it needs a filter and a cap anyway.
   NHI list for A, in the spec's order: single-payer-aff "single payer", medicare-for-all-aff
   "Medicare for All", public-option-aff "public option", aca-reform-aff "Affordable Care Act" (the
   coach's tag keyword; the label's "ACA" also names other things). Single payer's other eight
   children and the other affs are left for the coach to swap in.

2. The United States anchor.
   A. The preset gains country: United States (the resolution's own words, checked by the existing
      word-for-word test), appended to every ADDED query only; the reviewed queries are asked exactly
      as today (recommended). On the recorded courier feed fixture, the politics link queries for
      "health insurance" match 1 item today; with "United States" appended to them they match 0
      (feeds keep an entry only when every word is in it); A keeps the 1. The OpenAlex fixture
      answers every query alike, so its recall change is ac3's to measure.
   B. Append it to every query, the reviewed ones included: costs the feed match above.
   C. An OpenAlex author-country filter as well: filters by where authors work, not what the work is
      about; needs a stored SearchFilters field and an adapter change outside this task's packages;
      nothing for feeds. Recommended as an E07 follow-up only if ac3 still shows foreign NHI.

3. Fan-out size. A preset names at most 4 mechanisms (the loader refuses more). A DA's link search
   on it adds one query per mechanism plus one on the resolution's words, each from the DA's first
   link template that renders on {query}/{topic}, plus the country: at most 5 added.
   politics-da link: 7 queries today -> 12 (A, recommended), 17 (first two templates), 42 (every
   template). The other four DAs: 2 -> 7, 12, 12. On t05's estimate of ~100 keyless OpenAlex requests
   a day, one per query until t10: politics link ~14 searches a day today -> ~8 (A), ~5, ~2.
   The cost of A: the politics mechanism links are political capital only, not the party-popularity
   templates; the coach can say otherwise at his review.

4. The coach-reviewed guard.
   A. Fan-out at expansion time; no reviewed entry changes; the new words (country, mechanisms) live
      in the preset with its own review: awaiting_coach_review; taxonomy 1.2.1 -> 1.3.0; the guard's
      fixture is refreshed only after his review (recommended).
   B. New {mechanism} templates on the five DA entries: all five go back to awaiting_coach_review
      whole, so their reviewed uniqueness, impact and answers templates lose the guard until he
      reviews again.

5. Two smaller choices.
   a. Record a mechanism query's landscape id in an optional ExpandedQuery.mechanism (exclude_if
      unset, so other searches serialize as before; regenerates schemas/search.schema.json, outside
      the listed packages) (recommended), or only in its template id
      (politics-da/link/1/medicare-for-all-aff), with no schema change.
   b. DAs only, as the spec says (recommended), or advantages' link need too (an aff advantage's link
      is the plan's mechanism as well).

Not touched either way: commands/search.py (v1-e08-t06), and the 17 entries awaiting the coach
from v1-e08-t08.
```

## The PM's ruling (2026-11-04)

Every question was ruled as recommended. The proposal and its questions above are kept as written.

1. **A.** The NHI preset lists the four mechanisms in the order proposed, each tested against the
   landscape file, and the code reads no landscape file.
2. **A.** `country: United States` goes on the added queries only. The author-country filter (C) is a
   follow-up, and only if ac3 still shows other countries' NHI.
3. **A.** At most 4 mechanisms and at most 5 added queries, from the first template that always
   renders. The politics DA's link search goes from 7 queries to 12.
4. **A.** The fan-out runs at expansion time, and the preset carries its own `review`. Taxonomy
   1.2.1 becomes 1.3.0. The guard's fixture is refreshed only after the coach's review, and
   v1-e08-t08's 17 entries are untouched.
5. **5a:** the template id only (no `ExpandedQuery` field, no schema change). **5b:** DAs only, with
   advantages under Follow-up work, "after ac3".

## Files changed

- **`config/argument_taxonomy.yaml`** (1.2.1 → 1.3.0):
  - the `country` variable;
  - the NHI preset's `review: awaiting_coach_review`, `country: United States` and four `mechanisms`;
  - the header and topics comments.

  No argument entry or family changed.
- **`packages/debate_core/src/debate_core/domain/argument_taxonomy.py`:**
  - `TopicMechanism` (landscape id, label, phrase);
  - `TopicPreset.review` and `.mechanisms`;
  - `MAX_TOPIC_MECHANISMS = 4`;
  - the loader's preset rules (`_check_mechanisms`).
- **`packages/debate_core/src/debate_core/application/query_expansion.py`:**
  - the fan-out (`_mechanism_queries`, `_naming`, `MECHANISM_NEED`);
  - `_resolve` now also returns the preset;
  - the template loop builds candidates and then removes repeats as before, through a shared
    `_template_query`;
  - the module docstring has a section on the fan-out.
- **`packages/debate_core/tests/application/test_query_expansion.py`:**
  - the new tests and six refusal cases;
  - `review` on SMALL_TAXONOMY's preset and on one older refusal case;
  - both version pins moved to `1.3.0`.
- **`packages/debate_cli/tests/test_search_command.py`:** OpenAlex is asked the 12 queries, and the
  JSON carries the five added template ids.
- **`docs/guides/landscape-taxonomy.md`:** a paragraph under "Retire or merge a position". Renaming,
  retiring or relabelling an aff position that a search preset names fails a test until the preset
  matches.
- **`packages/debate_core/README.md`:** the two module rows mention the mechanisms.

## Deviations from the spec

1. **`packages/debate_core/README.md` is outside `constraints.packages`.** It gets two one-line row
   edits, as in v1-e08-t04 and t08.
2. **A required `review` on every topic preset.** The ruling put a review on the NHI preset. I made
   it required on every preset, as on every argument, so that a preset cannot slip in without one. No
   other preset exists, and only the test file's own taxonomy needed it.

## Decisions and assumptions

1. **The added queries use the preset's own `topic` and `country`.** A `--var` from the request does
   not change them, because the resolution query must be the resolution's words whatever was typed
   (ruling 5's reading). The reviewed queries still take the request's variables, as before.
2. **Repeats are removed across all the queries, in order.** The reviewed queries come first. An
   added query that repeats one of them, ignoring case and spacing, is asked once. None can repeat on
   NHI, because every added query ends with the country and no reviewed template names it.
3. **"Already names the country"** means the country's words appear, folded, as whole words.
   `beta plan in Testland` gets no second `Testland`.
4. **The committed-content test also checks each phrase is a landscape word:** the position's label,
   or one of the coach's tag keywords, ignoring case. A phrase therefore can't drift into words the
   landscape doesn't hold. "Affordable Care Act" is `aca-reform-aff`'s tag keyword, and "Medicare for
   All" is `medicare-for-all-aff`'s.
5. **A retired aff position fails the check.** The guide paragraph says so, and a mutant proved it.

## Review sheet for the coach

Rendered from `config/argument_taxonomy.yaml` 1.3.0. It uses taxonomy words only: landscape labels,
the coach's tag keywords, and the reviewed templates.

**What changes.** A DA's link search on the NHI topic still asks every link template you reviewed,
exactly as before. Then it adds up to five queries, all from that DA's first link template:
- one on the resolution's words, "national health insurance";
- one on each mechanism below.

Every added query ends with "United States" unless it already names it. That is the anchor rule. This
applies to the five DAs (politics, midterms, economy, spending, federalism) and only to their link
need. Advantages and the other needs are unchanged.

**The four mechanisms** (at most four, in this order):

| Order | Landscape position | Searched as |
|---|---|---|
| 1 | Single payer (`single-payer-aff`) | single payer |
| 2 | Medicare for all (`medicare-for-all-aff`) | Medicare for All |
| 3 | Public option (`public-option-aff`) | public option |
| 4 | ACA reform (`aca-reform-aff`) | Affordable Care Act |

**The five added queries for the ac6 search** (politics DA, link, "national health insurance"). The
first link template is `{query} political capital`. Your seven reviewed queries come first, as
before.

1. `national health insurance political capital United States`
2. `single payer political capital United States`
3. `Medicare for All political capital United States`
4. `public option political capital United States`
5. `Affordable Care Act political capital United States`

**The other DAs' added queries** use their own first link template the same way:

| DA | First link template | First added query |
|---|---|---|
| Midterms | `{query} voters election impact` | `single payer voters election impact United States` |
| Economy | `{query} cost economy` | `single payer cost economy United States` |
| Spending | `{query} cost federal budget` | `single payer cost federal budget United States` |
| Federalism | `{query} federal preemption states` | `single payer federal preemption states United States` |

**The mechanisms the cap leaves out** (any can be swapped in for one of the four):
- **Single payer's other mechanisms:** Global budgets, Single public authority, Lower payment rates,
  Value-based reimbursement, Disparate impact enforcement, Degrowth, Prescription drug coverage,
  Nanomedicine coverage.
- **Other affs:** UCC, Indigenous, Reproductive health, Tiered NHI, Incarceration, Vouchers, Medicaid
  expansion, Children's coverage, Ecological NHI, Human enhancement.
- **Not candidates:** Resolutional NHI, which the resolution query already covers, and Kritikal
  affirmative, which has no plan text.

**Three questions:**

1. Do you approve the four mechanisms and their search phrases, or would you swap any of them, or any
   phrase?
2. The politics DA's mechanism queries all use "political capital". Should they use a different link
   template instead, for example a party-popularity one such as "unpopular with Republicans"?
3. Do you approve the anchor rule, "United States" at the end of every added query and on none of
   your reviewed ones?

The PM applies the answers in a batch:
- flip the preset's `review` to `coach_reviewed`;
- raise `taxonomy_version` if anything changed;
- refresh the guard's fixture for the reviewed entries.

Moving a different politics template first would change a reviewed entry, so that entry would need
his review again. The other way to answer question 2 is a per-DA choice of template in the preset,
which is a code change.

## Operator follow-ups

ac1's coach review is a sign-off, not a command: the sheet above goes to him through the PM.

**ac3: after the merge, on an installed dev build that carries it, and after Thursday's v1-e31-t32
copy, as the PM schedules.** These are the same live calls as v1-e08-t05's ac6:
- OpenAlex, now 12 requests for this search instead of 7;
- the publisher feeds in `config/feeds/`.

They write only to dev's local data directory and three files on your Desktop, and print exit codes,
counts and taxonomy ids. No model is called. Each command takes under a minute, then the coach's
time.

**Operator command 1: check the installed build** (seconds)
Where: your Mac, any terminal
```bash
debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"])'
```
Success looks like the tag of the dev pre-release the PM named, built after this merge. Command 2
proves the build carries the change.

**Operator command 2: the Policy NHI search, politics DA link, repeated** (under a minute)
Where: the same terminal
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else cd "$HOME" && env DEBATE_ENV=dev debate-research --json search "national health insurance" --argument politics-da --need link --topic policy-2026-27-nhi --max-results 200 --save "$HOME/Desktop/search-policy-nhi-mechanisms.json" > /tmp/search-policy-nhi-mechanisms.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); r = e.get("error") or {}; d = e.get("data") or r.get("details") or {}; x = d.get("expansion") or {}; q = x.get("queries") or []; print("code", r.get("code"), "exit_code", r.get("exit_code")); print("status", d.get("status"), "results", len(d.get("results") or [])); print("taxonomy", x.get("taxonomy_version"), "queries", len(q), "warning", x.get("warning")); print("added", [t.rsplit("/", 1)[1] for t in (y.get("template_id") or "" for y in q) if t.count("/") == 3]); print("providers", [(p["provider"], p["outcome"], p["results"]) for p in d.get("providers") or []])' /tmp/search-policy-nhi-mechanisms.json; fi
```
Success looks like:
- `exit 0`;
- `code None exit_code None`;
- `status COMPLETE` and `results` above zero;
- `taxonomy 1.3.0 queries 12 warning None` (a later taxonomy is fine if the coach's batch has landed);
- `added ['resolution', 'single-payer-aff', 'medicare-for-all-aff', 'public-option-aff', 'aca-reform-aff']`;
- `providers` naming `openalex` and `rss`, each with a count.

`exit 6` with `rss` `partial` (an unreadable feed) is what v1-e08-t05's run gave, and still counts.
**`queries 7` or an empty `added` means the build predates this merge: stop there and do not make
the sheet.** Paste back the five lines. The titles stay in the saved file.

**Operator command 3: the coach's blind sheet and its key** (seconds, then the coach's time)
Where: the same terminal, after command 2 saved its file. This follows the PM's ruling on
v1-e08-t05's Q4. It writes two files to your Desktop, from the top 10 by the ranking and the top 10 by
raw provider order (up to 20 rows):
- **`labels-policy-nhi-mechanisms.csv`**, for the coach: `item`, `title`, `url` and an empty
  `relevant`, in title order with no rank;
- **`key-policy-nhi-mechanisms.csv`**, for the scoring session only: `item`, `rank`,
  `provider_order`.
```bash
python3 -I -c 'import csv, json, sys; d = json.load(open(sys.argv[1])); r = d["results"]; top = {x["rank"] for x in sorted(r, key=lambda x: x["rank"])[:10]} | {x["rank"] for x in sorted(r, key=lambda x: x["provider_order"])[:10]}; rows = sorted((x for x in r if x["rank"] in top), key=lambda x: ((x["title"] or "").casefold(), x["url"] or "")); s = csv.writer(open(sys.argv[2], "w", newline="")); k = csv.writer(open(sys.argv[3], "w", newline="")); s.writerow(["item", "title", "url", "relevant"]); k.writerow(["item", "rank", "provider_order"]); [(s.writerow([i, x["title"], x["url"], ""]), k.writerow([i, x["rank"], x["provider_order"]])) for i, x in enumerate(rows, start=1)]; print(sys.argv[2], len(rows), "rows; key", sys.argv[3])' "$HOME/Desktop/search-policy-nhi-mechanisms.json" "$HOME/Desktop/labels-policy-nhi-mechanisms.csv" "$HOME/Desktop/key-policy-nhi-mechanisms.csv"
```
Success looks like one line naming the labels file with between 10 and 20 rows, and the key file. I
ran this line on an invented 30-result file in the session scratchpad: it wrote 17 rows, the
untitled one first, and a key of the same items.
- The coach gets the labels file only. He marks `relevant` `y` or `n` on each row, asked the same as
  before: "would you want this in the first page for a debater researching this query?"
- The key stays with you until he has answered.
- The filled labels file, the key and the saved search file then go to the PM. The PM records
  nDCG@10 for the ranking and for provider order, and the relevant count, against ac6's 3 of 20 and
  0.746 (0.000 in provider order).

## Follow-up work

- **Advantages' link need, after ac3 (ruling 5b).** An aff advantage's link is the plan's mechanism
  too. If ac3 shows the fan-out helps, the same preset could feed advantages' link searches.
- **An OpenAlex author-country filter (E07), only if ac3 still shows other countries' NHI** (ruling
  2C).
- **A per-DA choice of template for the mechanism queries**, if the coach answers question 2 with a
  template that differs by DA. Today the fan-out takes each DA's first template that always renders.
- **v1-e08-t10 (ask each provider once per search)** takes the 12 OpenAlex requests back to 1. Until
  then, this search costs 12 of OpenAlex's keyless daily requests.

## Final checks

The Goal stays `InProgress`, because ac1's coach review and ac3 are open. No `set-phase` was run.

| Check | Result |
|---|---|
| `uv run scripts/validate_specs.py` | `OK: 608 files, 41 epics, 545 tasks, 22 releases` |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 671 shell code blocks in 246 Markdown files (1 session reports changed since origin/dev)` |
| `uv run --frozen python scripts/check_links.py` | `OK: 3531 relative links and anchors in 596 Markdown files` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 68 indexed documents under docs/ have a description` |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-04

**Notes:**

Built exactly as ruled, and the coach's rule now reaches every DA's link search without one reviewed
template changing.

1. **ac1's first part passes.** The proposal was committed with no code (`f56bde1`), and the first code
   commit (`79b86ed`) follows the ruling.
2. **ac2 passes.** Red first against a skeleton with the fan-out off: 23 failed, all at assertions,
   with the three checks the red run could not show proven by mutants instead, and said so. 23 mutants
   all caught, including the forbidden one (the resolution's query dropped: 17 tests) and three on the
   landscape file itself, so a renamed, retired or re-sided aff position fails a test until the preset
   matches. The CLI test shows OpenAlex asked exactly the 12 queries.
3. **No schema change** (`export_schemas.py --check`: 10 up to date), as ruling 5a asked; the template
   ids carry the mechanism.
4. **Deviations accepted.** (1) The README's two rows. (2) A required `review` on every topic preset:
   stricter than the ruling, and right, since a preset should never slip in unreviewed.
5. **Decisions accepted**, in particular (1): the added queries use the preset's own topic and country,
   so the resolution query stays the resolution's words whatever is typed.
6. **ac1's second part, the coach's review:** Charlie is the coach, so the PM asks him the sheet's three
   questions directly and applies his answers in the next batch (the preset to `coach_reviewed`, the
   version raised if anything changed, the guard's fixture refreshed). The batch is built after this
   merge, because it also changes `config/argument_taxonomy.yaml` for v1-e08-t08's 17 entries.
7. **ac3** runs after Thursday 2026-11-05's v1-e31-t32 copy, on a dev build carrying this merge, with
   the blocks above; the PM records nDCG@10 and the relevant count against ac6's.
8. **Follow-ups the PM files after ac3:** advantages' link need, the author-country filter (only if
   foreign NHI remains), and a per-DA template choice if the coach's answer needs it.
9. **Closing checks:** the affected set (275 files) is left to `ci` (agreement 10); the changed areas
   and the always-run list (2,088 passed), ruff, pyright, lint-imports, thin handlers, the schemas, the
   specs, links, the docs index and command blocks are clean.
10. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until the
    coach's review and ac3 are recorded.

## Operator records (recorded by the PM, 2026-11-04)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac1 (part): the coach reviews the new templates (operator) | NOT RUN (operator) | PASS | the coach's answers of 2026-11-04 to the sheet's three questions: (1) the four mechanisms and their phrases approved; he asked why the others are left out, and the PM's answer is the request budget until v1-e08-t10 lands; (2) the politics DA's mechanism queries must also cross the party-popularity templates (popular and unpopular with Republicans and with Democrats), which is new work, filed as `v1-e08-t16` after v1-e08-t10; (3) the anchor rule approved. The PM marked the NHI preset `coach_reviewed` in taxonomy 1.4.0 |

The Goal stays `InProgress` for ac3, the operator's repeated search, after Thursday 2026-11-05's v1-e31-t32 copy. `v1-e08-t16` repeats the blind search once the crossing is in, so each change gets its own before and after.

## Operator records (recorded by the PM, 2026-11-09)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3: the operator repeats v1-e08-t05's Policy search and the coach labels it blind; the PM records nDCG@10 and the relevant count against ac6's | NOT RUN | PASS | 2026-11-08, v1.1.0-dev.342: the politics DA's link on national health insurance, saved by the operator and labelled blind by the coach as v1-e08-t05's was (ranked and provider-order top tens merged, sorted by title, no rank shown). **6 relevant of 19 rows** (t05: 3 of 20); nDCG@10 **0.438** ranked against **0.746** in provider order (t05: 0.746 against 0.000). The coach's criterion: a politics DA link card is relevant only when it ties the plan's mechanism to the political fight over a specific bill, since each politics DA turns on its own agenda item |

Every criterion passes, so the Goal is `Succeeded`. More relevant results came back, but the ranking placed them below the providers' own order: that is `v1-e08-t24`. The coach's criterion is `v1-e08-t23`, after `v1-e08-t16`'s crossing.
