# Session report: v1-e06-t02-card-service

| | |
|---|---|
| Task | `v1-e06-t02-card-service` — CardService pipeline |
| Spec | [`plan_specs/v1/e06-card-cutting/t02-card-service.yaml`](../../plan_specs/v1/e06-card-cutting/t02-card-service.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t02-card-service` |
| Session status | COMPLETE |

## Summary

`CardService.cut_card` (`debate_core.application.card_service`) turns a stored snapshot and a research
need into a saved card. It reads the snapshot record and refuses one that is not ACCESSIBLE with
`SourceNotAccessibleError` (code `SOURCE_NOT_ACCESSIBLE`, t06's), before any model call. Otherwise it
loads the snapshot with every integrity check and runs, through injected services: `card.select`
(fail-closed), extraction from the snapshot, `card.markup` and the mapping onto `CardSpan`s, the tag,
CitationService, EvidenceVerifier, and one `CardRepository.create` at revision 1. Evidence text is
always the snapshot slice. Each model failure, unfit span or unverified required cite field after the
snapshot is loaded becomes a typed `CardFailure` on a saved UNVERIFIED card. The card keeps both
calls' `SourcedArtifactMetadata` as `generated_by`. The three cite rules of the PM's amendment are in,
each shown red first: a verified `retrieval` source, organization authors, and cleared fields that
stay cleared. Every criterion passed, 22 mutants were all caught, and the Goal is `Succeeded`.

What the PM should look at first:
* **Decision 1:** provider outages, missing snapshots and damaged snapshots propagate with nothing
  saved. The PM's note says "every failure after the snapshot exists saves an UNVERIFIED card". I read
  that as failures about the card, as the spec's parenthesis lists them. Question 1 asks the PM to
  confirm.
* **The schema changes** (Card, Citation, CitationFieldSource) are explained field by field under
  Decisions.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `request-result-types` | Done | `application/card_types.py`. Red against a skeleton that checks nothing (`895149e`): 10 failed, 2 passed. Green (`a2f24f3`): 12 passed. |
| `happy-path` | Done | `application/card_service.py`, `Card.generated_by`, the fake router's two hand-written answers, `tests/fixtures/card/card_world.py`. Red against a skeleton that saves a blank card (`4e99e02`): `-k verified` 6 failed, 3 passed (of the 7 new tests, 6 failed, 1 passed). Green (`8818c36`): 9 passed. |
| `unverified-paths` | Done | Tests written against the implementation, then run once against `4e99e02`'s skeleton `card_service.py` and restored (byte-checked): 15 failed, 3 passed of 18 (`41949fc`). The 3 that passed describe what the skeleton already did: an UNVERIFIED result must say why, a missing snapshot raises `NotFound`, and re-verifying an UNVERIFIED card stays UNVERIFIED. |
| ac5: the three cite rules | Done | Each red first against the tree before it, then green. **Retrieval source**: `068c14f` 33 failed, 108 passed; `f67bea5` 144 passed (in the same three files, after one t01 pin changed; see Deviation 4). **Organization authors**: `e702b68` 15 failed, 188 passed; `ea3dbc0` 203 passed. **Cleared fields**: `03dcb5f` 6 failed, 101 passed; `4113562` 108 passed. |
| `offline-e2e` | Done | `tests/application/test_card_service_e2e.py`. Run against `4e99e02`'s skeleton and restored: 2 failed. Green (`150f0b8`): 2 passed. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: on a recorded accessible article with fake-router fixtures, cut_card returns a VERIFIED Card whose evidence_text equals the snapshot slice, with tag, citation, CardSpans and snapshot_id/sha256 set | PASS | `uv run pytest packages/debate_core/tests/application/test_card_service.py -k verified` → 29 passed. The page is t04's synthetic news article, stored with t04's hand-written paragraphs as its text. The `card.select` and `card.markup` answers are hand-written files under `tests/fixtures/model_outputs/` holding offsets and paragraph numbers only. `test_an_accessible_article_is_cut_into_a_verified_card_whose_evidence_is_the_snapshot_slice` checks the evidence against a literal written from the paragraphs and against `text[212:320] + text[422:712]`. It also checks the envelope (212, 712), the omission (320, 422) and the tag. `test_the_verified_card_carries_its_snapshot_spans_and_cite` checks `snapshot_id`, `normalized_text_hash` (the snapshot's SHA-256) and `normalizer_version`, and the five spans with the words each marks (written by hand). It also checks that the cite is CitationService's and fully verified. |
| ac2: a ModelOutputError, an unreproducible span or a missing author/date yields a persisted UNVERIFIED card with machine-readable reasons | PASS | `uv run pytest packages/debate_core/tests/application/test_card_service.py -k "unverified or rejected"` → 29 passed. One test per reason, each reading the card back from the repository: `MODEL_OUTPUT_INVALID` for a refused selection and for a refused markup; `SPAN_MISMATCH` for a selection off the end of the snapshot and for markup across a cut; `CITATION_UNVERIFIED` naming `published_at` (the news page with its three date statements removed) and naming `authors` (its three author statements removed). `EVIDENCE_UNVERIFIED` with `CARD_INCOMPLETE` appears beside each model or span failure. A parametrized test maps all ten verifier codes, and every failure detail is checked to quote no word of the snapshot or tag. |
| ac3: a snapshot whose access_status is not ACCESSIBLE is rejected before any model call with a typed SourceNotAccessibleError and no card is created | PASS | Same command. `test_a_snapshot_that_is_not_accessible_is_rejected_before_any_model_call` covers each of the seven other statuses. Each raises `SourceNotAccessibleError` (code `SOURCE_NOT_ACCESSIBLE`), makes zero calls on the counting router around the fake, and stores no card. |
| ac4: the persisted card carries GeneratedArtifactMetadata (model_id, prompt ids/versions, temperature, snapshot_id) and a format_profile name, and re-running verification reproduces the same status | PASS | `test_the_verified_card_records_the_model_prompt_and_parameters_of_both_calls` reads the stored card: `card.select` and `card.markup` at 1.0.0, model `fake-fixture-model`, temperature `None` (nothing sent, so the route's default applied), the snapshot id, and `team-default`. A named profile is kept (`camp-condensed`). Re-verification: `test_re_verifying_a_saved_verified_card_reproduces_its_status` and `..._unverified_card_reproduces_its_status_and_reasons`, plus both e2e tests over a reopened SQLite store and a fresh verifier. |
| ac5: retrieval source, organization authors, cleared fields, tests shown failing first | PASS | Red and green counts per rule under Plan nodes. The tests are in `test_citation_service.py` (cite level), `test_citation_harvest.py` (harvester) and `test_card_service.py` (card level). An open-access PDF and an agency-authored release are both cut into VERIFIED cards. A cleared required field leaves the card UNVERIFIED with `CITATION_UNVERIFIED: ... authors`. `test_a_field_the_student_emptied_is_derived_again` is now `test_a_field_the_student_cleared_stays_cleared_on_re_resolution`. |
| Node `request-result-types`: `card_types.py` contains `class CutResult` | PASS | `grep -c "class CutResult" packages/debate_core/src/debate_core/application/card_types.py` → 1 |
| Node `happy-path`: `uv run pytest packages/debate_core/tests/application/test_card_service.py -k verified` | PASS | 29 passed in 2.12s (`-k verified` also selects every name containing "unverified") |
| Node `unverified-paths`: `... -k "unverified or rejected"` | PASS | 29 passed in 2.64s |
| Node `offline-e2e`: `uv run pytest packages/debate_core/tests/application/test_card_service_e2e.py` | PASS | 2 passed in 2.29s |
| Node `offline-e2e`: `uv run lint-imports` | PASS | Contracts: 18 kept, 0 broken. Planting `import httpx`, `typer`, `boto3` and `fastapi` in turn in `card_service.py` broke one contract each (17 kept, 1 broken); restored. |
| Forbidden: evidence text on a card that did not come from span extraction over the stored snapshot | Holds | The only text that reaches a card goes through `EvidenceExtractor.extract` over `SnapshotService.load`'s text and `place_evidence_on_card`. Model answers carry offsets only. |
| Forbidden: marking a card VERIFIED when any verifier check or required citation field fails | Holds | Only `EvidenceVerifier.verify_and_record` sets a status, and `CutResult` cannot be built VERIFIED with a reason. PM mutant "cite attached after verification" was caught (4 failed). |
| Forbidden: typer/fastapi/boto3/httpx in `debate_core.application` | Holds | lint-imports, as above. |
| Forbidden: live network or model calls in tests | Holds | The fake router and `ScriptedModelRouter`, respx for Crossref, and t06's replay transport, which answers only from the cassette (`transport.unrecorded == []`). |

### Mutation run (agreement 8)

22 mutants over `card_service.py`, `card_types.py`, `citation_service.py`, `citation_harvest.py`,
`edit_policy.py` and `domain/card.py`. Each was planted on a committed tree by exact-string
replacement, and each replacement was asserted to occur once, so none went in unplanted. Each ran
against the five covering files (`test_card_service.py`, `test_card_service_e2e.py`,
`test_citation_service.py`, `test_card_edit_service.py`, `test_citation_harvest.py`) with
`-n 0 -p no:randomly` and a fresh `HYPOTHESIS_STORAGE_DIRECTORY` each. Afterwards the original bytes
were written back and compared, and `git diff --quiet` was clean at the end. Of the five files only
`test_card_edit_service.py` imports Hypothesis, and no catch below is one of its properties. Baseline:
256 passed.

| Mutant | Caught by (first failure) |
|---|---|
| **PM:** card verified with a stand-in verified cite, then saved with its real one (a required field unverified) | 4 failed: `a_card_whose_page_states_no_date_is_saved_unverified_naming_published_at` |
| **PM:** an inaccessible snapshot reaches the router (access check removed) | 7 failed: `not_accessible_is_rejected_before_any_model_call[UNKNOWN]` |
| **PM:** an inaccessible snapshot reaches the router (checked after a selection call) | 7 failed: the same |
| **PM:** re-resolution refills a cleared field (`keep_student_edits` ignores the list) | 4 failed: `a_field_the_student_cleared_stays_cleared_on_re_resolution` |
| **PM:** re-resolution refills a cleared field (the edit policy records none) | 4 failed: the same |
| the edit policy also records what an edit claims it cleared | **survived** at first: the test only claimed a field the edit filled. Strengthened with a claimed field that was never filled (`f3b356e`) and run again: 1 failed, `what_an_edit_says_it_cleared_is_not_read` |
| a refused selection is raised, not recorded | 3 failed |
| a refused markup drops the evidence | 2 failed |
| markup that does not fit drops the evidence | 1 failed |
| `TEXT_MISMATCH` mapped to `EVIDENCE_UNVERIFIED` | 1 failed: `each_verifier_code_becomes_one_unverified_card_failure[TEXT_MISMATCH]` |
| a VERIFIED result may carry a reason | 1 failed |
| the argument is not put to the model | 16 failed |
| the tag stays the student's need | 3 failed |
| the model calls' provenance is not kept | 6 failed |
| a card may record a call shown another snapshot | 1 failed |
| the accessed date verified whatever the provenance | 9 failed |
| the retrieved URL a heuristic again | 12 failed |
| an organization stands in beside a named person | 3 failed: `never_stands_in_beside_a_named_person[meta_tag]` |
| only the bare `Organization` type counts | 7 failed |
| `og:site_name` becomes an organization author | 6 failed |
| an organization's JSON-LD credentials kept | 1 failed |
| an organization's short cite takes its last word | 2 failed |

### Checks before the report (agreement 10)

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (list only) | 521 of 535 test files, from 33 changed files. `domain/card.py` reaches every test through the root conftest's imports. That is the whole selection, past the two-minute line, so it was not run and is left to the PR's `ci` (PM ruling of 2026-10-19). |
| First attempt at a scoped run, with all of `tests/application/` included, under `alarm 115` on the interpreter | Stopped by the alarm at 115 s before it finished: no result. No orphaned workers were left (`pgrep`). |
| `.venv/bin/python -m pytest -n 8 -m "not slow and not live"` over `tests/domain`, `tests/evidence`, `tests/retrieval`; from `tests/application`: `test_card_service.py`, `test_card_service_e2e.py`, `test_citation_service.py`, `test_card_edit_service.py`, `test_verify_manifest.py`, `test_article_fetch.py`, `test_article_service.py`, `test_snapshot_service.py`, `test_port_conformance.py`, `test_structured_output.py`, `test_errors.py`; `integrations/models/test_record_replay.py` (the fixture scrub check), `test_fake_router.py`, `test_artifact_metadata.py`, `test_crossref_doi.py`, `local/test_sqlite_repos.py`; `debate_cli` `test_verify_command.py`, `tests/integration/test_verify_cli.py`, `tests/smoke/test_cli_smoke.py`, `tests/fixtures/test_cassette_hygiene.py`; the always-run list (`tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`) | 4539 passed in 37.09s |
| The e2e builds the real fetcher, which filters the process-wide httpx loggers, so in one process with `-n 0 -p no:randomly`: `test_card_service_e2e.py`, `test_http_fetcher.py`, `test_crossref_doi.py`, `test_citation_service.py`, then the reverse order | 240 passed (2.37 s); 240 passed (0.62 s) |
| `uv run --frozen ruff format --check .` / `ruff check .` | 1491 files already formatted / All checks passed |
| `uv run --frozen pyright` (whole repo, as CI) | 0 errors, 0 warnings, 0 informations |
| `uv run --frozen lint-imports` | Contracts: 18 kept, 0 broken |
| `uv run --frozen python scripts/check_thin_handlers.py` | OK: 67 CLI command and API route handlers within 25 statements |
| `uv run scripts/export_schemas.py --check` | OK: 10 schemas up to date |
| `uv run scripts/validate_specs.py` / `--require-succeeded v1-e06-t02-card-service` | OK: 478 files, 40 epics, 416 tasks, 22 releases / Succeeded |
| After this report: `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | OK: no `#` comments in 505 shell code blocks in 185 Markdown files (1 session report changed) |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | All 54 indexed documents under docs/ have a description |
| `pytest tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py` | 191 passed in 2.04s |

## Files changed

* **`debate_core.application`**: `card_types.py` (new): `CutRequest`, `CutResult`, `CardFailure`,
  `CardFailureReason`, `SourceNotAccessibleError` and the `CardSelecting` protocol. `card_service.py`
  (new): `CardService` and `failures_of`. `citation_service.py`: the retrieval source, organization
  authors, cleared fields, an organization's name whole in the short cite. `CITATION_FIELD_NAMES` now
  comes from the domain and is re-exported unchanged.
* **`debate_core.domain`**: `Card.generated_by`; `Citation.authors_are_organizations` and
  `Citation.cleared_by_student`, with validators; `CITATION_FIELD_NAMES`;
  `CitationFieldSource.RETRIEVAL`.
* **`debate_core.retrieval`**: `citation_harvest.py`. The URL of last resort is now `retrieval`. JSON-LD
  organization authors are kept apart as `organization_authors` (`ORGANIZATION_TYPES`), and
  credentials come from person authors only.
* **`debate_core.evidence`**: `edit_policy.py`. A cite edit records the fields it empties. The
  check that a changed field is not marked verified now compares cite fields only.
* **`packages/debate_core/schemas`**: `card.schema.json`, `citation.schema.json` (regenerated; see
  Decisions).
* **Tests**: `tests/application/test_card_service.py` (new, 51 tests), `test_card_service_e2e.py`
  (new, 2). Changed: `test_citation_service.py`, `tests/retrieval/test_citation_harvest.py` and
  `tests/domain/test_enums.py` (Deviation 4).
* **Fixtures (repository `tests/fixtures/`)**: `card/card_world.py` (new); two hand-written answers in
  `model_outputs/card.select/` and `model_outputs/card.markup/`; in `citation/`, the six expected
  cites edited by hand, `organization-report.html` and its `.expected.json`, the README row, and
  `citation_world.CASES`; `verify/*.json` regenerated by `manifest_world` (each card gains
  `generated_by: []`, each cite `authors_are_organizations: false` and `cleared_by_student: []`,
  nothing else).
* **Spec**: the Goal's phase, `Succeeded`.

## Deviations from the spec

1. **Files outside `constraints.packages`.** The fixtures in the repository's `tests/fixtures/`
   (`card/`, `model_outputs/`, `citation/`, `verify/`) are outside the listed packages. The PM's note
   names `model_outputs/` and t01's expected JSON. `card/card_world.py` follows `citation_world.py`'s
   place, since a test module under `packages/debate_core/tests` cannot import a sibling helper
   (importlib mode). `verify/*.json` are generated files that pin Card's JSON form, so they change with
   it.
2. **"CardRepository.save at revision 1" is `CardRepository.create`.** The port's `save` updates a
   stored card and refuses a new one; `create` stores a new card at revision 1.
3. **`CutRequest` has two fields beyond the spec's four**: `owner_id` (a Card requires its student)
   and an optional `organization_id`.
4. **t01's tests changed where the PM's rules change what they pin.**
   * The six hand-written expected cites: `accessed_at` becomes `retrieval`, verified for the five
     publisher-retrieved cases. The PDF's and the pasted text's URLs become `retrieval`, verified for
     the PDF only. `unverified_fields` follows.
   * `PAGE_METADATA_OF_THE_JOURNAL`'s accessed date.
   * The precedence test now lists `retrieval`.
   * `test_a_heuristic_value_is_never_verified` no longer lists `accessed_at`.
   * The harvester's seven URL pins.
   * `test_crossref_affiliations_are_credentials_naming_each_author` became `..._each_person_author`.
     The deposited consortium is not an author beside two named people, so its affiliation is no
     author's credential.
   * `test_a_field_the_student_emptied_is_derived_again` was turned, as the PM asked.
   * The `cite_of` helper builds through `evolve`, for pyright.
   * The ac1 test also compares `authors_are_organizations`, against the files that state it.
5. **The failure-path tests use `ScriptedModelRouter` answers written inline**, and two selector
   doubles for `SPAN_MISMATCH`. The PM's note asks for hand-written fake-router files. Those back ac1,
   ac4 and the e2e. A refused answer needs a refused repair after it, which the scripted router
   expresses in one line, as e05-t06's failure tests did. Everything is offsets only.

## Decisions and assumptions

1. **What propagates and what is a reason.** From the selection on, a failure about the card is a
   reason on a saved UNVERIFIED card. That covers a refused model answer, places that do not fit the
   snapshot, and a cite field that is missing or unverified. What is not a verdict about the card
   propagates and saves nothing: a missing snapshot (`NotFound`), a damaged one
   (`SnapshotIntegrityError`), a provider that cannot answer (`ProviderError`), an unregistered
   prompt, and a store error. This is the rule EvidenceVerifier and CardEditService already follow,
   and the spec's description lists the first three. The PM's note says "every failure after the
   snapshot exists", so this is Question 1.
2. **A damaged snapshot is checked before any model call**, because the model may only be shown text
   `SnapshotService.load` has checked. Tested: zero calls, no card.
3. **SPAN_MISMATCH in practice.** The fail-closed guard refuses every offset fault before
   extraction, as `MODEL_OUTPUT_INVALID`. `SPAN_MISMATCH` is CardService's own check on what it is
   given: an unguarded selector (the two doubles), or the verifier's `TEXT_MISMATCH` and
   `SPAN_OUT_OF_RANGE`.
4. **A fourth reason, `EVIDENCE_UNVERIFIED`**, carries any other verifier code in `verifier_code`.
   After a model failure that is usually `CARD_INCOMPLETE`, the consequence kept beside its cause.
5. **The argument.** The model is asked for "argument: need" when an argument is named, else the need,
   and `card.select`'s variables are unchanged. The committed answers were written for "De-extinction
   DA: money spent reviving the mammoth is money lost to living elephants".
6. **A card whose selection was refused** keeps the student's need as its tag (a Card must have one).
   It records the snapshot it was cut from, with no evidence.
7. **format_profile** is `DEFAULT_FORMAT_PROFILE`, `"team-default"`, the constant `domain.card`
   already had.
8. **Metadata.** Each call's `SourcedArtifactMetadata` (the `with_inputs` form e05-t06 introduced) is
   kept as `Card.generated_by` and returned as `CutResult.metadata`. A refused call has no response
   and leaves none; its failure names the prompt and version. Temperature is the route's: `None` when
   nothing was sent.
9. **The schema changes, field by field** (`export_schemas.py --check` OK):
   * `CitationFieldSource` gains `retrieval`, between `byline` and `heuristic`, in both schemas.
   * `Citation.authors_are_organizations` (boolean, default false) is true when `authors` names
     issuing organizations. A validator refuses it without authors.
   * `Citation.cleared_by_student` (array of cite-field names, default empty) lists the fields a
     student's last cite edit left empty, in cite order. A validator refuses a name that is not a cite
     field, and any other order.
   * `Card.generated_by` (array, default empty) holds each model call's provenance. It brings
     `SourcedArtifactMetadata`, `ResolvedRoute`, `TaskClass`, `ModelProvider` and `Effort` into
     `card.schema.json`'s `$defs`. A validator requires each record to name exactly the card's
     snapshot.
   * `card_manifest.v1.json` refers to `card.schema.json` and did not change.
   * Every new field has a default, so stored cards and t05's manifests written before this load
     unchanged. An older build reading a card written by this one refuses the new keys
     (`extra="forbid"`), as with any new field.
10. **Retrieval is ranked below byline and above heuristic.** It is the platform's own record, not a
    guess, and a page's own canonical statement still outranks it.
11. **Organization authors.**
    * They come from typed sources only: a JSON-LD `author` typed `Organization` or one of 23 subtypes
      (`ORGANIZATION_TYPES`; an entry also typed `Person` is a person), or a Crossref contributor with
      a whole name and no family name.
    * Untyped JSON-LD entries, plain strings, meta tags and bylines name people, as before.
    * An organization stands in only when no source names a person: a Crossref person outranks a
      page organization, and a page person outranks a Crossref organization.
    * Credentials are a person author's only, since an organization's affiliation is not a
      qualification.
    * The test organization is t04's invented agency, so the short cite is "Federal Office of
      Synthetic Wildlife 26". The PM's example used a real agency, and fixtures are synthetic.
12. **Cleared fields.**
    * The edit policy decides what is cleared, not the edit. A field counts as cleared when the edit
      leaves it empty and it held a value or was already cleared. A filled field is no longer
      cleared. A claim in the edit's own list is not read.
    * The domain does not require a listed field to be empty. Otherwise a student's editor could not
      fill a cleared field by evolving the stored cite: the cite would be refused before the policy
      saw it.
    * `keep_student_edits` keeps each listed field as stored and names it in `student_fields`.
13. **The fixture page for organization authors** is t04's press release, unchanged except for one
    JSON-LD block added to its head. t04's page itself is untouched. Its text is t04's paragraphs, so
    the card-level test uses them.
14. **Network.** Early in the session I ran one `git fetch origin dev` to see whether e05-t07 had
    landed. It is read-only but a network call, and my standing practice is to hand those to the
    operator. `scripts/task sync`'s own fetch was the PM's instruction. The sync rebased the branch
    (never pushed) onto `a077632` with no conflict. The commit ids in this report are the rebased
    ones, and the task's files were re-run on the synced tree: 256 passed.
15. **A slip, fixed.** `a401a32` was committed on a red run hidden by a pipe to `tail`. Its test
    reused the snapshot id the world had assigned, so nothing differed. `81faa36` fixes the test, and
    later checks were chained bare.

## Operator follow-ups

None. No command needed the network, credentials or more than two minutes. The whole-selection run
is the PR's `ci`.

## Follow-up work

1. **Question 1 for the PM (Decision 1).** Should a provider outage or a damaged snapshot also save
   an UNVERIFIED card? My recommendation is no: neither is a verdict about the card, and t06's `cut`
   can report "could not run" with its own exit code. If the PM wants such cards saved, it is one
   `except` clause and one reason code here.
2. **Wiring (`v1-e06-t06`).** The composition root builds `CardService`: `CardSelector` over the
   real guard and router, and `CitationService` with `crossref_doi_client` over a `FileDoiCache`.
   `test_doctor.py` and `test_installation.py` pin the container's integrations and will change then.
3. **Older builds and the new keys (`v1-e06-t05`, `t07`).** A manifest written after this task
   carries `generated_by`, `authors_are_organizations` and `cleared_by_student`. A build from before
   it refuses them. If t05's manifest promises readability by older builds, its writer should leave
   empty defaults out.
4. **An organization named only as a string.** JSON-LD `"author": "Federal Office of ..."` (untyped)
   stays a person-like author, unmarked, so its short cite takes the last word. The PM's rule takes
   organizations from typed sources only. A format profile (`v1-e06-t03`) may want to revisit it.
5. **Spec wording, if the PM wants it to match:** ac2's examples could add `EVIDENCE_UNVERIFIED`, and
   the happy-path node's "save" could say `create`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
