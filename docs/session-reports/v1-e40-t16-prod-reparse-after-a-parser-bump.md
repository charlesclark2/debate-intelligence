# Session report: v1-e40-t16-prod-reparse-after-a-parser-bump

| | |
|---|---|
| Task | `v1-e40-t16-prod-reparse-after-a-parser-bump` — Prod's parsed store re-parsed after a parser bump, from a copy restored with its sources |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t16-prod-reparse-after-a-parser-bump.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t16-prod-reparse-after-a-parser-bump.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t16-prod-reparse-after-a-parser-bump` |
| Session status | PARTIAL |

## Summary

The steps are written, to the PM's ruling of 2026-11-06 on the proposal (ac1). They live in the cutover
runbook's "Until the promotion", rewritten as one section in eight steps. Every hand publish sends the
weeks' raw sources and manifests. When three parser versions agree, the same publish also sends the
parsed store and the search index from the same restored copy: the installed build's, dev's index's,
and prod's function's (or the function about to be deployed from `main`). The parsed store is dev's
directory as restored, sent with `caselist parse --publish-only` and never parsed on the Mac. Three
checks guard it, each a Python heredoc that `tests/docs/test_prod_publish_checks.py` runs from the
runbook: the session checks, a `to_parse 0` check in the copy, and a comparison of the copy's index
with dev's on the PM's must-match set. The last two leave files in the copy that every prod-writing
block requires.

The promotion list gains the docx-9 promotion as item 6, and items 7, 8 and 10 are rewritten for
docx-9. The backfiles runbook says how a backfile follows a parser bump. The cloud-run image check
prints a parser line. **ac2, the operator's prod run, has not run**: it waits for dev's 2026-11-11 run
at docx-9, the promotion carrying it, and the PM's word. So the session is PARTIAL and the Goal stays
InProgress.

Read first: the cutover section's step 1 (what may go to prod in a session) and step 4 (the
comparison).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `prod-reparse` | IN PROGRESS | Written (ac1) and its criterion passes; the run (ac2) is the operator's, not yet |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the steps in the runbook, each with where it runs and what success looks like; check_command_blocks and check_links pass | PASS | `uv run scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 687 shell code blocks in 250 Markdown files`; `uv run scripts/check_links.py` → `OK: 3652 relative links and anchors in 617 Markdown files` |
| ac2: prod's parsed store at the new version, counts equal to dev's, index and function together, the copy deleted (operator) | NOT RUN | Waits for dev's run of 2026-11-11 at `2026.11.03-docx-9`, promotion item 6, and the PM's word |
| Node: docs checks pass (`uv run pytest tests/docs`) | PASS | `230 passed` |

Also run:

* `tests/scripts/test_caselist_run_image_plan_check.py` → `84 passed`.
* Every test outside `tests/docs` that names an edited document (19 files) → `365 passed in 45.20s`.
* `ruff check` and `ruff format --check` on `tests/docs` → clean.
* `pyright` on the two test files → `0 errors`.
* `lint-imports` → `20 kept, 0 broken`.
* `uv run scripts/validate_specs.py` → `OK: 643 files`.
* `uv run scripts/affected_tests.py --run` (101 files, the runbook edits reach every runbook-reading
  test) was stopped by `hard_stop.py` at its 115-second limit. Under the PM's ruling of 2026-10-19 it
  is left to the pull request's CI.

