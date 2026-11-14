# V1 acceptance criteria, and the end-to-end tests that cover them

Each criterion of the architecture proposal's §11 ("V1 acceptance criteria",
[`docs/architecture/architecture_proposal.md`](../../docs/architecture/architecture_proposal.md)),
with the tests in this directory that prove it through the CLI's own entry point, every boundary
recorded (`v1-e09-t05`). A criterion no test here covers is listed as uncovered, with the reason.

Every test here is marked `slow`: the PR `ci` check leaves them out, and validate-dev's slow tier and
the nightly run take them. Run them with:

```bash
uv run pytest -m slow tests/integration
```

The test files are written `research` for `test_e2e_research.py`, `failures` for
`test_e2e_failures.py` and `caselist` for `test_e2e_caselist.py`; each id below is a node id in that
file.

## 1. At least one scholarly source adapter and one current-news/RSS adapter work through the common SearchProvider interface

Covered. The real OpenAlex adapter and the real publisher-feed (RSS) adapter, each wrapped in the
production `ResilientProvider` in a `ProviderRegistry`, answer from recorded bodies.

| Test | What it shows |
|---|---|
| `failures::test_a_provider_outage_makes_the_search_partial_exit_6_naming_the_provider` | both adapters asked through the registry for one search: OpenAlex's outage is reported per provider (`openalex: error`), the feed's two items are the results (`rss: ok`), exit 6 `SEARCH_PARTIAL` |
| `research::test_search_auto_cut_3_writes_three_verified_cards_and_a_bannered_unverified_one_and_verify_agrees` | OpenAlex's recorded works become the ranked results that `--auto-cut 3` cuts |

## 2. Accessible URL → verified card works end to end with tag, cite, verbatim evidence, underlining, and DOCX export

Covered.

| Test | What it shows |
|---|---|
| `failures::test_cut_writes_each_kind_of_sources_card_from_its_snapshot_and_verify_agrees[news]` | `cut <URL>`, exit 0, VERIFIED: the DOCX holds the tag, the short cite `Whitfield 26`, the page's second paragraph verbatim and its underlined run; `verify` passes it |
| `failures::test_cut_writes_each_kind_of_sources_card_from_its_snapshot_and_verify_agrees[think-tank]` | the same for a think-tank report (`Ellery et al. 26`) |
| `failures::test_cut_writes_each_kind_of_sources_card_from_its_snapshot_and_verify_agrees[open-access journal]` | the same for an open-access journal PDF, cited from Crossref's recorded answer (`Okonkwo-Hale et al. 26`) |
| `research::test_search_auto_cut_3_writes_three_verified_cards_and_a_bannered_unverified_one_and_verify_agrees` | search → `--auto-cut 3` → one DOCX bundle of three VERIFIED cards under one block heading and, in its section under "UNVERIFIED — not finished cards", the government press release's card with `CITATION_UNVERIFIED` (ranked before the third VERIFIED card since `v1-e08-t24`, never counted toward the three), its embedded manifest equal to `bundle.manifest.json`; `verify bundle.docx` agrees card by card, three VERIFIED and the bannered one UNVERIFIED with `CITATION_UNVERIFIED`, exit 1 (`v1-e08-t26`) |
| `research::test_search_auto_cut_2_stops_before_the_press_release_and_verify_passes_the_whole_bundle` | the same search with `--auto-cut 2`: its two cards, the think-tank report and the open-access PDF, are ranked above the press release, so the search stops before it; the bundle holds VERIFIED cards only, with no UNVERIFIED section, and `verify bundle.docx` passes the whole bundle, exit 0 (`v1-e08-t28`) |

## 3. No generated evidence can pass verification unless it is reproducible from a stored source snapshot

Covered.

