# Session report: v1-e07-t13-profiles-enable-the-providers-that-passed-their-smoke

| | |
|---|---|
| Task | `v1-e07-t13-profiles-enable-the-providers-that-passed-their-smoke` — The dev and prod profiles enable the discovery providers whose live smoke passed |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t13-profiles-enable-the-providers-that-passed-their-smoke.yaml`](../../plan_specs/v1/e07-discovery-adapters/t13-profiles-enable-the-providers-that-passed-their-smoke.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t13-profiles-enable-the-providers-that-passed-their-smoke` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Both committed profiles now enable `openalex`, `crossref`, `rss`, `federal_register` and `govinfo`.
These are the providers with an adapter whose live smoke the PM recorded as passed on 2026-11-02.
The profiles' comments say what a machine without a contact email or an api.data.gov key sees. So do
the search guide (the `debate-research search` section of `packages/debate_cli/README.md`) and twelve
new tests that run on the committed profiles themselves. Enabling the government providers does not
widen their scope: they are still asked only on a topic whose feed file lists them, today NHI.

**Look first at** the request cost (part 3). Crossref still asks once per query, and its pacing is the
whole cost. On the recorded fixtures the twelve-query NHI link search went from 0.17 s to 9.15 s
without a contact email, sending 9 Crossref requests and leaving 3 "not asked", so every such search
is partial (exit 6). With an email it takes 3.8 s and sends all 12. Then look at the key-location
proposal (part 4). Nothing is built for either; both wait for your ruling, in the relay block under
Follow-up work.

Commit ids are on this branch, from `origin/dev` at `eb16dda`. The spec on dev differs only in its
phase.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `profiles-enable-the-providers-that-passe`: Providers enabled | Done | Profiles `a8bff7d`, tests `94d28ae` (shown failing first against the pre-task profiles), guide and container docstring `820b8ed`, `2defe9d`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the providers whose smoke passed are enabled in both profiles, the profiles' tests and the guide say so, and a run without a key or an email reports not_configured or the public pool as designed | PASS | Profiles: `config/profiles/dev.toml` and `prod.toml` `[providers] enabled = ["openalex", "crossref", "rss", "federal_register", "govinfo"]`. Tests: `test_the_committed_profiles_enable_the_providers_whose_smoke_passed_and_set_no_credential[dev,prod]` (`config show`: the five, from `profile:config/profiles/<env>.toml`; `providers.contact_email` and `providers.api_data_gov_key` null from `default`). Five search tests over the committed profiles, each run under dev and prod (the list follows this table). Guide: the README's search section, "Without a contact email or a key". |
| Node: `uv run pytest packages/debate_cli/tests -k "profile or settings"` | PASS | `108 passed, 5 warnings in 7.86s` (96 before this task, plus the 12 new) |

The five search tests on the committed profiles, run under dev and prod:

* `…a_search_with_no_topic_asks_crossref_publicly_and_no_government_source`: the footer is `openalex: ok, 3 results`,
  `crossref: ok, 1 result`, `rss: ok, 2 results`. The Crossref request has no `mailto` in its URL or its
  User-Agent, and neither government host is asked.
* `…a_contact_email_puts_crossref_in_the_polite_pool_and_is_never_printed`: with an invented address,
  the request carries `mailto=` and the User-Agent `mailto:` it, and neither output stream contains it.
* `…a_search_on_the_nhi_topic_without_a_key_reports_govinfo_not_configured`: exit 6. The Federal
  Register answers (`federal_register: ok, 1 result`), and the footer ends with `govinfo: not
  configured: no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY)`. GovInfo's host is never asked.
* `…a_search_on_the_nhi_topic_with_a_key_asks_govinfo_and_is_complete`: with an invented key, exit 0,
  `govinfo: ok, 1 result`, and the key is printed nowhere.
* `…without_a_contact_email_crossref_names_the_public_pool_in_the_footer`: the twelve-query NHI link
  search, `--providers crossref`, with a running clock and the timeout at 2 s. Exactly one Crossref
  request. The footer is `crossref: partial, 1 result from 12 queries: not asked: the public pool
  allows 1 query a second; set a contact email for the polite pool`, and the search exits 6.

