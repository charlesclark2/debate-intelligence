# Session report: v1-e08-t16-mechanism-queries-cross-the-chosen-link-templates

| | |
|---|---|
| Task | `v1-e08-t16-mechanism-queries-cross-the-chosen-link-templates` — A DA's mechanism queries cross the link templates the coach chose, and a preset may name more mechanisms |
| Spec | [`plan_specs/v1/e08-research-workflows/t16-mechanism-queries-cross-the-chosen-link-templates.yaml`](../../plan_specs/v1/e08-research-workflows/t16-mechanism-queries-cross-the-chosen-link-templates.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t16-mechanism-queries-cross-the-chosen-link-templates` |
| Session status | COMPLETE: the Goal stays `InProgress` for ac3, the operator's repeated search after the merge <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The politics DA's link search on the NHI topic now crosses the link templates the coach chose. It
was built as the PM ruled twice on 2026-11-11, with the coach's answers applied.

What a search now asks:
- **The coach's seven reviewed link queries come first,** unchanged and in order.
- **Then six templates are crossed, template-major,** each with the resolution's words and with each
  of the four mechanisms, and each query ends with "United States":
  1. the coach's own wording, `{query} costs political capital Congress`, a crossing-only template of
     the preset;
  2. then link templates 2, 4, 5, 6 and 7.
- **37 queries in all,** up from 12. They still go to OpenAlex in one request per page.

How it is configured:
- **The NHI preset lists the choice** in `mechanism_link_templates`, in `config/argument_taxonomy.yaml`
  1.6.0. The preset is `coach_reviewed`.
- **A DA template is named by its id and its exact text,** which the loader checks against the DA's
  entry.
- **A DA the preset doesn't name** crosses its first link template that names only `{query}` and
  `{topic}`, as before. The other four Policy DAs are unchanged.
- **`MAX_QUERIES_PER_SEARCH = 42` replaces the four-mechanism cap.** The loader refuses a preset that
  takes any DA's link search over it. That leaves 5 queries of room for v1-e08-t23.
- **No argument entry changed,** and the coach-reviewed guard and its fixture are untouched.

**The cost the PM accepted (ruling 3A):** Crossref can't reach all 37 queries, so this search is
PARTIAL on Crossref and exits 6. The search README says so.

Evidence:
- ac1 and ac2 pass. The tests ran red first against a skeleton: 25 failed, all at assertions.
- 24 mutants were all caught, none by a crash.
- **ac3 is the operator's after the merge, so the Goal stays `InProgress`.** Its blocks are under
  [Operator follow-ups](#operator-follow-ups).

For v1-e08-t23: under the 42-query maximum the politics DA's link search on NHI has **5 queries of
room**, one agenda-item template crossed with the five subjects (PM's ruling 4).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `mechanism-queries-cross-the-chosen-link`: Chosen templates | Done | Proposal (`802ad91`), two PM rulings and the coach's answers; tests first against a skeleton (`eaaa40a`, `53fe0c6`), red run; implementation (`7afe5a6`); 24 mutants; docs (`4db100f`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal (the per-DA template choice, the mechanism cap and the queries per search) is ruled on by the PM before any code, and the coach reviews the preset's changes (operator) | PASS | Proposal committed with no code (`802ad91`). The PM ruled on 2026-11-11 ([first ruling](#the-pms-ruling-2026-11-11)). The coach answered the review sheet in the session the same day ([his answers](#the-coachs-answers-2026-11-11)). The PM ruled again on those answers ([second ruling](#the-pms-ruling-after-the-coachs-answers-2026-11-11)). The first code commit, `eaaa40a`, follows both. |
| ac2: a preset names the link templates each DA's mechanism queries cross, and more mechanisms up to the stated maximum, by expansion tests on the recorded fixtures shown failing first, with every reviewed template unchanged | PASS | Red run [below](#red-run) (25 failed at assertions). Green: `test_query_expansion.py` and `test_search_command.py` give `226 passed in 10.60s`. The tests are listed [below](#what-the-tests-pin). Every reviewed template is unchanged: no argument entry changed, the guard passes, and the committed preset's DA templates are checked against `coach_reviewed_1_5_0.yaml`. |
| ac3: the operator repeats the Policy search and the coach labels it blind; the PM records nDCG@10 and the relevant count against v1-e08-t14's ac3 | NOT RUN | The operator's, after the merge. The blocks are under [Operator follow-ups](#operator-follow-ups). |
| Node: `uv run pytest packages/debate_core/tests/application/test_query_expansion.py` | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/application/test_query_expansion.py`: `138 passed in 4.62s`, after the sync |

### Red run

The skeleton was `eaaa40a`, "Crossed link template tests, written first against a skeleton that
crosses only the default". It had:
- `mechanism_link_templates` and `MAX_QUERIES_PER_SEARCH`, accepted with no rule on either;
- the NHI preset's six entries, in taxonomy 1.6.0;
- the crossing loop, fed only each DA's default template.

```
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -q --tb=line packages/debate_core/tests/application/test_query_expansion.py packages/debate_cli/tests/test_search_command.py
```

That gave `25 failed, 201 passed in 10.99s`, every failure at an assertion:

| Count | Failure | Tests |
|---|---|---|
| 17 | `DID NOT RAISE InvalidArgumentTaxonomy` | the 16 crossing refusals and the 43-template pair |
| 5 | The expected queries are missing, or the count is short (`assert 12 == 37`, `assert 12 == (7 + 30)`) | the politics expansion; reviewed-first for the politics DA; typed as a mechanism; only-a-DA's-link; the template-major crossing in the listed order |
| 2 | The stored search's provider queries are short | the stored search on both repositories |
| 1 | OpenAlex's joined request is the old 12 | the CLI test |

**The first red run, on `eaaa40a` itself, gave 26 failed.** The extra failure was my own
mistake, not the skeleton's: the one-request pin expected five DAs, and the taxonomy has nine (four are
the LD topic's). I corrected the count in `53fe0c6` before any implementation, and the run above is
after that correction.

**What the red run cannot show.** Six checks passed on the skeleton:
- the other four DAs' expansions, and reviewed-first for those four;
- the resolution's words once per crossed template, since the skeleton's default template already
  asks them once;
- a DA the preset doesn't name crossing its default;
- crossing-only templates never asked without the topic;
- the committed-preset content test;
- the one-request pin.

Each is proven by a mutant below.

### Mutants

Each mutant was applied to the committed tree and run against the two test files with
`-n 0 --tb=line`. The file was then restored with `git checkout HEAD --`. The script is kept in the
scratchpad, not committed. Every catch was at an assertion: no crash line, no collection error. No
test here uses Hypothesis, so agreement 8's database does not apply.

One batch was stopped by `hard_stop.py` mid-mutant, with the domain file still mutated. I restored it
from HEAD at once, confirmed the tree clean, and ran the rest in batches of four.

| Mutant | Caught by |
|---|---|
| Crossing subject-major, not template-major | 6 tests, the politics expansion among them |
| Crossing in the DA's template order, not the listed order | the template-major crossing test |
| Crossed queries asked before the reviewed ones | 17 tests |
| The resolution's words dropped from the crossing (the forbidden entry) | 23 tests, the resolution-once test among them |
| Default: the last renderable link template, not the first | 6 tests (the other four DAs, the unnamed DA) |
| Default: a DA the preset doesn't name crosses nothing | 14 tests |
| Default: an unnamed DA takes another DA's entries | 10 tests |
| Crossing-only entry: its DA not checked | the refusal `a crossing-only template of an advantage` |
| Crossing-only entry: its variables not checked | the refusal `a crossing-only template naming a bill` |
| Crossing-only entry: numbered from 0 | 5 tests, the politics expansion and the CLI's among them |
| Crossing-only entry: an id without the topic | 5 tests |
| Entry shape: both an id and an argument accepted | the refusal `a crossed template with an id and an argument` |
| DA template: the text check removed | the refusal `a crossed template whose text differs` |
| DA template: the need not checked | the refusal `a crossed template of another need` |
| One template crossed twice accepted | the refusal `one template crossed twice` |
| Crossed templates without mechanisms accepted | the refusal `crossed templates and no mechanisms` |
| Cap off by one (refuses 42) | the edge test (42 loads) |
| Cap counts mechanisms without the resolution | both over-the-maximum refusals |
| Cap counts only named entries (a default DA counts none) | the refusal `a DA link search one query over the maximum` |
| Cap raised to 43 | 3 tests |
| Pair template count not checked | the 43-template refusal |
| YAML: template 3 crossed instead of 2 | 6 tests, the committed-preset test among them |
| YAML: the coach's own wording dropped | 10 tests |
| `openalex.py`'s `MAX_URL_CHARS` lowered to 2,500 (the pin's own break) | the one-request pin: `('policy-2026-27-nhi', 'politics-da', 37)` |