| Test | What it shows |
|---|---|
| `research::test_search_auto_cut_3_writes_three_verified_cards_and_a_bannered_unverified_one_and_verify_agrees` | each card's evidence, the bannered UNVERIFIED card's too, is the stored snapshot document's text at the card's offsets, those offsets are the ones worked out by hand from the page's paragraphs, and the raw snapshot is the recorded page's bytes |
| `research::test_search_auto_cut_2_stops_before_the_press_release_and_verify_passes_the_whole_bundle` | the same for the clean bundle's two cards, and `verify` ran its snapshot checks on each (`snapshot_integrity`, `card_matches_snapshot`, `evidence_reconstructed`, `evidence_text_exact` among them) before it passed it |
| `research::test_the_bundle_does_not_verify_where_its_snapshots_are_not_stored` | the same bundle, verified against a data directory that never stored its sources: every card UNVERIFIED with `SNAPSHOT_MISSING`, the bannered one with `CITATION_UNVERIFIED` before it, exit 1 |
| `failures::test_a_hand_edited_evidence_word_in_an_exported_docx_makes_verify_fail_with_manual_edit` | one evidence word changed in an exported DOCX: UNVERIFIED with `MANUAL_EDIT`, exit 1; the untouched file still verifies |

## 4. Golden-card tests verify exact text and formatting against representative debate cards

**Uncovered here, by design.** The task's boundary is that it does not re-test golden formatting:
golden DOCX regression tests are
[`v1-e09-t02-docx-golden-tests`](../../plan_specs/v1/e09-v1-quality-pilot/t02-docx-golden-tests.yaml),
over the golden card fixtures of
[`v1-e09-t01-golden-card-fixtures`](../../plan_specs/v1/e09-v1-quality-pilot/t01-golden-card-fixtures.yaml).
Both were `Pending` when this map was written (2026-11-04). The tests in criterion 2 check that the
tag, cite, evidence and underlining are present, not the exact runs, styles and ranges a golden file
pins.

## 5. CLI output includes explicit retrieval/verification failures instead of silently fabricating metadata

Covered. Each test asserts the documented exit code and the error or reason code, in the JSON envelope
and in what the command prints, never a message's wording.

| Test | What it shows |
|---|---|
| `failures::test_cut_of_a_paywalled_or_robots_disallowed_url_exits_3_with_its_access_status_and_writes_nothing[paywalled]` | exit 3, `SOURCE_NOT_ACCESSIBLE`, `PAYWALLED`, no card and no file |
| `failures::test_cut_of_a_paywalled_or_robots_disallowed_url_exits_3_with_its_access_status_and_writes_nothing[robots-disallowed]` | exit 3, `SOURCE_NOT_ACCESSIBLE`, `ROBOTS_DISALLOWED`, no file, and the page never requested |
| `failures::test_cut_writes_each_kind_of_sources_card_from_its_snapshot_and_verify_agrees[government PDF]` | a PDF with no author, title, publication or date to read: exit 4, `CARD_UNVERIFIED` with `CITATION_UNVERIFIED`, the UNVERIFIED banner in the DOCX, and `verify` agreeing; no cite is filled in |
| `failures::test_a_provider_outage_makes_the_search_partial_exit_6_naming_the_provider` | exit 6, `SEARCH_PARTIAL`, the failed provider named |
| `failures::test_a_hand_edited_evidence_word_in_an_exported_docx_makes_verify_fail_with_manual_edit` | exit 1, `UNVERIFIED`, `MANUAL_EDIT` |
| `research::test_the_bundle_does_not_verify_where_its_snapshots_are_not_stored` | exit 1, `UNVERIFIED`, `SNAPSHOT_MISSING` |
| `research::test_search_auto_cut_3_writes_three_verified_cards_and_a_bannered_unverified_one_and_verify_agrees` | the robots-disallowed and paywalled results listed in `report.json` as `SKIPPED` with their access status |

## Beyond §11: the V1 caselist workflow

§11 predates the caselist epics; the task spec adds their workflow as scenario 6.

| Test | What it shows |
|---|---|
| `caselist::test_caselist_import_parse_landscape_files_build_and_store_sync_on_a_synthetic_archive` | an invented weekly archive imported (2 NEW, 1 DUPLICATE) and parsed (4 cards), a landscape report with the model stage replayed from a committed cassette (3 cards placed by alias, 1 by the model), a file built whose evidence hashes are the cards' own text, and `store sync --apply` to a moto bucket whose objects' bytes, local files and SHA-256 metadata agree |

## The suite's own rules

[`conftest.py`](conftest.py) disables Internet sockets for every test and shows one refused, refuses
at collection a module here without the module-level `slow` mark or with a socket opt-out, and gives
each test a data directory and `HOME` of its own. A missing recording is a `MissingFixtureError`,
never a skip ([`e2e_harness.py`](e2e_harness.py)).
