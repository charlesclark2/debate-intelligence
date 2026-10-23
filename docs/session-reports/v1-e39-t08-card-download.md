# Session report: v1-e39-t08-card-download

| | |
|---|---|
| Task | `v1-e39-t08-card-download` — Download a card or a small file as Verbatim .docx through the E33 writer |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t08-card-download.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t08-card-download.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t08-card-download` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A card page now offers **Download .docx** and **Add to cart**, and every signed-in page shows the
cart bar when the cart holds a card. Both send `POST /download`, which builds one Verbatim file with
the E33 `DocxEvidenceFileWriter`, as `files build` calls it after `v1-e33-t08`: no provenance line,
the header without its old sentence, and the sidecar built and dropped. The logic is
`debate_core.application.card_download`. It parses, deduplicates and caps the cart, then looks every
card up again through the lease's `ScreenedSearch`. Next it estimates the file's size and reads the
sources through `source_stores` within a byte budget. Only then does it build, and it writes the
`cards-downloaded` record before the file goes out. The cart lives in the browser's `sessionStorage`
(the PM's ruling), and download switches off when the index's parser is not the function's.

**The Goal stays `InProgress`.** ac4 (opening the files in Word with Verbatim and importing one
into Google Docs) is the operator's, after a dev deploy. Everything else passes.

**After the PM's review (2026-10-22): stopped before the PR, as condition 1 requires.** On the
operator's store, the share of index documents whose representative's source alone is over
2,000,000 bytes is **4.72% in hspf26 and 23.01% in openev**, both past the review's 2% line
(hsld26 0.73%, hspolicy26 0.92%; Decisions 1). Conditions 2 to 4 are done: a card whose own source
is over the budget is now a named, droppable refusal (tests shown failing first), the port's stale
sentence is fixed, and this report is updated. The budget's size, and what it measures, is the PM's
to rule on (the block at the end of Follow-up work).

**Look at first:**
1. **The cap is 8 cards, not 30, plus a second cap of 2 MB of sources.** The build time grows with
   the number of distinct sources, not the number of cards, so a card cap alone cannot bound it. 30
   cards from 30 mean-size sources took 29 s on the Mac, which is CloudFront's whole timeout
   (Decisions 1). On real sources, the 2 MB file-byte budget refuses too many cards in hspf26 and
   openev, while the part the writer parses is far smaller than the files (Decisions 1).
2. **Two packaging changes the spec did not name, without which the writer cannot run in the
   function.** The image gains debate-core's `docx` extra (lxml), and `debate_api` moves from the
   indirect lxml contract to a direct one of its own (Deviation 2).
3. **The index keeps no exact fingerprint.** The download derives it from the text the index shows,
   so the writer's own check holds the copied card to the page. A cite-only card is refused
   (Deviation 4).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `download` — Card download | Done (criterion PASS) | Built red first against two skeletons, then 21 of 21 mutants caught; ac4 is the operator's |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — a single card downloaded through the app route re-parses as its source, stubbed store | **PASS** | `test_download_of_one_card_through_the_route_re_parses_as_its_source`: `POST /download` → `200`, the `.docx` media type, `attachment; filename="team-evidence-cards-2026-11-02.docx"`, `private, no-store`. Re-parsed by the E31 parser: one card whose tag, cite, evidence text (hand-written: `Upland soils hold behind gabbro ridges a stressed warrant for decades.`) and `formatting_sha256` equal the source card's. Red against the absent skeleton. |
| **ac2** — the cart cap, a refused card's message, and dropping it to build the rest, tests shown failing first | **PASS** | `test_cart_over_the_cap_is_refused_before_a_card_is_looked_up_or_a_source_read` (cap 2, three cards → `409` "A download holds up to 2 cards…", no source read, nothing built, no record), `test_cart_at_the_cap_downloads`. `test_cart_with_a_refused_card_names_it_with_a_plain_reason_and_builds_nothing` names the card with a picture by place, tag and sentence (UNSUPPORTED_CONTENT). `test_download_refused_by_the_writers_read_back_names_the_card` (READBACK_MISMATCH), `test_cart_with_a_card_whose_source_is_lost_names_it`, and `test_cart_without_its_refused_card_builds_the_rest`. After the PM's review (condition 2): `test_cart_with_a_card_whose_own_file_is_over_the_source_budget_names_it` (card 2, by tag, "Its file is too large to download. Copy card still works.") and `test_cart_without_the_card_whose_own_file_is_too_large_builds_the_rest`, both shown failing first (they got `SOURCES_TOO_LARGE`), while `test_cart_whose_sources_only_add_up_past_the_budget_keeps_the_sources_message` pins the message that stays. In Chromium, `test_download_one_card_and_a_cart_by_keyboard_dropping_a_refused_card` clicks *Remove these from the cart and download the rest* and the file arrives. Red in both skeleton runs (below). |
| **ac3** — a parser-version mismatch switches download off with a message; each download writes one audit record | **PASS** | `test_download_is_switched_off_with_a_message_when_the_index_was_built_by_another_parser`: an index whose manifest names `2026.10.18-docx-5` → `503` "Download is off until the search's next weekly update. Copy card still works.", nothing read or built; the card page shows that sentence and no download button, and Copy card stays. `test_download_comes_back_on_when_an_index_of_the_functions_parser_is_published`. `test_download_writes_one_cards_downloaded_record_naming_every_card_in_order`: one record, both cards in cart order, the student's subject, schema-checked by the sink; `test_download_refused_for_any_reason_writes_no_record`. |
| **ac4** — the operator opens a downloaded single card and a cart file in Word with Verbatim and imports one into Google Docs; yes or no | **NOT RUN** | Needs a dev deploy, Word with Verbatim and a Google account: [Operator follow-ups](#operator-follow-ups) 1 to 3. |
| **ac5** — a cart whose built file would pass the buffered-response limit is refused before building, synthetic cart near the limit | **PASS** | `test_download_cart_two_bytes_past_the_buffered_limit_is_refused_before_building`: eight index cards of 185,447 characters estimate to exactly 3,000,000 bytes and go on to the build; the cart with one card a character longer → `FILE_TOO_LARGE`, no source read, writer never called. `test_download_estimate_is_above_every_file_the_writer_builds_from_the_worst_formatting`: every word its own fully formatted run, 1 and 30 cards; the estimate is above the real file each time. `test_download_file_built_past_the_buffered_limit_is_refused_and_never_sent` covers a file past the limit after the build, and `test_download_cart_whose_sources_pass_the_source_budget_is_refused_before_building` and `…_are_exactly_the_source_budget_downloads` cover the source budget. |
| **ac6** — (2026-10-20) a camp card downloads with its OpenEv line from `raw/openev/<year>` | **PASS, as amended** | "With its OpenEv line" is superseded by ac7 (spec, PM amendment 2026-10-22). `test_download_cart_with_a_camp_card_reads_it_from_raw_openev_2026_with_no_provenance_line`: the camp card's source is read from the `raw/openev/2026` store and the caselist card's from `raw/caselist/hsld26`, nothing else (`RecordingSourceStore` refuses every write). The file's paragraphs, written out by hand: the mixed header, the two headings, both cards. |
| **ac7** — a single card and a cart file hold no provenance line, and a camp card downloads from its `raw/openev/<year>` store, tests shown failing first | **PASS** | `test_download_of_one_card_holds_no_provenance_line_and_the_header_without_its_old_sentence` gives the file's every paragraph, written by hand: header, `Team evidence search`, `Downloaded cards`, tag, cite, evidence. No `[Disclosed`, `[OpenEv`, school, team code, tournament, round, camp or camp title appears, and nor does "below its cite". The cart test above shows the same for a cart. `test_download_sends_the_docx_alone_and_never_its_sidecar`: the response is the built `.docx` byte for byte, with the writer's seven parts and no sidecar keys. The Chromium journey checks the file the browser saved. Red against the absent skeleton. |
| **ac8** — a card suppressed after its page was rendered is refused at download and named; a download whose audit write fails is refused, tests shown failing first | **PASS** | `test_download_of_a_card_suppressed_after_its_page_was_rendered_is_refused_and_named[its-source]` and `[its-disclosure]`: the card page offers download, then a removal is appended and the five-minute recheck passes. The cart is refused `409`, naming card 2 by its place alone ("It is no longer in the search."). Nothing is read or built, and no record is written. `test_download_without_the_suppressed_card_builds_the_rest`. `test_download_whose_audit_record_cannot_be_written_is_refused_and_sends_no_file`: the file was built and not sent (`503`, JSON). `test_download_while_the_suppression_list_cannot_be_read_is_refused`. `test_download_without_the_sessions_csrf_token_is_refused_by_the_gate`: the gate refuses `/download` without the session's CSRF token (`403`), nothing built. Red in both skeleton runs. |
| Node `download` — `uv run pytest packages/debate_api/tests -k "download or cart"` | **PASS** | `91 passed in 6.67s` |

**Red first, recorded.** The tests ran against two skeletons of
`CardDownloadService.download`, each written over a saved copy of the file and restored by
sha256 (`2b5e353d…` before and after):

| Skeleton | Result | What failed |
|---|---|---|
| Feature absent: every download refused as an empty cart | `31 failed, 24 passed` | Every criterion: re-parse (ac1), cap and naming (ac2), switch-off and record (ac3), the size limits (ac5), the camp store and no line (ac6, ac7), suppression and the unwritten record (ac8) |
| Refuse nothing: no cap, no validation, no suppression, no parser check, no limits, audit failures swallowed, writer refusals unnamed | `21 failed, 34 passed` | Cart validation (6), cap, naming and dropping (5), switch-off (2), limits (3), suppression (2), the unwritten record (1), reading a source once (1), the duplicate (1) |

Two later tests were shown red against the code before their fixes:
`test_download_body_with_more_fields_than_a_download_sends_is_refused_not_failed` raised
`ValueError: Max number of fields exceeded`, which would have been a 500 (a bug, fixed in
`b74b43d`). `test_download_image_installs_debate_cores_docx_extra_and_lxml_with_it` failed with
`assert 'docx' in ['aws', 'tub']` before the packaging change.

**Mutation.** 21 mutants of the PM's four rules and the limits, each run against
`test_card_download.py` and `test_card_download_limits.py` with a new empty
`HYPOTHESIS_STORAGE_DIRECTORY` (these files use no Hypothesis), each restored and checked by sha256
after: **21 caught, 0 survived, 0 errored.**

| Rule | Mutants (each caught) |
|---|---|
| Cart validation | no length limit; skip a bad part instead of refusing; looser reference pattern; no deduplication; a doubled `cards` field taken; no body limit |
| Suppression at download | `card_source` ignores the predicate; the lease passes no predicate; a card not found dropped, not refused; the screen reads the unscreened service |
| Audit before the file | a failed write swallowed; the record written before the build (so refused builds were recorded); the route lets `AccessNotRecorded` reach the app's error handler; no check of the built file's size |
| The cap | `>=` for `>`; no cap; checked after the sources are read; the setting without its upper bound of 30 |
| The other limits | source budget `>=`; estimate `>=`; parser check always on |

**Before the report.** These are the results of the runs this report rests on:

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (before the `pyproject.toml` change) | 106 test files |
| `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" -q <the 106>` | **Stopped by the alarm at 96%** (load average 4 to 12 from other sessions). Two `F`s in the progress lines and no summary. Rerun in groups: the architecture, spec, script, local-reader and evidence-search files gave `1 failed, 1201 passed`, the failure being `test_the_unmodified_copy_keeps_every_contract`, the lxml contract that `31ed3e7` fixes. The other 32 files gave `1186 passed`, the 25 caselist files `474 passed` and `debate_api` `731 passed`. **The second failure did not reproduce**, and its test is not known. |
| `uv run scripts/affected_tests.py` (after it) | "The whole selection is affected: packages/debate_api/pyproject.toml is shared test ground." So nothing more was run, and the pull request's `ci` runs the whole selection (working agreement 10; the PM's ruling of 2026-10-19) |
| Changed test directories plus the always-run list and the docs checks, `-n auto -m "not slow and not live"`, after the last commit | `1567 passed in 24.48s` |
| `packages/debate_api/tests`, `-n 0 -p no:randomly` (the log test reads process-wide logging state) | `733 passed, 20 deselected` |
| `packages/debate_api/tests/browser -m slow` (outside the PR path) | `20 passed` |
| `uv run ruff format --check .`; `uv run ruff check .` | `1128 files already formatted`; `All checks passed!` |
| `uv run --frozen pyright` (CI's scope) | `0 errors` |
| `uv run lint-imports` | `Contracts: 16 kept, 0 broken.` |
| `uv lock --check`; `uv export --package debate-api --frozen --no-dev --no-emit-workspace` | lock consistent; the export holds `lxml==6.1.3` |
| `uv run scripts/check_thin_handlers.py` | `OK: 47 … handlers within 25 statements` (`card_download` 10, `card_page` 20) |
| `uv run scripts/validate_specs.py`; `check_command_blocks.py`; `check_links.py` | all `OK` |

## Files changed

- **`packages/debate_core/src/debate_core/application/card_download.py`** (new): the use case, its
  refusals, the size estimate and the caps.
- **`packages/debate_core/src/debate_core/application/evidence_search.py`,
  `search_index_holder.py`, `ports/search_index_reader.py`**: `card_source` (the representative and
  where it was read from, under the same predicate as `card`), the manifest's parser version on
  every lease, and element indices on a card lookup's occurrences.
- **`packages/debate_core/src/debate_core/integrations/local/search_index_reader.py`** and its
  statement-shape test: the occurrences statement reads the two index columns that were already
  stored (Deviation 1).
- **`packages/debate_core/src/debate_core/testing/search_index.py`**: `published_index` takes the
  manifest's parser version.
- **`packages/debate_api`**: `download.py` (the route), configuration (the two settings), the
  container (writer, parser, `S3SnapshotStore` per prefix on one client), state, pages, routes, the
  card page and the cart bar, `app.js` (cart and download) and `app.css`. `pyproject.toml` adds the
  `docx` extra.
- **`packages/debate_api/tests`**: the test world's synthetic sources and recording stores
  (`conftest.py`); `test_card_download.py`, `test_card_download_limits.py` and
  `test_card_download_image.py`. The Chromium journey and a cart test. The route lists of the
  authorization matrix, the exposure check and the script check gained `/download`, and the card
  page's bar test gained the new row.
- **`pyproject.toml`, `uv.lock`, `tests/architecture/test_import_contracts.py`**: the API's direct
  lxml contract and its probes (Deviation 2).
- **`docs/runbooks/evidence-search.md`**: download, the caps with the measurements, timing on dev,
  and a row in What to record.
- **`plan_specs/.../t08-card-download.yaml`**: the PM's cart-ruling comment, above the folded
  description (checked: not in the parsed description).

## Deviations from the spec

1. **Files outside `constraints.packages`.** All are needed for the download the spec describes,
   and none changes the index format (v1-e39-t13's):
   - `debate_core.integrations.local.search_index_reader` reads the occurrences'
     `first_element_index` and `last_element_index`, which the index stores but no reader read. The
     writer finds a card by them. The search statement is unchanged. The hand-written statement list
     in `test_search_index_reader_sqlite_features.py` gained the two columns, and its slow replay
     against the Lambda image's SQLite is the next `validate-dev`'s.
   - `debate_core.testing.search_index.published_index(parser_version=...)`, defaulting to the
     version it always wrote.
   - The packaging and contracts in Deviation 2.
   - The runbook section, and the spec comment the PM asked for.
2. **The function's image and the import contracts.** `debate_api` depends on
   `debate-core[aws,docx,tub]` (it was `[aws,tub]`), because the writer and its parser need lxml and
   the image installs exactly what `uv.lock` records for `debate-api`. Without the extra the function
   would start and fail on its first download, as `v1-e01-t17` found for the CLI.
   `test_card_download_image.py` holds the container's wiring and the lock together. In the root
   `pyproject.toml`, `debate_api` leaves the indirect "Document libraries stay inside
   debate_core.integrations.docx_parser" list for a new direct contract, "The API reaches lxml only
   through debate_core.integrations". This copies the CLI (`v1-e31-t06`) and the API's own AWS SDK
   contract (`v1-e39-t05`). Two planted probes in `tests/architecture` prove it breaks on a route
   importing lxml or python-docx.
3. **"A cart of up to 30 cards held in the session" is now 8 cards plus a source budget, held in
   the browser.** The browser part is the PM's ruling of 2026-10-22. The 8 is the measured number
   the PM's notes foresaw ("if that's below 30, say so … as a setting"). The second cap,
   `TUB_DOWNLOAD_SOURCE_BYTES`, is not in the spec. It is needed because the time is per source and
   grows with its size: one camp-sized source took 4.5 s on its own (Decisions 1). Since the PM's
   review, a card whose own source is over that budget is a refused card of its own
   (`SOURCE_TOO_LARGE`, named by its place), and only a cart whose sources add up past it gets the
   cart-wide `SOURCES_TOO_LARGE`.
4. **The fingerprint, and cite-only cards.** The writer refuses a card whose source paragraphs do
   not have the recipe's exact fingerprint. The index keeps no exact fingerprint, so the download
   takes it from the evidence text the index holds (`fingerprint_text`, E31's rule for a FULL or
   ABBREVIATED card). The writer's check then holds the copied card to the text the page showed. A
   CITE_ONLY card's fingerprint is over its full cite, which the index stores without its cutter
   mark. So a cite-only card is refused, named, with "It is a cite with no card text … Copy card
   copies the cite."
5. **How `source_stores` is used.** The use case reads each source through
   `source_stores(source_prefix(caselist, snapshot))`, the same stores and prefixes ac6 names, before
   the build. That lets it refuse a cart over the source budget before building. It then gives the
   writer one in-memory store of exactly those bytes, rather than the writer's own `source_stores`
   argument. The writer's checks are unchanged, and a missing or damaged source still comes back as
   its SOURCE_UNAVAILABLE.
6. **"Nothing outside the function's /tmp (clean it after each build)":** a download writes no file
   anywhere. Sources and the built file stay in memory, and the writer and parser use no temporary
   files (`grep` for `tempfile` in both: none). So there is nothing to clean.
7. **The card page's action bar has a second row.** Copy card's row is unchanged. Download .docx
   and Add to cart are on a row below it, because both rows do not fit 1366 px once Copy card's
   status reads "Copied. Paste it into Google Docs or Word." The t06 test that put the card text
   within 40 px of the Copy button now measures from the bar's bottom, and still asserts that the
   status shares the Copy button's line.

## Decisions and assumptions

1. **The caps, from measurement** (2026-10-22, operator's Mac, Apple M3 Pro, load average 6 to 10
   from other sessions). Synthetic sources built with Word-like run markup until their size matched
   the mean disclosed file: 236 KB, 3.6 MB of `document.xml`, 35 cards of about 1,400 words. The
   script is not committed: `measure_download.py` in the session's scratchpad.

   | Cart | Build | File |
   |---|---|---|
   | 1 card | 0.70 s | 7.2 KB |
   | 10 cards from 10 sources | 10.04 s | 41.5 KB |
   | 30 cards from 30 sources | 29.06 s | 117.9 KB |
   | 30 cards from 1 source | 2.51 s | 118.1 KB |
   | 1 card from a camp-sized source (1,004 KB, 150 cards) | 4.51 s | |
   | Worst formatting (one fully formatted run per word), 30 cards | | 245,404 bytes: 0.95 bytes per character |

   Peak memory: 10 mean-size sources held about 830 MB during the build (about 80 MB each), so 30
   would pass the function's 2,048 MB. The function's core is assumed to be **half** the Mac's speed
   (Graviton2 at 2,048 MB, one full core). That assumption is untested until Operator follow-up 4.
   Under it, 8 mean-size sources are about 16 s, and 2 MB of sources at the slowest rate measured
   (4.5 s per MB) about 18 s. Both are under two thirds of the 30 s that CloudFront's default origin
   timeout (no `origin_read_timeout` in `distribution.tf`) and the function's timeout set. Both are
   settings (`TUB_DOWNLOAD_CARD_CAP` 1 to 30, `TUB_DOWNLOAD_SOURCE_BYTES`), unset by Terraform.

   **Real source sizes** (the PM's condition 1; 2026-10-22; read-only on the operator's dev store,
   aggregates only). The sources named by index `f29b81c276dd67c5`'s occurrences, the newest local
   index (v1-e39-t12's rebuild), with sizes read from `blobs/sha256`; **runtime 3.1 s**. Index
   `767b9c7c056b80cb`, published to dev, gave the same picture to within 0.1 point (2.9 s).

   | Caselist | Sources | p50 bytes | p95 bytes | Largest | Documents whose source alone is over 2,000,000 |
   |---|---|---|---|---|---|
   | hsld26 | 5,965 | 69,708 | 353,223 | 7,133,832 | 93 of 12,714 (0.73%) |
   | hspf26 | 3,524 | 72,419 | 1,431,736 | 7,823,779 | 519 of 11,000 (**4.72%**) |
   | hspolicy26 | 3,799 | 157,358 | 884,755 | 7,679,194 | 193 of 20,961 (0.92%) |
   | openev | 102 | 204,500 | 2,238,723 | 6,854,554 | 1,325 of 5,759 (**23.01%**) |

   The same share at other file-byte budgets (0.7 s): over 3 MB 0.32 / 4.16 / 0.24 / 17.40%; over
   4 MB 0.24 / 2.93 / 0.18 / 10.12%; over 5 MB 0.03 / 2.63 / 0.08 / 1.28%; over 6 MB 0.02 / 2.41 /
   0.05 / 1.28%; over 8 MB 0% everywhere (hsld26 / hspf26 / hspolicy26 / openev).

   **Bytes on disk are not what costs time.** The writer parses each source's `word/document.xml`.
   Read from the zip directories alone (no content; 5.2 s), the sources over 2 MB have a
   `document.xml` of, at the median, 269 KB (hsld26, 30 sources), 469 KB (hspf26, 160), 701 KB
   (hspolicy26, 30; 92% of their compressed bytes are media) and 2.0 MB (openev, 6). The largest
   `document.xml` of any source is 6.4 MB, 3.8 MB, 6.6 MB and 10.6 MB. The synthetic measurements
   above cost about 0.2 to 0.3 s per MB of `document.xml` on the Mac and about 22 MB of memory per
   MB, so even the largest real source is about 3 s and 240 MB alone.
2. **The file-size limit is 3 MB**, a constant, not a setting. A function URL buffers 6 MB, and the
   Lambda Web Adapter base64-encodes a binary body, so 4.5 MB of file fills it, and 3 MB leaves a
   third. The estimate is 16,384 bytes, plus 2,048 per card, plus 2 per character of tag, cite and
   text: about twice the worst measured. A built file is checked again after the build.
3. **Which occurrence is copied: the card's representative**, the one whose text the page shows.
   A card whose representative is suppressed is "no longer in the search", as its page is.
4. **The recipe a cart becomes.** One pocket, *Team evidence search*, and one block, *Downloaded
   cards*, holding the cards in cart order. A recipe needs one format, caselist and side, which a
   mixed cart does not have. Those go into the sidecar alone, which is never sent, so the first
   card's event and store stand in, with the format's first side. The occurrence's `membership`
   (not kept in the index, read by no writer) is `UNLINKED`. Its disclosure is `None`, since the
   provenance goes nowhere.
5. **Statuses.** `409` for a cart that cannot be built as sent; `400` for one that cannot be read;
   `503` for download switched off, an unreadable index or list, or an unwritten record. Each
   refused card carries its place in the cart. A card still in the search carries its tag or short
   cite, cut at 80 characters. A removed card carries neither, so its words are never repeated.
6. **The file name** is `team-evidence-cards-<UTC date>.docx`: nothing about the cards.
7. **The cart in the browser.** `sessionStorage` key `tub-download-cart` holds a list of
   references matching the server's pattern. The browser's cap mirrors the server's, from
   `data-tub-cart-cap`, but the server enforces it. The cart is emptied on sign-out and on any page
   without a session. Cards already in the cart show *Remove from cart*.
8. **Smoke checks.** `validate-dev` runs no signed-in check (t10's PM amendment of 2026-10-21), and
   a download needs a session, so no smoke check is added here. The unsigned answer (`401` for a
   POST without a session) is in the authorization matrix, which now lists `/download`.

## Operator follow-ups

Set `WT` once, in a new terminal window:

```bash
WT=/Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t08-card-download
```

**1. Rehearse the dev deploy** (expected runtime ~4 min: a sync, then an image build; changes
nothing outside the worktree). The block stops if a `DEBATE_*` override is set or a `caselist pull`
is running (working agreement 11). Docker Desktop must be running.

**Operator command** (expected runtime ~4 min)
Where: `${WT}`
```bash
cd "${WT}"
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  uv sync --all-packages
  uv export --package debate-api --frozen --no-dev --no-emit-workspace | grep -c '^lxml=='
  scripts/tub_deploy.sh dev --dry-run
fi
```
Read before going on: two `none` lines; then `1` from the export (lxml is in the image's
requirements; `0` means the lock lost the extra, so stop); then the script's dry-run end, an image
built and no push. A `STOP` line, a `0` or a build error stops here; paste it back.

**2. Deploy dev** (expected runtime ~3 min; changes the dev function), only after block 1 read
cleanly:

**Operator command** (expected runtime ~3 min)
Where: `${WT}`
```bash
cd "${WT}"
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  scripts/tub_deploy.sh dev
fi
```
Success looks like the runbook's step 8: `{"status":"ok"}` through CloudFront, then `Deployed <sha>
to dev` and the digest the function runs.

**3. ac4: the coach's check in Word, with Verbatim, and in Google Docs** (expected ~15 min, by
hand). Sign in on `https://tub.dev.wfbdebate.com/`. On a card page, check that **Download .docx**
and **Add to cart** show; if *Download is off* shows instead, the dev index was built by another
parser: rebuild and publish it with this build first (runbook, "Download .docx and the cart"). Then:

- download one card, and open it in Word with the Verbatim template;
- add three or four cards from different files to the cart (a camp card among them if the dev
  index has one), choose **Download cart**, and open that file too;
- upload one of the two to Google Drive and open it with Google Docs.

Record **yes or no** for each of the three: *the single card opens in Word with Verbatim, its tag,
cite, underlining, highlighting and sizes as on the card page*, *the cart file does the same for
every card*, *Google Docs keeps the formatting*. Also note that no file shows a `[Disclosed: …]` or
`[OpenEv: …]` line.

**4. Time a download on dev**, right after step 3, with the runbook's command (seconds): download a
cart of eight cards from eight different files, then:

**Operator command** (expected runtime seconds)
Where: your Mac, anywhere
```bash
aws logs filter-log-events --profile debate-admin --region us-east-1 --log-group-name debate-dev-tub-app \
  --filter-pattern '"REPORT RequestId"' --query 'events[-5:].message' --output text
```
Success looks like the cart's `REPORT` line with `Duration` under 20,000 ms and `Max Memory Used`
under 1,400 MB. Paste the lines back. Over either, the Mac-to-function allowance (Decisions 1) was
too small, and the two defaults need lowering before the pilot opens.

## Follow-up work

1. **ADR-0019 says otherwise in two places** (the PM's to amend; not edited here). Its (d) puts the
   cart in a `__Host-tub_cart` cookie, which the PM's ruling of 2026-10-22 replaces with the
   browser's `sessionStorage`. Its (a) 2 says a 30-card download "is far below the 6 MB response
   limit". That is true of the file's size (118 KB measured), but the build time is per source, and
   the cap is 8 (Decisions 1).
2. **The two download settings are not in Terraform's environment block** for the function
   (`infrastructure/modules/evidence_search/main.tf`). If the dev timing says change, it is a code
   default or that block: an E39 infrastructure follow-up, `v1-e39-t04`'s module.
3. **Real source sizes: measured** (the PM's condition 1; Decisions 1). The share over 2,000,000
   bytes passes 2% in hspf26 and openev, so the PR waits for the PM's ruling below.
4. **The port's docstring: fixed** (condition 3, `f6dcae9`).
5. **The second failure in the cut-short affected run** did not reproduce in any group. If the
   pull request's `ci` shows a failure outside the files this branch touches, paste it into this
   session.
6. **`pyright` named on two `tests/architecture` files** (`test_fakes_reach_only_their_port.py:144`,
   `test_thin_handlers.py:21`) reports two errors. They exist on `origin/dev` too and are outside
   CI's pyright scope, so they were left alone.

**For the PM: condition 1's stop**, one paste-ready block:

```text
v1-e39-t08 (card download), condition 1 stopped the PR: real source sizes.

Measured read-only on the operator's dev store (index f29b81c276dd67c5, 3.1 s), the documents whose
representative's source alone is over 2,000,000 bytes: hsld26 0.73%, hspf26 4.72%, hspolicy26 0.92%,
openev 23.01%. Over 2% in hspf26 and openev, so I stopped before the PR. Conditions 2 to 4 are done
(a card whose own source is over the budget is now a named, droppable refusal; tests failed first).

What the numbers show: file bytes are the wrong measure. The writer's cost follows each file's
word/document.xml, not its size on disk. The sources over 2 MB have a document.xml of 269 KB (hsld26),
469 KB (hspf26), 701 KB (hspolicy26) and 2.0 MB (openev) at the median; the largest document.xml of
any source is 10.6 MB (openev), about 3 s and 240 MB on the Mac at the measured rate. Big files are
big for images and other parts (hspolicy26's: 92% media).

Options:
(a) Budget the sum of the cart's document.xml sizes instead of file bytes, read from each fetched
    file's zip directory before the build (no parse). Recommended: 20,000,000 bytes of document.xml,
    about 6 s and 450 MB on the Mac, 12 s at the assumed 2x slower function. No real source is over it
    alone (0% refused for their own file in every caselist); the card cap of 8 stays. The zip
    directory is read by a function the composition root passes in from docx_parser, so the
    application layer still never opens a .docx itself. About an hour, tests first, then a short
    re-review.
(b) Keep file bytes and raise the budget to 8,000,000: 0% over in every caselist today, but a cart of
    eight such files could hold far more XML than the timing allows, so the card cap would need to fall.
(c) Keep 2,000,000 file bytes: 4.7% of hspf26 and 23% of camp cards can never be downloaded (Copy card
    still works for them).

I recommend (a). The dev timing (Operator follow-up 4) checks it either way.
```
## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED, with conditions closed in-session
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

The download is what the spec and the 2026-10-22 rulings asked for:
* fail-closed on suppression, the parser check and the audit write;
* no provenance line and no sidecar sent;
* both skeletons red, and 21 of 21 mutants caught.

The CSRF gate covers `/download` like every other unsafe method, and
`test_download_without_the_sessions_csrf_token_is_refused_by_the_gate` pins it. Name that test in
the ac8 row.

**Rulings on your four questions**

1. **Caps: (a).** 8 cards plus 2,000,000 bytes of sources until the dev timing (Operator
   follow-up 4) says otherwise. Predictable beats more.
2. **Packaging: accepted**, with the `docx` extra in the image and the API's own direct lxml
   contract, as the CLI's was in v1-e31-t06.
3. **A cite-only card is refused: accepted.** v1-e39-t12's rule C drops those documents from the
   index, so the case should become rare.
4. **ADR-0019 (d) and (a) 2:** the PM amends both in the next PM batch. Don't edit the ADR here.

**Deviations 1 to 7 and Decisions 1 to 8 are accepted.**

**Conditions, to close in this session before the PR**

1. **Measure real source sizes before the budget ships.** This is your Follow-up 3, done now.
   * Read-only on the operator's store, aggregates only, in seconds (working agreement 2).
   * Per caselist (hsld26, hspf26, hspolicy26, openev): the p50, p95 and maximum source bytes,
     and the count and share of index documents whose representative's source alone is over
     2,000,000 bytes. Those cards can never be downloaded under the budget.
   * Record the numbers in the runbook beside the caps and in Decisions 1. Report the runtime.
   * **If that share is over 2% in any caselist, stop and bring the numbers to the PM before
     the PR.** The budget would then be set on data, not left as written.
2. **A card whose own source is over the budget is refused as that card, with a message that
   fits it.**
   * Today it gets `SOURCES_TOO_LARGE`, whose message says to download "a card from a large file
     on its own". For that card, that cannot work.
   * Make it a refused-card reason, named by its place like the others, so that *Remove these
     from the cart and download the rest* still works. The message: "Its file is too large to
     download. Copy card still works."
   * A cart refused only because its sources add up past the budget keeps today's message.
   * Write the tests first and show them failing.
3. **Fix the stale docstring** in `debate_core.application.ports.evidence_file_writer` (your
   Follow-up 4). It is one sentence, accepted outside `constraints.packages`.
4. **Then update the stale parts of this report** (Summary, Deviations, Decisions 1, the ac2 and
   ac8 rows, Follow-up work). No new review is needed for that.

**The PR.** Open it with `--partial`. ac4 is the operator's after a dev deploy, so the Goal stays
`InProgress`. v1-e39-t10 depends on this task but waits for the prod promotion anyway. The PM
records ac4 and the timing and sets the Goal `Succeeded` in a PM batch. If the PR's `ci` shows a
failure outside the files this branch touches (your Follow-up 5), stop and bring it to the PM.

**Operator follow-ups, after the merge, in this order:**
* v1-e39-t12's two blocks (its rebuilt index publishes first).
* Then blocks 1 and 2 here, from this worktree before `scripts/task finish`. The branch already
  carries v1-e39-t11.
* Then, in one sitting on dev: v1-e39-t11's four-point check, ac4 here, and step 4's timing.
  Over 20,000 ms or 1,400 MB, bring the `REPORT` lines to the PM before the pilot opens.

**Follow-up work:**
* 1 (ADR-0019): the PM batch.
* 2 (Terraform settings): only if the timing says so.
* 3: condition 1.
* 4: condition 3.
* 5: the PR's `ci`.
* 6 (pyright on two `tests/architecture` files): added to v1-e01-t31's brief, which is about the
  repository's own checks.

If anything comes out differently, stop and ask for another review.
