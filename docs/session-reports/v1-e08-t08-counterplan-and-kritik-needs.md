# Session report: v1-e08-t08-counterplan-and-kritik-needs

| | |
|---|---|
| Task | `v1-e08-t08-counterplan-and-kritik-needs` — Counterplans and kritiks get the research needs their arguments have |
| Spec | [`plan_specs/v1/e08-research-workflows/t08-counterplan-and-kritik-needs.yaml`](../../plan_specs/v1/e08-research-workflows/t08-counterplan-and-kritik-needs.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t08-counterplan-and-kritik-needs` |
| Session status | COMPLETE: the Goal stays `InProgress` for ac1's coach review (operator) |

## Summary

The argument taxonomy now gives each family of arguments its own needs (taxonomy 1.2.0, file schema
2). DAs and advantages keep the five needs; framing has "framework good" and answers with no window;
theory has interpretation, standards, voters and answers; counterplans have solvency, net benefit,
competition and answers; kritiks have link, impact, alternative, framework and answers. An argument's
kind chooses its family. The loader refuses an argument whose templates are not exactly its family's
needs, and `search --need` with a need from outside the argument's family exits 2, listing that
argument's needs. Util, deontology, structural violence and cost-benefit are reshaped into framing
using the coach's content, and theory gets its own family. Five generic counterplans and generic.yaml's
ten named kritiks are added under the landscape's ids. The DAs and advantages the coach reviewed are
byte-identical to 1.1.0, and a frozen copy of his reviewed file now guards them.
**ac1's coach review is NOT RUN (operator), so the Goal stays `InProgress`.** The review sheet is
[below](#review-sheet-for-the-coach). The PM should look first at the shape (decisions 1 and 2) and
at which counterplans and kritiks are in (question 1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `counterplan-and-kritik-needs`: CP and K needs | Done | Tests written first and run red against a refuse-nothing skeleton, then the shape, the rules and the 1.2.0 content. 17 mutants in 20 runs (two redone after their first attempts failed by refusing to load), all caught at assertions. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 (part): the taxonomy validates needs per family, every counterplan and kritik has a template for each need of its family, and the added ids match the landscape's, by tests shown failing first | PASS | Red: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -p no:randomly -n 0 -q packages/debate_core/tests/application/test_query_expansion.py` on the skeleton (commit `3b02fd3` with the family rules switched off and needs looked up in every family) → `28 failed, 61 passed`, every failure at an assertion (`DID NOT RAISE InvalidArgumentTaxonomy`, mismatched families, `DID NOT RAISE UnknownExpansionChoice`); the CLI's new tests on the same skeleton → `7 failed, 1 passed` (util with `--need uniqueness` searched and exited 0). Green: the same files plus `tests/smoke/test_search_smoke.py` → `139 passed`. |
| ac1 (part): the coach reviews them (operator) | NOT RUN | The coach's. The sheet is below. Every added or reshaped entry says `review: awaiting_coach_review`. |
| Node `counterplan-and-kritik-needs`: CP and K needs tests pass (`uv run pytest packages/debate_core/tests/application/test_query_expansion.py -k taxonomy`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/application/test_query_expansion.py -k taxonomy` → `55 passed in 2.35s` |

Before the report:

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 254 of 660 test files from 11 changed files. The CLI command edit reaches the whole CLI through the app. |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | Stopped at its 115-second limit (exit 124), with 11 workers on 6,572 items and the machine at a load average near 20 (other sessions). It reached 15% with no failure. **Over two minutes, so the affected set is left to the pull request's `ci` check (agreement 10), not handed over.** |
| Changed areas and the always-run list: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -m "not slow and not live" packages/debate_core/tests/application/test_query_expansion.py packages/debate_core/tests/application/test_federated_search.py packages/debate_cli/tests/test_search_command.py tests/smoke/test_search_smoke.py tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py` | `557 passed in 27.38s`. Every test file that imports the taxonomy or the expansion module is in it. |
| `ruff format --check .` / `ruff check .` | `1829 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core packages/debate_cli tests/smoke` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 72 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 578 files, 41 epics, 515 tasks, 22 releases` |

### Mutants

Each mutant was applied to the committed tree, run against `test_query_expansion.py` and
`test_search_command.py` (bounded with `scripts/hard_stop.py 115`), and restored with
`git checkout HEAD --`. No property test covers this code, so agreement 8's Hypothesis database does
not apply. The four the PM named come first.

| Mutant | Caught by |
|---|---|
| A framework given a uniqueness need: framing gets `uniqueness`, and each framework a uniqueness template so the file still loads | 5 failures: the committed families test, the framing-window test, and the util and deontology refusals |
| A family's pair left empty but passing validation: `_check_templates` skips an empty template list | 4 failures: `a need with no templates`, `a need with an empty template list`, `a framing pair left empty`, `a framing pair left out` (`DID NOT RAISE`) |
| A need from another family accepted by search: `_resolve` looks the need up in every family | 14 failures in core and CLI, including the CLI's `util --need uniqueness` exits 2 |
| A reviewed DA template changed: politics-da's `{query} vote count Senate` becomes `House` | `test_the_committed_taxonomy_keeps_every_coach_reviewed_entry_as_he_reviewed_it` (`AssertionError: politics-da`) |
| A reviewed template's window changed (politics-da uniqueness 30 → 60 days) | the same test |
| The DA family's uniqueness default changed (365 → 180) | the same test, on the needs |
| Framing answers given a five-year window | the framing-window test and the framing expansion test |
| A kind no family takes falls back to the first family | `a kind no family takes` |
| Two families may take one kind | `a kind in two families` |
| One name may mean two needs | `one name meaning two needs` |
| Two needs of a family may share a name | `two needs of a family with one id` (`DID NOT RAISE`), a case added after the first run of this mutant was caught only through the cross-family name rule's message |
| Templates for a need outside the family accepted | `templates for a need the file does not list`, `a framework given a uniqueness need` |
| The refusal lists every family's needs | 14 failures, core and CLI |
| cap-k removed | 6 failures: the added-ids test, spellings, the cap-k refusal and expansion, two CLI cases (rerun: the first attempt renamed it, which broke the landscape-id rule and failed by refusing to load. That is a crash, not a catch, so it was redone) |
| federalism-cp added | the added-ids test and the shared-landscape-ids test (rerun for the same reason) |
| states-cp's `landscape_id` removed | the two landscape-id tests |
| heg marked `awaiting_coach_review` | the coach-reviewed test (`AssertionError: heg`) |

## Files changed

- `config/argument_taxonomy.yaml`: schema 2, taxonomy 1.2.0. `families` replaces `needs`. The
  framing and theory entries are reshaped, and five counterplans and ten kritiks are added. The DA and
  advantage entries and the topics section are byte-identical to 1.1.0 (checked with `diff` against
  `5e6abee`).
- `packages/debate_core/src/debate_core/domain/argument_taxonomy.py`: `NeedFamily`,
  `ArgumentKind.COUNTERPLAN` (`cp`) and `KRITIK` (`k`), the family rules, `family_of` and
  `find_need(argument, name)`. The taxonomy-wide `need()` is gone; a family has one.
- `packages/debate_core/src/debate_core/application/query_expansion.py`: the need is resolved within
  the argument's family. `UnknownExpansionChoice` takes the argument and then says
  `util has no need 'uniqueness'; its needs are: framework-good, answers`.
- `packages/debate_core/tests/application/test_query_expansion.py`: SMALL_TAXONOMY reshaped into two
  families (test-da's needs are word for word as before, so no model fixture key moved). Adds the
  committed-file tests, eleven family rules in the refusal table, and the refusals and expansions per
  family. The ac2 test pins taxonomy `1.2.0`; its queries and windows are unchanged.
- `packages/debate_core/tests/fixtures/argument_taxonomy/coach_reviewed_1_1_0.yaml`: the coach-reviewed
  1.1.0 file, copied byte for byte from `5e6abee` below a header. It is the coach's record, not output
  of the code.
- `packages/debate_cli/tests/test_search_command.py`: the command-level tests. A need outside the
  family exits 2 and lists that argument's needs (five families). Each family's own need expands,
  with or without a window, before any provider is asked.
- `packages/debate_cli/src/debate_cli/commands/search.py`: the `--need` help text, which listed only
  the DA needs.
- `tests/smoke/test_search_smoke.py`: `util --need uniqueness` exits 2 and lists `framework-good`.
- `packages/debate_core/README.md`: the module row mentions families.

## Deviations from the spec

1. **Files outside `constraints.packages`.** The PM's context asks for command-level tests, and
   working agreement 5 asks for a smoke check when a user-facing surface changes. Neither path is in
   the spec's packages, and the spec has no smoke node. Added:
   `packages/debate_cli/tests/test_search_command.py`, `tests/smoke/test_search_smoke.py`, and the
   one-line `--need` help text in `debate_cli/commands/search.py`, which would otherwise tell a
   framework's user to pick uniqueness. The PM may want the spec's packages to name them.
2. **The file's `schema_version` is raised from 1 to 2.** The shape changed (`families` replaces
   `needs`), and the loader now refuses a schema 1 file, naming the field. Only the taxonomy file and
   its loader carry the number; a stored search records `taxonomy_version`, not the schema.
3. **The ac2 test's `taxonomy_version` pin moved from 1.1.0 to 1.2.0.** The PM asked both for 1.2.0
   and for the test to pass as it is. Its seven queries, their window and the stored-search test are
   untouched.
4. **I ran one `git fetch origin dev`** (read-only) to check that the spec had not been amended on
   dev. It had not. My standing rule is to hand even a read-only network call to the operator; I
   should have used the local `origin/dev`.

## Decisions and assumptions

1. **Needs are defined per family, not in one list that families pick from.** A need's description
   and window differ by family: framing's answers have no window, while a DA's have five years, and a
   kritik's link is not a DA's link. The expand prompt sends the need's own label and description.
   One rule keeps the names consistent: a name means the same need in every family that has it (`at`
   is always answers, `link` always link).
2. **An argument's kind chooses its family; arguments do not name a family.** Each family lists the
   kinds it takes (`kinds: [da, advantage]`). An argument naming its family as well as its kind could
   disagree with itself (`kind: cp`, `family: kritik`). With one source there is nothing to disagree.
   The loader refuses a kind that two families take, and an argument whose kind no family takes.
3. **New kinds `cp` and `k`** are the landscape's own kind words, so a test checks each added
   argument's kind against the landscape position with its id.
4. **Which counterplans and kritiks.** "Generic" is read as not about the topic's mechanism:
   - Counterplans: process-cp (generic.yaml), plus states-cp, courts-cp, delay-cp and advantage-cp
     (they are in the NHI file but are topic-independent).
   - Kritiks: generic.yaml's ten named kritiks.
   - Left out: generic-k (a catch-all for cards that fit no named kritik, not something to search
     for); the NHI-specific counterplans (nhs, public option, smokers, taxes, sex offenders,
     vouchers, optional legislation, religious freedom, ucf), whose templates would need topic
     wording; the NHI file's disability-k, debility-k and trump-k; federalism-cp and free-market-cp,
     as the PM said. Question 1.
5. **Windows for the new families are drafts:**
   - theory: every need any age;
   - counterplan: solvency, net benefit and answers five years, competition any age;
   - kritik: link five years, the rest any age.

   Framing is any age, as the coach ruled. Question 3.
6. **Utilitarianism and deontology keep `formats: [LD]`**, and structural violence and cost-benefit
   keep Policy, LD and PF, as 1.1.0 had them. Only their needs and templates changed.
7. **The reviewed entries are guarded by the coach's own file.** A test compares every
   `coach_reviewed` entry, and the DA family's needs, with the frozen 1.1.0 copy. When the coach
   changes a reviewed template at a later review, his reviewed file is copied there with it. A
   template written into a test would have to be copied from the code under test; his file is the
   record.

## Questions for the PM

```text
v1-e08-t08 questions (session of 2026-11-02). Each was decided provisionally; the recommended option is what the branch does.

1. Which counterplans and kritiks are "the generic ones the Policy landscape names".
   A. Topic-independent ones (recommended): process, states, courts, delay and advantage CPs, and
      generic.yaml's ten named Ks. Not generic-k (a catch-all), not the NHI-mechanism CPs (their
      templates would need topic wording), not disability-k, debility-k or trump-k from the NHI file.
   B. Only generic.yaml's: process-cp and the ten Ks (states, courts, delay and advantage CPs out).
   C. Every cp and k in both landscape files (about 28 arguments), with {topic}-only templates.

2. How an argument names its family.
   A. Its kind chooses it; each family lists its kinds (recommended): one source, nothing to disagree.
   B. A `family:` field on each argument as well, validated against the kind.

3. Windows for theory, counterplan and kritik needs.
   A. The drafts, for the coach's review (recommended): theory any age; CP solvency, net benefit and
      answers five years, competition any age; K link five years, the rest any age.
   B. Ask the coach before merging.

4. The search.expand prompt's system text lists only the DA family's five needs.
   A. Leave it; the user message already sends the need's own label and description, and model
      expansion is off unless asked for. File a follow-up for prompt 1.1.0 (recommended).
   B. Widen this task to prompts/.
```

## Operator follow-ups

No commands. The affected set takes longer than two minutes, so it is left to the pull request's `ci`
check (agreement 10).

The coach's review (ac1) is a sign-off, not a command. He reads the sheet below. For each entry he
accepts, he changes `review: awaiting_coach_review` to `coach_reviewed` in
`config/argument_taxonomy.yaml` and corrects its templates and windows. Then:

- raise `taxonomy_version`;
- copy the reviewed file into
  `packages/debate_core/tests/fixtures/argument_taxonomy/` so the guard covers the new reviewed
  entries;
- record ac1.

Cost-benefit's wording is his to give (the amendment asks for it at review).

## Follow-up work

- `prompts/search/expand.md` 1.1.0: the system text lists the DA family's five needs, so it is wrong
  for a framework, a counterplan or a kritik. Fix it by naming the family's needs, or by sending
  them as a variable (E08 or E05). Question 4.
- LD de-extinction framing presets and topic arguments, once v1-e32-t06 commits the resolution (as
  v1-e08-t04 left it).
- federalism-cp and free-market-cp, once the landscape task that adds them lands.

## Review sheet for the coach

Rendered from `config/argument_taxonomy.yaml` 1.2.0. The DAs and advantages he reviewed in 1.1.0 are
unchanged and not repeated.

In each template:
- `{query}` is what the student typed;
- `{topic}` is "national health insurance" with the NHI preset, and otherwise the query.

A template uses its need's window unless it says otherwise; none of these does.

The questions for him:
- Is each family's list of needs right, in his terms?
- Are the windows right?
- Are these the counterplans and kritiks to have?
- Cost-benefit's own wording.

| Family | Kinds | Need (aliases) | Default window | What a card shows |
|---|---|---|---|---|
| DAs and advantages | da, advantage | Uniqueness (uq, u) | 1 yr | Where things stand now, before the plan or action. |
|  |  | Link (l) | 5 yr | How the plan or action sets the argument off. |
|  |  | Internal link (il) | 5 yr | The step that connects the link to the impact. |
|  |  | Impact (i, impacts) | any age | What happens in the end, and why it matters. Older scholarship is fine. |
|  |  | Answers (AT) (at, a2, answers-to) | 5 yr | Evidence answering the other side's version of the argument. |
| Framing | framework | Framework good (fw-good) | any age | Why the round should be weighed this way. |
|  |  | Answers (AT) (at, a2, answers-to) | any age | Why the round should not be weighed this way. |
| Theory | theory | Interpretation (interp) | any age | The rule the theory argument says debaters should follow. |
|  |  | Standards (standard) | any age | Why the interpretation is better for debate, such as fairness, education or ground. |
|  |  | Voters (voter, voting-issue) | any age | Why breaking the rule is a reason to vote, and what the judge should do about it. |
|  |  | Answers (AT) (at, a2, answers-to) | any age | Evidence answering the other side's theory argument. |
| Counterplans | cp | Solvency (solves) | 5 yr | That the counterplan solves the affirmative's advantages, or does what the plan does. |
|  |  | Net benefit (nb, net-benefits) | 5 yr | A reason to prefer the counterplan that the plan, or doing both, does not get. |
|  |  | Competition (comp) | any age | Why the counterplan is a reason to reject the plan rather than to do both. |
|  |  | Answers (AT) (at, a2, answers-to) | 5 yr | Evidence answering the counterplan, such as that it does not solve or that both can be done. |
| Kritiks | k | Link (l) | 5 yr | How the affirmative's plan, assumptions or representations link to the kritik. |
|  |  | Impact (i, impacts) | any age | What the linked assumptions lead to, and why it matters. |
|  |  | Alternative (alt) | any age | What the kritik offers instead of the affirmative. |
|  |  | Framework (fw) | any age | How the judge should weigh the round, so that the kritik comes first. |
|  |  | Answers (AT) (at, a2, answers-to) | any age | Evidence answering the kritik, such as the permutation, the alternative failing or the affirmative's framework. |

| Argument (aliases) | Family | Format | Need | Templates |
|---|---|---|---|---|
| `util` Util (utilitarianism, consequentialism) | Framing | LD | Framework good | `utilitarianism good framework`<br>`predictions good policy making`<br>`expert predictions accurate`<br>`utilitarianism inevitable`<br>`{topic} utilitarianism` |
|  |  |  | Answers (AT) | `utilitarianism bad framework`<br>`predictions bad policy making`<br>`expert predictions inaccurate`<br>`utilitarianism not inevitable`<br>`{topic} consequences unpredictable` |
| `deontology` Deontology (kant, kantianism, deont) | Framing | LD | Framework good | `deontology good framework`<br>`deontology allows better policy making`<br>`Kantian ethics justification`<br>`{topic} rights and duties` |
|  |  |  | Answers (AT) | `deontology bad framework`<br>`deontology fails policy making`<br>`deontology ignores consequences`<br>`{topic} consequences matter more than rights` |
| `structural-violence` Structural violence (sv) | Framing | Policy, LD, PF | Framework good | `evaluate structural violence above other consequences`<br>`structural violence outweighs extinction`<br>`structural violence comes first`<br>`{topic} structural violence` |
|  |  |  | Answers (AT) | `war turns structural violence`<br>`economic decline turns structural violence`<br>`structural violence inevitable`<br>`structural violence can't be solved`<br>`extinction outweighs structural violence` |
| `cost-benefit` Cost-benefit (cba, cost-benefit-analysis) | Framing | Policy, LD, PF | Framework good | `cost benefit analysis good framework`<br>`cost benefit analysis good policy making`<br>`cost benefit predictions accurate`<br>`cost benefit analysis inevitable`<br>`{topic} cost benefit analysis` |
|  |  |  | Answers (AT) | `cost benefit analysis bad framework`<br>`cost benefit predictions inaccurate`<br>`cost benefit analysis not inevitable`<br>`{query} benefits overstated` |
| `theory` Theory (ld-theory) | Theory | LD | Interpretation | `{query} debate interpretation`<br>`{query} theory interpretation`<br>`competing interpretations debate theory` |
|  |  |  | Standards | `{query} debate fairness`<br>`{query} debate education`<br>`{query} debate ground`<br>`debate education portable skills` |
|  |  |  | Voters | `debate fairness voting issue`<br>`debate education voting issue`<br>`drop the debater theory`<br>`drop the argument theory` |
|  |  |  | Answers (AT) | `reasonability debate theory`<br>`{query} theory frivolous`<br>`theory not a voting issue`<br>`{query} counter interpretation` |
| `process-cp` Process CP (process, cp-process) | Counterplans | Policy | Solvency | `{query} consultation process solves`<br>`{query} commission recommendations implemented`<br>`{topic} enacted through a referendum` |
|  |  |  | Net benefit | `{query} consultation improves relations`<br>`{topic} commission depoliticizes`<br>`{query} referendum democratic legitimacy` |
|  |  |  | Competition | `should means immediate and certain`<br>`resolved means a firm decision`<br>`{query} counterplan competition` |
|  |  |  | Answers (AT) | `{query} consultation fails`<br>`{topic} commission recommendations ignored`<br>`permutation do both {query}` |
| `states-cp` States CP (states, cp-states, states-counterplan) | Counterplans | Policy | Solvency | `states solve {query}`<br>`state level {topic}`<br>`{query} state innovation`<br>`{query} fifty states coordination` |
|  |  |  | Net benefit | `{query} federal action undermines federalism`<br>`{query} state action avoids politics`<br>`{topic} federal spending tradeoff` |
|  |  |  | Competition | `states counterplan competition federal government`<br>`uniform fifty state fiat legitimate` |
|  |  |  | Answers (AT) | `states can't solve {query}`<br>`{query} race to the bottom states`<br>`states lack funding for {query}`<br>`{query} federal action key` |
| `courts-cp` Courts CP (courts, cp-courts) | Counterplans | Policy | Solvency | `{query} Supreme Court ruling`<br>`courts solve {query}`<br>`{topic} judicial decision compliance` |
|  |  |  | Net benefit | `{query} court action avoids politics`<br>`{topic} courts avoid a fight in Congress`<br>`{query} judicial action legitimacy` |
|  |  |  | Competition | `courts counterplan competition Congress`<br>`{query} courts not Congress` |
|  |  |  | Answers (AT) | `courts can't solve {query}`<br>`{query} court ruling backlash`<br>`{query} courts lack enforcement`<br>`court legitimacy low now` |
| `delay-cp` Delay CP (delay, cp-delay) | Counterplans | Policy | Solvency | `{query} delay solves`<br>`{topic} phased implementation`<br>`{query} wait for evidence` |
|  |  |  | Net benefit | `{query} bad timing now`<br>`{topic} delay avoids political backlash`<br>`{query} implementation timing economy` |
|  |  |  | Competition | `should means immediate`<br>`delay counterplan competition immediacy` |
|  |  |  | Answers (AT) | `{query} delay costs`<br>`{query} urgent now`<br>`{topic} delay never happens`<br>`delay counterplans bad theory` |
| `advantage-cp` Advantage CP (adv-cp, advantage-counterplan) | Counterplans | Policy | Solvency | `{query} alternative policy solves`<br>`{query} alternative solutions`<br>`alternatives to {topic}` |
|  |  |  | Net benefit | `{topic} costs too much`<br>`{query} cheaper alternative`<br>`{query} less disruptive alternative` |
|  |  |  | Competition | `counterplan competition through net benefits`<br>`advantage counterplans legitimate` |
|  |  |  | Answers (AT) | `{query} alternative fails`<br>`only {topic} solves {query}`<br>`advantage counterplans bad theory` |
| `cap-k` Cap K (cap, capitalism-k, k-cap) | Kritiks | Policy | Link | `{topic} reform props up capitalism`<br>`{query} capitalism`<br>`{query} commodification` |
|  |  |  | Impact | `capitalism causes environmental destruction`<br>`capitalism structural violence`<br>`capitalism causes war` |
|  |  |  | Alternative | `reject capitalism alternative`<br>`socialism alternative to capitalism`<br>`{query} socialist alternative` |
|  |  |  | Framework | `material analysis comes first`<br>`{query} capitalism framework` |
|  |  |  | Answers (AT) | `capitalism good`<br>`capitalism sustainable`<br>`socialism fails`<br>`permutation reform and socialism` |
| `racial-capitalism-k` Racial capitalism K (racial-cap-k, racial-cap) | Kritiks | Policy | Link | `{topic} racial capitalism`<br>`{query} racial hierarchy capitalism` |
|  |  |  | Impact | `racial capitalism violence`<br>`racial capitalism dispossession` |
|  |  |  | Alternative | `abolition of racial capitalism`<br>`{query} Black radical tradition` |
|  |  |  | Framework | `racial capitalism framework comes first`<br>`{query} race analysis first` |
|  |  |  | Answers (AT) | `racial capitalism theory wrong`<br>`{query} reform helps communities of color`<br>`capitalism reduces racism` |
| `security-k` Security K (security, k-security) | Kritiks | Policy | Link | `{query} securitization`<br>`{query} threat construction`<br>`{topic} securitizes` |
|  |  |  | Impact | `securitization justifies violence`<br>`security logic causes war` |
|  |  |  | Alternative | `reject security logic`<br>`{query} desecuritization` |
|  |  |  | Framework | `representations come first security`<br>`{query} threat discourse matters` |
|  |  |  | Answers (AT) | `securitization good`<br>`{query} threat is real`<br>`realism true` |
| `biopolitics-k` Biopolitics K (biopolitics, biopower-k, k-biopolitics) | Kritiks | Policy | Link | `{topic} biopolitics`<br>`{query} biopower population management`<br>`{query} health surveillance` |
|  |  |  | Impact | `biopolitics justifies killing`<br>`biopower control over life` |
|  |  |  | Alternative | `resist biopolitics`<br>`{query} refuse biopower` |
|  |  |  | Framework | `biopolitics framework comes first`<br>`{query} Foucault framework` |
|  |  |  | Answers (AT) | `biopolitics inevitable`<br>`biopower good for health`<br>`{query} biopolitics not totalizing` |
| `settler-colonialism-k` Settler colonialism K (settler-colonialism, set-col-k, k-set-col) | Kritiks | Policy | Link | `{topic} settler colonialism`<br>`{query} settler state`<br>`{query} Indigenous land` |
|  |  |  | Impact | `settler colonialism genocide`<br>`settler colonialism ongoing violence` |
|  |  |  | Alternative | `decolonization alternative`<br>`{query} land back`<br>`{query} Indigenous sovereignty` |
|  |  |  | Framework | `settler colonialism framework comes first`<br>`{query} decolonial framework` |
|  |  |  | Answers (AT) | `settler colonialism theory wrong`<br>`{query} reform helps Indigenous communities`<br>`decolonization alternative fails` |
| `colonialism-k` Colonialism K (colonialism) | Kritiks | Policy | Link | `{topic} colonialism`<br>`{query} colonial relations`<br>`{query} global health imperialism` |
|  |  |  | Impact | `colonialism violence`<br>`colonial logic causes war` |
|  |  |  | Alternative | `decolonial alternative`<br>`{query} decolonize` |
|  |  |  | Framework | `decolonial framework comes first`<br>`{query} colonial framing` |
|  |  |  | Answers (AT) | `colonialism critique wrong`<br>`{query} not colonial`<br>`decolonial alternative fails` |
| `antiblackness-k` Antiblackness K (antiblackness, k-antiblackness) | Kritiks | Policy | Link | `{topic} antiblackness`<br>`{query} antiblackness`<br>`{query} reform cannot reach antiblackness` |
|  |  |  | Impact | `antiblackness gratuitous violence`<br>`antiblackness social death` |
|  |  |  | Alternative | `afropessimism alternative`<br>`{query} Black fugitivity` |
|  |  |  | Framework | `antiblackness framework comes first`<br>`{query} ontology first` |
|  |  |  | Answers (AT) | `afropessimism wrong`<br>`antiblackness not ontological`<br>`{query} reform helps Black communities` |
| `psychoanalysis-k` Psychoanalysis K (psychoanalysis, psycho-k, k-psychoanalysis) | Kritiks | Policy | Link | `{query} desire fantasy`<br>`{topic} psychoanalysis`<br>`{query} fear of death` |
|  |  |  | Impact | `death drive violence`<br>`fantasy of mastery violence` |
|  |  |  | Alternative | `traverse the fantasy`<br>`{query} psychoanalysis alternative` |
|  |  |  | Framework | `psychoanalysis framework comes first`<br>`{query} Lacan framework` |
|  |  |  | Answers (AT) | `psychoanalysis wrong`<br>`psychoanalysis not falsifiable`<br>`{query} psychoanalysis fails` |
| `queer-k` Queer K (queer, queer-intelligibility-k) | Kritiks | Policy | Link | `{topic} queer`<br>`{query} reproductive futurism`<br>`{query} heteronormativity` |
|  |  |  | Impact | `heteronormativity violence`<br>`reproductive futurism excludes queer life` |
|  |  |  | Alternative | `queer theory alternative`<br>`{query} queer futurity` |
|  |  |  | Framework | `queer theory framework comes first`<br>`{query} queer framework` |
|  |  |  | Answers (AT) | `reproductive futurism wrong`<br>`queer theory alternative fails`<br>`{query} helps queer people` |
| `buddhism-k` Buddhism K (buddhism, k-buddhism) | Kritiks | Policy | Link | `{query} attachment to outcomes`<br>`{topic} Buddhism`<br>`{query} suffering` |
|  |  |  | Impact | `attachment causes suffering`<br>`craving suffering Buddhism` |
|  |  |  | Alternative | `Buddhist non attachment`<br>`{query} mindfulness alternative` |
|  |  |  | Framework | `Buddhism framework comes first`<br>`{query} Buddhist ethics` |
|  |  |  | Answers (AT) | `Buddhism quietism`<br>`non attachment fails`<br>`{query} Buddhism cannot solve` |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-02

**Notes:**

Accepted, with the Goal `InProgress` for the coach's review (ac1, operator). Needs are now per family:
a framework has no uniqueness, and `search` refuses a need from another family with exit 2, naming
that argument's needs. The guard that freezes the coach's reviewed 1.1.0 file is the right way to keep
his DA and advantage review intact.

1. **ac1 (code):** 28 core and 7 CLI tests failed against the skeleton, and 139 pass now, the smoke
   check included. The 17 mutants, the PM's four among them, were all caught at assertions. The two
   that failed by refusing to load were redone, which is right.
2. **The rulings on your questions:**
   * **Q1, A.** The topic-independent counterplans and generic.yaml's ten named kritiks.
     `federalism-cp` and `free-market-cp` arrive with the landscape task the PM files next.
     `health-profiteering-advantage` is an advantage, so it is that task's too.
   * **Q2, A.** The kind chooses the family.
   * **Q3, A.** The windows are drafts for the coach's review.
   * **Q4, A.** The PM files prompt `search.expand` 1.1.0 (the family's needs sent as a variable) as a
     p3 follow-up.
3. **For the coach's review, two templates the PM flags:**
   * On 2026-11-02 the coach described `antiblackness-k`'s alternative as an epistemological
     reframing of how we approach health care, and `psychoanalysis-k` as desire read through Lacan or
     Žižek. The templates here (afropessimism, fugitivity, traverse the fantasy) should be checked
     against those descriptions.
   * Cost-benefit's own wording is still his to give.
4. **Deviations accepted:**
   * the CLI test, the smoke check and the `--need` help line, outside the packages;
   * schema 2;
   * ac2's version pin at 1.2.0, with its queries unchanged.
5. **Deviation 4 (the `git fetch`):** noted. It is the second session this week. The rule stands: use
   the local `origin/dev`. Network calls, read-only ones included, go to the operator, except
   `scripts/task sync` when the PM asks for it.
6. **Closing checks:** the affected set (254 files) is left to `ci` (agreement 10). The bounded run (557
   passed), ruff, pyright, lint-imports, thin handlers and the specs are clean.
7. **After the coach's review:** the PM applies his corrections in a batch, flips the entries to
   `coach_reviewed`, refreshes the frozen fixture, records ac1 and sets the Goal `Succeeded`.
8. **Merge:** `scripts/task pr --partial` once `ci` is green.

## Operator records (recorded by the PM, 2026-11-03)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac1 (part): the coach reviews them (operator) | NOT RUN (operator) | PART: 3 of 20 entries reviewed | the coach's answers of 2026-11-02, relayed by Charlie: `antiblackness-k` approved as drafted; `psychoanalysis-k` approved, with no Zizek template added; `cost-benefit` approved as written. The PM marked the three `coach_reviewed`, raised `taxonomy_version` to 1.2.1 (no template changed), and refreshed the guard's fixture as `coach_reviewed_1_2_1.yaml`, which now holds 12 reviewed entries |

The Goal stays `InProgress`. The PM's relay of 2026-11-02 asked about only the three entries the PM had flagged and wrongly called them the last; 17 entries added or reshaped by this task still say `awaiting_coach_review` (util, deontology, structural-violence, theory, the five counterplans, and eight of the kritiks). Their review sheet is above. When the coach has read them, the PM applies his answers the same way and sets the Goal `Succeeded`.
