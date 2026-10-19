# Session report: v1-e04-t01-url-canonicalization

| | |
|---|---|
| Task | `v1-e04-t01-url-canonicalization` — URL canonicalization and identifier detection |
| Spec | [`plan_specs/v1/e04-article-retrieval/t01-url-canonicalization.yaml`](../../plan_specs/v1/e04-article-retrieval/t01-url-canonicalization.yaml) |
| Epic / release | `v1-e04-article-retrieval` / `v1.3` |
| Branch | `task/v1-e04-t01-url-canonicalization` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

New package `debate_core.retrieval`, pure functions only. `canonicalize_url` applies the RFC 3986
syntax rules, unwraps link wrappers and AMP caches when the destination is written out in the URL,
then strips the documented tracking parameters and AMP variants and sorts what is left.
`apply_rel_canonical` accepts a same-site canonical, accepts a cross-site one only from an AMP cache
to its origin's site, and records the rule as a stable `StrEnum` value. `detect_identifiers` finds
DOIs, arXiv ids and PMIDs in URLs and text. "Same site" means the same registrable domain, read
from a Public Suffix List snapshot that is a file in the package and is never fetched. Every
criterion passed and the Goal is `Succeeded`.

**PM rulings of 2026-10-19 are applied** (see "PM rulings" near the end):

- `pyproject.toml` is now in the spec's packages, as a PM amendment.
- `debate_core.retrieval` is also on the boto3, httpx and lxml forbidden lists. Each new entry is
  shown failing under a deliberate import.
- The trailing-slash prose is amended.
- The Public Suffix List pin moved to a `shasum` file, so one documented command refreshes the
  list and its hash together.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `canonical-rules` | Done | `retrieval/canonical_url.py` and `retrieval/query_parameters.py`. 63-pair variant table, rule tests and a 4-property Hypothesis suite. |
