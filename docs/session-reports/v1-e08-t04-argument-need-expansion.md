# Session report: v1-e08-t04-argument-need-expansion

| | |
|---|---|
| Task | `v1-e08-t04-argument-need-expansion` — Argument/need query expansion |
| Spec | [`plan_specs/v1/e08-research-workflows/t04-argument-need-expansion.yaml`](../../plan_specs/v1/e08-research-workflows/t04-argument-need-expansion.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t04-argument-need-expansion` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The federated search's expand stage now exists. A search that names an argument and a need
(`ExpansionRequest`, which t05's `--argument` and `--need` will fill) asks its providers the queries
the taxonomy gives that pair, each with its own date window. A search that names neither is unchanged.

- **The taxonomy.** `config/argument_taxonomy.yaml` covers 14 arguments × 5 needs, with 142 templates.
  It validates whole when it loads (`domain/argument_taxonomy.py`).
- **Expansion.** `QueryExpansionStage` in `application/query_expansion.py` does the expanding.
- **Model expansion.** It is off unless the request asks (`use_model`, t05's `--expand-llm`). It runs
  `search.expand@1.0.0` through the `StructuredOutputGuard` on `high_volume` with `fail_closed=False`.
  The answer must pass the schema and a query check. If it doesn't, the search uses the templates
  alone and records a warning.
- **Storage.** Each expansion is recorded on the stored `Search` (`Search.expansion`).

Criteria ac1 to ac3 pass, and every node criterion passes. **ac4, the coach's review, is NOT RUN, so
the Goal stays `InProgress`.** The review sheet for him is [below](#review-sheet-for-the-coach-ac4).

**Look first at:**
- the `Search` field decision (Decisions 1);
- the naming choice against the landscape taxonomy (Decisions 2);
- the five questions under "Questions for the PM", which I answered provisionally and carried on.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `taxonomy`: Argument/need taxonomy and templates | Done | `config/argument_taxonomy.yaml`, `domain/argument_taxonomy.py` (`ArgumentTaxonomy`, `Argument`, `Need`, `QueryTemplate`, `TopicPreset`). The loader and the typed errors live in `application/query_expansion.py`. |
| `template-expansion`: Deterministic expansion stage | Done | `expand_with_templates`, `provider_queries`, `QueryExpansionStage`. `SearchState.expansion` and `Search.expansion` record it. |
| `llm-expansion`: Optional LLM expansion | Done | `prompts/search/expand.md` (released, locked), `QueryExpansion` / `SuggestedQuery` schema, `model_query_problems` check, fallback. |
| `coach-review`: Coach taxonomy review | Not done | Needs the coach. The sheet is below. |

## Acceptance criteria

**Red run first.** I wrote the tests against a skeleton that refused nothing, and committed it as
`ff5407a`, "Query expansion tests, written first against a skeleton that refuses nothing". The
skeleton held all five of the PM's mutants at once:
- no taxonomy validation (so a pair with no template passed);
- an unknown argument or need taken as the first one;
- a template's own window ignored;
- model expansion on by default;
- no check beyond the schema, and no fallback.

```
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -q -p no:randomly packages/debate_core/tests/application/test_query_expansion.py --tb=line
```

That gave `40 failed, 24 passed in 0.29s`, with no collection error. The failures by their `E` line:

| Count | Failure | Tests |
|---|---|---|
| 12 | `DID NOT RAISE InvalidArgumentTaxonomy` | The broken-taxonomy cases |
| 5 | `DID NOT RAISE UnknownExpansionChoice` | Unknown argument, need, topic and variable; the before-any-provider test |
| 5 | `assert 1 == 2` | Model calls: no repair, because no query check ran |
| 4 | `ModelOutputError` uncaught | Schema-invalid answers: no fallback |
| 2 | `ProviderUnavailable`, `BudgetExceededError` uncaught | Unreachable model and budget refusal |
| 1 | `DID NOT RAISE ValidationError` | `variables` cannot set `query` |
| 1 | `router.calls == []` failed | Model expansion on by default |
| 10 | Wrong windows or warnings | Assertion failures, each on the window or warning value its test pins |

The 24 that passed are the committed-taxonomy content checks and the happy paths the skeleton already
did.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the taxonomy validates on load and every (argument, need) pair has at least one template; unknown values raise a typed error listing valid choices | PASS | `test_the_committed_taxonomy_validates_and_every_argument_need_pair_has_a_template` checks all 70 pairs of the committed file. `test_a_taxonomy_that_breaks_a_rule_is_refused_when_it_loads` has 16 cases, each refused with `InvalidArgumentTaxonomy` naming the rule: a need with no templates or an empty list, templates for an unknown need, an undeclared variable, a pair with no template that renders on query/topic alone, positional or format-spec fields, repeated ids or aliases, and so on. `test_the_taxonomy_refuses_an_unknown_choice_with_a_typed_error_listing_the_valid_ones` covers an unknown argument, need, topic and variable. Each raises `UnknownExpansionChoice` with `kind`, `value`, `choices` and the message `unknown argument 'heg'; the arguments are: test-da, test-framework`. An unknown argument fails the search before any provider is asked. |
| ac2: politics-da + link on "health insurance" expands to deterministic queries and a default since window; the expansion is recorded on the persisted Search | PASS | `test_template_expansion_of_politics_da_link_on_health_insurance` compares the whole `SearchExpansion` with one written by hand from the YAML. The queries are `health insurance political capital`, `… partisan fight Congress` and `… unpopular with voters`, each with `since` = now − 60 days, window `template`, ids `politics-da/link/1..3`. `test_template_expansion_is_asked_of_every_provider_and_recorded_on_the_stored_search` runs it through `FederatedSearchService` on the in-memory and SQLite repositories. The provider is asked exactly those three queries with those filters. The reloaded `Search.expansion` equals the expansion, and the stored `ProviderStatus.query`s match. Window rules: need default, template override, the search's own `since` kept, counted back from `until`, `any` = no `since`, each with its own test. |
| ac3: with --expand-llm and fake-router fixtures, validated extra queries are appended with rationale and prompt metadata; a malformed model output falls back to template queries with a warning | PASS | `test_model_expansion_appends_validated_queries_with_rationale_and_prompt_metadata` uses `FakeModelRouter` over the committed fixture `tests/fixtures/model_outputs/search.expand/45c3…json`, on both repositories. Two model queries are appended after the template queries, each with its rationale and the need's 14-day window. The fixture's third answer repeats a template query and is asked once. `Search.expansion.model` is `search.expand@1.0.0`, task class `high_volume`, provider `fake`. `test_model_expansion_of_a_malformed_output_falls_back_to_the_template_queries_with_a_warning` uses a fixture and its `model.repair` fixture, both carrying an `evidence` key the schema refuses. The queries are the templates' alone, the warning ends `(INVALID_MODEL_OUTPUT)`, and one WARNING is logged. Nine more malformed shapes are never asked (13 words, two lines, a link, a bare host, more than asked, over 120 characters, blank, no rationale, another shape). Off by default: `test_model_expansion_is_off_unless_the_request_asks_for_it` shows the router is not called. |
| ac4: Charlie reviews the taxonomy for Policy, LD and PF coverage and debate-term accuracy | NOT RUN | Needs the coach. The sheet is below. Every entry says `review: awaiting_coach_review` until he changes it. |
| Node `taxonomy`: `uv run pytest packages/debate_core/tests/application/test_query_expansion.py -k taxonomy` | PASS | Run under `hard_stop.py 115`: `29 passed in 2.12s` |
| Node `template-expansion`: `… -k template` | PASS | `26 passed in 2.11s` |
| Node `llm-expansion`: `uv run pytest packages/debate_core/tests/application/test_query_expansion.py` | PASS | `64 passed in 2.06s` |
| Node `coach-review`: Coach approves taxonomy | NOT RUN | As ac4. |

### Mutants

There are 25 runs over 24 distinct mutants. That is a few over the ~20 cap, because round two
re-ran the survivor and added the PM's literal mutant. Each run:
1. applied one mutant to the committed code;
2. ran the test file with `-n 0 -p no:randomly --tb=line` under `hard_stop.py 115`;
3. restored the file with `git checkout HEAD --`.

No test here uses Hypothesis, so agreement 8's database isolation does not apply. The scripts are in
the scratchpad and are not committed.

Round one, at `2186740`, had 22 mutants. 21 were caught and 1 survived.

| Mutant | Result | Caught by (reason) |
|---|---|---|
| **An unknown argument accepted** (taken as the first) | CAUGHT, 2 failed | unknown-choice `[argument]`, before-any-provider (DID NOT RAISE) |
| An unknown need accepted | CAUGHT, 1 | unknown-choice `[need]` |
| **A pair with no template passes validation** (empty-pair check off) | **SURVIVED** | See below |
| A pair whose every template needs an optional variable passes | CAUGHT, 1 | DID NOT RAISE |
| Templates for an unknown need pass | CAUGHT, 1 | DID NOT RAISE |
| An undeclared template variable passes | CAUGHT, 1 | Message assertion only; strengthened in round two |
| A format spec or positional field passes | CAUGHT, 1 | DID NOT RAISE |
| A repeated id or alias passes | CAUGHT, 1 | DID NOT RAISE |
| A landscape id unlike the id passes | CAUGHT, 1 | DID NOT RAISE |
| **LLM expansion on by default** | CAUGHT, 4 | off-by-default (`router.calls == []`), ac2 expansion equality, ac2 stored-search test |
| The stage ignores `use_model` and always asks the model | CAUGHT, 3 | off-by-default (`router.calls`), stored-search test |
| **A malformed model output used as a query** (no `check=`) | CAUGHT, 6 | Never-asks cases (`1 == 2` calls), repaired-answer test |
| Word limit not checked | CAUGHT, 1 | `[thirteen words]` |
| A link not refused | CAUGHT, 3 | `[a link]`, `[a bare host]`, repaired-answer |
| More queries than asked kept | CAUGHT, 1 | `[more than asked]` |
| A refused answer not caught (no fallback) | CAUGHT, 10 | Uncaught `ModelOutputError` |
| An unreachable model or budget refusal not caught | CAUGHT, 2 | Uncaught `ProviderUnavailable` / `BudgetExceededError` |
| **A template's window ignored** | CAUGHT, 8 | ac2 example, template-window, keeps-since, counts-from-until, stored-search |
| The search's own `since` replaced by the default | CAUGHT, 1 | keeps-the-search's-own-since |
| The window counts back from now, not `until` | CAUGHT, 1 | counts-back-from-until |
| An unknown variable accepted | CAUGHT, 1 | unknown-choice `[variable]` |
| A model query repeating a template asked twice | CAUGHT, 3 | Fixture test on both repositories, repeats-only test |

**The survivor.** The explicit "no template for this need" check was masked by the later rule that
every pair needs a template naming only `{query}` and `{topic}`, because an empty list has none of
those either. The two tests asserted only words both refusals share. I kept the check, because its
message is the right one ("argument test-da has no template for the need impact" against "every
template needs a variable a search may not have"). I pinned that message in the tests (`de006a5`),
and made the undeclared-variable case one that only its own check can refuse.

Round two, at `de006a5`:
- the empty-pair check off: CAUGHT, 2 failed, on the pinned message;
- the PM's literal mutant, both pair checks off: CAUGHT, 3 failed, DID NOT RAISE;
- an undeclared variable passes: CAUGHT, 1, now DID NOT RAISE.

### Checks before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `620 of 646 test files … chosen in 30.2 s from 16 changed files`. The cause is `domain/search.py`: it is imported by `debate_core.domain`, which the root conftest imports through `testing.fakes.clock_and_ids`. That is the whole selection, about six minutes, so under agreement 10 it is left to the pull request's `ci` check, with no hand-off. |
| Always-run list (`tests/architecture tests/specs` + the CLI's `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`), `-n auto -m "not slow and not live"`, under `hard_stop.py 115` | `375 passed in 23.30s` |
| `packages/debate_core/tests/domain`, `integrations/local`, `integrations/models`, the SearchRepository contract, `tests/scripts/test_lock_prompts.py` | `1991 passed in 8.22s` (schemas, round trip, SQLite repos, prompt lock and registry, the fixture redaction scan) |
| `packages/debate_core/tests/application` (the changed modules' test directory) | `4972 passed in 111.03s`, inside the 115-second bound |
| `tests/config`, `tests/scripts/test_stamp_build.py`, `test_federated_search.py` | `146 passed in 2.89s` |
| `uv run --frozen ruff check .` / `ruff format --check .` | `All checks passed!` / `1790 files already formatted` |
| `uv run --frozen pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` (23 s) |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 70 … handlers within 25 statements` |
| `scripts/export_schemas.py --check` / `scripts/lock_prompts.py --check` | `OK: 10 schemas … up to date` / exit 0 |
| `uv run scripts/validate_specs.py`, docs checks | See [Final checks](#final-checks) |

## Files changed

- **`config/argument_taxonomy.yaml`** (new): the taxonomy. It has 3 variables (`query`, `topic`,
  `bill`), 5 needs with their default windows, 14 arguments with 142 templates, and one topic preset.
- **`packages/debate_core/src/debate_core/domain/argument_taxonomy.py`** (new): the taxonomy's models
  and whole-file validation, and alias lookup that forgives case, spaces and underscores. It does no
  I/O.
- **`packages/debate_core/src/debate_core/domain/search.py`**: `SearchExpansion`, `ExpandedQuery`,
  `QueryOrigin`, `WindowSource`, and `Search.expansion`, which is optional. A search without an
  expansion serializes exactly as before (`exclude_if`).
- **`packages/debate_core/schemas/search.schema.json`**: regenerated with `scripts/export_schemas.py`.
- **`packages/debate_core/src/debate_core/application/query_expansion.py`** (new):
  - the loader and the typed errors (`InvalidArgumentTaxonomy`, `UnknownExpansionChoice`);
  - template expansion;
  - the `QueryExpansion` schema and its query check;
  - `QueryExpansionStage`.
- **`application/federated_search_types.py`, `application/federated_search.py`**: `ExpansionRequest`,
  `SearchRequest.expansion`, `SearchState.expansion`. The service stores the state's expansion on the
  `Search`. The docstrings name the new stage.
- **`prompts/search/expand.md`, `prompts/prompts.lock.json`**: `search.expand@1.0.0`, released and
  locked with `scripts/lock_prompts.py`.
- **`tests/fixtures/model_outputs/search.expand/` (2) and `model.repair/` (1)**: hand-written answers,
  filed with `FixtureDirectory` under the stage's real requests. One answers in the schema. The other,
  and its repair, carry an `evidence` key the schema refuses. The inputs are invented ("community
  clinic funding", "rural hospital staffing") and the synthetic taxonomy is the test's own.
- **`packages/debate_core/tests/application/test_query_expansion.py`** (new): 64 tests.
- **`packages/debate_core/README.md`**: rows for the new modules.

## Deviations from the spec

1. **Files outside `constraints.packages`.** Expected, per the PM's note:
   - `domain/argument_taxonomy.py`, a node output;
   - the tests under `packages/debate_core/tests`.

   Also outside the list, and following from the decisions below:
   - `domain/search.py` and its committed schema (Decisions 1);
   - the prompt lock entry and the model fixtures under `tests/fixtures/model_outputs/`;
   - two README rows.
2. **The fallback is wider than `ModelOutputError`.** The spec says model expansion falls back on
   `ModelOutputError`. It also falls back on `ProviderError` (unreachable, throttled, refused) and on
   `BudgetExceededError`, because the forbidden list says model expansion is never "required for
   search to work". A prompt-registration mistake (`PromptMismatchError`, unknown prompt) still
   raises: that is a bug, not a model failure.
3. **One validation rule the spec does not name.** Every (argument, need) pair must have at least one
   template that names only `{query}` and `{topic}`. Those are the variables every search has, so
   every pair always expands to at least one query. A template naming `{bill}` is skipped, and
   recorded as skipped, when the request gives no bill.
4. **The spec's example templates are reworded.** The example was politics-da + uniqueness →
   "{topic} midterms polling", "{bill} votes Senate".
   - The midterms polling template went to **midterms-da**. That DA is the landscape's own and is
     where the template means something.
   - politics-da's uniqueness templates are "{query} vote count Senate", "{query} likely to pass
     Congress" and "{bill} whip count".
   - The midterms are on 3 November, so a politics-DA template naming them would be stale within days
     (Questions 3).
5. **No smoke check.** The task adds no user-facing surface: there is no CLI until t05, so there is
   nothing for `validate-dev` to run.

## Decisions and assumptions

1. **`Search` gets an `expansion` field.** This answers the amendment's question. Each provider
   call's `ProviderStatus.query` holds the exact query and filters, but not:
   - which argument and need, after aliases were resolved;
   - which template each query came from;
   - whether its `since` came from the need, the template or the person's own `--since`;
   - which templates were skipped;
   - a model query's rationale and the prompt metadata (ac3 requires both);
   - the fallback warning.

   A search that reached no provider (none enabled, all not configured) has no `ProviderStatus` to
   read even the queries from. The field is optional and left out of the JSON when it is empty, so
   older documents and searches without expansion are unchanged.
2. **Ids are shared with the landscape where the argument exists there.** I gave the shared names
   rather than mapping different ones:
   - `politics-da` and `economy-da` (the generic and NHI landscape ids);
   - `midterms-da`, `federalism-da`, `economy-advantage`, `pandemics-advantage`,
     `inequality-advantage`.

   Each of these also sets `landscape_id` to the same id. The loader refuses a `landscape_id` that
   differs from the entry's id. A test reads the landscape files and checks both directions: every
   shared id is marked, and no mapping dangles. The code never reads the landscape files. The spec's
   spellings resolve as aliases:
   - `econ-da` → `economy-da`;
   - `ptx` → `politics-da`;
   - `elections` → `midterms-da`.

   `spending-da`, `heg`, `util`, `deontology`, `structural-violence`, `theory` and `cost-benefit` have
   no landscape counterpart. The LD `theory` is deliberately not mapped to the Policy-only
   `generic-theory`.
3. **Topic values come from what is committed.** The one preset, `policy-2026-27-nhi`, sets `topic`
   to "national health insurance". A test checks that this appears word for word in `topics.yaml`'s
   resolution. LD's de-extinction preset waits for v1-e32-t06's resolution. Until then `{topic}` comes
   from the request (`ExpansionRequest.variables`), and otherwise falls back to the query. A test
   checks that no template holds a four-digit number, and the file comment says what changes week to
   week is a variable.
4. **Terminology.** No label or template says "harm" or "harms" (a test checks this), and none says
   inherency. Needs are labelled Uniqueness, Link, Internal link, Impact and Answers (AT), with
   aliases `uq`/`u`, `l`, `il`, `i`/`impacts`, `at`/`a2`/`answers-to`. Lookups ignore case, and
   accept spaces or underscores for hyphens ("Politics DA", "internal link").
5. **Windows.** Defaults:

   | Need | Default window |
   |---|---|
   | Uniqueness | 14 days |
   | Link | 180 days |
   | Internal link | 365 days |
   | Impact | any age |
   | Answers | 365 days |

   politics-da and midterms-da set 7 days on their uniqueness templates and 60 days on their links.
   The person's own `--since` always wins and is recorded as `request`. With only `--until` set, the
   window counts back from it, so an "as of" search keeps its window.
6. **Model expansion.**
   - `ExpansionRequest.use_model` defaults to False. t05 maps `--expand-llm` onto it.
   - The stage takes an optional guard. Without one, a request for model expansion gets the templates
     and the warning "model expansion is not configured".
   - The model is asked for at most 3 queries (the stage takes 1 to 5; the schema holds 5).
   - Each query is one printable line of at most 12 words and 120 characters, with no link. The
     rationale is at most 300 characters.
   - A suggestion that repeats a template query (case and spacing ignored) is dropped. If every one is
     dropped, no model metadata is recorded and a warning says so.
   - The prompt asks for query strings and a reason in the model's own words. It forbids evidence,
     quotations and invented bill names.
7. **CPs and Ks are left out.** The five needs fit DAs, advantages and framing, but a counterplan's
   research is solvency and net benefit, and a K's is link, alternative and framework. Writing the
   states CP under "uniqueness" would teach the wrong terms. Questions 4.

## Questions for the PM

Each one is reversible. I chose the option marked as recommended and carried on.

```text
v1-e08-t04 questions (session of 2026-11-01). Each was decided provisionally; the recommended option is what the branch does.

1. Search.expansion (the amendment's question).
   A. Keep the optional Search.expansion field (recommended): argument, need, template ids, window
      source, skipped templates, model rationale, prompt metadata and the fallback warning are not
      recoverable from ProviderStatus.query, and ac3 asks for rationale and metadata to be kept.
   B. Drop it and rely on ProviderStatus.query: loses all of the above, and a search that reached no
      provider loses its queries too.

2. Ids against the landscape taxonomy.
   A. Same ids where the landscape has the argument, landscape_id set to it, spec spellings as aliases
      (recommended): one name per argument across landscape and search.
   B. Spec spellings as ids (econ-da) with an explicit landscape_id map: two names for one argument.

3. midterms-da after 3 November, and "ptx/elections".
   A. Keep midterms-da (the landscape's id) with elections and elections-da as aliases, ptx as an alias
      of politics-da, and let the coach rename it after the election (recommended).
   B. Rename now to elections-da: the landscape would still say midterms-da.

4. Counterplans and kritiks.
   A. Leave them out until the needs list has their parts (solvency, net benefit, alternative,
      framework): a follow-up task, with the coach's terms (recommended).
   B. Force them into the five needs now.

5. LD de-extinction arguments.
   A. Generic LD framing only (util, deontology, structural violence, theory) until v1-e32-t06 commits
      the resolution; the coach adds topic arguments then (recommended).
   B. Write de-extinction arguments now from the topic's name alone: would mean topic wording not taken
      from a committed resolution.
```

## Operator follow-ups

None. The affected set is the whole selection, so it is left to the pull request's `ci` check
(agreement 10), not handed over.

ac4 is the coach's. He reads the sheet below and, for each entry he accepts, changes `review:
awaiting_coach_review` to `coach_reviewed` in `config/argument_taxonomy.yaml`. He corrects any
template there, raises `taxonomy_version`, and approves in the PR. A changed template that a test
quotes must be updated in that test too: only ac2's politics-da link example and the
committed-taxonomy checks read the file.

## Follow-up work

- **v1-e08-t05 (search command):**
  - map `--argument`, `--need`, `--topic` (topic preset id), `--var bill=…` and `--expand-llm` onto
    `ExpansionRequest`;
  - build `QueryExpansionStage` with `load_argument_taxonomy(ARGUMENT_TAXONOMY_PATH)`, and a guard
    only when `--expand-llm` is given;
  - wire it into the container;
  - decide whether `UnknownExpansionChoice` exits as a usage error (2) rather than the default domain
    failure (1);
  - print `expansion.warning`.
- **v1-e32-t06 (LD de-extinction taxonomy):** add the LD topic preset to `config/argument_taxonomy.yaml`
  from its committed resolution, and the coach's topic arguments.
- **A needs list for counterplans and kritiks** (Questions 4), with the coach's terms.
- **v1-e08-t07 (daily presets):** the topic preset could name its `config/feeds/` topic
  (`health-insurance`, `politics`). That is t07's to decide.

## Review sheet for the coach (ac4)

One row per argument and need, rendered from `config/argument_taxonomy.yaml` 1.0.0. In each template:
- `{query}` is what the student typed;
- `{topic}` is the topic, which is "national health insurance" for the NHI preset and otherwise the
  query;
- `{bill}` is the agenda item the student names; a template with `{bill}` is skipped when they
  don't.

A window marked "(own)" is the template's; the others are the need's default. The notes the file
carries for his review:
- midterms-da: rename after 3 November?
- spending-da: keep it, or fold it into debt-da?
- heg: no NHI landscape position.
- theory: not mapped to the Policy-only generic-theory.
- structural-violence and cost-benefit: listed for PF, which has no teams this season. Generic framing
  only.

| Argument (aliases) | Format | Need | Templates, each with its window |
|---|---|---|---|
| `politics-da` Politics DA (ptx, politics, ptx-da) | Policy | Uniqueness | `{query} vote count Senate` · 7 d (own)<br>`{query} likely to pass Congress` · 7 d (own)<br>`{bill} whip count` · 7 d (own) |
|  |  | Link | `{query} political capital` · 60 d (own)<br>`{query} partisan fight Congress` · 60 d (own)<br>`{query} unpopular with voters` · 60 d (own) |
|  |  | Internal link | `political capital key to the president's agenda {query}` · 365 d<br>`{bill} needs presidential political capital` · 365 d |
|  |  | Impact | `{query} fails consequences` · any age<br>`{bill} fails impact` · any age |
|  |  | Answers (AT) | `winners win political capital {query}` · 365 d<br>`political capital theory wrong {query}` · 365 d |
| `midterms-da` Midterms DA (elections, elections-da) | Policy | Uniqueness | `{topic} midterms polling` · 7 d (own)<br>`{query} election forecast` · 7 d (own) |
|  |  | Link | `{query} voters election impact` · 60 d (own)<br>`{topic} issue swing voters` · 60 d (own) |
|  |  | Internal link | `{query} turnout swing voters` · 365 d<br>`{query} control of Congress` · 365 d |
|  |  | Impact | `{query} control of Congress consequences` · any age<br>`divided government consequences` · any age |
|  |  | Answers (AT) | `{query} will not affect elections` · 365 d<br>`{query} low issue salience voters` · 365 d |
| `economy-da` Economy DA (econ-da, econ, economy) | Policy | Uniqueness | `{query} economic growth forecast` · 14 d<br>`{query} recession risk` · 14 d |
|  |  | Link | `{query} cost economy` · 180 d<br>`{topic} economic impact` · 180 d |
|  |  | Internal link | `{query} business investment` · 365 d<br>`{query} consumer spending` · 365 d |
|  |  | Impact | `economic decline causes war` · any age<br>`{query} economic decline impact` · any age |
|  |  | Answers (AT) | `{query} economy resilient` · 365 d<br>`economic decline does not cause war` · 365 d |
| `spending-da` Spending DA (spending, fiscal-da) | Policy | Uniqueness | `{query} federal spending debate Congress` · 14 d<br>`Congress spending restraint {query}` · 14 d |
|  |  | Link | `{query} cost federal budget` · 180 d<br>`{query} CBO cost estimate` · 180 d |
|  |  | Internal link | `federal deficit raises interest rates` · 365 d<br>`{query} deficit spending tradeoff` · 365 d |
|  |  | Impact | `national debt crisis consequences` · any age<br>`{query} deficit impact` · any age |
|  |  | Answers (AT) | `{query} pays for itself savings` · 365 d<br>`deficit spending sustainable` · 365 d |
| `federalism-da` Federalism DA (federalism) | Policy | Uniqueness | `states lead {query} policy` · 14 d<br>`{query} state innovation federalism` · 14 d |
|  |  | Link | `{query} federal preemption states` · 180 d<br>`{query} federal government overrides state authority` · 180 d |
|  |  | Internal link | `federal preemption spills over federalism` · 365 d<br>`{query} federalism precedent other policy areas` · 365 d |
|  |  | Impact | `federalism laboratories of democracy` · any age<br>`federalism key to democracy {query}` · any age |
|  |  | Answers (AT) | `{query} federal action consistent with federalism` · 365 d<br>`federalism resilient to preemption` · 365 d |
| `heg` Heg (hegemony, heg-advantage) | Policy | Uniqueness | `US global leadership decline {query}` · 14 d<br>`US military readiness {query}` · 14 d |
|  |  | Link | `{query} US military readiness` · 180 d<br>`{query} US global leadership` · 180 d |
|  |  | Internal link | `US economic strength key to hegemony` · 365 d<br>`{query} US soft power` · 365 d |
|  |  | Impact | `US hegemony prevents great power war` · any age<br>`US primacy deters conflict` · any age |
|  |  | Answers (AT) | `US hegemony unsustainable` · 365 d<br>`{query} heg resilient` · 365 d |
| `economy-advantage` Economy advantage (econ-advantage, econ-adv) | Policy | Uniqueness | `{query} costs hurting the economy` · 14 d<br>`{topic} costs workers employers` · 14 d |
|  |  | Link | `{topic} boosts economic growth` · 180 d<br>`{query} economic benefits` · 180 d |
|  |  | Internal link | `{query} labor market mobility` · 365 d<br>`{query} productivity` · 365 d |
|  |  | Impact | `economic growth prevents conflict` · any age<br>`{query} economic growth impact` · any age |
|  |  | Answers (AT) | `{topic} hurts the economy` · 365 d<br>`{query} economic costs` · 365 d |
| `pandemics-advantage` Pandemics advantage (pandemics, pandemic-advantage) | Policy | Uniqueness | `{query} pandemic preparedness gaps` · 14 d<br>`pandemic risk rising {query}` · 14 d |
|  |  | Link | `{topic} pandemic response` · 180 d<br>`{query} uninsured delay care disease spread` · 180 d |
|  |  | Internal link | `uninsured avoid care disease spread` · 365 d<br>`{query} disease surveillance` · 365 d |
|  |  | Impact | `pandemic extinction risk` · any age<br>`{query} pandemic deaths` · any age |
|  |  | Answers (AT) | `{topic} does not solve pandemics` · 365 d<br>`pandemic extinction unlikely` · 365 d |
| `inequality-advantage` Inequality advantage (inequality) | Policy | Uniqueness | `{query} health disparities` · 14 d<br>`{query} inequality rising` · 14 d |
|  |  | Link | `{topic} reduces inequality` · 180 d<br>`{query} closes coverage gaps` · 180 d |
|  |  | Internal link | `health inequality life expectancy gap` · 365 d<br>`{query} health inequality` · 365 d |
|  |  | Impact | `inequality undermines democracy` · any age<br>`{query} inequality structural violence` · any age |
|  |  | Answers (AT) | `{topic} fails to reduce disparities` · 365 d<br>`{query} inequality persists` · 365 d |
| `util` Util (utilitarianism, consequentialism) | LD | Uniqueness | `{topic} current outcomes` · 14 d<br>`{query} status quo trends` · 14 d |
|  |  | Link | `{topic} consequences` · 180 d<br>`{query} costs and benefits` · 180 d |
|  |  | Internal link | `{query} aggregate welfare` · 365 d<br>`{topic} long term effects` · 365 d |
|  |  | Impact | `utilitarianism justification ethics` · any age<br>`consequentialism defense moral theory` · any age |
|  |  | Answers (AT) | `utilitarianism critique aggregation` · 365 d<br>`{query} consequences unpredictable` · 365 d |
| `deontology` Deontology (kant, kantianism, deont) | LD | Uniqueness | `{topic} rights now` · 14 d<br>`{query} consent autonomy` · 14 d |
|  |  | Link | `{topic} treats people as means` · 180 d<br>`{query} rights duties ethics` · 180 d |
|  |  | Internal link | `{query} moral duty` · 365 d<br>`{topic} autonomy dignity` · 365 d |
|  |  | Impact | `Kantian ethics justification` · any age<br>`categorical imperative defense` · any age |
|  |  | Answers (AT) | `deontology ignores consequences critique` · 365 d<br>`Kantian ethics fails` · 365 d |
| `structural-violence` Structural violence (sv) | LD, PF | Uniqueness | `{query} structural inequality` · 14 d<br>`{topic} marginalized communities` · 14 d |
|  |  | Link | `{topic} effect on marginalized communities` · 180 d<br>`{query} disproportionate impact` · 180 d |
|  |  | Internal link | `{query} structural violence` · 365 d<br>`structural inequality causes premature death` · 365 d |
|  |  | Impact | `structural violence framework prioritize` · any age<br>`structural violence outweighs extinction` · any age |
|  |  | Answers (AT) | `structural violence framing critique` · 365 d<br>`extinction outweighs structural violence` · 365 d |
| `theory` Theory (ld-theory) | LD | Uniqueness | `{query} debate norms` · 14 d<br>`{topic} debate interpretation` · 14 d |
|  |  | Link | `{query} interpretation abuse debate` · 180 d<br>`{query} debate ground` · 180 d |
|  |  | Internal link | `debate education portable skills` · 365 d<br>`{query} debate fairness` · 365 d |
|  |  | Impact | `debate fairness intrinsic value` · any age<br>`debate education value` · any age |
|  |  | Answers (AT) | `reasonability competing interpretations debate` · 365 d<br>`{query} theory frivolous` · 365 d |
| `cost-benefit` Cost-benefit (cba, cost-benefit-analysis) | PF | Uniqueness | `{topic} current costs benefits` · 14 d<br>`{query} status quo` · 14 d |
|  |  | Link | `{query} costs benefits evidence` · 180 d<br>`{topic} effects` · 180 d |
|  |  | Internal link | `{query} probability magnitude` · 365 d<br>`{topic} timeframe effects` · 365 d |
|  |  | Impact | `cost benefit analysis weighing` · any age<br>`{query} cost benefit analysis` · any age |
|  |  | Answers (AT) | `cost benefit analysis critique` · 365 d<br>`{query} benefits overstated` · 365 d |

## Final checks

The task Goal stays `InProgress`, because ac4 is open. No `set-phase` was run.

| Check | Result |
|---|---|
| `uv run scripts/validate_specs.py` | `OK: 569 files, 41 epics, 506 tasks, 22 releases` |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 648 shell code blocks in 209 Markdown files (1 session reports changed since origin/dev)` |
| `uv run --frozen python scripts/check_links.py` | `OK: 3361 relative links and anchors in 533 Markdown files` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 64 indexed documents under docs/ have a description` |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