### What the tests pin

Every expected query is written by hand from the ruling and the YAML, not produced by the code.

- **The politics DA's whole 37-query expansion on NHI.** The 30 crossed queries are listed one by one
  (`NHI_POLITICS_CROSSED`), and the reviewed seven come first.
- **Reviewed first, for every Policy DA.** The politics DA adds 30 and the other four add 5 each.
- **The resolution's words.** Every crossed template is asked once on them, whatever was typed. This
  is the forbidden entry.
- **The crossing on a small taxonomy:**
  - template-major, in the preset's listed order (3 before 2), not the DA's;
  - a crossing-only template takes the need's window and an id from the topic;
  - a DA template keeps its own window;
  - a DA the preset doesn't name crosses its first renderable template;
  - crossing-only templates are never asked without the topic.
- **The maximum at its edge:**
  - a DA link search of exactly 42 loads, and so does a pair of 42 templates;
  - 43 is refused both ways;
  - five mechanisms now load.
- **Sixteen refusals:**
  - an alias, an advantage (by id and as a crossing-only template), another need, a malformed id and
    a number past the DA's templates;
  - a text that differs, and `{bill}` (by id and as a crossing-only template);
  - a positional field, a template crossed twice, id and argument both or neither, and crossed
    templates with no mechanisms;
  - two over-the-maximum presets.
- **The committed preset:** its six entries, its review, and each DA template's text against the
  coach-reviewed record.
- **One OpenAlex request per page** for all nine DAs' link searches on NHI, at `--max-results 200`,
  through the adapter's own `works_requests`.
- **The stored search, on both repositories:** the providers are asked the 30 crossed queries, and
  their template ids are recorded.
- **The CLI:** OpenAlex is asked the 37 queries in one joined request, and the JSON carries the 30
  crossed template ids.
- **The Crossref public-pool footer (dev and prod profiles):** `1 result from 37 queries`, where it was
  12.

