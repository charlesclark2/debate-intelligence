<!-- docs-index: The camp release manifest's member-row fields, including OpenEv's own camp word from the pull's listing -->
# The camp release manifest

A camp release manifest, `manifests/openev/<year>-<event>.jsonl` (`manifests/openev/2026-policy.jsonl`),
is one camp release's files for one year and event, merged across every download. Its rows have every
key a caselist manifest row has, at the same `schema_version` (1), with the disclosure fields `null`,
plus the camp fields below. The writer is `debate_core.application.caselist.openev_manifest`, whose
module docstring is the full account: how imports merge, how suppressed files leave no row, and what
the summary row counts.

## The camp fields of a member row

| Field | Since | What it holds |
|---|---|---|
| `camp`, `lab`, `file_title` | `v1-e30-t04` | What the importer read from the file's path and name. `camp` is the canonical camp from `camp_aliases.yaml`, `UNKNOWN` when the table knows none |
| `year` | `v1-e30-t04` | The release's topic year, also the `raw/openev/<year>/` prefix its sources publish to |
| `imported_on` | `v1-e30-t04` | The date given to the import that wrote the row |
| `archive_sha256` | `v1-e30-t04` | The download the row came from |
| `existing_origin`, `existing_caselist` | `v1-e30-t04` | The source document the bytes were already filed as, if any |
| `openev_id`, `upstream_path_sha256` | `v1-e30-t14` | The OpenEv id the file was downloaded as, and the SHA-256 of its upstream path, never the path |
| `openev_camp_word` | `v1-e30-t31` | OpenEv's own word for the camp, from the pull's listing, when it is one address word; otherwise `null` |

Each field was added as a key, not as a new version, so `schema_version` stays 1. Every reader of a
row reads it as a mapping and ignores a key it does not know, or keeps it byte for byte.

## `openev_camp_word`

OpenEv's page for a camp is `https://opencaselist.com/openev/<year>/<word>`, and the word is OpenEv's
own. `GET /openev` lists it on every file (`OpenEvFile.camp`). The row's `camp` is the importer's
canonical camp, which is often not OpenEv's word, so the camp link maps through the hand-filled
`openev` section of `camp_aliases.yaml` instead (`v1-e39-t28`). The listing's word is the exact source
for every file a build with this field pulls.

* **Written by the pull**, on each row of a file it imports: a single document's row, or every member
  row of a camp release that is a zip, which all carry the zip's word.
* **Kept only when it is one address word**: letters A to Z in either case and digits, matched
  whole, the pattern the camp link checks (`OPENEV_CAMP_WORD_PATTERN` in
  `debate_core.domain.search_source_links`), and not `UNKNOWN`. A word with a space, a slash, a hyphen, a trailing newline or another letter, an empty
  word and a listing with no camp all give `null`.
* **`null` on a hand import** (`caselist import-openev`), which has no listing.
* **Absent on a row written before `v1-e30-t31`**, and on a row an unchanged re-import keeps byte for
  byte. Nothing re-derives it: `caselist reimport-openev-metadata` keeps the key as written, and the
  delivery record does not keep the word. A reader takes an absent key as no word.
* **Not read yet.** Neither the search index nor the card page reads it. A later task can join it
  into the index by the row's `sha256`, as `v1-e39-t16` joins `openev_id`, and prefer it to the
  table's word.

### Earlier builds read these rows

The cloud run's image (`v1.1.0-dev.251`) and the Mac's installed build (`v1.1.0-dev.200`) were each
built offline from their tags and run over a manifest this build's pull wrote, on 2026-11-01. Each
merged a new pull into it and kept this build's rows byte for byte, re-derived it keeping the word,
removed a file from it, published it and found the status in sync. Its parse source list was the same
with and without the word. Neither build's index build reads a release manifest. The commands and
output are in `docs/session-reports/v1-e30-t31-openev-camp-word-on-the-manifest-row.md`. A
`schema_version` bump would not have been read: both refuse a row whose version is not 1.

The deployed search function reads no release manifest. Its role reads `reports/tub/search/` for the
index, the suppression list and `raw/` sources, and the index it reads carries no camp word.

### How many rows carry one, 2026-11-01

Counted on the operator's Mac, read-only, counts only. Its two release manifests have 108 member rows
(`2026-policy` 106, `2026-ld` 2), none with an `openev_id` key and none with a camp word: all were
written before `v1-e30-t14`. None of the sync's run records, its run details, the delivery record or
the download-start record keeps a listing's camp. So no camp word is recoverable for those rows, and
every row the pull writes from now on carries one when the listing gives an address word. The cloud
run's store, seeded from this Mac at the cutover (2026-10-26), was not counted: that is a read of the
bucket.