| `rel-canonical` | Done | `apply_rel_canonical`, `RelCanonicalRule` and `RelCanonicalDecision` in `canonical_url.py`. Registrable domains come from `retrieval/public_suffix.py` and the bundled list. |
| `identifiers` | Done | `retrieval/identifiers.py`: `detect_identifiers` returns `ScholarlyIdentifiers`, which `as_article_identifiers()` turns into the domain `ArticleIdentifiers`. |
| `quality-gates` | Done | Idempotence property beside the table, pyright over `packages/debate_core`, then 65 mutants, all caught on the final source. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: canonicalize_url is idempotent and maps a table of at least 40 real-world variant pairs (news, think-tank, .gov, AMP, Google News redirect patterns) | PASS | Table: 63 pairs (13 news, 14 AMP, 9 link-wrapper/redirect, 8 think tank, 14 .gov, 5 IDNA/Unicode). Every PM-required shape is in it: percent-encoded paths, IDNA hosts (including `faß.de`), content parameter beside tracking ones, Google News legacy and Google `/url` redirects decoded from the query, the Google News `/articles/CBMi…` id kept undecoded, AMP in host, path and query forms, and trailing-slash rows kept both ways. `test_a_variant_maps_to_its_canonical_form` and `test_a_canonical_form_is_its_own_canonical_form` pass for all 63. Idempotence property `test_canonicalization_is_idempotent` passes at 300 examples (default) and at 15,000 examples per property (`URL_PROPERTY_EXAMPLES=15000`, fresh database, `4 passed in 40.81s`). |
| ac2: tracking stripping uses a documented allow/deny list; content parameters (id, p, article) are preserved | PASS | `retrieval/query_parameters.py`: 68 deny entries, 14 allow entries and 2 AMP markers, each with its reason. `test_an_allow_listed_parameter_survives_beside_tracking_parameters` (14 cases), `test_every_deny_rule_strips_its_parameter` (68), `test_no_deny_rule_or_amp_marker_matches_an_allow_listed_parameter` (14), `test_an_unknown_parameter_is_kept` (10), and the property `test_a_content_parameter_survives_with_its_value`. All pass. |
| ac3: apply_rel_canonical accepts same-registrable-domain canonicals, rejects cross-domain ones unless allow-listed (AMP caches), records the rule | PASS | `uv run pytest packages/debate_core/tests/retrieval/test_canonical_url.py -k rel_canonical` → `25 passed in 10.22s`. Covers: same site on another subdomain; relative, scheme-relative and document-relative references; http vs https; refusals for a syndication partner, `bbc.co.uk`/`bbc.com`, two owners under `co.uk`, two owners under `github.io`, and two IPs; AMP cache and Google AMP viewer accepted; an AMP cache naming a third site refused; a link wrapper refused; unusable references; stable rule values. |
| ac4: detect_identifiers finds DOI, arXiv (new and old style) and PMID in URLs and text and normalizes them | PASS | `uv run pytest packages/debate_core/tests/retrieval/test_identifiers.py` → `64 passed in 5.10s`. Includes trailing `.` `)` `,` `;` in running text for each kind, and a DOI that ends in its own parenthesis (`10.1061/(asce)0733-9445(2004)130:4(605)`). |
| Node `canonical-rules`: canonicalization table tests pass | PASS | `uv run pytest packages/debate_core/tests/retrieval/test_canonical_url.py` → `300 passed in 11.29s` |
| Node `rel-canonical`: rel=canonical tests pass | PASS | `uv run pytest packages/debate_core/tests/retrieval/test_canonical_url.py -k rel_canonical` → `25 passed in 10.22s` |
| Node `identifiers`: identifier tests pass | PASS | `uv run pytest packages/debate_core/tests/retrieval/test_identifiers.py` → `64 passed in 5.10s` |
| Node `quality-gates`: retrieval tests pass | PASS | `uv run pytest packages/debate_core/tests/retrieval` → `468 passed in 4.26s` (final code, after the rulings; 467 before the pin test was split in two) |
| Node `quality-gates`: pyright passes | PASS | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`, and CI's `uv run --frozen pyright` → the same (10.9 s), both on the final code after the last format. |
| Epic node `t01`: task reports phase Succeeded | PASS | `uv run scripts/validate_specs.py --require-succeeded v1-e04-t01-url-canonicalization` → `v1-e04-t01-url-canonicalization: Succeeded`; `uv run scripts/validate_specs.py` → `OK: 366 files, 38 epics, 308 tasks, 20 releases` |

### Red run first

The tests were written against a refuse-nothing skeleton with the real signatures, then committed
in that state (`40b81ee`). In the skeleton, `canonicalize_url` returned its input,
`apply_rel_canonical` accepted everything, `detect_identifiers` found nothing,
`registrable_domain` returned the host, and the rule tables were empty. The run was
`pytest packages/debate_core/tests/retrieval -n 0`: **213 failed, 141 passed, 3 skipped**.
Representative failures:

```text
E       AssertionError: assert 'HTTPS://WWW....mes&smtyp=cur' == 'https://www....us-trump.html'
E       AssertionError: assert 'https://www....#main-content' == 'https://www....l-2022-08-16/'
E       Failed: DID NOT RAISE InvalidUrlError                                   (13 of these)
E       AssertionError: assert <RelCanonicalRule.SAME_SITE: 'same_site'> is <RelCanonicalRule.CROSS_SITE_REFUSED: 'cross_site_refused'>   (7)
E       AssertionError: assert () == ('32109013',)                              (10, PMIDs)
E       AssertionError: assert 'WwW.example.COM' == 'example.com'
E       AssertionError: the list is empty                                        (3, the rule tables)
E       AssertionError: assert '#' not in 'http://192.0.2.10#'                   (domain-URL property)
E       IndexError: tuple index out of range                                     (11, running-text tests reading [0] of an empty result)
```

Why the 141 passed:

- 10 variant rows and the 62 self-canonical rows: the expected value equals the input, so the
  identity function satisfies them.
- 22 PSL vectors whose answer is the host itself.
- 13 identifier negatives ("no DOI is invented").
- The static network scan.
- Three properties. Idempotence holds for an identity function, "no tracking parameter
  survives" holds with an empty deny list, and "content parameter survives" holds when nothing
  is ever dropped.

The 3 skips were tests parametrized over the then-empty tables. What this shows: **idempotence
alone cannot tell a no-op from a canonicalizer.** The hand-written table carries ac1, and the
property only guards it.

### Mutation table

65 mutants, each applied alone to the source as of `5dc66b8` (`7b2d299` then changed only
`pyproject.toml`). After the rulings, `public_suffix.py` changed (the pin moved to a file). Its 10
mutants (0, 1, 38 to 45) were re-run on the final source, `8e4294d`: all caught, with the same
failure counts as in the table. The other 55 target code that has not changed since `5dc66b8`. Each was run against `pytest packages/debate_core/tests/retrieval -n 0` with
**a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY` per mutant** (a new temporary directory each
time). The driver saved byte copies, restored them in `finally` and asserted byte equality. It
classified each mutant from the pytest summary line and reported "did not apply" when the match
text was not found exactly once.