**Planted breaks.** Ten, each in the runbook's text, each caught by the test written for it (`1
failed`, or `11 failed` for the second):

1. The comparison drops `occurrence_rows`.
2. The comparison writes its OK file on a difference.
3. The checks ignore the `testcl26` seed.
4. The checks count no removal.
5. The checks deploy from any `main`.
6. The parse check ignores `to_parse`.
7. The parse check ignores zero sources.
8. `--publish-only` without the comparison's guard.
9. The index publish without the Wednesday guard.
10. The deletion's search at `-maxdepth 4`.

The file was restored with `git checkout HEAD --` and is clean.

## Files changed

* `docs/runbooks/caselist-cutover.md`: "Until the promotion" in eight steps:
  1. which weeks, and the checks;
  2. the copy;
  3. the parse check;
  4. the comparison with dev's index;
  5. raw sources and manifests;
  6. `--publish-only` per store, `openev` included;
  7. prod's function, then the index;
  8. the copy deleted, with the marker search.
* `docs/runbooks/evidence-search.md`: the promotion list's new item 6 (the docx-9 promotion), items 7,
  8 and 10 rewritten, the rest renumbered, and the references to them updated.
* `docs/data/evidence-search-pilot.md`: the tick table renumbered with the new row 6.
* `docs/data/parsed-card-store.md`, `docs/data/search-index.md` and
  `docs/runbooks/parsed-store-retention.md`: their references to the renumbered items.
* `docs/runbooks/caselist-backfiles.md`: "A parser bump: the rebuild in the cloud", with dev's rebuild
  and prod's once-only rule, and Q4 (i)'s measured needs. Also its refusal table and docs-index line.
* `docs/runbooks/caselist-cloud-run.md`:
  * a `PARSER:` line in "A new image, later"'s check, from the existing commands;
  * dev's function deployed the day after the first run at a new parser;
  * the backfile rebuild after a bump.
* `docs/runbooks/annual-purge.md`: its link to the deleting block, now step 8.
* `tests/docs/test_prod_publish_checks.py`: new; it runs the three heredocs on synthetic inputs and
  checks the guards of the blocks around them.
* `tests/docs/test_restored_copy_search.py`: the cutover's step 8 search, tested like the purge's and
  the landscape runbook's.

## Deviations from the spec

* **Tests in `tests/docs`.** The spec's packages list `tests/scripts`, but the runbook-block tests live
  in `tests/docs`, as `test_cutover_plan_checks.py` does. The two test files are there.
* **Renumbered promotion list.** The PM asked for the new promotion "as its own item, before items 6
  and 7". It is item 6, and old items 6 to 13 became 7 to 14. That touched references in
  `docs/data/search-index.md`, `docs/data/parsed-card-store.md` and
  `docs/runbooks/parsed-store-retention.md`, all inside the packages. Past session reports keep the
  old numbers.
* **No Wednesday, for every hand publish.** The section said "Wednesday after the run has recorded,
  or any day after". The PM's "never on a Wednesday" now covers the whole section, raw sources too,
  since it is one section.
* No spec edit was needed: the ruling's follow-ups are listed below for the PM.

## Decisions and assumptions

* **A failed check holds back the parsed store, not the raw sources.** The weekly raw publish must go
  on before the docx-9 promotion, when the parser versions cannot agree. So step 1 says `RAW SOURCES
  AND MANIFESTS: go on` and gives each reason the parsed store and index wait. Only `testcl26` in
  dev's index (J5 to J9), or an unreadable manifest, stops the whole session.
* **"No removal newer than the manifest"** compares each removal-log `recorded_at` with the
  manifest object's `LastModified`, since the manifest holds no build time.
* **The comparison reads the manifest the restore brought.** That is
  `tub-index/<id>/manifest.json`, restored under the same lock as the parsed store and checked
  against the pointer's digest. That is the same moment as the copy, which a second read of the
  bucket would not be. The index is built into `prod-index/` inside the copy, so it never shares a
  directory with the restored manifest and is deleted with the copy.
* **The steps run in order, and files in the copy enforce it.** Step 3 writes `parse-checked.txt`
  and step 4 writes `prod-index-compared.txt`, each only on OK. Step 4 refuses without the first.
  Steps 6 and 7 refuse without the second.
* **Step 7 re-reads prod's function's parser** before the index publish, and stops if it is not the
  restored version.
* **The deletion block has no guards.** The copy is deleted on every path, a Wednesday included.
* **`openev`**: step 6 publishes its parsed store. Its weekly manifests go through step 5 with
  `CASELIST=openev` when the runs list an `openev` week.
* **The room figure** is now measured (the operator's read of 2026-11-06), not estimated:
  * the four stores' `docx-7` parsed store was 11,147,679,654 bytes in 18,345 objects;
  * every raw source of the four stores was 4,983,016,785 bytes, an upper bound for the weeks'
    sources, since a weekly manifest names every stored source;
  * the Mac had 56 GB free.
* **Q6 (2)** needed no code: the check reads the parser constant at both commits with `git show`,
  as it already read the format. So no p2 follow-up is needed for it.

## Measured on 2026-11-06 (the operator's read-only block)

Bucket listings, counts only:

* Dev's parsed store at `2026.10.27-docx-7`:
  * `hsld26`: 7,033 objects, 3,533,189,389 bytes;
  * `hspolicy26`: 5,193 objects, 5,690,892,229 bytes;
  * `hspf26`: 6,011 objects, 1,722,797,405 bytes;
  * `openev`: 108 objects, 200,800,631 bytes;
  * `hspolicy25`: 14,343 objects, 13,510,680,041 bytes.
* Prod holds `docx-1`, `-2`, `-3`, `-5` and `-6` for the four stores, no `docx-7`, and no `hspolicy25`
  at all.
* Prod's newest weekly manifests are of 2026-10-13. Dev has 2026-10-20, 10-27 and 11-03 (`hspf26`:
  11-04), and the `full/2026-10-20` archives of `hspolicy26` and `hspf26`, which prod's listing
  lacks. Three weeks are owed.
* Raw sources dev holds and prod lacks:
  * `hsld26`: 2,060 objects, 252,101,999 bytes;
  * `hspolicy26`: 2,000 objects, 583,368,416 bytes;
  * `hspf26`: 1,571 objects, 608,721,305 bytes;
  * `openev`: 1 object, 1,018,033 bytes, under the same two manifest names, `2026-ld` and
    `2026-policy`.
* `hspolicy25`'s raw sources: 14,340 objects, 3,672,747,197 bytes.
* Dev's index `e95f10c1a8fda754`, at `docx-7`, SQLite 3.50.4: 57,760 documents, the list at 6 entries
  and 1 path hold, the four stores and no `testcl26`. Prod has no search index.
* **The functions (Q6), read 2026-11-06:**
  * Dev's function runs image `sha256:49f40f11…`, tag `e9769533f50c`, pushed 2026-11-02 22:05 CST
    and deployed 2026-11-03 04:05:59 UTC. That commit parses at `2026.10.27-docx-7` and writes index
    format 3, and both `origin/dev` and `origin/main` contain it.
  * Prod's function runs `sha256:e26ab269…` at `3f8276130`, deployed 2026-11-03 05:33:34 UTC. It
    parses at `docx-7` and writes index format 3. `origin/main` contains it; `origin/dev` does not,
    since it is the promotion's own commit.
  * So dev's function and dev's index (`e95f10c1a8fda754`) are both at `docx-7`, and Download is on
    in dev today. The ruling's plan stands: dev's function stays at `docx-7` until the 2026-11-11
    run's docx-9 index, and is deployed at docx-9 on 2026-11-12.
* Q4 (i) on the Mac: about 17.4 GB (`hspolicy25`'s parsed store and sources, and `openev`'s parsed
  store), against 56 GB free.

## Operator follow-ups

Two read-only blocks, after the weekend, never on a Wednesday. Each writes nothing to either bucket
or to disk, and prints counts, versions, digests and keys only.

**1. Sizes: the owed weeks, by name and by digest, and what they need** (expected runtime ~2 to 4 min,
listings and one fetch per owed manifest)
Where: your Mac, a new window
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e40-t16-prod-reparse-after-a-parser-bump
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(TZ=America/Chicago date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
else
  aws sso login --sso-session debate
  python3 -I - <<'SIZES'
import json, re, shutil, subprocess, tomllib
from pathlib import Path
def bucket(name):
    return tomllib.load(open("config/profiles/" + name + ".toml", "rb"))["storage"]["s3"]["bucket"]
DEV, PROD = bucket("dev"), bucket("prod")
PROFILE = {DEV: "debate-dev-evidence", PROD: "debate-prod-evidence"}
WHERE = {DEV: "dev", PROD: "prod"}
STORED = {"NEW", "UNCHANGED", "CHANGED", "DUPLICATE"}
FOLLOWED = ["hsld26", "hspolicy26", "hspf26", "openev"]
def aws(bucket, *arguments):
    ran = subprocess.run(["aws", *arguments, "--profile", PROFILE[bucket]], capture_output=True, text=True)
    if ran.returncode:
        code = re.search(r"\(([A-Za-z]+)\)", ran.stderr)
        print("  " + WHERE[bucket] + ": " + arguments[0] + " " + arguments[1] + " refused: " + (code.group(1) if code else "exit " + str(ran.returncode)))
        return None
    return ran.stdout
def listing(bucket, prefix):
    out = aws(bucket, "s3api", "list-objects-v2", "--bucket", bucket, "--prefix", prefix, "--query", "Contents[].[Key,Size]", "--output", "json")
    return {} if out is None else {key: size for key, size in (json.loads(out or "null") or [])}
def digest(bucket, key):
    out = aws(bucket, "s3api", "head-object", "--bucket", bucket, "--key", key, "--query", "Metadata.sha256", "--output", "text")
    return None if out is None else out.strip()
def named(bucket, key):
    out = aws(bucket, "s3", "cp", "s3://" + bucket + "/" + key, "-")
    found = {}
    for line in (out or "").splitlines():
        row = json.loads(line) if line.strip() else {}
        if row.get("kind") == "member" and row.get("classification") in STORED and row.get("sha256") and isinstance(row.get("byte_size"), int):
            found[row["sha256"]] = row["byte_size"]
    return found
def newest_version(store):
    versions = {}
    for key, size in listing(DEV, "parsed/" + store + "/").items():
        count, total = versions.get(key.split("/")[2], (0, 0))
        versions[key.split("/")[2]] = (count + 1, total + size)
    for version in sorted(versions):
        print("  parsed " + store + " " + version + ": " + format(versions[version][0], ",") + " objects, " + format(versions[version][1], ",") + " bytes")
    return versions[sorted(versions)[-1]] if versions else (0, 0)
def raw_prefix(store):
    return "raw/openev/" if store == "openev" else "raw/caselist/" + store + "/"
def owed(store):
    prefix = "manifests/" + store + "/"
    dev = {key[len(prefix):-6]: key for key in listing(DEV, prefix) if key.endswith(".jsonl")}
    prod = {key[len(prefix):-6]: key for key in listing(PROD, prefix) if key.endswith(".jsonl")}
    lacks = sorted(set(dev) - set(prod))
    differs = sorted(name for name in set(dev) & set(prod) if digest(DEV, dev[name]) != digest(PROD, prod[name]))
    print("  manifests " + store + ": dev " + str(len(dev)) + ", prod " + str(len(prod)) + "; prod lacks " + (", ".join(lacks) or "none") + "; another digest in prod: " + (", ".join(differs) or "none"))
    sources = {}
    for name in lacks + differs:
        sources.update(named(DEV, dev[name]))
    in_prod = {key.rsplit("/", 1)[-1] for key in listing(PROD, raw_prefix(store))}
    held = sum(1 for one in sources if one in in_prod)
    total = sum(sources.values())
    print("  sources those name: " + format(len(sources), ",") + ", " + format(total, ",") + " bytes; prod holds " + format(held, ",") + " of them")
    return lacks + differs, total
bundle = aws(DEV, "s3api", "head-object", "--bucket", DEV, "--key", "manifests/_run-state/run-state.tar.gz", "--query", "ContentLength", "--output", "text")
bundle_bytes = int(bundle.strip()) if bundle and bundle.strip().isdigit() else 0
print("run-state bundle: " + format(bundle_bytes, ",") + " bytes, gzipped")
parsed, sources, snapshots, newest = 0, 0, {}, {}
for store in FOLLOWED:
    print(store)
    newest[store] = newest_version(store)[1]
    parsed += newest[store]
    names, total = owed(store)
    sources += total
    snapshots[store] = names
print("hspolicy25")
backfile_parsed = newest_version("hspolicy25")[1]
openev_parsed = newest["openev"]
prefix = "manifests/hspolicy25/"
backfile_sources = {}
for key in listing(DEV, prefix):
    if key.endswith(".jsonl"):
        backfile_sources.update(named(DEV, key))
print("  sources its manifests name: " + format(len(backfile_sources), ",") + ", " + format(sum(backfile_sources.values()), ",") + " bytes")
free = shutil.disk_usage(Path.home()).free
print("hand publish copy: " + format(parsed + sources + bundle_bytes, ",") + " bytes (parsed " + format(parsed, ",") + ", owed sources " + format(sources, ",") + ", bundle " + format(bundle_bytes, ",") + " gzipped)")
print("Q4 (i) copy for hspolicy25: " + format(backfile_parsed + openev_parsed + sum(backfile_sources.values()) + bundle_bytes, ",") + " bytes")
print("free on the Mac: " + format(free, ",") + " bytes")
print("owed snapshots: " + "; ".join(store + " " + (", ".join(names) or "none") for store, names in snapshots.items()))
SIZES
fi
```
Success looks like the bundle's size, then for each store its parsed versions, a `manifests` line
(dev's count, prod's, what prod lacks, and any manifest prod holds under another digest), and a
`sources those name` line. Then `hspolicy25`, the `hand publish copy` and `Q4 (i) copy` totals, the
free bytes, and `owed snapshots`. A `refused:` line names the call and the AWS code. Paste it back
as it is.