### Shown failing first

The tests were committed (`94d28ae`). Then `config/profiles` was put back to `8ee3a7d` (the pre-task
`["openalex", "rss"]`) and the twelve were run (`hard_stop.py 115 … pytest -k "committed_profile or
committed_profiles_enable" -n 4 --tb=line`). Result: `12 failed`, each at an assertion:

* the config test: `assert ['openalex', 'rss'] == ['openalex', …'govinfo']`;
* no topic: a footer without the crossref line;
* the polite pool: `'  crossref: ok, 1 result' in [… no crossref …]`;
* NHI without a key and NHI with one: the exit-code assertion (0 where 6 was expected, and the search
  text where 0 was expected);
* the public pool: the exit-code assertion, because crossref was not enabled and the search failed.

The profiles were restored with `git checkout HEAD -- config/profiles`, and the tree was clean.

### Part 2: the government providers' scope

Enabling them in the profiles does not change their scope. `TOPIC_ENABLED_PROVIDERS` and the fan-out
still ask `federal_register` and `govinfo` only when two things hold: `providers.enabled` lists them,
and the search's `--topic` is one whose feed file lists them under `government_providers`. Only
`config/feeds/health-insurance.yaml` does, for `policy-2026-27-nhi`. No code or feed file changed.
The tests show it on the committed profiles: no topic means neither host is asked and neither is in
the footer; the NHI topic asks the Federal Register once for a one-query search.

### Part 3: requests and fixture wall time per search, before and after

A temporary measuring test (never committed) ran in `test_search_command.py`'s seams. The container
built every provider from the committed profile itself, `DEBATE_ENV` was dev or prod, and the
profile's own per-host interval applied. The committed `config/feeds/` lists were read, with every
feed answered by the Courier fixture. The clock ran from the fixture's `NOW` in real time, so
Crossref's pacer could advance. "Before" is HEAD at `8ee3a7d`'s profiles; "after" is `a8bff7d`. The
email and key were invented values set in the environment. Dev and prod agreed within 0.05 s on every
row.

| Search | Queries | Credentials | Before: requests (OA + feeds), wall, exit | After: OpenAlex, Crossref, Federal Register, GovInfo, feeds | After: wall, exit |
|---|---|---|---|---|---|
| `midterm elections --since 2026-09-14` | 1 | any | 1 + 10, 0.11–0.14 s, 0 | 1, 1, 0, 0, 10 | 0.08–0.13 s, 0 |
| `health insurance --argument politics-da --need link` | 7 | none | 1 + 10, 0.12–0.14 s, 0 | 1, 7, 0, 0, 10 | 6.10–6.15 s, 0 |
| same | 7 | email | same | 1, 7, 0, 0, 10 | 2.11–2.12 s, 0 |
| `national health insurance --argument politics-da --need link --topic policy-2026-27-nhi` | 12 | none | 1 + 10, 0.16–0.17 s, 0 | 1, **9 (3 not asked)**, 12, 0 (not configured), 10 | **9.15 s, 6** |
| same | 12 | email | same | 1, 12, 12, 0 (not configured), 10 | 3.82 s, 6 |
| same | 12 | email and key | same | 1, 12, 12, 12, 10 | 3.82–3.83 s, 0 |

All of the added time is Crossref's pace. The fixtures answer at once, so the wall time is the pacer:
one query a second on the public pool and three on the polite pool. The other providers add requests
but no measurable time. A live search adds Crossref's own answer times on top. For the twelve-query
NHI search the requests go from 11 to 32 (no credentials), 35 (email) or 47 (email and key), against
`providers.search_deadline_seconds` of 15 s. Without an email the last three of twelve queries are
always not asked under the profiles' 10-second timeout, so every expanded NHI search on such a
machine is partial. It is also partial without a key, through GovInfo. A search of seven queries
sends all seven on either pool, as the operator's 2026-11-02 smoke found.