**The property tests ran under every mutant.** Every run collected the full selection: 467 tests,
or 468 under mutant 48, which adds a deny entry and so one parametrized test.

**Result: 65 of 65 caught.** "Props" lists which of the four properties also failed:
I = idempotence, D = valid domain URL, T = no tracking parameter, C = content parameter survives.

| # | Mutant | Failed | Props | # | Mutant | Failed | Props |
|---|---|---|---|---|---|---|---|
| 0 | ASCII host keeps its case | 11 | I D T C | 33 | cross-site canonical accepted | 7 | – |
| 1 | trailing dot kept on host | 6 | I D T C | 34 | site is the last two labels | 2 | – |
| 2 | default port kept | 3 | – | 35 | references resolved by urljoin alone | 1 | – |
| 3 | percent hex keeps its case | 1 | – | 36 | blank rel=canonical not absent | 2 | – |
| 4 | encoded unreserved not decoded | 2 | – | 37 | `accepted` always true | 12 | – |
| 5 | non-ASCII left raw | 2 | – | 38 | PSL exception rules ignored | 5 | – |
| 6 | dot segments kept | 2 | – | 39 | PSL wildcard rules ignored | 10 | – |
| 7 | dot-dot pops the root | 1 | – | 40 | PSL shortest rule wins | 37 | – |
| 8 | fragment kept | 4 | C | 41 | PSL default rule is empty | 6 | – |
| 9 | empty query pieces kept | 1 | – | 42 | PSL IP check removed | 1 | – |
| 10 | tracking parameters kept | 106 | T | 43 | PSL empty-label check removed | 5 | – |
| 11 | AMP query markers kept | 4 | – | 44 | PSL private section ignored | 8 | – |
| 12 | parameters not sorted | 4 | – | 45 | PSL exception lines read as exact | 6 | – |
| 13 | repeated names sorted by value | 2 | – | 46 | deny prefixes ignored | 29 | – |
| 14 | amp host label kept | 4 | – | 47 | parameter names case-sensitive | 4 | – |
| 15 | amp host becomes bare site | 2 | – | 48 | content parameter on the deny list | 5 | C |
| 16 | amp label inside registrable domain dropped | 2 | – | 49 | AMP marker ignores its value | 1 | – |
| 17 | amp path segments kept | 6 | – | 50 | DOI not lowercased | 9 | – |
| 18 | amp suffix not stripped | 5 | – | 51 | DOI not percent-decoded | 4 | – |
| 19 | AMP path empty-list guard removed | 5 | I D T C | 52 | DOI trailing punctuation kept | 7 | – |
| 20 | `.amp` suffix kept | 2 | – | 53 | DOI closing bracket always trimmed | 1 | – |
| 21 | amp suffix guard removed | 4 | I | 54 | DOI viewer suffix kept | 2 | – |
| 22 | content rules run once | 2 | I | 55 | DOI lookbehind removed | 1 | – |
| 23 | no wrapper check after content rules | 1 | – | 56 | arXiv version kept | 5 | – |
| 24 | wrapper depth unbounded | 1 | – | 57 | arXiv month not checked | 1 | – |
| 25 | wrapper host not checked | 1 | – | 58 | arXiv trailing-digit lookahead removed | 1 | – |
| 26 | wrapper parameter name not checked | 1 | – | 59 | arXiv subject class kept | 1 | – |
| 27 | destination needs no public host | 1 | – | 60 | arXiv DOI rule removed | 2 | – |
| 28 | AMP cache secure flag inverted | 6 | – | 61 | PMID zero accepted | 1 | – |
| 29 | AMP cache drops origin query | 1 | – | 62 | Europe PMC form removed | 1 | – |
| 30 | same-site judged on canonical, not served host | 3 | – | 63 | identifiers not deduplicated | 1 | – |
| 31 | AMP cache allow rule removed | 2 | – | 64 | identifiers not ordered by position | 1 | – |
| 32 | AMP cache allows any site | 1 | – | | | | |

