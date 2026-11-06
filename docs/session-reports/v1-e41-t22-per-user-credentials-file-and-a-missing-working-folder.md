# Session report: v1-e41-t22-per-user-credentials-file-and-a-missing-working-folder

| | |
|---|---|
| Task | `v1-e41-t22-per-user-credentials-file-and-a-missing-working-folder` — Keys come from a per-user file in any folder, and a deleted working folder no longer crashes a command |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t22-per-user-credentials-file-and-a-missing-working-folder.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t22-per-user-credentials-file-and-a-missing-working-folder.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t22-per-user-credentials-file-and-a-missing-working-folder` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

## Proposal for the PM's ruling (written before any code)

Read for it: `debate_core.application.settings` (every layer and every `cwd` read), `config show`,
`doctor`, v1-e07-t13's report (Q2 and the PM's ruling), `docs/runbooks`, `docs/guides`, the CLI
README's search section, `.env.example` and the root README's precedence paragraph.

### What is true today, and where it differs from the spec's wording

* **There is one `.env`, not two layers.** The spec lists "the working folder's `.env`, the
  checkout's `.env`". `_default_dotenv_path` (settings.py line 1615) reads exactly one file: the
  checkout root's `.env` when the working folder is inside a checkout (`find_repository_root`), and
  the working folder's own `.env` only outside one. The order today is: flag, `DEBATE_*` variables,
  that one `.env`, the profile, the built-in profile, the field default.
* **A blank exported variable already wins.** Measured with invented values: an exported
  `DEBATE_PROVIDERS__CONTACT_EMAIL=` (empty) over a `.env` that sets an email leaves the setting
  blank, with source `env:DEBATE_PROVIDERS__CONTACT_EMAIL`, and Crossref uses its public pool.
* **The crash, traced.** `debate-research --version` run from a deleted folder exits 70 with
  `FileNotFoundError` from `root_callback` (app.py line 197) → `resolve_environment` →
  `_environment_from_dotenv` → `_default_dotenv_path` → `find_repository_root` → `Path.cwd()`.
  `load_settings` fails the same way.
* **No runbook or guide names the smoke folder.** `grep -rn crossref-smoke` finds it only in three
  session reports (v1-e07-t03, v1-e07-t13, and the PM's review of v1-e08-t10, which asks for that
  task's live check to be run from `~/Documents/debate/crossref-smoke`). What tells a reader where
  keys are read is the CLI README's search section ("Today a `.env` is read from the checkout a
  command runs in, or, outside a checkout, from the folder it runs in"), `.env.example`'s precedence
  comment and the root README's precedence paragraph.
* **Plain `doctor` loads no settings, on purpose**: `scripts/install_channel.sh` and `validate-dev`
  run it on machines with no configuration (doctor.py module docstring). Provider rows need
  settings.

The relay block in this session's message to the operator carried the proposal and its questions.

### The PM's ruling (2026-11-05)

1. **Order: yes**, flag > `DEBATE_*` variables > the one `.env` > `~/.debate-research/<env>.env` >
   profile > built-in > default. `<env>` is the resolved environment, `DEBATE_ENV` is never read
   from the file, the path is fixed, `test` reads no per-user file, the higher layer wins outright
   and a blank counts, `config show` prints only the winner, masked, with no new JSON key. The guide
   says plainly that a key left in a checkout's or folder's `.env` wins, and how to see which won.
2. **The four names, as a constant**; the caselist token refused with the `caselist auth login`
   hint; the completeness test accepted; refusals name the file and line, never a value; a line
   without `=` or with an invalid name by its line number only; a name given twice refused with both.
3. **`0o077`**, one rule with the token file; `fstat` on the open file before any byte is read; a
   symlink judged by its target; no ownership check; refused on Windows; a file the owner cannot
   read gives "could not read". A `0o620` file is refused too, by test.
4. **Yes**: one `working_folder()`, every startup read through it, relative-path validators a
   `ConfigurationError` naming the field, the one warning line from the root callback.
   `--version` from a deleted folder exits 0 with the warning, red first against exit 70.
5. **`doctor --providers`**, rows as proposed, except OpenAlex's: "with a key" / "keyless (a lower
   daily allowance)", because the daily figures are not this build's.
6. **A**: an autouse fixture in the root `conftest.py`; a Deviation.
7. **All three docs**; the guide uses placeholders only, and its move-the-keys block prints no value.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