I judge this heavy for a student's machine without an email. The options are in the relay block below.

### Part 4: where `.env` and the keys are looked for today

Read from `debate_core.application.settings`:

* **The process environment**, from wherever the command runs: `DEBATE_PROVIDERS__CONTACT_EMAIL` and
  `DEBATE_PROVIDERS__API_DATA_GOV_KEY` (`_environment_layer`).
* **One `.env` file, and only one** (`_default_dotenv_path`, settings.py line 1615). The code calls
  `find_repository_root()`, which walks up from the working folder to the nearest folder holding
  `config/profiles`. If it finds one, the file is `<that folder>/.env`; if not, it is
  `<working folder>/.env`. Nothing else is tried: not the home folder, not the data directory, not
  the folder of the installed build.
* An installed build reads its profiles from its wheel, but its `.env` from the working folder as
  above. Run from `~/Documents/debate/crossref-smoke` it reads that folder's `.env`, which is why the
  operator's keys work there. Run from `$HOME`, it reads `$HOME/.env` only if one exists, so it runs
  keyless. Run inside a source checkout, it reads the checkout's `.env`.
* The same file is also where `DEBATE_ENV` may come from (`resolve_environment` →
  `_environment_from_dotenv`), so it is read before any profile.
* **The crash.** `find_repository_root` calls `Path.cwd()` (settings.py line 1504), and
  `_default_dotenv_path` calls it again. When the working folder no longer exists, `Path.cwd()` raises
  `FileNotFoundError`, and nothing catches it. I reproduced this offline: `load_settings()` run from a
  deleted scratch folder fails in `resolve_environment` → `_environment_from_dotenv` →
  `_default_dotenv_path` → `find_repository_root` → `Path.cwd()`. `--version` takes the same path
  (`app.py` line 197), so it crashes too.

The proposal is in the relay block. No key, email or token was read, printed or written in this
session. The only values used were invented ones in tests and in the measurement.

## Checks before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | 205 of 692 test files selected (the container docstring edit and the profiles widen the set). Stopped at the 115-second limit at 54%, with no failure mark in the output. **Over two minutes, so under agreement 10 it is left to the pull request's `ci` check, not handed over.** |
| The changed test files, the profile readers and the always-run list: `hard_stop.py 115 … pytest -m "not slow and not live and not partition_proof" -n auto` over `test_search_command.py`, `test_config_command.py`, `test_version.py`, `test_installation.py`, `test_container_factories.py`, `test_app.py`, `test_help_rendering.py`, `commands/test_doctor.py`, `tests/architecture`, `tests/specs`, `tests/smoke/test_cli_smoke.py`, `tests/scripts/test_stamp_build.py`, `debate_core/tests/application/test_settings.py` | `720 passed in 26.48s` |
| `… pytest -n 0 packages/debate_core/tests/application/test_settings_environments.py` | `34 passed in 0.15s` |
| `uv run ruff format --check .` / `uv run ruff check .` | `1941 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 72 CLI command and API route handlers within 25 statements` |
| `uv run python scripts/check_command_blocks.py --base origin/dev` | OK: no `#` comments in 670 shell code blocks in 247 Markdown files (1 session report changed since origin/dev) |
| `uv run scripts/validate_specs.py` (after setting the phase to Succeeded) | `OK: 619 files, 41 epics, 556 tasks, 22 releases` |

## Files changed

* **`config/profiles/dev.toml`, `prod.toml`:** the five providers are enabled. Dev's comment says
  which smoke passed, what a machine without an email or a key sees, and that the government scope is
  unchanged; prod's points to it. No credential is in either file: `test_settings.py`'s existing scan
  passes, and the new config test checks it too.
* **`packages/debate_cli/tests/test_config_command.py`:** the committed profiles' enabled list, its
  source, and no credential from them.
* **`packages/debate_cli/tests/test_search_command.py`:** the `committed_profile` fixture (dev and
  prod, the container building the providers, run from a folder of its own so no `.env` can supply a
  credential) and five tests. The shared `Seams` gains `moving_clock`, which is off by default, so
  every existing test keeps its still clock.