In the final pass, every mutant the properties caught was also caught by an example test. Getting
to 65 of 65 took several fixes. Each survivor was treated as a fact about the code, not something
to make go away:

- **Equivalent mutants, so the check was removed** (working agreement 8):
  - `.lower()` on the scheme: `urlsplit` already lower-cases it.
  - `transitional=False` passed to idna: idna 3.20 documents the argument as "Deprecated and
    ignored", because UTS #46 dropped transitional processing in Unicode 15.1. Its default was
    already off.
  - The parse step's empty path to `/`: the AMP path rebuild, which every URL passes through,
    already yields `/`.
  - `unquote` on parameter names in `query_parameters`: the syntax rules have already decoded
    every unreserved character, and the lists hold nothing else.
  - `\b` before the `PMID` and `arXiv:` labels: no realistic text glues the label to a preceding
    word.
  - The PSL wildcard guard `start + 1 < len(labels)`: the empty string is never a rule. This one
    was removed by reasoning, before it was run.
- **A missing test, so one was added**: empty query pieces; an AMP suffix that is the whole
  segment name; a wrapper with a second URL-valued parameter; and, found before the runs by
  hunting for checks no test read, userinfo, a lone `%`, a lone surrogate, the AMP cache's own
  query, the post-content-rules wrapper check, the dotless-destination guard, and arXiv ordering.
- **One the property caught only sometimes.** "Dot-dot pops the root" was caught by the
  idempotence property in one cold run and missed in the next. It now has its own row
  (`gov-dot-dot-at-the-root`), and the property is not counted as its guard.

Attempts that were not counted, and were redone:

- The first `.amp suffix kept` mutant errored at collection, because my replacement text left an
  unbalanced parenthesis.
- In the final pass, `dot segments kept` did not apply (stale match text after the `or "/"`
  removal).
- Batch 3 of the final pass was killed by its alarm at load ~40, after mutant 59. That left
  mutant 60 applied to `identifiers.py`. The file was committed before mutating, so it was
  restored from HEAD (the diff showed only the one mutated line), and mutants 60 to 64 were re-run
  in batches of three.

### Contract placement mutated too

Four mutations of the new placement in `pyproject.toml` were run against the five new rows in
`tests/architecture/test_import_contracts.py`, with `uv run --frozen` and the file restored
byte-for-byte afterwards. Each row is caught by at least one mutation:

| Mutation | Rows that failed |
|---|---|
| retrieval above application | retrieval → application.settings; retrieval → evidence |
| retrieval above evidence, not independent | retrieval → evidence |
| retrieval below domain | domain → retrieval; evidence → retrieval |
| retrieval off the delivery-framework list | retrieval → typer |

### Forbidden lists mutated too (PM ruling 1)

Three new rows import each library from retrieval on purpose: `import boto3`, `import httpx`,
`from lxml import html`. Taking `debate_core.retrieval` off each list in turn, with the file
restored byte-for-byte after:

| Mutation | Result (`pytest tests/architecture/test_import_contracts.py -k retrieval`) |
|---|---|
| retrieval off the AWS SDK list | `1 failed, 7 passed`: the `import boto3` row |
| retrieval off the httpx list | `1 failed, 7 passed`: the `import httpx` row |
| retrieval off the document-library list | `1 failed, 7 passed`: the `from lxml import html` row |

The whole contract suite, `uv run --frozen pytest tests/architecture/test_import_contracts.py`,
gives `41 passed`, and `uv run --frozen lint-imports` gives `Contracts: 12 kept, 0 broken.`

### The pin, mutated

On `8e4294d`, `pytest packages/debate_core/tests/retrieval/test_public_suffix.py`:

