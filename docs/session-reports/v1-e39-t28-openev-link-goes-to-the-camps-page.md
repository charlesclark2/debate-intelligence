# Session report: v1-e39-t28-openev-link-goes-to-the-camps-page

| | |
|---|---|
| Task | `v1-e39-t28-openev-link-goes-to-the-camps-page` — A camp card links to its camp's page on OpenEv, the address the operator confirmed |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t28-openev-link-goes-to-the-camps-page.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t28-openev-link-goes-to-the-camps-page.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t28-openev-link-goes-to-the-camps-page` |
| Session status | BLOCKED <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The count came first (ac1) and it met the spec's stop condition. The stored `camp` is not OpenEv's
address word: it is the importer's canonical camp name from
`packages/debate_core/src/debate_core/application/caselist/camp_aliases.yaml`. 14 of the 15 stored
values are that table's canonical names, and the 15th is `UNKNOWN`. Of the three words the operator
confirmed, only UTNIF is a stored value. HDC and UM7 are neither stored values nor words of any of the
106 manifest paths, and the alias table spells neither one. Nothing else the Mac holds records
OpenEv's own folder word for these files either. So, as the spec and the PM's context say, **no link
was built**. Nothing outside this report changed. Choosing the camp's address word is the PM's call,
and it may need a format change: the [question](#questions-for-the-pm) gives the options. The
phase stays `InProgress`, with ac2 not built and ac3 left to the operator after a merge.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `openev-link-goes-to-the-camps-page` (Camp page link) | NOT STARTED | Stopped at the count, as the spec says: "No index format change, unless the count shows the stored camp is not the address's word, in which case stop and report" |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1, "Counts first: the distinct camp values, how many are one address word, and how many of the 102 camp files with cards get a link, recorded in the report with no camp named beyond the three confirmed" | PASS | [The count](#the-count-first), below. Two read-only scripts in the session's scratch directory, run with `/usr/bin/python3 -I` in 0.46 s. They print counts only, plus yes/no for the three confirmed words |
| ac2, "A camp card whose stored camp is one address word … links to `https://opencaselist.com/openev/<year>/<camp>` … by tests shown failing first" | NOT RUN | Not built: the count shows the stored camp is not the address's word, the spec's condition to stop and report. A link built from the stored value now would point 96 of the 98 linkable camp files at an address that has not been confirmed |
| ac3, "After dev's function is deployed with this task, the coach opens one camp card's link on dev and it lands on that camp's page" | NOT RUN | The operator's, after a merge, and no link exists to open |
| Node criterion "Camp page link tests pass" (`uv run pytest packages/debate_core/tests/domain -k source_link`) | NOT RUN | Nothing changed for it to test. As things stand it would pass on t16's code, which is not this task's link, so its green would mean nothing |

## The count first

Taken 2026-10-31 on the operator's Mac, read-only (SQLite opened `mode=ro`), counts only. No camp
beyond the three confirmed, no title, no lab and no path was printed. Sources: the caselist database's
`caselist_camp_files`, the parsed store `parsed/openev/2026.10.20-docx-6/` (`index.jsonl`,
`occurrences.jsonl`), the release manifests `objects/manifests/openev/`, the four local indexes under
`tub-index/`, and the sync's run records. The published dev index is in the bucket and was not read,
because the local count answers the question.

| Question | Count |
|---|---|
| Camp files in the store | 104 (`caselist_camp_files`): 102 `2026-policy` and 2 `2026-ld`. All are year 2026 |
| Camp files with cards | 102, all `2026-policy`. Each has one `caselist_camp_files` row, and its occurrence rows carry one camp |
| Distinct stored camp values | **15**, the same in `caselist_camp_files`, in the parsed occurrence rows and in all four local indexes (three are format 1 and one is format 2, `camp_year` 2026 throughout) |
| Of those, one address word (letters and digits) | **12**, plus `UNKNOWN`, which is one word too but is the parser's "could not read" ([Decisions](#decisions-and-assumptions)). The other 2 values contain a space |
| Of the 102 with cards, linkable under the spec's rule as written (one word, not `UNKNOWN`, year from 2013 to 2026) | **98**. Of the other 4, 3 have a camp with a space and 1 is `UNKNOWN`. None is refused for its year |
| Years | 2026 only, so every file is inside OpenEv's archive (2013 to the current season, 2026) |
| **Is the stored camp the address's word?** | **No, not in general.** 14 of the 15 values are canonical names from `camp_aliases.yaml`, and the 15th is `UNKNOWN`. The importer records the canonical name, not the spelling the file used: for 9 of the 102 files, the stored camp is not a word of the file's own path |
| The three confirmed words | **UTNIF** is a stored value, with 2 files, and both paths name it. **HDC** and **UM7** are not stored values, and neither is a word of any of the 106 `2026-policy` manifest paths. The alias table spells neither one, so no file can be stored under either |
| Anything holding OpenEv's own folder word | Nothing for these files. The hand import's paths are `<folder>/<file>` (105 of 106 rows, all one folder, which is no camp's spelling and none of the three words) or a bare file name (1), so no path has a `<camp>` folder. The sync's run records keep `openev_id`, `year`, `event` and the inbox name of 7,972 listing decisions, but not the listing's `camp`. `OpenEvFile.camp`, the API listing's own camp field, is seen by the pull and stored nowhere |

**What this means for the link.** The address `https://opencaselist.com/openev/<year>/<camp>` takes
OpenEv's folder word. The store holds the word this repository's alias table chose. The two agree for
UTNIF, where the canonical name is also the confirmed word. For the other 11 one-word camps, which
hold 96 of the 98 linkable files, nothing the repository holds says whether they agree. And the two
confirmed camps that are not UTNIF cannot be reached by any stored value. The alias table also folds
several spellings into one canonical name, which OpenEv may file as more than one camp. A link built
from the stored value would be right for 2 files and unconfirmed for 96.

## Files changed

* `docs/session-reports/v1-e39-t28-openev-link-goes-to-the-camps-page.md`: this report.

Nothing else. `OPENEV_FILE_URL_TEMPLATE`, t16's tests, the docs and the runbooks are unchanged. The
`caselist-cloud-run.md` hold on images carrying t16 **stays**: the year-page link is still the only
link in the code, and no stored camp file has an id, so it still shows nowhere.

## Deviations from the spec

1. **Stopped at ac1, as the spec allows.** The spec says "No index format change, unless the count
   shows the stored camp is not the address's word, in which case stop and report", and the PM's
   context adds "then the camp needs its own column, which is a format change and the PM's call". The
   count shows exactly that, so ac2, the docs, the runbook edits and the mutants were not started.

## Decisions and assumptions

These are for whichever task builds the link once the PM has ruled. None was built here.

* **`UNKNOWN` gets no link.** It is one word of capitals, so the spec's "one address word" rule alone
  would link `/openev/2026/UNKNOWN`. That is 1 of the 102 files.
* **The current season is `current_season_start`**, the repository's only rule for it
  (`packages/debate_cli/src/debate_cli/commands/caselist_backfile.py`: the season starts on 1 August).
  It lives in `debate_cli`, so the link in `debate_core.domain` needs it moved into the domain, for
  example a small `debate_core/domain/season.py` that the CLI imports. That touches `debate_cli`,
  which is outside this spec's packages. The card page has the date through `services.clock()`.
* **That rule refuses the next topic year for about two months.** OpenEv's camps publish a topic
  year's files in June and July, before the season the rule counts starts on 1 August. Under the
  rule, a 2027 camp file imported in July 2027 would get no link until 1 August. The PM may prefer
  "up to the current season plus one".
* **No network call, and the published dev index was not read.** The local stores answered the
  question, and every local index agrees with them.

## Questions for the PM

Paste-ready:

> **v1-e39-t28, one question. The stored camp is not OpenEv's address word.**
>
> Counted read-only on the Mac. The 102 camp files with cards (all `2026-policy`) are stored under 15
> camp values: 14 are canonical names from `camp_aliases.yaml`, the 15th is `UNKNOWN`. 12 are one
> address word, which would give 98 of the 102 files a link. Of the confirmed words, only **UTNIF**
> (2 files) is a stored value. **HDC and UM7 are neither stored values nor words in any of the 106
> manifest paths, and the table spells neither.** The hand import's paths have no `<camp>` folder,
> and nothing on the Mac keeps the API listing's own `camp` field (`OpenEvFile.camp`). So no stored
> value is known to be OpenEv's folder word except UTNIF. Under the spec's rule, the link would be
> right for 2 files and unconfirmed for 96.
>
> Options:
>
> **(a) Measure, then decide. No code.** The operator prints the 12 addresses the rule would build
> (operator follow-up 1; the terminal only, never the report) and opens each one signed in. They tell
> the PM how many land on a camp page that lists files. If all 12 do, t28 goes ahead as written, with
> `UNKNOWN` refused. If some do not, choose from (b) to (d) for those camps.
>
> **(b) An OpenEv word for each canonical camp, in the alias table. No format change.** Each camp in
> `camp_aliases.yaml` gains an optional `openev:` word, filled once a season from OpenEv's sidebar.
> The link maps the stored camp through it, and a camp without one gets no link. This covers the 102
> hand-imported files. A canonical camp that gathers spellings OpenEv files as two camps gets no
> `openev:` word, so no link. t28's rule becomes "camp, through the table, and year".
>
> **(c) A new index column for OpenEv's own camp word, from the listing's `camp`. Format 4.** The pull
> writes `OpenEvFile.camp` onto the manifest row, and the build joins it as t16 joins `openev_id`.
> This is exact for every file the pull imports from now on, but gives **none of the 102**
> hand-imported files a link, and it is a manifest and format change with t16's deploy order.
>
> **(d) Drop the camp link from the pilot.**
>
> **Recommendation: (a), then (b) for any camp it does not confirm.** (a) is twelve pages and no code,
> and it may show most canonical names already work. (b) is the only option that reaches this
> season's 102 files, and it needs no format change or deploy order. (c) is the right long-term source
> for pulled files, and can come later beside (b) if the table drifts.
>
> Either way, two choices for the amended spec: `UNKNOWN` gets no link (it is one word), and "the
> current season" is `current_season_start` (1 August) moved into the domain. That touches
> `debate_cli`. It refuses a new topic year's camp files in June and July, so "current season plus
> one" may be better.

## Operator follow-ups

1. **Only if the PM chooses (a): open the addresses the rule would build.** This reads the Mac's
   caselist database read-only and prints one address per one-word stored camp. The words are camp
   names, so they stay in the terminal: report only the counts to the PM.

   **Operator command** (expected runtime under a second)
   Where: your Mac, anywhere
   ```bash
   python3 -I -c 'import os, re, sqlite3; db = sqlite3.connect("file:" + os.path.expanduser("~/.debate-research/dev/debate.sqlite3") + "?mode=ro", uri=True); camps = sorted({(year, camp) for year, camp in db.execute("select year, camp from caselist_camp_files") if re.fullmatch("[A-Za-z0-9]+", camp) and camp != "UNKNOWN"}); print("\n".join(f"https://opencaselist.com/openev/{year}/{camp}" for year, camp in camps) or "STOP: no camp in the store")'
   ```
   Success looks like 12 lines, each `https://opencaselist.com/openev/2026/<word>` (the session ran it
   and counted 12 well-formed lines without printing them). Open each one in a browser signed in to
   openCaselist. Tell the PM how many of the 12 open a camp's page that lists files, and how many open
   something else (an empty page, a year page or an error).

2. **ac3** stays the operator's after whichever task builds the link merges: deploy dev's function
   (`evidence-search.md`, Moving the index to format 3, step 1), then the coach opens one camp card's
   link on dev. Not listed as a block here, because no link exists yet.

## Follow-up work

* **The camp-page link itself**, once the PM rules: t28 continued with an amended spec, or a new task
  for (b) or (c).
* **`OpenEvFile.camp` is seen by the pull and stored nowhere** (E30 or E34). Whatever the ruling, a
  pulled file's own OpenEv camp is the one exact source of the address word. Keeping it on the
  manifest row costs little and is what (c) needs.

## What was run before this report

| Command | Result |
|---|---|
| `/usr/bin/python3 -I <scratch>/count_camps.py` | The counts above, in 0.46 s |
| `/usr/bin/python3 -I <scratch>/count_confirmed.py` | HDC 0 and UM7 0 (paths naming it, files stored under it); UTNIF 2 and 2 |
| `.venv/bin/python -I -c …` (stored values against the alias table's keys) | 15 stored, 14 canonical names, `UNKNOWN` present |
| Operator follow-up 1's command, piped to a line count | 12 lines, 12 well-formed |
| `git diff HEAD origin/dev -- plan_specs/v1/e39-evidence-search-pilot/` | Only the start commit's phase: no PM amendment since the branch started |
| A count of the manifest paths' folders | 105 rows with a folder, 1 distinct folder, 0 folders that are a camp spelling or a confirmed word |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | 35 test files (the always-run list and the report and spec readers; only this report changed): **1667 passed in 92.45 s**, pytest exited 0 after 94 s |
| `uv run --frozen ruff check .`, `ruff format --check .` | All checks passed; 1729 files already formatted |
| `uv run --frozen lint-imports` | 20 kept, 0 broken |
| pyright | Not run: no Python changed |
| `scripts/check_command_blocks.py --base origin/dev`, `scripts/check_links.py`, `scripts/docs_index.py --check-descriptions` | OK: no `#` comments in 636 blocks (this report among them); 3232 links and anchors OK; 61 documents described |
| `uv run scripts/validate_specs.py` | OK: 549 files, 41 epics, 486 tasks, 22 releases. The Goal stays `InProgress` |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