* **`packages/debate_cli/README.md`:** the search guide says which providers the profiles enable and
  what a student without an email or a key sees. It also says where a `.env` is read today, and gives
  the GovInfo rate as about 80 twelve-query searches an hour (it said 90 at eleven queries).
* **`packages/debate_cli/src/debate_cli/container.py`:** the `discovery_providers` docstring no longer
  says Crossref and the government sources are "not enabled by default". Docstring only.

## Deviations from the spec

1. **The public pool is not named on every search.** The brief says a student without an email sees
   "Crossref's public pool, named in the footer". The footer names the pool only when it could not
   send a query in time, which happens on an expanded search. A one-query search without an email
   shows `crossref: ok, N results`, exactly as with one. `CrossrefProvider.__repr__` names the pool,
   but nothing a student sees prints it. The tests and the guide state the real rule. Naming the pool
   on every search would be a presenter or adapter change, and the brief keeps the providers' code
   unchanged, so I did not make it; it is a question in the relay block.
2. **The search guide is the CLI README.** No search guide exists under `docs/guides/` (the spec's
   packages list it). The search command's guide is the `debate-research search` section of
   `packages/debate_cli/README.md`, which is inside the `debate_cli` package constraint, so that is
   where the update went. `v1-e08-t15`'s spec also names "the search guide" with `docs/guides` and
   will meet the same gap.

## Decisions and assumptions

* **The order of `enabled`** is OpenAlex, Crossref, the feeds, then the two government sources. The
  setting says "in no order", but the footer follows it, so scholarly sources come first, then news,
  then the topic-only sources.
* **The public-pool test lowers the timeout to 2 s.** At the profiles' 10 s the test would take about
  9 s of real time. With 2 s it shows the same footer in about a second and is deterministic: the
  second query's turn falls after its deadline whatever the load. The 10 s behaviour is the
  measurement above.
* **No extra secret scan.** `test_no_committed_profile_contains_anything_that_looks_like_a_secret`
  (debate_core) already reads every committed profile for each credential field. The new CLI test
  checks the effect instead: with no environment, both credentials are null and come from `default`.

## Operator follow-ups

None required. The smokes this task rests on are the PM's records of 2026-11-02. Once the next dev
pre-release is installed, `debate-research config show` from any folder will list the five providers
under `providers.enabled`.

## Follow-up work

Two proposals and one question, for the PM. Nothing below is built.