**2. Dev's and prod's functions: the build and parser each runs (Q6)**, run 2026-11-06 (its result
is under Measured above) (expected runtime ~1 min)
Where: your Mac, a new window
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e40-t16-prod-reparse-after-a-parser-bump
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$OVERRIDES" || "$(TZ=America/Chicago date +%u)" = 3 ]]; then
  echo "STOP: a DEBATE_ override is set, or it is Wednesday"
else
  aws sso login --sso-session debate
  git fetch --quiet origin
  for ENVIRONMENT in dev prod; do
    URI=$(AWS_PROFILE=debate-admin aws lambda get-function --region us-east-1 --function-name "debate-${ENVIRONMENT}-tub" --query Code.ImageUri --output text)
    UPDATED=$(AWS_PROFILE=debate-admin aws lambda get-function-configuration --region us-east-1 --function-name "debate-${ENVIRONMENT}-tub" --query LastModified --output text)
    IMAGE=$(AWS_PROFILE=debate-admin aws ecr describe-images --region us-east-1 --repository-name "debate-${ENVIRONMENT}-tub" --image-ids "imageDigest=${URI##*@}" --query 'imageDetails[0].[imageTags[0],imagePushedAt]' --output text)
    COMMIT=$(printf '%s' "$IMAGE" | awk '{ print $1 }' | sed 's/-uncommitted-.*//')
    PARSER=$(git show "${COMMIT}:packages/debate_core/src/debate_core/integrations/docx_parser/parser.py" | sed -n 's/^DOCX_PARSER_VERSION: Final = "\(.*\)"$/\1/p')
    FORMAT=$(git show "${COMMIT}:packages/debate_core/src/debate_core/domain/search_index.py" | sed -n 's/^SEARCH_INDEX_FORMAT_VERSION: Final = \([0-9]*\)$/\1/p')
    echo "${ENVIRONMENT} function: image ${URI##*@}, tag and push time ${IMAGE}, updated ${UPDATED}"
    echo "${ENVIRONMENT} function: commit ${COMMIT}, parser ${PARSER:-unread}, index format ${FORMAT:-unread}, on origin/dev $(git merge-base --is-ancestor "$COMMIT" origin/dev 2>/dev/null && echo yes || echo no), on origin/main $(git merge-base --is-ancestor "$COMMIT" origin/main 2>/dev/null && echo yes || echo no)"
  done