### Checks before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `303 of 740 test files (40.9%) chosen in 19.8 s from 10 changed files.` |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | Stopped at its 115-second limit. **Over two minutes, so under agreement 10 the affected set is left to the pull request's `ci` check, not handed over.** |
| The test files that exercise the taxonomy, expansion, search and daily, the discovery adapters, the domain, the changed areas and the always-run list, under `hard_stop.py 115 … pytest -q -n auto -m "not slow and not live and not partition_proof"`. The files: the CLI's `test_search_command.py`, `test_daily_command.py`, `test_app.py`, `test_help_rendering.py` and `test_container_factories.py`; core's `test_query_expansion.py`, `test_daily_presets.py`, `test_digest_service.py`, `test_federated_search.py` and `test_batch_cut_service.py`; `integrations/discovery`; `domain`; `tests/smoke/test_search_smoke.py`; `tests/architecture`, `tests/specs` and `tests/config`; and `tests/scripts`' `test_stamp_build.py`, `test_check_command_blocks.py` and `test_docs_index.py` | `3338 passed in 70.86s` before the sync; **`3343 passed in 39.02s` after it** |
| `uv run --frozen ruff format --check .` / `ruff check .` | `2056 files already formatted` / `All checks passed!` (after the sync) |
| `uv run --frozen pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 74 CLI command and API route handlers within 25 statements` |
| `scripts/export_schemas.py --check` | `OK: 10 schemas in packages/debate_core/schemas are up to date` (no schema change) |
| `uv run scripts/validate_specs.py`, docs checks | See [Final checks](#final-checks) |

**The sync.** origin/dev moved during the session: v1-e07-t15 changed when GovInfo without a key
counts as partial. Its changes overlapped this branch in the search README and `test_search_command.py`.
- `scripts/task sync` rebased the branch. It pushed nothing, because the branch has never been pushed.
- The test file rebased cleanly.
- The README conflicted in the GovInfo paragraph. I kept dev's new wording and applied this task's
  37-query counts to it.
- The checks above were run again after the rebase.

## Proposal for the PM's ruling

What I read and measured, all offline:
- v1-e08-t14's report, including the coach's answers of 2026-11-04 and its ac3 record of 2026-11-08
  (6 relevant of 19 rows; nDCG@10 0.438 ranked against 0.746 in provider order);
- v1-e08-t10's report and `integrations/discovery/openalex.py`;
- `application/query_expansion.py`, `domain/argument_taxonomy.py` and their tests;
- `config/argument_taxonomy.yaml` 1.5.0, `config/landscape/taxonomies/policy-2026-27-nhi.yaml`, and
  the specs of v1-e08-t23 and v1-e08-t24.

The measuring scripts are kept in the session scratchpad and are not committed:
- the joined OpenAlex URLs, from the real `works_requests` and `works_url`, with no request sent;
- Crossref's pace, through the virtual-time harness of `test_crossref.py` over a mock transport;
- the ranking's terms, from the real `query_terms`.

Every word below is a taxonomy word: a reviewed template, a landscape label or a coach's tag keyword.
The team counts are aggregates already committed by v1-e32-t15.

### 1. How a preset names the templates a DA's mechanism queries cross

**Recommendation: a list on the topic preset, `mechanism_link_templates`.** Each entry names a
template by its id, as the search's JSON already records it, together with the template's text:

```yaml
    mechanism_link_templates:
      - {template_id: politics-da/link/1, text: "{query} political capital"}
      - {template_id: politics-da/link/4, text: "{query} popular with Republicans"}
      - {template_id: politics-da/link/5, text: "{query} unpopular with Republicans"}
      - {template_id: politics-da/link/6, text: "{query} popular with Democrats"}
      - {template_id: politics-da/link/7, text: "{query} unpopular with Democrats"}
```

**Why the text as well as the id.** Template ids are positional. If a reviewed DA entry ever gains,
loses or reorders a link template, `politics-da/link/4` would quietly point at a different template.
The text never changes the template; it is a check. The loader refuses the file when the template at
that id no longer has that text, so the preset has to be looked at again. The mechanisms already work
this way, with each landscape label checked against the landscape file. The option without the check
(B: ids alone) is shorter and is in the questions.

**What the crossing does.** For a DA the preset names, the DA's link search:
1. asks every reviewed link template, as today, first;
2. then asks each named template, in the listed order, on the resolution's words and then on each
   mechanism;
3. ends each of those queries with the country unless it already names it, as today.

That is template-major order. It keeps today's 12 queries as the first 12, in today's order, and adds
the new ones after them. A crossed query's template id takes the form today's do:
`politics-da/link/4/single-payer-aff`, `politics-da/link/4/resolution`. Nothing in the stored search
changes shape, so no schema changes (v1-e08-t14's ruling 5a).

**A DA the preset does not name** crosses its first link template that names only `{query}` and
`{topic}`. That is today's rule, and for each of the five DAs it is their template 1, so the
midterms, economy, spending and federalism searches are unchanged.

**What the loader refuses**, each naming the preset and the entry:
- an argument that is not a DA, or an alias instead of its id;
- a need other than `link`;
- a number with no template;
- a text that is not the template's at that id;
- a template naming a variable beyond `{query}` and `{topic}`;
- the same template twice;
- chosen templates on a preset with no mechanisms;
- a DA link search over the maximum (section 3).

### 2. The NHI preset's choice for the politics DA

**Political capital (template 1) plus the four party-popularity templates (4 to 7),** as the coach
said on 2026-11-04. Templates 2 ("partisan fight Congress") and 3 ("unpopular with voters") are not
crossed. The coach named only the party-popularity ones, and the review sheet asks him to confirm it.

| Politics DA link search, `national health insurance --topic policy-2026-27-nhi` | Queries |
|---|---|
| Today (v1-e08-t14) | 7 reviewed + 1 template × 5 subjects = **12** |
| This proposal, with today's four mechanisms | 7 + 5 templates × 5 subjects = **32** |

The subjects are the resolution's words plus each mechanism. The 20 new queries are the four
party-popularity templates on each subject: for example `single payer unpopular with Republicans
United States` and `national health insurance popular with Democrats United States`. They are listed
in full on the review sheet.

### 3. The maximum of queries per search, and the mechanism cap

**Where the limit comes from.** v1-e08-t10 joins every query of a search that share a date window
into one OpenAlex `search=`, as `(q1) OR (q2) …`. `openalex.py` defines
`MAX_URL_CHARS: Final = 3_500`, documented as: "OpenAlex refuses one over about 4 KB with `400` and
suggests splitting an `OR` list into chunks (developers.openalex.org/guides/searching, read by the PM
2026-11-04)". `works_requests` splits the queries into the fewest requests whose URL, at its last page,
stays within that limit. The search therefore never breaks: a larger search costs one more request
per page.

**So the maximum is the size that keeps one request per page.** I measured it with the module's own
`works_requests` and `works_url`, on the committed politics templates. The search's typed query was
`national health insurance` at `--max-results 200`, the ac3 search, where the last page sends `page=2`
and has the longest URL. Added mechanisms come in the order of section 4.

| Maximum | Mechanisms the preset can name | Politics link queries | Each other DA's link queries | Longest URL (of 3,500) | Requests per page |
|---|---|---|---|---|---|
| 32 | 4 (today's) | 32 | 7 | 2,286 | 1 |
| 37 | 5 | 37 | 8 | 2,594 | 1 |
| **42 (recommended)** | **6** | **42** | **9** | **2,947** | **1** |
| 47 | 7 | 47 | 10 | 3,280 | 1 |
| 52 | 8 | 52 | 11 | split | 2 |

The figure 47 agrees with v1-e08-t10's split test: of 96 queries of this shape, 47 fit one request.

**Why 42 and not 47.** Two things the preset doesn't control also go into the joined request:
- what the debater types, which appears in all seven reviewed queries, with no length limit on
  `SearchRequest.query`;
- `--expand-llm`'s model queries: three by default, five at most, each up to 120 characters. They
  share the link window, so they join the same request.

The longest typed query that still goes in one request at each size:

| Maximum | No model queries | 3 model queries of 60 characters | 3 of 120 | 5 of 120 |
|---|---|---|---|---|
| 32 | 198 | 167 | 141 | 105 |
| 37 | 155 | 123 | 97 | 60 |
| **42** | **105** | **73** | **47** | **10** |
| 47 | 56 | 25 | 0 | 0 |

At 42, a typed query of about 100 characters still goes in one request, and so does a typical
`--expand-llm`. At 47 there is no room for either.

**The rule.** `MAX_QUERIES_PER_SEARCH = 42` (in `domain/argument_taxonomy.py`) replaces
`MAX_TOPIC_MECHANISMS = 4`. The loader computes each DA's link search on each preset as its link
templates plus its crossed templates × (1 + mechanisms), and refuses a preset that takes any of them
over 42, naming the DA and the count. It also checks every (argument, need)'s own template count
against the same number. That count is at most 7 today, so nothing changes, but the name stays honest.

The number of mechanisms is then whatever fits. The politics DA binds: (42 − 7) / 5 = 7 subjects,
which is the resolution plus six mechanisms. URL length depends on the phrases as well as the count.
So a test also pins that every DA's link search on every committed preset, on the ac3 query, is one
OpenAlex request per page. A preset whose phrases are long fails that test before it ships.

**Requests per search, provider by provider** (the dev and prod profiles enable all five, and the NHI
topic lists the two government providers in `config/feeds/health-insurance.yaml`):

| Provider | 12 queries (today) | 32 queries | 42 queries | Source of the figure |
|---|---|---|---|---|
| OpenAlex | 2 (two pages of 100) | 2 | 2 | measured above |
| Publisher feeds | 1 read per feed | same | same | v1-e08-t10 |
| Crossref, polite pool | 12 sent, COMPLETE (answers in 0.5 s or 1.5 s); 9 sent, PARTIAL (2.5 s) | at most 28 sent (0.5 s), 18 (1.5 s), 9 (2.5 s): **PARTIAL** | same as 32 | measured on virtual time |
| Crossref, public pool | 9 / 6 / 3 sent: PARTIAL | 9 / 6 / 3: PARTIAL | same | measured on virtual time |
| Federal Register | 12 | 32 | 42 | one request per query, no stated limit |
| GovInfo | 12 | 32 | 42 | one per query; the key allows 1,000 an hour (`data_gov.py`): about 83, 31 or 23 such searches an hour |

**The Crossref cost.** Crossref sends a query only while its answer could still arrive within the
10-second timeout, less a 2-second reserve. The rest are answered "not asked" and the search is
PARTIAL (`crossref.py`, `pace.py`). On the polite pool, today's 12 queries complete when Crossref
answers within 1.5 seconds. Any search of 32 or more never completes. The queries Crossref skips are
the last ones, so the crossed queries: Crossref still asks the reviewed seven and the first 11 to 21
added ones.

The search's results are not wrong, but every NHI politics link search would read PARTIAL and exit 6.
Fixing it is a Crossref adapter change, in `debate_core.integrations`, outside this task's packages. I
recommend accepting it here, saying so in the guide, and an E07 follow-up (questions, item 3).

### 4. Which added mechanisms the cap allows, and in what order

At 42 the preset can name **two more**, six in all.

The order you gave was single payer's other mechanisms, then Medicaid expansion, UCC and tiered NHI.
Taken in landscape order, the first two are global budgets and single public authority. They are also
the two read most. Teams reading each, from v1-e32-t15's committed table (assigned aff rounds, counts
only):

| Candidate | Landscape id | Teams | Phrase (label or the coach's tag keyword) |
|---|---|---|---|
| Global budgets | `global-budgets-aff` | 53 | `global budgets` |
| Single public authority | `single-public-authority-aff` | 26 | `single public authority` |
| Value-based reimbursement | `value-based-reimbursement-aff` | 14 | `value based reimbursement` |
| Lower payment rates | `lower-payment-rates-aff` | 9 | `lower payment rates` |
| UCC | `ucc-aff` | 7 | `universal catastrophic coverage` (tag keyword; "UCC" also names other things, as "ACA" did) |
| Disparate impact enforcement | `disparate-impact-enforcement-aff` | 5 | `disparate impact` |
| Degrowth | `degrowth-aff` | 3 | `degrowth` |
| Tiered NHI | `tiered-nhi-aff` | 2 | `tiered national health insurance` |
| Prescription drug coverage | `prescription-drug-coverage-aff` | 2 | `prescription drug coverage` |
| Nanomedicine coverage | `nanomedicine-coverage-aff` | 2 | `nanomedicine` |
| Medicaid expansion | `medicaid-expansion-aff` | 1 | `Medicaid expansion` |

**Recommendation: add global budgets, then single public authority,** in that order after today's
four.
- Medicaid expansion, UCC and tiered NHI don't fit at 42.
- Even at 47 only value-based reimbursement would come next.
- The coach can swap any of the six.

For his review, the same table gives today's four: Medicare for all 15 teams, public option 8, and
ACA reform 1. ACA reform is read by as few teams as Medicaid expansion, and by fewer than every
other candidate above.

Every phrase above meets the existing rules: no digits, the label or a tag keyword, and no two
phrases alike.

### 5. Room for v1-e08-t23 (the agenda item)

The crossing is a function of two lists: the templates to cross and the subjects to cross them with.
v1-e08-t23 adds one more template set, the agenda-item templates, which name `{bill}` beside the
subject. It crosses them with the same subjects, in the same template-major order, after this task's.
When the request names no agenda item they are skipped, as `{bill}` templates are today, and the
search says its links are generic.

This task's rule refusing a crossed template that names more than `{query}` and `{topic}` is the one
line t23 relaxes. Nothing else of the shape changes.

**The maximum applies to t23 too.** At 42, the politics DA has 10 queries left after this task's 32:
two agenda-item templates × five subjects. If the coach adds the two mechanisms, there are none left.
So the choice in section 4 is also a choice between more mechanisms now and room for t23's agenda item
later. t23's proposal would then have to give up mechanisms, or remeasure and raise the maximum, which
the URL table shows has little headroom left.

### 6. What the larger query count does to the ranking (said, not fixed here)

v1-e08-t24's finding: on t14's search the ranking (0.438) did worse than provider order (0.746). Its
suspicion is that the features favour results that match many queries loosely.

- **BM25's terms do not change with the crossing.** The ranking scores each result against the
  distinct words of every query asked (`query_terms`). The 12 queries of today have 26 distinct terms;
  the 32 of the crossing have the same 26, because the party-popularity words and the mechanism words
  are already there. On a given result set the crossing leaves every score where it was.
- **Each added mechanism adds its words to that bag.** Global budgets adds `global` and `budgets`;
  single public authority adds `authority`. A result that uses those words anywhere then scores for
  them, whatever its link. This is the loose-match effect t24 suspects, and it grows with mechanisms,
  not with templates.
- **The result set does change.** OpenAlex's 200 works answer the whole `OR` of 32 groups instead of
  12, so the party-popularity groups bring their own works into the same pool. Crossref skips the
  crossed queries (section 3). The feeds keep few or no added items: the added queries end with
  "United States", and v1-e08-t14 found they matched no fixture item.
- **Attribution.** v1-e08-t10 found that live works almost always go to every query. Each query's
  record therefore carries the whole joined answer, and the footer's OpenAlex count can read 200 × 32.
  That is `v1-e08-t19`, still Pending.
- **What ac3 will measure.** With t24 unbuilt, the ranking is expected to keep falling below provider
  order. Provider order is the measure of what the crossing itself retrieves. The PM can record both
  nDCG@10 figures as before, and t24's offline replay can re-score this search as well.

### What the build would change (after the ruling)

- **`domain/argument_taxonomy.py`:**
  - `TopicPreset.mechanism_link_templates` (a template id and its text);
  - `MAX_QUERIES_PER_SEARCH = 42` in place of `MAX_TOPIC_MECHANISMS`;
  - the loader rules of section 1, checked against the taxonomy's own DA entries.
- **`application/query_expansion.py`:** `_mechanism_queries` takes the DA's chosen templates (or the
  default) and crosses them template-major. The module docstring is updated.
- **`config/argument_taxonomy.yaml`:** 1.5.0 becomes 1.6.0. The NHI preset gets the five politics
  templates and any mechanisms the coach approves, and the header and preset comments are updated.
  The preset's `review` depends on question 5.
- **Tests, written first and run red against a skeleton** that accepts the new field and crosses
  nothing. Every expected query is written by hand:
  - the politics DA's whole 32-query (or 42-query) expansion on NHI;
  - today's 12 kept as its first 12;
  - the other four DAs unchanged;
  - the resolution's own words kept as one query for every crossed template;
  - each loader refusal;
  - the maximum, off by one each way;
  - one OpenAlex request per page for every committed preset's DA link search;
  - the committed preset's choices checked against the reviewed templates' text;
  - the coach-reviewed guard unchanged;
  - the CLI test: OpenAlex asked the 32 queries in one joined request.

  No test calls a live provider.
- **`docs/guides/landscape-taxonomy.md`:** a sentence on the crossing and on what a preset's change
  costs (the Crossref PARTIAL).
- **Not touched:** every argument entry and the guard's fixture `coach_reviewed_1_5_0.yaml`;
  `debate_core.integrations` (Crossref); the ranking.

## Questions for the PM

```text
v1-e08-t16 proposal (session of 2026-11-11). No code yet; the build starts on your ruling and the
coach's review. Full proposal: docs/session-reports/v1-e08-t16-mechanism-queries-cross-the-chosen-link-templates.md.

1. How a preset names a DA's crossed templates.
   A. A list on the topic preset, mechanism_link_templates, each entry a template id as the search
      JSON records it (politics-da/link/4) plus that template's text, which the loader checks, so a
      reviewed entry that ever reorders its link templates fails the load instead of silently
      crossing a different template (recommended).
   B. Ids alone (shorter; a reorder would go unnoticed until a test or the coach caught it).
   Either way: crossed template-major (each chosen template on the resolution's words, then each
   mechanism), after the reviewed queries, so today's 12 stay the first 12 in today's order; ids
   politics-da/link/4/single-payer-aff; no schema change. A DA the preset does not name crosses its
   first link template that names only {query} and {topic} (template 1 for all five DAs today), so
   midterms, economy, spending and federalism are unchanged at 7 queries.

2. The NHI choice for politics: link templates 1, 4, 5, 6, 7 (political capital and the four party-
   popularity ones); not 2 (partisan fight Congress) or 3 (unpopular with voters). Politics link
   search 12 -> 32 queries, still one OpenAlex request per page (2,286 of 3,500 URL characters,
   measured with works_requests/works_url at --max-results 200).

3. The stated maximum and the mechanism cap. The limit is openalex.py's MAX_URL_CHARS = 3_500 (OpenAlex
   refuses ~4 KB with 400; your reading of its searching guide, 2026-11-04); past it the joined
   request splits, so the cost of going over is one more request per page, never a broken search.
   Measured (politics binds: 7 reviewed + 5 crossed x (1 + mechanisms)):
     max 32: 4 mechanisms, URL 2,286; typed query up to 198 chars alone, 105 with 5 max model queries
     max 37: 5 mechanisms, URL 2,594; 155 / 60
     max 42: 6 mechanisms, URL 2,947; 105 / 10 (47 with 3 model queries of 120 chars) (recommended)
     max 47: 7 mechanisms, URL 3,280; 56 / 0
     max 52: 8 mechanisms: 2 requests per page
   Other DAs at 42: 9 queries each. Rule: MAX_QUERIES_PER_SEARCH = 42 replaces MAX_TOPIC_MECHANISMS = 4;
   the loader refuses a preset that takes any DA's link search over it; a test pins every committed
   preset's DA link search to one OpenAlex request per page.
   The cost you should rule on: Crossref still asks one query at a time, paced. Measured on virtual
   time, its polite pool sends at most 28 of a search's queries (18 if it answers in 1.5 s); today's
   12 complete, but every search of 32 or more is PARTIAL (exit 6), the crossed queries being the
   ones not asked. Federal Register and GovInfo take one request per query (GovInfo's key allows
   1,000 an hour: ~31 such searches an hour at 32). Options:
   A. Accept it here, say it in the guide, and file an E07 follow-up for Crossref (for example: queries
      its pace cannot reach are not counted as partial, or Crossref is asked the reviewed queries
      only) (recommended).
   B. Hold the crossing to what Crossref completes (about 12 to 18 queries), which cannot hold the
      coach's 32.

4. Added mechanisms, at 42: two more. In your order (single payer's others first, then Medicaid
   expansion, UCC, tiered NHI) and by teams reading them (v1-e32-t15's committed table), the first two
   are global budgets (53 teams, phrase "global budgets") and single public authority (26, "single
   public authority"); recommended, in that order after today's four. Medicaid expansion (1 team),
   UCC (7, phrase "universal catastrophic coverage", since "UCC" names other things) and tiered NHI
   (2, "tiered national health insurance") do not fit at 42. For the coach: of today's four, ACA reform
   is read by 1 team.
   Note for v1-e08-t23: at 42 the politics DA has 10 queries of room after the crossing's 32, enough
   for two agenda-item templates x five subjects; adding these two mechanisms uses all of it. So
   choose between (a) the two mechanisms now, or (b) today's four and room kept for t23.

5. The preset's review. The preset is coach_reviewed today. If the coach answers the review sheet
   before the build (the operator's plan), the build commits the preset as coach_reviewed in 1.6.0
   with his answers applied (recommended); otherwise it goes back to awaiting_coach_review until his
   batch.

6. Ranking (said, not fixed): the crossing adds no BM25 term (26 distinct terms at 12 queries and at
   32), so on a given result set no score moves; each added mechanism adds its words (global, budgets,
   authority), the loose-match surface v1-e08-t24 suspects. The result set does change (OpenAlex's 200
   answer 32 OR groups). ac3 should record provider-order nDCG beside the ranked one, since provider
   order measures what the crossing retrieves while t24 is unbuilt.
```

## The PM's ruling (2026-11-11)

The proposal and its questions above are kept as written. The ruling, summarised:

1. **A.** `mechanism_link_templates` names each template by its id and its text, checked on load. The
   crossing is template-major and comes after the reviewed queries, so today's 12 stay the first 12,
   in today's order. The ids are as proposed. A DA the preset doesn't name crosses its first link
   template that names only `{query}` and `{topic}`.
2. **The politics DA crosses link templates 1, 4, 5, 6 and 7,** not 2 or 3. Its link search goes from
   12 queries to 32.
3. **`MAX_QUERIES_PER_SEARCH = 42` replaces `MAX_TOPIC_MECHANISMS = 4`.**
   - The loader refuses a preset that takes any DA's link search over 42.
   - A test pins every committed preset's DA link searches to one OpenAlex request per page.
   - **Crossref: option A.** A search past Crossref's pace is PARTIAL, and that is accepted. The search
     guide says which providers can't reach every query of a long search, and that the footer names
     them. Crossref and the partial rule are not changed here; the PM files an E07 task.
4. **Mechanisms: option (b). Today's four are kept.** The 10 queries of room under 42 are kept for
   v1-e08-t23's agenda-item templates. Global budgets and single public authority are not added. The
   team counts in section 4 stay recorded for the coach's later choice.
5. **The preset's review.** If the coach answers the review sheet before the build, the preset is
   committed as `coach_reviewed` in 1.6.0 with his answers applied. Otherwise it is
   `awaiting_coach_review`.
6. **Accepted.** The guide's ranking note says it, and ac3's record carries provider-order nDCG@10
   beside the ranked figure.

The build starts once the coach has answered the sheet below. Its tests run red first, then mutants
on the crossing order, the default template, the text check and the cap.

## Review sheet for the coach

Revised after the PM's ruling, which settled the mechanism questions: today's four stay. Two questions
are left.

**What changes.** Your seven politics DA link templates are still asked exactly as you reviewed
them, first. Today the mechanism queries use only "political capital". With this change, each of
these five templates is asked on the resolution's words and on each of the four mechanisms (single
payer, Medicare for All, public option, Affordable Care Act). Every query ends with "United States",
as you approved:

1. `{query} political capital` (as today)
2. `{query} popular with Republicans`
3. `{query} unpopular with Republicans`
4. `{query} popular with Democrats`
5. `{query} unpopular with Democrats`

"Partisan fight Congress" and "unpopular with voters" are not crossed. The other four DAs (midterms,
economy, spending, federalism) are unchanged.

**The 20 new queries for the ac6 search** (politics DA, link, "national health insurance"), after
today's 12:

| Template | Resolution | Single payer | Medicare for All | Public option | Affordable Care Act |
|---|---|---|---|---|---|
| popular with Republicans | `national health insurance popular with Republicans United States` | `single payer popular with Republicans United States` | `Medicare for All popular with Republicans United States` | `public option popular with Republicans United States` | `Affordable Care Act popular with Republicans United States` |
| unpopular with Republicans | `national health insurance unpopular with Republicans United States` | `single payer unpopular with Republicans United States` | `Medicare for All unpopular with Republicans United States` | `public option unpopular with Republicans United States` | `Affordable Care Act unpopular with Republicans United States` |
| popular with Democrats | `national health insurance popular with Democrats United States` | `single payer popular with Democrats United States` | `Medicare for All popular with Democrats United States` | `public option popular with Democrats United States` | `Affordable Care Act popular with Democrats United States` |
| unpopular with Democrats | `national health insurance unpopular with Democrats United States` | `single payer unpopular with Democrats United States` | `Medicare for All unpopular with Democrats United States` | `public option unpopular with Democrats United States` | `Affordable Care Act unpopular with Democrats United States` |

**Two questions:**

1. Should the mechanism queries cross political capital and the four party-popularity templates, as
   above?
2. Should "partisan fight Congress" and "unpopular with voters" stay uncrossed? Crossing them too
   would add 10 queries (42 in all) and use up the room kept for the next task's agenda-item queries.

**For later, no answer needed:** the counts of teams reading each other aff are in section 4 of the
proposal, for when you want to add a mechanism.

## The coach's answers (2026-11-11)

Given by the operator in the session, to the sheet above and to two follow-up questions I asked
because the first answers could be read two ways:

1. **Which templates the mechanism queries cross:** political capital, partisan fight Congress, and
   the four party-popularity templates. "Unpopular with voters" is not crossed.
2. **The political capital wording:** the mechanism queries use a new wording, `{query} costs
   political capital Congress`, which **replaces** `{query} political capital` in the crossing. His
   seven reviewed queries on what the debater typed are unchanged.

**Where this differs from the PM's ruling, so the build waits for the PM again:**
- **Template 2 is crossed.** Ruling 2 said not 2 or 3; the coach says 2, not 3.
- **The crossing includes a template that does not exist yet.** Ruling 1 names templates by a DA
  entry's id and text, so the new wording needs a home. It must not change a reviewed template.
- **Today's 12 no longer stay the first 12.** Ruling 1 kept them as the prefix. Under the coach's
  answer the reviewed 7 stay first and in order, but today's five `… political capital United States`
  mechanism queries are replaced.
- **Less room for v1-e08-t23.** Ruling 4 kept 10 queries of room under 42; this leaves 5.

**Measured** with the same scripts: 7 reviewed + 6 crossed templates × 5 subjects = **37 queries**.
That is one OpenAlex request per page (the longest URL is 2,686 of 3,500), with room for a typed query
up to 141 characters. The only new BM25 term is `costs`. If the new wording went on the politics DA
entry instead, every politics link search would ask it: 38 on NHI (2,754), leaving 4, too few for
one agenda-item template on five subjects.

The PM's questions are under
[Questions for the PM after the coach's answers](#questions-for-the-pm-after-the-coachs-answers).

## Questions for the PM after the coach's answers

```text
v1-e08-t16, after the coach's answers (2026-11-11). Still no code.

The coach answered the review sheet (his follow-ups asked in the session, recorded in the report):
the politics DA's mechanism queries cross "{query} costs political capital Congress" (a NEW wording,
replacing "{query} political capital" in the crossing), "{query} partisan fight Congress" (template
2) and the four party-popularity templates (4 to 7); not "unpopular with voters" (3). His seven
reviewed queries stay as they are. That differs from your ruling in four ways, so I am holding the
build:

1. Template 2 is crossed (ruling 2 said not 2 or 3). Apply the coach's answer? (recommended: yes,
   ruling 5 applies his answers.)

2. Where the new wording lives.
   A. On the NHI preset, as a crossing-only template: a mechanism_link_templates entry with its own
      text and no DA template id (the loader checks it names only {query} and {topic}); recorded as
      politics-da/link/policy-2026-27-nhi-1/<subject>. No argument entry changes, the guard and its
      fixture are untouched, searches without --topic are unchanged; the preset is committed
      coach_reviewed in 1.6.0, since the coach wrote the wording (recommended).
   B. On the politics DA entry as an 8th link template, named by id like the others. The entry
      changes (he approves it, but the guard fixture coach_reviewed_1_5_0.yaml must be refreshed in
      this task), and every politics link search, with or without a topic, asks it too: 7 -> 8
      reviewed queries; 38 on NHI.

3. Today's 12 as the first 12 (ruling 1). Under the coach's answer the reviewed 7 stay first and in
   order, and today's five "... political capital United States" mechanism queries are replaced by
   "... costs political capital Congress United States". Amend ruling 1 to "the reviewed queries
   first, unchanged" (recommended), keeping template-major order in the listed order: the new
   wording, 2, 4, 5, 6, 7.

4. Size and room for v1-e08-t23. Measured: 7 + 6 x 5 = 37 queries, one OpenAlex request per page
   (2,686 of 3,500 URL characters; typed queries up to 141 characters fit); new BM25 term: "costs"
   only. Under 42 that leaves 5 queries (ruling 4 kept 10): one agenda-item template on five
   subjects. With 2B it is 38 and 4 left, too few for one. Accept 37 and 5 left, keeping 42?
   (recommended: yes.)

Unchanged from your ruling: id + text check for DA templates, the default for an unnamed DA, the
42 maximum and its loader rule and pin, Crossref option A with the guide note, today's four
mechanisms, provider-order nDCG in ac3.
```

## The PM's ruling after the coach's answers (2026-11-11)

Summarised; the build follows it.

1. **Template 2 is crossed:** the coach's answer stands over ruling 2. The politics DA's mechanism
   queries cross, in this order: the coach's new wording `{query} costs political capital Congress`,
   then link templates 2, 4, 5, 6 and 7. Template 3 is not crossed.
2. **Option A.** The new wording is a crossing-only entry in the NHI preset's
   `mechanism_link_templates`. It has its own text and no DA template id, it is checked on load to
   name only `{query}` and `{topic}`, and it is recorded as
   `politics-da/link/policy-2026-27-nhi-1/<subject>`.
   - No argument entry changes, and `coach_reviewed_1_5_0.yaml` and its guard are untouched.
   - Searches without `--topic` are unchanged.
   - The preset is committed `coach_reviewed` in 1.6.0, with the coach's answers recorded here.
3. **Ruling 1 is amended.** The coach's seven reviewed queries come first, unchanged and in order.
   The crossing follows, template-major in point 1's order. Today's five "political capital"
   mechanism queries become the new wording's.
4. **Accepted: 37 politics link queries,** one OpenAlex request per page (2,686 of 3,500 characters).
   `MAX_QUERIES_PER_SEARCH` stays 42, which leaves 5 queries for v1-e08-t23, and the report says so
   for t23.

Everything else in the first ruling stands:
- the id plus text check for DA templates, and the default for a DA the preset doesn't name;
- the cap's loader rule and its pin;
- Crossref option A, with the guide's note;
- today's four mechanisms;
- provider-order nDCG@10 beside the ranked figure in ac3.

The build runs its tests first and shows them failing, then mutants on the crossing order, the
crossing-only entry's check, the default template and the cap.

## Files changed

- **`config/argument_taxonomy.yaml`** (1.5.0 → 1.6.0): the NHI preset's `mechanism_link_templates`,
  which are the coach's crossing-only wording and the politics DA's templates 2, 4, 5, 6 and 7. The
  header and the preset comment are updated. No argument entry or family changed.
- **`packages/debate_core/src/debate_core/domain/argument_taxonomy.py`:**
  - `MechanismLinkTemplate` and `TopicPreset.mechanism_link_templates`;
  - `MAX_QUERIES_PER_SEARCH = 42` in place of `MAX_TOPIC_MECHANISMS = 4`, and `MECHANISM_NEED` moved
    here from the application layer, which still re-exports it;
  - the loader's crossing rules (`_check_mechanism_links`, `_crossed_template`) and the pair template
    count;
  - `ArgumentTaxonomy.mechanism_link_templates`, which resolves a DA's crossed templates and its
    default.
- **`packages/debate_core/src/debate_core/application/query_expansion.py`:** the crossing,
  template-major over the resolved templates; the module docstring.
- **`packages/debate_core/tests/application/test_query_expansion.py`:**
  - the tests [above](#what-the-tests-pin);
  - the version pins moved to 1.6.0;
  - the "five plan mechanisms" refusal removed, because five now load under the maximum.
- **`packages/debate_cli/tests/test_search_command.py`:** OpenAlex is asked the 37 queries; the Crossref
  public-pool footer reads `from 37 queries`, and its worked example is updated.
- **`packages/debate_cli/README.md`:** in the `search` section, which providers a long search leaves
  partial and that the footer names them (ruling 3), the GovInfo request count, and the ranking note
  (ruling 6).
- **`docs/guides/landscape-taxonomy.md`:** a preset's crossed templates, the text check and the
  42-query maximum.
- **`packages/debate_core/README.md`:** the two module rows.

## Deviations from the spec

1. **`packages/debate_cli/README.md` and `packages/debate_core/README.md` are outside
   `constraints.packages`.**
   - The PM's ruling 3 asks for "the search guide". The search command's user documentation is the
     CLI README's `debate-research search` section: no file under `docs/guides` covers search.
   - That section already described the 12-query search's Crossref and GovInfo figures, so it had to
     change anyway.
   - The core README gets its two one-line rows, as in v1-e08-t14.
2. **The coach's answers changed the ruled design**, and the PM ruled again before any code. That is
   recorded above, not a deviation in the build: the crossing-only wording, template 2, today's five
   political capital queries replaced, and 5 queries left for t23.

## Decisions and assumptions

1. **Measurements use the ac3 search's own settings**: `national health insurance`,
   `--max-results 200`, the link window. Added mechanisms come in section 4's order. A longer typed
   query or longer phrases mean longer URLs; section 3's second table gives the margin.
2. **Model queries are not counted in the maximum.** They are opt-in, and at most five. The headroom
   table shows what they cost.
3. **The cap counts a DA's link templates as written**, including any that name `{bill}` and may be
   skipped, so the count is the most that DA's link search can ask.
4. **A crossing-only template's id** is `<da>/link/<topic id>-<n>`, numbered among that DA's
   crossing-only entries on the preset. A DA template keeps its own id. Both are suffixed with the
   subject, as before.
5. **"The same template twice"** means the same DA and the same text, ignoring case and spacing. A
   crossing-only template that repeats one of the DA's own is refused too.
6. **The maximum applies to every DA,** including the four LD de-extinction DAs. On the NHI preset each
   gets the default crossing, as in v1-e08-t14, so the pin checks nine DAs.

## Operator follow-ups

**ac3: after the merge, on an installed dev build that carries it.** These are the same live calls as
v1-e08-t14's ac3:
- OpenAlex: one joined request per page, so two;
- the publisher feeds;
- Crossref, which will send only some of the 37 queries (ruling 3A);
- the Federal Register and GovInfo, 37 requests each.

They write only to dev's local data directory and three files on your Desktop, and print exit codes,
counts and template ids. No model is called. Each command takes under a minute, then the coach's
time.

**Operator command 1: check the installed build** (seconds)
Where: your Mac, any terminal
```bash
debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"])'
```
Success looks like the tag of the dev pre-release built after this merge. Command 2 proves the build
carries the change.

**Operator command 2: the Policy NHI search, politics DA link, repeated** (under a minute)
Where: the same terminal
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else cd "$HOME" && env DEBATE_ENV=dev debate-research --json search "national health insurance" --argument politics-da --need link --topic policy-2026-27-nhi --max-results 200 --save "$HOME/Desktop/search-policy-nhi-crossing.json" > /tmp/search-policy-nhi-crossing.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); r = e.get("error") or {}; d = e.get("data") or r.get("details") or {}; x = d.get("expansion") or {}; q = x.get("queries") or []; c = [y.get("template_id") or "" for y in q]; c = [t for t in c if t.count("/") == 3]; print("code", r.get("code"), "exit_code", r.get("exit_code")); print("status", d.get("status"), "results", len(d.get("results") or [])); print("taxonomy", x.get("taxonomy_version"), "queries", len(q), "warning", x.get("warning")); print("crossed", len(c), "templates", sorted({t.rsplit("/", 2)[1] for t in c})); print("providers", [(p["provider"], p["outcome"], p["results"]) for p in d.get("providers") or []])' /tmp/search-policy-nhi-crossing.json; fi
```
Success looks like:
- `exit 6`, with `code SEARCH_PARTIAL exit_code 6`, because Crossref can't reach all 37 queries
  (ruling 3A). `exit 0` and `code None` is fine too.
- `status PARTIAL` (or `COMPLETE`) and `results` above zero;
- `taxonomy 1.6.0 queries 37 warning None`;
- `crossed 30 templates ['2', '4', '5', '6', '7', 'policy-2026-27-nhi-1']`;
- `providers` naming `openalex` and `rss`, each with a count, and `crossref` if it is enabled.

**`queries 12` or `taxonomy 1.5.0` means the build predates this merge: stop there and don't make the
sheet.** Paste back the five lines. The titles stay in the saved file. I ran the summary line on an
invented envelope in the session scratchpad, and it printed the lines above.

**Operator command 3: the coach's blind sheet and its key** (seconds, then the coach's time)
Where: the same terminal, after command 2 saved its file. It is v1-e08-t14's block with new file
names. It writes two files to your Desktop, from the top 10 by the ranking and the top 10 by raw
provider order (up to 20 rows):
- **`labels-policy-nhi-crossing.csv`**, for the coach: `item`, `title`, `url` and an empty `relevant`,
  in title order with no rank;
- **`key-policy-nhi-crossing.csv`**, for the scoring session only: `item`, `rank`, `provider_order`.
```bash
python3 -I -c 'import csv, json, sys; d = json.load(open(sys.argv[1])); r = d["results"]; top = {x["rank"] for x in sorted(r, key=lambda x: x["rank"])[:10]} | {x["rank"] for x in sorted(r, key=lambda x: x["provider_order"])[:10]}; rows = sorted((x for x in r if x["rank"] in top), key=lambda x: ((x["title"] or "").casefold(), x["url"] or "")); s = csv.writer(open(sys.argv[2], "w", newline="")); k = csv.writer(open(sys.argv[3], "w", newline="")); s.writerow(["item", "title", "url", "relevant"]); k.writerow(["item", "rank", "provider_order"]); [(s.writerow([i, x["title"], x["url"], ""]), k.writerow([i, x["rank"], x["provider_order"]])) for i, x in enumerate(rows, start=1)]; print(sys.argv[2], len(rows), "rows; key", sys.argv[3])' "$HOME/Desktop/search-policy-nhi-crossing.json" "$HOME/Desktop/labels-policy-nhi-crossing.csv" "$HOME/Desktop/key-policy-nhi-crossing.csv"
```
Success looks like one line naming the labels file, with between 10 and 20 rows, and the key file.
- The coach gets the labels file only. He marks `relevant` `y` or `n` on each row, under his criterion
  of 2026-11-08: a politics DA link card is relevant only when it ties the plan's mechanism to the
  political fight over a specific bill.
- The key stays with you until he has answered.
- The filled labels file, the key and the saved search file then go to the PM. The PM records the
  relevant count, nDCG@10 for the ranking and **nDCG@10 in provider order beside it** (ruling 6),
  against v1-e08-t14's 6 of 19, 0.438 ranked and 0.746 in provider order.

## Follow-up work

- **Crossref under a large expanded search (E07): the PM files it (ruling 3).** Every search over
  about 18 to 28 queries is PARTIAL on Crossref's polite pool.
- **More mechanisms are the coach's later choice (ruling 4).** The team counts are in section 4. Each
  mechanism costs the politics DA's NHI link search 6 queries, and only 5 are left.
- **For v1-e08-t23:** 5 queries of room under 42, which is one agenda-item template on five subjects.
  The crossing takes its template set as one more entry list. Its one rule to relax is the
  crossing's `{query}`/`{topic}`-only check, for a template that names `{bill}`.
- **The four LD de-extinction DAs get the mechanism crossing on the NHI preset** (their first link
  template), as they did under v1-e08-t14. That is not new here, but an LD DA on a Policy topic's
  preset is probably not wanted. A format check on the fan-out is a small E08 item if the PM wants it.

## Final checks

The Goal stays `InProgress`, because ac3 is open. No `set-phase` was run.

| Check | Result |
|---|---|
| `uv run scripts/validate_specs.py` | `OK: 667 files, 41 epics, 604 tasks, 22 releases` |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 700 shell code blocks in 257 Markdown files (1 session reports changed since origin/dev)` |
| `uv run --frozen python scripts/check_links.py` | `OK: 3760 relative links and anchors in 642 Markdown files` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 69 indexed documents under docs/ have a description` |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