- **One rule added to the list (`example.co.uk`), hash file unchanged** → `1 failed, 92 passed`:
  `test_the_bundled_snapshot_matches_its_pinned_hash`. No vector covers the new rule, so the hash
  is the only thing that notices it.
- **Hash file edited, list unchanged** → `1 failed, 92 passed`, the same test.

Both files were restored and verified byte-equal.

The refresh command in the module docstring was run exactly as written, except that it changed
into a scratch directory instead of `retrieval/data`. Exit 0. It fetched the same
338,207 bytes (`VERSION: 2026-10-17_18-52-06_UTC`) and wrote a hash file identical to the
committed one. A wheel built with `uv build --package debate-core --wheel` contains both
`retrieval/data/public_suffix_list.dat` and `retrieval/data/public_suffix_list.dat.sha256`.

### Full default suite

Run in eighths, one command per part, because other sessions kept the load between 7 and 28:
`uv run --frozen pytest --part K/8 -q`. This run is on the final code, `8e4294d`:

| Part | Result | Wall |
|---|---|---|
| 1/8 | 1119 passed | 54.5 s |
| 2/8 | 1122 passed | 39.5 s |
| 3/8 | 1123 passed | 41.2 s |
| 4/8 | 1117 passed | 38.6 s |
| 5/8 | 1113 passed | 38.4 s |
| 6/8 | 1123 passed, 1 xfailed | 45.3 s |
| 7/8 | 1 failed, 1121 passed | 49.4 s |
| 8/8 | 1118 passed, 1 xfailed | 51.8 s |