fi
```
Success looks like two lines for `dev` and two for `prod`: the image digest, its tag (the commit) and
push time, when the function was updated, then the commit, its parser version and index format, and
whether `origin/dev` and `origin/main` contain it. Expected: prod at `3f82761…`, parser
`2026.10.27-docx-7`. Dev's is the open question.

**3. ac2, later**: the cutover runbook's "Until the promotion", steps 1 to 8, after all of these:

* dev's 2026-11-11 run records its index at `2026.11.03-docx-9`;
* dev's function is deployed at docx-9 on 2026-11-12;
* promotion item 6;
* the PM's word.

Never on a Wednesday.

## Follow-up work

* **p2, wanted before the prod session: a dry run for `caselist parse --publish-only`** (the PM's Q7).
  Until it exists, steps 3 and 4 stand as its plan.
* **p3: a backfile with no directory at the running parser version is named** (accepted by the PM,
  Q4). `caselist runs --remote` or `doctor` would say so.
* **Prod's one-time backfile publish**, tied to the promotion, before the run's home moves (Q4 (i)):
  the steps are not written here. The size block above measures what it needs.
* **`openev` differs by one raw object** between dev and prod under the same manifest names. Size
  block 1 says whether a manifest's digest differs. If it does, step 5 with `CASELIST=openev`
  publishes it, and the PM may want to know which re-import caused it.
* **Stale note:** `docs/data/evidence-search-pilot.md`'s row 9 still says "Not before `v1-e30-t33`",
  which has merged. That is the PM's record to update.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-06

**Notes:**

Written to the ruling. The steps cannot run out of order, because the files the checks leave in the copy
gate every prod write, and the checks are tested where they live: in the runbook's own text, against
ten breaks planted there.

1. **ac1 passes.** "Until the promotion" is one eight-step section. Prod's parsed store is dev's
   directory as restored, sent with `--publish-only`, and never parsed on the Mac. The comparison
   uses the must-match set, with index_id reported but not required. testcl26 in dev's index, or a
   removal newer than the manifest, stops the parsed store. Each step says where it runs and what
   success looks like. The command blocks, links and `tests/docs` (230) pass, and the 101-file
   affected set is the pull request's `ci` under the ruling of 2026-10-19.
2. **The measurements settle Q6 and size the session.** Dev's function and dev's index are both at
   docx-7 (image `e9769533f50c`, deployed 2026-11-03), so Download is on in dev today and the ruling's
   order stands: dev's function goes to docx-9 on 2026-11-12, after the 11-11 run. Prod is three weeks
   behind (newest manifests 2026-10-13, the `full/2026-10-20` archives missing) and holds no docx-7.
   The first prod session therefore covers three weeks and a whole new directory. About 11.1 GB of
   parsed store plus at most 5.0 GB of sources against 56 GB free fits. So does Q4 (i)'s 17.4 GB.
3. **Deviations accepted.** The tests in `tests/docs` follow `test_cutover_plan_checks.py`. The
   promotion list is renumbered with the docx-9 promotion as item 6: prod's parsed store is now 7,
   the index 8, removal 9 and retirement 10. Past reports keep the old numbers. "Never on a
   Wednesday" covers the whole section.
4. **Decisions accepted.** A failed check holds back the parsed store and index, not the weekly raw
   publish, because that has to go on until the docx-9 promotion. The comparison reads the manifest
   restored under the same lock, which is the same moment as the copy. Step 7 re-reads prod's
   function's parser before the index publish. The deletion block has no guards, so it deletes on
   every path. Q6 (2) needed no code.
5. **Operator follow-up 1 runs from the main clone**, not this worktree, which may be gone by then:
   replace its first line with `cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence`.
   Run it after the weekend, never on a Wednesday, and paste it back as it is (counts, keys and digests
   only). Follow-up 2 has run, and its result is above.
6. **Follow-ups, which the PM files in the next batch:**
   - the `--publish-only` dry run, p2, wanted before the prod session (E31, beside v1-e31-t30);
   - a backfile with no directory at the running parser version is named, p3 (E40);
   - prod's one-time backfile publish, p3, tied to the promotion (E40).
   The openev object that differs between dev and prod waits for follow-up 1's digest line. The
   PM updates `evidence-search-pilot.md`'s stale row in the same batch.
7. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until ac2 is
   recorded, after dev's 2026-11-11 run at docx-9, dev's function on 2026-11-12, promotion item 6 and
   the PM's word.
