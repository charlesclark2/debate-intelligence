# Session report: v1-e32-t40-model-stage-reads-the-argument-not-the-subject

| | |
|---|---|
| Task | `v1-e32-t40-model-stage-reads-the-argument-not-the-subject` — The model stage names the argument a card is read as, with each position's side and description, and the scrub and scan fixed |
| Spec | [`plan_specs/v1/e32-argument-landscape/t40-model-stage-reads-the-argument-not-the-subject.yaml`](../../plan_specs/v1/e32-argument-landscape/t40-model-stage-reads-the-argument-not-the-subject.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t40-model-stage-reads-the-argument-not-the-subject` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The code half is done and tested; the coach's half is not, so **the Goal stays `InProgress`** with ac2
and ac3 NOT RUN. Per the PM's brief, I stop here until the PM relays the coach's answers.

* **Descriptions (step 1).** Every one of the 103 positions the Policy prompt sends now has a one-line
  description: 102 drafted here (81 NHI, 21 of `generic.yaml`'s Policy positions), plus
  `kritikal-aff`'s from `v1-e32-t17`. Taxonomy `policy-2026-27-nhi` 1.4.1, `generic` 1.1.1. They are
  drafts until the coach approves them. [The review sheet](#review-sheet-for-the-coach) lists them, and
  14 are marked as guesses.
* **Prompt 1.1.0 (step 2).** Registered, released and locked. The stage runs 1.1.0, and a 1.0.0 cassette
  is never served to it.
* **The scrub (step 3).** Every disclosing team's school, code and tournament comes out of each card's
  heading path, tag, cite and excerpt, on both paths: the evaluation and a landscape run.
* **The scan (step 4).** It reads values, not keys, leaves out the positions text, holds tournaments only,
  and reads the repair cassettes. It also skips cassettes of other prompt versions, which goes beyond
  the brief ([decision 4](#decisions-and-assumptions)).
* **The smoke check (step 5).** It passes against the checkout's script and against an installed build
  stamped from this branch. It fails against a scrub break, a repair-scan break, and a break inside the
  installed build alone.
* **The re-record (step 6).** The operator block is in [a new runbook](../runbooks/landscape-model-evaluation-record.md),
  copied [below](#operator-follow-ups). It waits on the coach's approval.

**Look at first:** the review sheet, the 13 rows' command, and
[decision 3](#decisions-and-assumptions): the prompt's extra line on generic positions.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `model-stage-reads-the-argument-not-the-s` (Argument not subject) | Code done; Goal criteria ac2 and ac3 open | Its own criterion passes. ac2 and ac3 are the coach's and the operator's |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: prompt 1.1.0 registered and locked, sending each position's side and description and stating the rationale limit; the scrub removing the third list from all four fields; the scan reading values only, skipping the positions text, holding only tournaments and reading repair cassettes; all by tests shown failing first | PASS | [Red runs](#checks-shown-failing-for-their-reason): 1 + 3 + 5 + 10 + 2 tests failed on their assertions before each implementation. 20 mutants, the PM's six among them, are all caught on assertions. `uv run scripts/lock_prompts.py --check` → exit 0. The tests: `test_prompt_1_1_0_reads_the_argument_not_the_subject_with_sides_descriptions_and_the_limit`, `test_every_position_the_policy_prompt_sends_has_its_side_and_a_one_line_description`, `test_the_third_list_comes_out_of_every_field_an_evaluation_sends` (heading, tag, cite and excerpt in one request, by hand), `test_model_a_run_sends_no_disclosing_teams_name_in_a_heading_or_tag`, and the scan tests in `test_evaluation_scan_hits.py` and `test_landscape_model_stage.py` |
| ac2: every NHI position has a one-line description, the coach has approved them and answered the 13 rows' question (operator, recorded by the PM) | NOT RUN | Half done: 103 of 103 positions have one, which the test above checks. The coach's approval and his answer on the 13 rows are pending. The sheet is [below](#review-sheet-for-the-coach). The 13 rows are not in docs/data, so [the operator's JSON-only command](#1-the-13-rows-by-number) lists them by number |
| ac3: the operator's re-record of the same 47 cards under 1.1.0 and its `--breakdown` (operator, recorded by the PM) give counts recorded in docs/data, and its scan finds no name in the prompt inputs | NOT RUN | Waits on ac2: the spec forbids a re-record before the coach approves. The blocks are [below](#2-after-the-coach-approves-re-record-the-47-under-110) and in `docs/runbooks/landscape-model-evaluation-record.md`. docs/data says what changed and holds no number yet |
| ac4: a smoke check runs `landscape evaluate` on a synthetic sample against the checkout's script and an installed build, and fails against a break | PASS | `tests/smoke/test_landscape_evaluate_smoke.py`, 2 tests. **Checkout's script:** `hard_stop.py 115 … pytest -p no:randomly -n 0 tests/smoke/test_landscape_evaluate_smoke.py` → 2 passed in 2.32 s. **Installed build:** wheels stamped `v0.0.1-dev.40` from commit `44913b9` (offline), installed into a scratch venv. `DEBATE_SMOKE_BIN=<venv>/bin/debate-research DEBATE_SMOKE_EXPECT_SHA=<sha> DEBATE_SMOKE_EXPECT_TAG=v0.0.1-dev.40 …` → 2 passed in 2.23 s. **Breaks:** (1) the tag scrub dropped in the checkout → both fail with exit 1 `EVALUATION_BELOW_BAR`, the prompt-input scan finding the planted tournament (`other_names` 1); (2) the service not passing the repair cassettes → the scan assertion fails; (3) the tag scrub dropped in the installed copy only → both fail with `MISSING_FIXTURE_ERROR`, because the build asks for a request nobody recorded. Each break was restored after its run |
| Node: `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "evaluat or model_stage or scrub or scan"` | PASS | `hard_stop.py 115 .venv/bin/python -m pytest -q -n 6 packages/debate_core/tests packages/debate_cli/tests -k "evaluat or model_stage or scrub or scan"` → **267 passed** in 15.08 s, after the last code commit |

## Review sheet for the coach

> **For the coach** (relayed by the PM): one line per position, which the model now reads beside each
> id to tell neighbours apart. Approve the whole list, or correct a row's description. The side and the
> kind are the taxonomy's and are not changed. The last column marks my guesses. "Harms" is not used.

| # | id | kind | side | file | description | to check |
|---|---|---|---|---|---|---|
| 1 | `single-payer-aff` | aff | aff | nhi | A plan for one public insurer that pays for everyone's care, with no narrower mechanism named. |  |
| 2 | `global-budgets-aff` | aff | aff | nhi | A single payer plan that pays hospitals a fixed yearly budget instead of paying per service. |  |
| 3 | `single-public-authority-aff` | aff | aff | nhi | A single payer plan run by one public authority that collects and pays out the money. |  |
| 4 | `medicare-for-all-aff` | aff | aff | nhi | A single payer plan that extends Medicare to everyone (Medicare for All). |  |
| 5 | `lower-payment-rates-aff` | aff | aff | nhi | A single payer plan whose mechanism is lower rates paid to doctors, hospitals and drug makers. |  |
| 6 | `value-based-reimbursement-aff` | aff | aff | nhi | A single payer plan that pays providers for patient outcomes rather than for the number of services. |  |
| 7 | `disparate-impact-enforcement-aff` | aff | aff | nhi | A single payer plan that enforces disparate impact rules against discrimination in care. |  |
| 8 | `degrowth-aff` | aff | aff | nhi | A single payer plan defended as a move toward degrowth, away from an economy built on growth. |  |
| 9 | `prescription-drug-coverage-aff` | aff | aff | nhi | A single payer plan centred on covering prescription drugs. |  |
| 10 | `nanomedicine-coverage-aff` | aff | aff | nhi | A single payer plan that covers nanomedicine treatments. |  |
| 11 | `nhi-aff` | aff | aff | nhi | A plan that enacts the resolution's national health insurance as worded, with no narrower mechanism. |  |
| 12 | `public-option-aff` | aff | aff | nhi | A plan for a government insurance plan anyone can buy, alongside private insurers. |  |
| 13 | `ucc-aff` | aff | aff | nhi | A plan for universal catastrophic coverage, insuring everyone against large costs with a sliding-scale deductible. |  |
| 14 | `indigenous-aff` | aff | aff | nhi | A plan for the health insurance of Indigenous peoples, such as reforming the Indian Health Service. |  |
| 15 | `reproductive-health-aff` | aff | aff | nhi | A plan that covers reproductive care, including abortion, for example by ending the Hyde Amendment. |  |
| 16 | `tiered-nhi-aff` | aff | aff | nhi | A plan for national health insurance in tiers, a basic public level with further levels above it. | A guess at what the tiers are |
| 17 | `incarceration-aff` | aff | aff | nhi | A plan that extends health insurance to people in prison or jail. |  |
| 18 | `voucher-aff` | aff | aff | nhi | A plan that gives people vouchers to buy private insurance. |  |
| 19 | `medicaid-expansion-aff` | aff | aff | nhi | A plan that expands Medicaid to more people or to every state. |  |
| 20 | `aca-reform-aff` | aff | aff | nhi | A plan that reforms or builds on the Affordable Care Act's marketplaces and subsidies. |  |
| 21 | `childrens-coverage-aff` | aff | aff | nhi | A plan that insures every child. |  |
| 22 | `eco-nhi-aff` | aff | aff | nhi | A plan for national health insurance tied to ecological health, such as climate or environmental care. | A guess |
| 23 | `human-enhancement-aff` | aff | aff | nhi | A plan that covers human enhancement technologies beyond treating illness. | A guess |
| 24 | `kritikal-aff` | aff | aff | nhi | An affirmative with a role of the ballot, an advocacy statement or a method and no plan text. | Written in v1-e32-t17; unchanged |
| 25 | `costs-advantage` | advantage | aff | nhi | The plan lowers health care costs, and the impact is what lower costs save, such as household budgets. |  |
| 26 | `coverage-advantage` | advantage | aff | nhi | The plan insures the uninsured or underinsured, and the impact is the lives coverage saves. |  |
| 27 | `disease-advantage` | advantage | aff | nhi | The plan improves the treatment or prevention of a disease, and the impact is that disease's toll. |  |
| 28 | `inequality-advantage` | advantage | aff | nhi | The plan reduces health or economic inequality, and inequality is the impact. |  |
| 29 | `economy-advantage` | advantage | aff | nhi | The plan strengthens the economy as a whole, and an economic collapse or recession is the impact. |  |
| 30 | `growth-advantage` | advantage | aff | nhi | The plan raises the rate of economic growth, through productivity, entrepreneurship or labour mobility. |  |
| 31 | `bioterror-advantage` | advantage | aff | nhi | The plan readies the health system for a bioterror attack, and the attack's casualties are the impact. |  |
| 32 | `budgets-advantage` | advantage | aff | nhi | The plan relieves state or federal budgets of health spending. |  |
| 33 | `stagnation-advantage` | advantage | aff | nhi | The plan ends secular stagnation, the claim that the economy is stuck in long-term slow growth. |  |
| 34 | `access-advantage` | advantage | aff | nhi | The plan improves access to care, such as rural hospitals, clinics and providers. |  |
| 35 | `innovation-advantage` | advantage | aff | nhi | The plan speeds medical innovation, and the treatments it produces are the impact. |  |
| 36 | `data-advantage` | advantage | aff | nhi | The plan creates one shared health data system, for records, research or tracking disease. |  |
| 37 | `pandemics-advantage` | advantage | aff | nhi | The plan improves preparedness for and response to a natural pandemic. |  |
| 38 | `pharma-advantage` | advantage | aff | nhi | The plan lowers drug prices or changes the drug industry, as a benefit of the plan. |  |
| 39 | `sustainability-advantage` | advantage | aff | nhi | The plan makes the health system environmentally sustainable, cutting its emissions or waste. |  |
| 40 | `biotech-advantage` | advantage | aff | nhi | The plan strengthens the biotech industry or the country's lead in biotech. |  |
| 41 | `midterms-da` | da | neg | nhi | The plan changes who wins the midterm elections, and that result causes the impact. |  |
| 42 | `pharma-da` | da | neg | nhi | The plan cuts drug makers' profits, so drug research and the biotech lead decline. |  |
| 43 | `economy-da` | da | neg | nhi | The plan hurts the economy through its costs, taxes or lost jobs, and a recession is the impact. |  |
| 44 | `irs-da` | da | neg | nhi | The plan overloads the IRS with running it, which trades off with its enforcement work, such as tracking terrorist financing. |  |
| 45 | `stocks-da` | da | neg | nhi | The plan crashes health sector stocks or the stock market. |  |
| 46 | `rates-da` | da | neg | nhi | The plan's spending or borrowing raises interest rates, and higher rates cause the impact. |  |
| 47 | `capital-flight-da` | da | neg | nhi | The plan's taxes or costs drive capital and investors out of the country. |  |
| 48 | `federalism-da` | da | neg | nhi | A federal program takes health policy from the states, and the loss of federalism is the impact. |  |
| 49 | `hhs-da` | da | neg | nhi | The plan overloads the Department of Health and Human Services, which trades off with its other work. |  |
| 50 | `court-clog-da` | da | neg | nhi | The plan sets off lawsuits that clog the courts and delay other rulings. |  |
| 51 | `taxes-da` | da | neg | nhi | The taxes that pay for the plan cause the impact, economic or political. |  |
| 52 | `permitting-reform-da` | da | neg | nhi | Passing the plan costs the votes or time that permitting reform needs in Congress. | Drafted as a politics-style trade-off |
| 53 | `unions-da` | da | neg | nhi | The plan replaces union-negotiated health benefits, which weakens unions. |  |
| 54 | `doctors-da` | da | neg | nhi | The plan cuts doctors' pay or freedom, which causes a doctor shortage. |  |
| 55 | `medical-devices-da` | da | neg | nhi | The plan cuts the medical device industry's revenue, so device innovation declines. |  |
| 56 | `innovation-da` | da | neg | nhi | The plan cuts the profits that fund medical innovation, so innovation declines. |  |
| 57 | `debt-da` | da | neg | nhi | The plan's cost adds to the national debt, and a debt crisis is the impact. |  |
| 58 | `ai-da` | da | neg | nhi | The plan takes funding or attention from artificial intelligence, harming AI development or leadership. | A guess at the link story |
| 59 | `democracy-da` | da | neg | nhi | The plan weakens democracy, through backlash, polarization or concentrated power. | A guess at the link story |
| 60 | `states-cp` | cp | neg | nhi | The fifty states, not the federal government, enact the plan. |  |
| 61 | `nhs-cp` | cp | neg | nhi | The federal government runs the health care providers itself, a national health service, instead of insuring care. |  |
| 62 | `advantage-cp` | cp | neg | nhi | The negative solves the affirmative's advantages with a different policy, without the plan. |  |
| 63 | `courts-cp` | cp | neg | nhi | The courts, not Congress, bring about the plan's change. |  |
| 64 | `public-option-cp` | cp | neg | nhi | A public option beside private insurance, instead of the affirmative's plan. |  |
| 65 | `smokers-pic` | cp | neg | nhi | The plan, except that smokers are excluded from coverage. |  |
| 66 | `taxes-pic` | cp | neg | nhi | The plan, paid for without the tax the affirmative uses. |  |
| 67 | `sex-offenders-pic` | cp | neg | nhi | The plan, except that sex offenders are excluded from some coverage. |  |
| 68 | `vouchers-cp` | cp | neg | nhi | Vouchers to buy private insurance, instead of the affirmative's plan. |  |
| 69 | `delay-cp` | cp | neg | nhi | The plan, enacted after a delay. |  |
| 70 | `optional-legislation-cp` | cp | neg | nhi | The plan passed as legislation that states or people may opt into, rather than as a mandate. | A guess |
| 71 | `religious-freedom-cp` | cp | neg | nhi | The plan, with an exemption for religious objectors. |  |
| 72 | `ucf-cp` | cp | neg | nhi | A universal coverage fund that pays for care, instead of the affirmative's plan. | A guess at what UCF stands for |
| 73 | `disability-k` | k | neg | nhi | The affirmative treats disability as something to cure or prevent; the alternative rejects that view. |  |
| 74 | `debility-k` | k | neg | nhi | The affirmative ignores debility, the slow wearing down of whole populations that rights and coverage do not reach. | Puar's debility, as drafted |
| 75 | `trump-k` | k | neg | nhi | The affirmative's plan or its framing props up, or is taken over by, the Trump administration. | A guess at the link story |
| 76 | `nhi-t` | t | neg | nhi | The affirmative's plan is not national health insurance as the negative defines the term. | Drafted generically; which definition do teams read? |
| 77 | `multipayer-t` | t | neg | nhi | National health insurance means a system with more than one payer, so a single payer plan is not topical. | Which way does this T cut? Drafted as: NHI is multi-payer, so single payer is not topical |
| 78 | `single-payer-t` | t | neg | nhi | National health insurance means single payer, so a plan that keeps private insurers is not topical. | Drafted as: NHI is single payer, so keeping private insurers is not topical |
| 79 | `no-single-payer-t` | t | neg | nhi | Single payer is not national health insurance, so a single payer plan is not topical. | Drafted close to T-multi-payer; how do the two differ? |
| 80 | `establish-t` | t | neg | nhi | Establish means create a new program, so a plan that expands or reforms an existing one is not topical. |  |
| 81 | `should-t` | t | neg | nhi | Should means immediate and certain, so a plan that is delayed or conditional is not topical. |  |
| 82 | `comprehensive-t` | t | neg | nhi | National health insurance must be comprehensive, so a plan covering one group or one service is not topical. |  |
| 83 | `cap-k` | k | neg | generic | The affirmative's reform props up capitalism; the alternative rejects capitalism. |  |
| 84 | `racial-capitalism-k` | k | neg | generic | The affirmative ignores how capitalism depends on racial hierarchy; the alternative rejects racial capitalism. |  |
| 85 | `security-k` | k | neg | generic | The affirmative's threat scenarios, such as war, pandemics or bioterror, are securitization that justifies violence. |  |
| 86 | `biopolitics-k` | k | neg | generic | The plan's management of health is biopolitical control over life and populations. |  |
| 87 | `settler-colonialism-k` | k | neg | generic | The affirmative takes for granted the settler state on Indigenous land; the alternative is decolonization. |  |
| 88 | `colonialism-k` | k | neg | generic | The affirmative reproduces colonial relations between nations or peoples, beyond the settler state. |  |
| 89 | `antiblackness-k` | k | neg | generic | The affirmative's reform cannot reach antiblackness, which structures the state and health care. |  |
| 90 | `psychoanalysis-k` | k | neg | generic | The affirmative's desire to fix health care or to avert its impacts is read through psychoanalysis. |  |
| 91 | `queer-k` | k | neg | generic | The affirmative's vision of health or of the future excludes queer life; queer theory is the alternative. |  |
| 92 | `buddhism-k` | k | neg | generic | The affirmative's attachment to outcomes produces suffering; the alternative is Buddhist non-attachment. |  |
| 93 | `generic-k` | k | neg | generic | A kritik card, a link, alternative, framework or impact, that fits no named kritik in this list. |  |
| 94 | `framework-t` | t | neg | generic | The affirmative must defend a plan by the federal government; read against affirmatives with no plan. |  |
| 95 | `politics-da` | da | neg | generic | Passing the plan spends political capital or changes Congress's agenda, so another item on it fails. |  |
| 96 | `process-cp` | cp | neg | generic | The plan, enacted through a different process, such as a consultation, a commission or a referendum. |  |
| 97 | `condo-bad` | theory | aff | generic | The negative's conditional counterplans or kritiks are unfair, a reason to reject them or the negative. |  |
| 98 | `fifty-state-fiat-bad` | theory | aff | generic | The negative may not fiat that all fifty states act together. |  |
| 99 | `process-cps-bad` | theory | aff | generic | Counterplans that change only how the plan is passed are illegitimate. |  |
| 100 | `aspec` | theory | neg | generic | The affirmative must name the agency that carries out the plan. |  |
| 101 | `fspec` | theory | neg | generic | The affirmative must say how the plan is funded. |  |
| 102 | `vagueness` | theory | neg | generic | The plan text is too vague for the negative to know what it does. |  |
| 103 | `generic-theory` | theory | both | generic | A theory argument about the rules of debate that fits no listed theory position, read by either side. |  |

### The 13 rows in question

These are the 9 cards the model gave a wrong position of the label's kind (all same-side neighbours)
and the 4 it placed although the coach labelled them none. The coach answers one thing for those rows:
should those positions be told apart at all? That is a taxonomy question; the labels stay as they are.
t39 counted the rows but did not record their numbers, and docs/data does not hold them. A JSON-only
command lists them by sample row number ([operator follow-up 1](#1-the-13-rows-by-number)). It prints
two lists of numbers, which the coach then reads beside his own labelled CSV.

## Checks shown failing for their reason

Each red run covered the new tests alone. It ran against the code as it stood before that step (the
pre-task code, or a skeleton that accepted the new parameters and did nothing with them), with
`hard_stop.py 115 … pytest -p no:randomly -n 0 --tb=line`.

| Step | Red run | Why each failed |
|---|---|---|
| Descriptions | 1 failed | the committed taxonomy, read as the prompt sends it, listed positions with no description |
| Prompt 1.1.0 | 3 failed | no 1.1.0 was registered. The stage ran 1.0.0, and a 1.0.0 cassette was served to it (`DID NOT RAISE MissingFixtureError`) |
| Scrub | 5 failed, 4 passed | the request kept `harbor classic` in the heading, tag, cite and excerpt. The 4 that passed say what the scrub must leave alone (no names, a partial word, the `repr`, t21's tag), and a do-nothing skeleton meets them |
| Scan | 10 failed | the scan counted a key, the positions text and other versions' cassettes, and read no repair cassette |
| CLI | 2 failed | no `scan.repair_cassettes` key, and a name in a repair cassette exited 0 |

The run-path scrub test (`test_model_a_run_sends_no_disclosing_teams_name_in_a_heading_or_tag`) was
written after the scrub. It fails when the run builds its candidates with no names (a mutant, restored
after).

### Mutants

20 mutants. Each ran alone over the six core test files with `-x`, or for the last one the CLI test
file, and was restored from `HEAD` after. **All 20 were caught, each on an assertion.** No test here
uses Hypothesis, so agreement 8's database rule does not apply. The PM's six are the first seven rows (a name left in a heading path and in an excerpt are two).

| Mutant | First test to fail |
|---|---|
| The stage left on 1.0.0, so a stale cassette serves it | `test_the_stage_runs_classify_position_1_1_0_as_released`; alone, `test_a_cassette_recorded_under_1_0_0_is_never_served_to_the_stage_after_the_bump` fails too (`DID NOT RAISE`) |
| A third-list name left in a heading path | `test_a_heading_loses_another_teams_tournament_and_one_left_empty_is_dropped` |
| A third-list name left in an excerpt | `test_the_third_list_comes_out_of_every_field_an_evaluation_sends` |
| A JSON key counted as a school (keys read again) | `test_evaluation_scan_reads_values_not_keys_and_no_two_values_together` |
| The positions text scanned (the evaluation passes no `leave_out`) | `test_the_scan_leaves_out_the_positions_text_the_cassettes_hold` |
| The repair cassettes skipped by the evaluation's scan | `test_the_evaluation_scans_its_prompts_repair_cassettes_filed_under_the_caselist` |
| A description missing from the request | `test_the_prompt_lists_active_positions_and_numbers_the_cards` |
| The tag sent without the third list | `test_the_third_list_comes_out_of_every_field_an_evaluation_sends` |
| The cite sent without it | the same |
| The evaluation builds its candidates without the reading's names | the same |
| The third list holds every team name again | `test_the_scan_holds_only_tournaments_on_its_third_list` |
| Cassettes of another prompt version scanned | `test_the_evaluation_scans_no_cassette_of_another_prompt_version` |
| The version filter drops a text whose version it cannot read | `test_the_scan_finds_a_school_a_team_code_and_a_tournament_in_a_cassette` |
| The scrub makes one pass only | `test_a_name_that_taking_another_out_brings_together_comes_out_too` |
| The scrub matches a phrase by its first word alone | `test_a_word_that_only_starts_like_a_name_stays` |
| A heading path read as separate values by the scan | `test_evaluation_scan_finds_a_school_two_headings_spell_together` |
| The hit listing reads keys across fields again | `test_evaluation_scan_leaves_out_the_committed_positions_text` |
| The hit listing reads the positions text | the same |
| The repair listing reads the failed prompt's positions | `test_evaluation_scan_lists_a_repair_cassettes_copy_of_the_failed_prompt_without_its_positions` |
| The command passes with a name in a repair cassette | `test_evaluate_under_the_bar_or_with_a_name_in_a_cassette_exits_1[changes3]` |

## Tests and checks run before this report

Run after the last code commit (`44913b9`; the commit after it is docs only):

* **The affected set is over two minutes, so it is left to the pull request's `ci`** (agreement 10).
  `scripts/affected_tests.py` selects **306 files**: the model stage reaches the container.
  `hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` reached 65% before the limit
  stopped it, with no failure printed up to then.
* Within two minutes, over the changed areas and the always-run list:
  * the command: `hard_stop.py 115 … pytest -q -n 6 -m "not slow and not live" tests/architecture
    tests/specs tests/config …/test_app.py …/test_help_rendering.py …/test_container_factories.py
    packages/debate_core/tests/arguments/landscape packages/debate_core/tests/integrations/landscape
    …/test_prompt_lock.py …/test_landscape_model_stage.py …/test_landscape_evaluation_breakdown.py
    …/test_position_classification.py …/test_landscape_run.py …/test_landscape_report.py
    …/test_landscape_seeding.py packages/debate_cli/tests/test_landscape_command.py
    tests/smoke/test_landscape_evaluate_smoke.py tests/smoke/test_landscape_smoke.py
    tests/scripts/test_stamp_build.py`;
  * the result: **2134 passed** in 27.08 s.
* The node's criterion: **267 passed** in 15.08 s (above).
* `ruff format --check .` → 1807 files already formatted. `ruff check .` → all checks passed.
* `pyright packages/debate_core packages/debate_cli tests/smoke/test_landscape_evaluate_smoke.py` → 0
  errors.
* `lint-imports` → 20 kept, 0 broken.
* `scripts/check_thin_handlers.py` → 71 handlers within 25 statements.
* `scripts/lock_prompts.py --check` → exit 0.
* `scripts/docs_index.py --check-descriptions` → OK. `scripts/check_links.py` → OK.
  `scripts/check_command_blocks.py --base origin/dev` → OK.
* `scripts/validate_specs.py` → OK (run last, after this report).

## Files changed

* **Taxonomy** (`config/landscape/`): `taxonomies/policy-2026-27-nhi.yaml` gets 81 descriptions and goes
  to 1.4.1. `taxonomies/generic.yaml` gets 21 and goes to 1.1.1. `topics.yaml` moves to 1.4.1. No id,
  alias, kind or side changed.
* **Prompt**: `prompts/landscape/classify_position@1.1.0.md` (new, released) and
  `prompts/prompts.lock.json` (one entry added). 1.0.0 is unchanged.
* **`debate_core.arguments.landscape`**:
  * `tag_scrub.py`: `DisclosedNames`, a word-level scrub of every disclosing team's names that repeats
    until nothing more comes out, and `card_tag`'s optional `disclosed`.
  * `model_stage.py`: `sent_headings` takes the names, and `ModelCandidate.disclosed` carries them to
    the excerpt. `name_scan` reads values (`scanned_values`, `json_values`) and takes `leave_out`.
  * `scan_hits.py`: reads values; leaves out the positions text in a cassette and in a repair cassette's
    failed prompt.
  * `seeding.py`: `SeedTeam.tournament`.
* **`debate_core.application`**:
  * `landscape_model_stage.py`: 1.1.0, and the cite and excerpt scrubbed of the names.
  * `position_classification.py`: `model_candidate` takes the reading's names, and a run builds them.
  * `landscape_model_evaluation.py`: the third list holds tournaments only, and
    `FormatEvaluation.repair_cassettes`. Adds `scans_clean`, `scanned_cassettes`, `scanned_repairs` and
    `committed_positions`. The evaluation and the breakdown read the same filtered cassettes.
  * `landscape_seeding.py`: sets each team's tournament.
* **`debate_cli`**: `commands/landscape.py` adds `scan.repair_cassettes` to the summary. A name there
  fails the evaluation, and the display and help say so. `container.py` is untouched.
* **Tests**:
  * new: `test_third_list_scrub.py` and `tests/smoke/test_landscape_evaluate_smoke.py`;
  * added to: `test_model_stage.py` (arguments) and `test_landscape_model_stage.py`;
  * rewritten by hand for the new rules: t39's `test_evaluation_scan_hits.py` and
    `test_landscape_evaluation_breakdown.py`'s hit expectations and answer keys;
  * pins moved from 1.0.0 to 1.1.0 in `test_landscape_command.py`, and t07's version-bump test now runs
    1.0.0, then 1.1.0, in `test_position_classification.py`.
* **Docs**: `docs/runbooks/landscape-model-evaluation-record.md` (new). The replay runbook gets its
  checkout section. `docs/data/landscape-model-evaluation.md` gets what changed, with no new counts.

## Deviations from the spec

None to the scope. Three choices go a step beyond the PM's words. Each is listed under decisions for the
PM to keep or drop:

* the generic-position line in the prompt (decision 3);
* the scan's prompt-version filter (decision 4);
* `generic.yaml`'s descriptions (decision 1).

## Decisions and assumptions

1. **"Every NHI position" includes `generic.yaml`'s Policy positions.** The prompt sends the merged
   taxonomy, and 5 of t39's 34 positions (`politics-da`, `cap-k`, `generic-k`, `colonialism-k`,
   `generic-theory`) are generic. A description is wording that moves no count, so each file takes a
   patch bump (the taxonomy guide's rule).
2. **The descriptions are drafts, committed.** The test and the request need them in the file. The
   header comment of each file says they wait on the coach, and they reach a model only through the
   re-record that waits on his approval.
3. **The prompt adds one line beyond the brief.** "When the list has a generic position of a kind, whose
   description says it fits no named position of that kind, choose it ... rather than answering null."
   It is aimed at `generic-k` being refused 3 of 3. It leans on the descriptions, so it is
   topic-neutral. 1.1.0 is released and locked (ac1 asks for it locked). Dropping or rewording the line
   before the re-record means a 1.1.1, which costs nothing, since nothing is recorded under 1.1.0 yet.
4. **The evaluation scans only the cassettes of the prompt version it ran.** Otherwise t39's three 1.0.0
   cassettes, whose heading paths hold the 9 names, would fail every future evaluation's scan however
   clean 1.1.0 is. A text whose version cannot be read is still scanned, so the filter fails toward
   reading more. The repair cassettes were already filtered by prompt version and caselist (t39).
5. **The positions text is cut by equality with the committed taxonomy's.** A cassette or repair
   cassette recorded under the same taxonomy loses exactly that text. One recorded under another
   taxonomy shows its taxonomy words as hits, and that is the safe direction to fail in.
6. **A list of strings alone is one value to the scan** (a heading path), so a name the scrub misses
   across two headings still counts, as t39's listing showed. Values from different keys never join.
7. **The third-list scrub is the model stage's alone.** `card_tag` takes it as an option. t21's local
   classifier and the queue order read tags without it, as their proxy model was trained. That rule is
   unchanged.
8. **The smoke check records in its own process.** The checkout's evaluation records over a scripted
   model, and the build under test replays. On validate-dev both are the same commit, so a build that
   asks differently fails as `MISSING_FIXTURE_ERROR`. The model stage needs a checkout's `prompts/`, so
   the build runs in a scratch directory holding a copy of `prompts/` and an empty `config/profiles/`.
   No harness code changed.
9. **Batches stay at 20, and the bar, the set, the labels and the review threshold are untouched.**

## Operator follow-ups

### 1. The 13 rows, by number

Run now, no need to wait on anything. It replays t39's 1.0.0 recording, which only a checkout of
t39's merge can do (this branch asks for 1.1.0), so it goes in a scratch worktree. No model is called.
Expected runtime: about 2 minutes for the setup, about a minute for the listing.

Setup, once. It adds a scratch worktree at t39's merge commit beside this one, and syncs its venv:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t40-model-stage-reads-the-argument-not-the-subject
git worktree add --detach ../t39-replay-rows 28d4c88
cd ../t39-replay-rows && uv sync --quiet --all-packages
```

The listing. The evaluation's JSON goes straight into a filter that prints only sample row numbers:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/t39-replay-rows
```

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --breakdown | uv run python -c 'import json, sys; d = json.load(sys.stdin); b = (d.get("data") or d["error"]["details"])["breakdown"]; rows = lambda o: sorted(c["sample_row"] for c in b["cards"] if c["outcome"] == o); print("wrong position of the label kind:", rows("wrong_position_same_kind")); print("placed though labelled none:", rows("placed_labelled_none"))'; fi
```

Success looks like two lines, the first with 9 numbers and the second with 4. Paste them back, or
straight to the PM for the coach. A Python `KeyError` means the replay did not run as t39's did: paste
nothing, and say so.

Then remove the scratch worktree. It holds nothing but the checkout and its venv:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t40-model-stage-reads-the-argument-not-the-subject
git worktree remove ../t39-replay-rows
```

### 2. After the coach approves: re-record the 47 under 1.1.0

**Do not run this until the PM relays the coach's approval of the descriptions** (the spec forbids a
re-record before it). If the coach corrects descriptions, the corrections are committed first, at
taxonomy 1.4.2. The steps are `docs/runbooks/landscape-model-evaluation-record.md`'s 2 to 4, copied
here; read the runbook for what each output means. Paste back only the JSON: never the terminal
listing of hits (policy 1.21).

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t40-model-stage-reads-the-argument-not-the-subject
```

Step 2: what the recording will read, with no model call (about a minute). Expected: `error.code`
`MISSING_FIXTURE_ERROR` naming `landscape.classify_position@1.1.0`. Stop on anything else.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl; fi
```

Step 3: record (about a minute; the live calls are made here, 3 or 4 of them, a few cents). Expected:
`prompt_version` `1.1.0`, `labelled`, `found` and `asked` all 47, and the three `scan` entries. Exit 0
means it meets the bar with clean scans; exit 1 `EVALUATION_BELOW_BAR` holds the same counts in
`error.details`. Paste the JSON.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --model-mode record; fi
```

Step 4: the breakdown as JSON (about a minute, no model call). Expected: the same counts, and
`breakdown.outcomes` summing to 47. Paste the JSON.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run debate-research --json landscape evaluate --caselist hspolicy26 --snapshot 2026-10-20 --sample ~/Documents/debate/landscape-review/policy-2026-27-nhi-coach-sample-labelled.csv --sample-rows ~/.debate-research/dev/landscape/local-classifier/hspolicy26/policy-2026-27-nhi-coach-sample.jsonl --breakdown; fi
```

The counts then go to `docs/data/landscape-model-evaluation.md`. If accuracy meets 85% with a clean
prompt-input scan, the PM can lift the hold on live runs. If not, the breakdown and the options go to
the PM.

## Follow-up work

* **The 1.0.0 cassettes still hold names.** The three classify cassettes and the one repair cassette on
  the operator's Mac carry the 9 heading-path names t39 found (6 again in the repair cassette).
  Condition 4 of the data-use policy says a cassette never holds them. `landscape cassettes --delete`
  removes a whole caselist's cassettes, the 1.1.0 ones included, so removing 1.0.0's alone needs a
  `--prompt-version` option or a hand step. For the PM: see question 2.
* **If 1.1.0 falls short: the card's side.** The disclosing team's side of the round (aff or neg) is
  known for every card and is not an identifier. Sending it is the most direct fix left for
  other-side answers (10 of t39's 11 wrong-kind answers). It is a prompt input, so it is a prompt
  1.2.0 and a new task, not this one.

## Questions for the PM

> **v1-e32-t40: the code is done; two things wait on the coach, and three choices are yours.** The
> Goal stays `InProgress`: ac2 (the coach's approval and his answer on 13 rows) and ac3 (the re-record)
> are NOT RUN. ac1 and ac4 pass. The report is `docs/session-reports/v1-e32-t40-model-stage-reads-the-argument-not-the-subject.md`.
>
> 1. **For the coach.** (a) The review sheet in the report: 103 positions with id, kind, side and a
>    one-line description, 14 marked as guesses (the three Ts on single and multi-payer, `ucf-cp`,
>    `trump-k` and others). Approve, or correct rows. (b) The 13 rows (9 same-side neighbours, 4 placed
>    though labelled none): should those positions be told apart at all? Their numbers come from
>    operator follow-up 1, a JSON-only command that prints two lists of row numbers. Corrections land
>    as taxonomy 1.4.2, and then the operator runs follow-up 2, the re-record.
> 2. **The 1.0.0 cassettes hold 9 real names** (policy condition 4). Options: (a) after the 1.1.0
>    re-record is accepted, delete them, by hand, or through a new `--prompt-version` option on
>    `landscape cassettes`, a small follow-up task; (b) keep them until the 36.8% diagnosis is closed;
>    (c) delete all hspolicy26 cassettes now and re-record after. **Recommended: (a)**. No checkout
>    after this merge can replay them anyway, the evaluation no longer reads them, and the 1.1.0
>    recording survives.
> 3. **The prompt's line on generic positions** (decision 3). It goes beyond your three asks and is aimed
>    at `generic-k` refused 3 of 3. **Recommended: keep it.** Dropping it before the re-record costs a
>    1.1.1 and nothing else.
> 4. **The scan reads only the cassettes of the prompt version that ran** (decision 4). Without the
>    filter, 1.0.0's cassettes fail every later scan. A text with no readable version is still scanned.
>    **Recommended: keep it.**
> 5. **Descriptions on `generic.yaml`'s 21 Policy positions too** (decision 1). Five of t39's 34
>    positions are generic. **Recommended: keep them**, at generic 1.1.1.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