Total: 8,956 passed, 2 xfailed, 1 failed. The failure is the known one from the PM notes,
`tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline` ("no
baseline is established for the pr-subset tier"), and was not investigated.

An earlier full run, before the rulings, gave 8,952 passed with the same single failure.
Part 1 of that run had first failed on this branch, in
`tests/architecture/test_single_interpreter_source.py`. That guard read my `"idna>=3.10"` as a
Python 3.10 mention. The floor is now `idna>=3.7` (see Decisions), and part 1 was re-run on
`7b2d299`. Part 2 ran on `5dc66b8`, which differs from `7b2d299` only in that bound and the
lockfile line.

Other checks: `uv run --frozen ruff format --check .` → `830 files already formatted`;
`uv run --frozen ruff check .` → `All checks passed!`; `uv run --frozen lint-imports` →
`Contracts: 12 kept, 0 broken.`

## Files changed

- `packages/debate_core/src/debate_core/retrieval/`: the new package.
  - `canonical_url.py`: rules, wrappers, AMP caches and rel=canonical.
  - `query_parameters.py`: the deny, allow and AMP lists with reasons.
  - `public_suffix.py`: registrable domains, and in its docstring the refresh command.
  - `identifiers.py`.
  - `__init__.py`.
  - `data/public_suffix_list.dat`: the PSL, 338,207 bytes, MPL-2.0, unmodified.
  - `data/public_suffix_list.dat.sha256`: its hash, as `shasum -a 256` writes it.
- `packages/debate_core/tests/retrieval/`, the tests:
  - `test_canonical_url.py`: the table, rules, lists and rel=canonical.
  - `test_canonical_url_properties.py`: four Hypothesis properties.
  - `test_identifiers.py`.
  - `test_public_suffix.py`: the PSL project's own vectors, transcribed, plus the pin.
  - `test_no_network.py`: a static scan for network imports.
- `packages/debate_core/pyproject.toml` and `uv.lock`: `idna>=3.7` as a direct debate-core
  dependency. It was already locked at 3.20 through httpx and requests, so the lock gains two
  lines and no package.
- `pyproject.toml`, the import contracts:
  - The layers contract becomes `evidence | retrieval`, and its name says "evidence and
    retrieval".
  - Retrieval joins the delivery-framework list (`8c2e179`).
  - Retrieval joins the boto3, httpx and lxml forbidden lists (`b50d2cd`, PM ruling 1).
- `tests/architecture/test_import_contracts.py`: the renamed `CORE_LAYERS` constant and eight
  violation rows for retrieval: five for the placement, three for the forbidden lists.
- `plan_specs/v1/e04-article-retrieval/t01-url-canonicalization.yaml`:
  - Goal phase set to `Succeeded`.
  - PM amendments of 2026-10-19: `pyproject.toml` added to `constraints.packages`, with a
    comment citing ruling 1, and the trailing-slash sentence (ruling 2).

## Deviations from the spec

1. **Edits outside `constraints.packages`, now settled by a PM amendment.**
   - **The root `pyproject.toml`.** The layers contract is `exhaustive`. With the package
     unplaced, `uv run --frozen lint-imports` printed `The following modules are not listed as
     layers: - debate_core.retrieval` and `Contracts: 11 kept, 1 broken.` I placed the package
     beside evidence in `8c2e179` and asked the PM. Ruling 1 (2026-10-19): *"(c). Keep
     8c2e179's layers placement … Also add debate_core.retrieval to the boto3, httpx and lxml
     forbidden lists now … Record the pyproject.toml edit as a PM amendment to the spec's
     packages, citing this ruling."* The spec now reads
     `packages: [debate_core.retrieval, pyproject.toml]`, under a comment citing the ruling.
   - **Three files the amendment does not name, listed so the PM can see them:**
     - `tests/architecture/test_import_contracts.py`, the rows that show each placement and each
       forbidden entry failing, which the ruling asked for.
     - `packages/debate_core/pyproject.toml` and `uv.lock`, for the `idna` dependency, which the
       PM notes allowed "kept to debate_core".
2. **Trailing slashes: amended by the PM.** The spec said "normalize trailing slashes". I kept
   them as published, because `/x/` and `/x` resolve relative links differently (RFC 3986
   §5.2.3). Ruling 2 (2026-10-19): *"Amend. The description reads 'keep trailing slashes as
   published (the empty path becomes /); a same-site rel=canonical resolves the two forms',
   marked 'PM amendment 2026-10-19'."* The description now says so. The code and tests were
   already that rule (`gov-trailing-slash-kept`, `gov-no-trailing-slash-kept`,
   `test_rel_canonical_decides_a_trailing_slash`). It passes as amended, and it would have
   failed only the original wording.

## Decisions and assumptions

- **Public Suffix List: vendored, not a dependency** (agreed by the PM, 2026-10-19). The file is
  `retrieval/data/public_suffix_list.dat`, exactly as publicsuffix.org published it:
  `// VERSION: 2026-10-17_18-52-06_UTC`, `// COMMIT: 52b71b3c4576ff77450cc7ebcfc7f34a916af3f9`,
  sha256 `3e6ca639…c1c2a4`. I downloaded it once, by hand; nothing in the code fetches it.
  - Why not `tldextract`: it fetches the list by default, and it brings `requests` and `filelock`
    into the domain core.
  - Why not `publicsuffixlist`: it ships an update command that rewrites its bundled copy inside
    site-packages, so "pinned" would depend on nobody running it.
  - **The pin is a file.** It started as a Python constant. The PM asked for a documented command
    that updates the list and its hash together, and a command cannot edit a constant reliably.
    So the hash is now `data/public_suffix_list.dat.sha256`, in the format `shasum -a 256`
    writes. The version and commit are read from the list's own header, so no copy of them can
    go stale.
  - **How to refresh it** is in `public_suffix.py`'s docstring:
    1. Run one command, which changes into `retrieval/data`, fetches from
       https://publicsuffix.org/list/public_suffix_list.dat (the only source the list's
       maintainers support), and rewrites the hash file.
    2. Run the retrieval tests.
    3. Commit both files in one PR that names the new `// VERSION:` line.

    The docstring also says what a newly failing vector means. Changing one file without the
    other fails `test_the_bundled_snapshot_matches_its_pinned_hash`, so an update is always a
    deliberate, reviewed change.
  - **The algorithm** is the list's own: exception rules first, then the longest rule, a
    wildcard matches one label, and an unlisted host's suffix is its last label. It is about 40
    lines, checked against the PSL project's 77 test vectors, transcribed from
    `tests/test_psl.txt` at the same commit (public domain).
  - Licence: MPL-2.0, which applies file by file. The file keeps its header, and nothing else is
    affected.
  - Both sections are used, ICANN and private, so `alice.github.io` and `bob.github.io` are
    different sites.
