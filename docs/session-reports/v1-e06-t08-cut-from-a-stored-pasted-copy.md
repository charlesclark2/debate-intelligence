# Session report: v1-e06-t08-cut-from-a-stored-pasted-copy

| | |
|---|---|
| Task | `v1-e06-t08-cut-from-a-stored-pasted-copy` — `cut` can cut a card from the user's own stored copy of an article, with that provenance |
| Spec | [`plan_specs/v1/e06-card-cutting/t08-cut-from-a-stored-pasted-copy.yaml`](../../plan_specs/v1/e06-card-cutting/t08-cut-from-a-stored-pasted-copy.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t08-cut-from-a-stored-pasted-copy` |
| Session status | PARTIAL: built and tested; ac1 waits on the PM's ruling on one word, so the Goal stays InProgress |

## Summary

`debate-research cut URL --from-paste` cuts a card from the copy the coach stored with
`fetch --paste`. It reads the newest USER_SUPPLIED snapshot stored for the URL's canonical form and
makes no fetch. The card carries USER_SUPPLIED on the card, in the manifest and in the `--json`
source, and the manifest's snapshot reference names that copy. Its cite ends "user-supplied text".
The evidence passes every check against the copy, the same checks a retrieved page gets. With no
stored copy, the command exits 1 with a hint that names `fetch --paste`. `fetch`'s exit-3 hint now
names `cut URL --from-paste`.

**Look at Deviation 1 first.** The citation rules verify no cite field of user-supplied text, so
every card cut from a pasted copy is UNVERIFIED for its cite alone. `cut` exits 4 and `verify`
exits 1, each with one reason, CITATION_UNVERIFIED. ac1 says the card "is VERIFIED against that
snapshot", so it is FAIL as written and PASS as amended.

Deviation 2 is the other change the spec didn't foresee. CardService's access gate had to let a
user's copy through, because `fetch --paste` records its status as UNKNOWN.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cut-from-a-stored-pasted-copy` (Pasted copy) | Done; its criterion passes | Red run against a skeleton (`010f976`), implementation (`9207fd2`), installed-build smoke checks (`3a75cf7`), a test the first mutant run showed was missing (`dc6467b`), and a fix the affected set caught (`42c4ae1`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a card cut from a stored pasted copy is VERIFIED against that snapshot | **FAIL as written / PASS as amended** (Deviation 1) | The evidence verifies against the copy: every required check ran, and the only reason is `CITATION_UNVERIFIED` naming all five required cite fields (`test_a_card_cut_from_a_pasted_copy_is_unverified_for_its_cite_alone`, `test_a_user_supplied_snapshot_is_cut_whatever_status_its_user_reported_and_unverified_for_its_cite`). `verify out.docx` → exit 1, reason codes `["CITATION_UNVERIFIED"]`, no `SNAPSHOT_REFERENCE_MISMATCH` or `PROVENANCE_MISMATCH` (`test_verify_finds_a_card_cut_from_a_pasted_copy_true_to_that_copy_and_unverified_for_its_cite_alone`, and the smoke check). The card status is UNVERIFIED, not VERIFIED. |
| ac1: carries USER_SUPPLIED provenance in its manifest | PASS | Manifest card `provenance_mode` USER_SUPPLIED with the pasted snapshot's id. `snapshots` is exactly that copy's reference, hand-written: SHA-256 of the pasted bytes, `user-supplied-text-1`, the canonical URL and the clock's time (`test_the_manifest_of_a_card_cut_from_a_pasted_copy_records_user_supplied_and_references_that_copy`). The stored card row says the same. A card with no evidence placed says it too (`test_a_user_supplied_card_with_no_evidence_placed_still_says_user_supplied`). |
| ac1: makes no fetch | PASS | `seams.transport.requested == []` after `cut --from-paste` (CLI). On the paywalled path the request list is unchanged by the cut. `fetcher.requested_urls == []` in the core tests. The installed build's network-guard log stays empty. |
| ac1: without a stored copy the command refuses with the --paste hint | PASS | Exit 1, `NO_USER_SUPPLIED_COPY`, hint `... fetch --paste FILE --source-url '<url>' --i-have-lawful-access`. No request, no model call, no file and no card, both with nothing stored and with only the publisher's snapshot stored (`test_from_paste_with_no_pasted_copy_stored_exits_1_with_the_fetch_paste_hint_and_fetches_nothing[2]`, plus the smoke check). |
| ac1: fetch's exit-3 hint names the option | PASS | `fetch PAYWALLED_URL` → exit 3. Its hint holds `--paste` and `cut <url> --from-paste`, and following it works end to end (`test_a_paywalled_source_can_be_pasted_and_cut_from_the_paste_as_the_fetch_hint_says`). |
| ac1: by tests shown failing first | PASS | Red against the skeleton at `010f976`: 17 failed, 5 passed (below). Smoke red against a stamped build of the start commit `b132780`: 2 failed. |
| ac1: an installed-build smoke check | PASS | `tests/smoke/test_cut_smoke.py`, two new checks. On an offline stamped, installed build of `42c4ae1` (wheels, `DEBATE_SMOKE_BIN`): cut and fetch smoke, **10 passed in 8.26s**. On the checkout's console script: 10 passed in 5.61s. |
| Node: `uv run pytest packages/debate_cli/tests/test_cut_command.py -k paste` | PASS | **9 passed in 2.98s** (bounded by `scripts/hard_stop.py 115`). |

### Red run

A skeleton that refuses nothing: `--from-paste` accepted and ignored, `user_supplied_copy` falling
back to a retrieval, CardService and fetch's hint unchanged. Command:
`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <the four test files> -k "paste or user_copy or user_supplied" -p no:randomly`
→ **17 failed, 5 passed**. Grouped by reason:

* the cut fetched the page and exited 0 with a VERIFIED, publisher-retrieved card (CLI tests);
* `SourceNotAccessibleError: snapshot ... is UNKNOWN / PAYWALLED` (CardService, two cases);
* `DID NOT RAISE NoUserSuppliedCopy`, and a request where none may be made (core);
* the payload has no `provenance_mode`; the help has no `--from-paste`; the hint has no `cut ... --from-paste`.

The five passes were expected: three existing user-text tests that `-k` also picks, the
reported-ACCESSIBLE case (cuttable before this task), and the invalid-URL refusal (the fallback
raises it too). Smoke red: on a stamped build of `b132780` both new smoke checks failed at the cut
with `No such option: --from-paste` (exit 2), after the build's own `fetch --paste` succeeded.

### Mutants

Thirteen mutants, each against the six covering test files (`test_cut_command`, `test_fetch_command`,
`test_verify_command`, `test_article_service`, `test_article_fetch`, `test_card_service`). No
Hypothesis property covers this code, so agreement 8's database rule does not apply.

| Mutant | Result |
|---|---|
| PM: the card's provenance written as PUBLISHER_RETRIEVED in CardService | **Survived the first run**, caught after a new test. `place_evidence_on_card` copies provenance from the snapshot over CardService's value, so the mutant only shows on a path that places no evidence. On that path a refused selection would have saved a pasted copy's card claiming PUBLISHER_RETRIEVED, which is this task's first forbidden outcome. `test_a_user_supplied_card_with_no_evidence_placed_still_says_user_supplied` (`dc6467b`) catches it: 1 failed. |
| PM: provenance written as PUBLISHER_RETRIEVED in `place_evidence_on_card` | Caught, 8 failed. The first run's version raised NameError (49 errors), which doesn't count as a catch. It was redone import-safe. |
| PM: a fetch made despite `--from-paste` | Caught, 8 failed |
| PM (variant): `user_supplied_copy` fetches when none is stored | Caught, 5 failed |
| PM: no stored paste exits 0 (the publisher's snapshot stands in) | Caught, 2 failed |
| PM: `verify` refuses a USER_SUPPLIED snapshot reference | Caught, 1 failed |
| The access gate not relaxed for a user's copy | Caught, 9 failed |
| The access gate dropped for every provenance | Caught, 7 failed (t02's gate test) |
| `cut` applies the ACCESSIBLE check to a pasted copy | Caught, 6 failed |
| The oldest pasted copy answers, not the newest | Caught, 1 failed |
| fetch's exit-3 hint does not name `--from-paste` | Caught, 1 failed |
| cut's no-copy hint does not name `fetch --paste` | Caught, 2 failed |
| The payload's provenance hard-coded | Caught, 1 failed |

### Checks before the report

* **Affected set**: `uv run scripts/affected_tests.py --run`, bounded by `scripts/hard_stop.py 115`,
  picked **110 of 660 files**. It was stopped at its 115-second limit about 45% through, at a load
  of 13 from other sessions. One test had failed, and a verbose rerun named it:
  `tests/architecture/test_a_command_module_imports_no_other_command.py::...[cut]`. `cut` had
  imported `ATTESTATION_FLAG` from `fetch`. The fix (`42c4ae1`) moves the flag to
  `debate_cli/options/lawful_access.py`, the rule's own place for shared options. The whole set is
  past two minutes at this load, so it is **left to the pull request's `ci`** (agreement 10). Within
  two minutes I ran:
  * the always-run list (`tests/architecture/`, `tests/specs/`, `test_app.py`,
    `test_help_rendering.py`, `test_container_factories.py`) with the cut, fetch and verify command
    tests: **496 passed in 30.70s**;
  * the affected files under the changed areas (`packages/debate_core/tests/application`,
    `packages/debate_cli/tests`, 50 files) in two bounded halves: **664 passed in 83.06s** and
    **759 passed in 11.97s**.
  The remaining 60 affected files lie outside the changed areas and are CI's.
* `uv run --frozen ruff check .` → All checks passed. `ruff format --check .` → 1829 files already formatted.
* `uv run --frozen pyright packages/debate_cli packages/debate_core` → 0 errors. Pyright on `tests/smoke/test_cut_smoke.py` → 0 errors.
* `uv run --frozen lint-imports` → 20 kept, 0 broken.
* `uv run --frozen python scripts/check_thin_handlers.py` → 72 handlers within 25 statements.
* `uv run scripts/validate_specs.py` → OK: 578 files, 41 epics, 515 tasks, 22 releases.
* The spec has not been amended on dev: `git diff origin/dev` on it shows only the phase. I compared
  against the local `origin/dev` ref (644736e), not a fresh fetch.

## Files changed

* `debate_core/application`:
  * `article_service.py`: `user_supplied_copy(url)` and `NoUserSuppliedCopy`;
  * `article_fetch.py`: its report;
  * `card_service.py`: the access gate passes a USER_SUPPLIED snapshot;
  * `card_types.py`: a docstring line.
* `debate_cli`:
  * `commands/cut.py`: `--from-paste`, the no-copy refusal and hint, help and docstring;
  * `presenters/cut_presenter.py`: provenance in the `fetch` progress event, the payload's `source`
    and the table;
  * `commands/fetch.py`: the exit-3 hint, the `--paste` docstring, and the flag now imported;
  * `options/lawful_access.py` (new): `ATTESTATION_FLAG`, shared by both commands.
* Tests:
  * `packages/debate_cli/tests/test_cut_command.py`: 8 tests, 9 cases;
  * `packages/debate_core/tests/application/`: ArticleService 4 tests, ArticleFetch 2, CardService 2;
  * `tests/smoke/test_cut_smoke.py`: 2 checks.

## Deviations from the spec

1. **ac1's "is VERIFIED" can't hold for a pasted copy without inventing a cite.** The spec asks for
   the cite "as the citation rules already treat a user-supplied copy". Those rules (`v1-e06-t01`)
   verify no cite field of USER_SUPPLIED text, not even Crossref's answer for a DOI in its URL.
   t01's hand-written `tests/fixtures/citation/user-supplied.expected.json` shows the result:
   authors and publication missing, everything else unverified. The verifier's `CITATION_VERIFIED`
   check therefore makes every such card UNVERIFIED. `cut` exits 4 with the banner
   `UNVERIFIED — not a finished card: CITATION_UNVERIFIED`, and `verify` exits 1 with that one
   reason. What does hold: the evidence is reconstructed from the copy byte for byte, the
   provenance and snapshot-reference checks pass, and no other reason appears. Proposed amendment
   for ac1: "its evidence is verified against that snapshot, and the card is UNVERIFIED for its cite
   alone, as the citation rules treat a user-supplied copy". Question 1 below.
2. **CardService's access gate changed (t02's ac3).** CardService refused any snapshot not
   ACCESSIBLE. `fetch --paste` records the user's reported status, UNKNOWN, so no pasted copy could
   reach the model. The gate now passes a USER_SUPPLIED snapshot whatever status its user reported.
   That status is the user's report about the publisher ("accessibility is only as reported", on
   `ProvenanceMode`), and the copy was stored only on their lawful-access attestation. The gate is
   unchanged for every other provenance; t02's seven-status test still passes and catches the
   gate-dropped mutant. Question 2 below.

## Decisions and assumptions

1. **The shape is `--from-paste`, a flag.** It cuts the newest USER_SUPPLIED snapshot stored for the
   URL's canonical form. A snapshot id was the alternative, but the coach knows the URL, not a ULID.
   The publisher's snapshot never stands in for a missing copy.
2. **No stored copy exits 1, not 2.** The command line is right; the store doesn't hold the copy.
   That is the same kind of answer as a missing snapshot, which is already 1 for `cut`. A usage
   error (2) is decided before anything is read. The error code is `NO_USER_SUPPLIED_COPY`, named
   for its class like every other.
3. **The manifest's `SnapshotReference` gained no provenance field.** Provenance is on the
   manifest's card, and the verifier's `PROVENANCE_MATCHES_SNAPSHOT` checks it against the stored
   record. The reference names the copy, whose `extractor_version` is `user-supplied-text-1`. A new
   field would mean manifest version 3 and a schema change for no new check.
4. **`cut`'s `--json` `source` gains `provenance_mode`**, and so does the `fetch` progress event. The
   table gains a Provenance row. No test or smoke check pins these key sets whole (checked by grep).
5. **The hints shell-quote the URL** (`shlex.quote`). A URL with `?`, like the news fixture's, would
   otherwise fail in zsh with "no matches found" when pasted.
6. **The test copy is the news article's own text** (t04's paragraphs). The model is shown only the
   numbered text and the need, so the committed `card.select` and `card.markup` answers apply
   unchanged, and every expected value (tag, evidence, underlines) is t06's hand-written one. The
   pasted cite, `[no author] 26 [September 14, 2026; <url>; accessed October 26, 2026; user-supplied
   text]`, and its six marks were derived by hand from the citation and rendering rules before the
   run. The first test placed the cite before the banner; the renderer writes tag, banner, cite, and
   the test was corrected to that order.

## Operator follow-ups

Optional, after this merges and a dev pre-release carrying it is installed on the Mac: one live
cut from a pasted copy, reporting the exit code and status only (the PM's brief). The PM picks the
article. Replace `URL`, `NEED` and the file with the PM's choice. Expected runtime under a minute.

First store the copy (exit 0 and `USER_SUPPLIED` in the table is success):

```bash
cd "$HOME" && env DEBATE_ENV=dev debate-research fetch --paste "$HOME/library-copy.txt" --source-url 'URL' --i-have-lawful-access
```

Then cut it with the live model. The JSON goes to a file and only the exit code is printed:

```bash
cd "$HOME" && env DEBATE_ENV=dev DEBATE_MODEL_MODE=live debate-research --json cut 'URL' --from-paste --need 'NEED' --output "$HOME/pasted-card.docx" > "$HOME/pasted-cut.json"; echo "exit $?"
```

Then the status and reason codes alone:

```bash
cd "$HOME" && python3 -c 'import json; d = json.load(open("pasted-cut.json")); p = d["data"] or d["error"]["details"]; print(p["status"], [r["reason"] for r in p["reasons"]])'
```

Success under ruling (a): `exit 4`, then `UNVERIFIED ['CITATION_UNVERIFIED']`. Paste back those two
lines only.

## Follow-up work

1. **A way to state a pasted copy's cite** (E06 or E04). `fetch --paste` takes no title, author or
   publication, so a pasted copy's cite has none, as this task's cite shows. `--title` and the rest,
   stored unverified like a student's cite edit, would make the exported card's cite usable. It
   would still be UNVERIFIED by the rules.
2. **A cut-specific hint for an unrecorded replay** is t06's follow-up 2. `cut --from-paste` meets it
   the same way.

### Questions for the PM

```text
PM questions from v1-e06-t08-cut-from-a-stored-pasted-copy (2026-11-02)

Facts the spec did not have:
- Citation rules (v1-e06-t01): no cite field of a USER_SUPPLIED snapshot is ever verified, and a
  pasted copy has no markup, so authors and publication are missing
  (tests/fixtures/citation/user-supplied.expected.json). The verifier's CITATION_UNVERIFIED check
  makes every card cut from a pasted copy UNVERIFIED: cut exits 4, verify exits 1.
- CardService (t02 ac3) refused any snapshot not ACCESSIBLE; fetch --paste records UNKNOWN.

Q1. ac1 says the card "is VERIFIED against that snapshot"; the brief says verify "accepts it".
  (a) Keep the cite rules. Built this way: the evidence passes every check against the copy
      (reconstruction, hashes, provenance, the manifest's snapshot reference), and the card is
      UNVERIFIED for its cite alone, its one reason CITATION_UNVERIFIED. cut exits 4 with the banner;
      verify exits 1 with that one reason and no SNAPSHOT_REFERENCE_MISMATCH or PROVENANCE_MISMATCH.
      Amend ac1 to: "its evidence is verified against that snapshot, and the card is UNVERIFIED for
      its cite alone, as the citation rules treat a user-supplied copy".
  (b) Change the cite rules so a pasted copy can verify. Authors and publication still have no
      source, so VERIFIED would need invented values: against E06 ac2 and evidence integrity.
  Recommendation: (a), the only option that invents nothing. ac1: FAIL as written, PASS as amended.
  The Goal stays InProgress until you rule.

Q2. CardService's access gate now passes a USER_SUPPLIED snapshot whatever status its user reported
  (the status is the user's report about the publisher; the copy was stored on their lawful-access
  attestation). Unchanged for every other provenance; t02's seven-status test still passes.
  Recommendation: accept, and note it on t02's ac3 if you want it on record.

FYI, built as follows unless you say otherwise:
- cut URL --from-paste cuts the newest USER_SUPPLIED snapshot stored for the URL's canonical form;
  no fetch; the publisher's snapshot never stands in.
- No stored copy: exit 1, NO_USER_SUPPLIED_COPY, hint naming
  `debate-research fetch --paste FILE --source-url URL --i-have-lawful-access`.
- No provenance field added to SnapshotReference (that would be manifest version 3); provenance is
  on the manifest's card and checked by the verifier.
- cut's --json source gains provenance_mode.
- --i-have-lawful-access moved to debate_cli/options/lawful_access.py (a command module may not
  import another, v1-e01-t32).

Reply with: Q1 (a|b), Q2 (accept|other), and any change to the FYI items.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