```text
PM questions from v1-e07-t13 (2026-11-05). Profiles enabled; nothing below is built.

Q1. Crossref's cost on an expanded search (measured on the recorded fixtures, both profiles)
    The 12-query NHI link search went from 0.17 s and 11 requests to:
      no email: 9.15 s, 9 Crossref requests + 3 "not asked", exit 6 every time
      email:    3.82 s, 12 Crossref requests
    7 queries: 6.1 s without an email, 2.1 s with one. One query: no change (0.08-0.13 s).
    All of the added time is Crossref's pace (1 query/s public, 3/s polite). Live adds answer time.
    Options:
      A. Cap Crossref per search: send the first N queries in expansion order. Treat the rest as
         "not asked: capped at N", which is NOT partial (like v1-e07-t14's "not counted as partial").
         Computed from the pace, not measured: N=4 is about 3 s public, about 1 s polite.
         N=4 sends only link templates on NHI (the 5 mechanism queries come last).
      B. Join: one Crossref request with the queries' words together. Crossref's query.bibliographic
         is a relevance-scored free-text match with no documented OR, so it is a different search,
         and attribution falls back to "every query", as OpenAlex's mostly does live.
         Needs a live comparison (operator) before anyone could judge it.
      C. Leave it. Make the contact email part of setup (Q2 makes that one step per machine).
         With an email, all 12 are sent in about 3.8 s plus Crossref's answer times.
    Recommendation: C now, and A as a follow-up only if students go without an email.
    Why: with an email the cost is about 4 s inside the 15 s deadline, and every query is asked.
    A cap discards coverage to save time a one-line setup already saves.

Q2. Where keys live (proposal; settings code is outside this task's packages)
    Today: exported DEBATE_PROVIDERS__* variables, or ONE .env: <checkout root>/.env when the
    working folder is inside a checkout, else <working folder>/.env. Run from $HOME, the build is
    keyless. A deleted working folder crashes every command, --version included: Path.cwd()
    raises FileNotFoundError, in find_repository_root and _default_dotenv_path.
    Proposal:
      - A per-user file ~/.debate-research/<env>.env, read below a found .env and above the profile.
        The path is fixed: it must be known before settings, and the data dir is a setting.
      - It holds credentials only (contact_email, openalex/semantic_scholar/api_data_gov keys,
        caselist_token). Any other DEBATE_* in it, DEBATE_ENV included, is refused by name.
      - It is refused when group/other can read it, with the message naming `chmod 600 <file>`.
      - A working folder that cannot be read counts as "no checkout, no .env". The command goes
        on; config show says the folder could not be read.
      - config show: the Source column names the file (user-env:~/.debate-research/dev.env), and
        the value is ***. No new JSON key (the smoke pins those key sets whole).
      - doctor: a row like its Model profile row that never fails, per enabled provider, e.g.
        "crossref: contact email set (user-env:…), polite pool" or "crossref: no contact email,
        public pool"; "govinfo: no api.data.gov key, not configured". Values never printed.
    Sub-questions: (a) refuse or only warn on a readable file? I recommend refuse.
      (b) Should a command that writes the file from a hidden prompt (never argv) come now or
      later? I recommend later. (c) Build it as a new task in debate_core.application settings?
      I recommend yes, with the cwd crash fix in the same task.

Q3. Should a one-query search name Crossref's pool? Today the footer names it only on "not asked".
    I recommend no: doctor (Q2) is where a missing email belongs, not every search's footer.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-05

**Notes:**

The three providers that passed their smokes are on in both profiles, the government sources keep their
topic scope, and the cost of turning Crossref on is measured instead of discovered by students.

1. **ac1 passes.** Both profiles enable openalex, crossref, rss, federal_register and govinfo; twelve new
   tests on the committed profiles themselves, red first against the pre-task profiles (12 failed, each at
   an assertion); no credential in either profile, and none printed with invented values set.
2. **Part 2:** scope unchanged. The government providers are still asked only on a topic whose feed file
   lists them (NHI), shown by test with no topic and with the NHI topic.
3. **Part 3, the PM's ruling on Q1: C.** With a contact email the 12-query NHI search sends every query in
   about 3.8 s inside the 15 s deadline; a cap would discard coverage that one line of setup saves. A cap
   (A) is filed only if machines without an email become common. The join (B) is not pursued: Crossref
   has no OR, so it would be a different search.
4. **Part 4, Q2: approved as a new task**, filed by the PM (E41, p2) with the working-folder crash fix in
   the same task: a per-user `~/.debate-research/<env>.env` holding credentials only, (a) refused when
   group or others can read it, (b) no writing command yet, (c) in `debate_core.application` settings;
   `config show` names its source with the value masked, and `doctor` gains the never-failing provider
   rows.
5. **Q3: no.** A one-query search doesn't name Crossref's pool; doctor is where a missing email belongs.
6. **One more follow-up the PM files (E07, p3):** a provider that is `not configured` (GovInfo without a
   key) makes every NHI search exit 6, though a retry can never get more. It should be named in the footer
   without making the search partial, as v1-e07-t14's standing feed failures are.
7. **Deviations accepted.** (1) The public pool is named only when a query goes unasked; the tests and the
   guide state the real rule. (2) The search guide is the CLI README's search section; the PM notes it on
   v1-e08-t15's spec, which names a guide that doesn't exist.
8. **Closing checks:** the affected set (205 files) is left to `ci` (agreement 10); the changed files,
   profile readers and the always-run list (720 passed), the settings tests, ruff, pyright, lint-imports,
   thin handlers, command blocks and the specs are clean.
9. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.