- **New dependency: `idna`**, BSD-3-Clause, floor 3.7, locked at 3.20, debate-core only. The
  standard library's `idna` codec is IDNA 2003, which maps `faß.de` to `fass.de`, a different
  registered domain. idna's UTS #46 mapping is nontransitional, as the WHATWG URL Standard and
  current browsers are. ASCII labels are only lower-cased, so real hosts with `_` stay usable.
  The floor is 3.7 because that release fixed CVE-2024-3651 (quadratic-time `encode()` on crafted
  input), and the hosts encoded here come from untrusted links. `3.10` also tripped the
  single-interpreter-source guard.
- **Kept as they are, because each can name a different resource:**
  - `http` (not upgraded to https), `www.` (not added or removed), trailing slashes;
  - userinfo, in normalized form;
  - unknown query parameters, the default the forbidden list requires;
  - the order of a repeated parameter's values (the sort is stable).
- **Link wrappers are unwrapped only from a named table** (`LINK_WRAPPERS`: Google `/url`, Google
  News legacy `/news/url`, Facebook `l.php`, Outlook Safe Links, LinkedIn `/redir/redirect`), and
  only when the destination parameter's decoded value is an absolute http(s) URL with a dotted
  host. `url=` elsewhere is content. Google News `/articles/CBMi…` and `t.co` links carry no
  literal destination and are kept. Nesting is unwound to 8 deep; more raises `InvalidUrlError`.
- **AMP rules.**
  - An `amp` path segment anywhere, a final `.amp`, and `.amp.html` → `.html`.
  - `?amp`, `?amp=1`, `?amp=true` and `?outputType=amp`, but not other values (`amp=4` is kept).
  - The `amp.` host label, only outside the registrable domain: `amp.dev` keeps its name.
    `amp.` + registrable becomes `www.` + registrable, and a deeper label is just dropped. Where
    the guess is wrong, the page's same-site rel=canonical corrects it after the fetch.
  - AMP cache and Google AMP viewer URLs spell out their origin, `s/` meaning https.
- **rel=canonical "site" is the host that served the HTML,** before any AMP or wrapper rule,
  because that host's HTML is making the claim. So a link wrapper's page cannot vouch for the
  publisher, but an AMP cache can, for the origin its URL names. That is the one allow rule
  (`AMP_CACHE_ORIGIN`). A reference with a scheme is absolute (RFC 3986 §5.2.2). Python's
  `urljoin` follows RFC 1808 here and turned a declared `https://` into the fetched URL, which the
  `UNUSABLE` test caught. A refused canonical is still recorded as `declared_url`.
- **The recorded rule** is `RelCanonicalRule`, a `StrEnum` with values `absent`, `unusable`,
  `same_site`, `amp_cache_origin` and `cross_site_refused`. A test pins the set of values, so
  t05 can store the string.
- **The allow list guards the deny list at test time and is not read at run time.** Unknown
  parameters are kept anyway, so a run-time "allow beats deny" branch could never be told from
  its absence. The tests fail if any deny rule or AMP marker matches an allow-listed name, or if a
  wrapper's destination parameter is not allow-listed.
- **Identifiers.** `ScholarlyIdentifiers` keeps every DOI, arXiv id and PMID in order of
  appearance, since a reference list has many. `as_article_identifiers()` takes the first of
  each, which is right for an article's own URL or metadata; which inputs to trust is t05's
  call. Other normalizations: an old-style arXiv subject class is dropped (`math.GT/0309136` →
  `math/0309136`); an arXiv DOI (`10.48550/arXiv.…`) also yields the arXiv id; publisher viewer
  suffixes (`/full`, `/pdf`, `.pdf`, …) are trimmed from DOIs. Known limits, documented in the
  module: a DOI with a raw `<`, `>` or `&` (old SICI DOIs) is cut short, and a bare `2101.01234`
  in text is not taken as arXiv.
- **Layer placement:** retrieval sits beside evidence, independent of it in both directions. t02
  to t05 put their models (`fetch_types`, `access`, `extraction`) in retrieval and their httpx,
  trafilatura and pdf adapters in `debate_core.integrations`. This placement allows that, and
  since PM ruling 1 the boto3, httpx and lxml contracts require it.
- **No-network guarantee:** pytest's `--disable-socket` covers tests. `test_no_network.py` also
  scans every retrieval module for network imports (`socket`, `http`, `urllib.request`, `httpx`,
  `requests`, `tldextract`, …), which covers code that would only reach out outside a test.

## Operator follow-ups

None. Everything that ran is recorded above, and nothing needs credentials or a long run.

## Follow-up work

- **A site-root rel=canonical** (v1-e04-t05). A common CMS bug gives every article
  `rel=canonical` = the homepage, and the same-site rule accepts it. The PM is adding a safeguard
  to t05's spec ("I'll put it into t05's spec in my next batch").
- **More link wrappers** (YouTube `/redirect?q=`, DuckDuckGo `/l/?uddg=`, Slack `slack-redir.net`)
  can be added to `LINK_WRAPPERS` with a test each when they show up in real use. I left them out
  so that every rule in the table has a test.
- The forbidden-list contracts and the PSL refresh procedure were follow-ups in the first draft
  of this report. Both are now done, under PM ruling 1 and the FYI.

## PM rulings (2026-10-19) and what was done

1. **(c): keep the placement, and add retrieval to the boto3, httpx and lxml lists.**
   - Done in `b50d2cd`: `debate_core.retrieval` is in each list's `source_modules`, with a comment
     in the httpx and lxml contracts saying that fetching and parsing are adapters.
   - Three rows import each library from retrieval on purpose, and removing each entry fails
     exactly its row (see "Forbidden lists mutated too").
   - Recorded as a PM amendment to `constraints.packages` (Deviation 1).
2. **Amend the trailing-slash prose.** Done in `8e4294d` (Deviation 2).

FYI items:

- **Vendored PSL with a sha256 test: agreed.** The refresh note is in the module docstring. The
  pin moved to a `shasum` file so that the one command updates the list and its hash together.
  The command was run as written against a scratch directory, and both pin mutations fail the
  pin test.
- **Site-root rel=canonical:** the PM is taking it into t05; nothing changed here.

No open questions.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-19

**Notes:**

Accepted, with the phase `Succeeded`.

**The work itself:**

* **The red run against a refuse-nothing skeleton,** and the honest reading of it: idempotence alone
  cannot tell a no-op from a canonicalizer. The hand-written 63-pair table carries ac1, and the
  property only guards it.
* **65 of 65 mutants caught,** with each property's catches listed. Six equivalent checks were
  removed, not tested. The flaky "dot-dot pops the root" catch was given its own row rather than
  credited to the property.
* **The Public Suffix List is vendored with a hash file,** refreshed by one documented command that
  was run as written, and both pin mutations fail the pin test. The algorithm is checked against the
  list project's own 77 vectors. The private section is used, so two github.io users are two sites.
* **`idna` with UTS #46, nontransitional,** because the standard library's IDNA 2003 maps `faß.de`
  to another registered domain. The floor is set past the CVE.
* **Same site is judged on the host that served the HTML,** so a link wrapper cannot vouch for a
  publisher, and an AMP cache can only for the origin its URL names. Catching `urljoin`'s RFC 1808
  behaviour by test was a good find.
* **Ruling 1 is done and proven:** the placement mutated four ways, and each forbidden-list entry
  fails exactly its row when removed.

**Rulings:**

* **Deviation 1:** accepted. `pyproject.toml` is in the amended packages. The contract test file,
  `packages/debate_core/pyproject.toml` and `uv.lock` are what rulings 1 and the notes asked for.
* **Deviation 2:** accepted, as amended.
* **Decisions:** all accepted. Keeping `http`, `www.`, trailing slashes, userinfo and unknown
  parameters as published is the right default, because each can name a different resource.

**For `v1-e04-t05`, added to its spec in the next PM batch:**

* **A site-root rel=canonical** is refused when the fetched path is not `/` (your follow-up).
* **The canonical form is an identity key, not a fetch target.** The `amp.` to `www.` host rewrite
  is a guess that a page's rel=canonical corrects after the fetch. t05 fetches the URL as given (or
  a wrapper's literal destination), never a host the canonicalizer guessed, and stores both.

**More link wrappers:** added when they appear in real use, each with its test, as you say. No task
needed.
