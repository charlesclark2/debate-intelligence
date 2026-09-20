# Caselist and OpenEv data-use policy

| | |
|---|---|
| Policy version | 1.0 |
| Status | **Draft — not yet approved.** Nothing this policy governs may happen until the [Approval](#approval) section is filled in. |
| Owner | Charlie Clark (product owner and head coach) |
| Written by | v1-e30-t01-caselist-data-use-policy implementation session, 2026-09-19 |
| Applies to | Everything the platform collects from OpenCaselist and OpenEv, and everything derived from it, in every environment |
| Approved by | _pending_ — see [Approval](#approval) |
| Next review | Start of the 2027-28 season, or sooner if a source's terms change |

This is the policy that governs how the Debate Intelligence Platform collects, stores, uses and
removes evidence that **other teams disclose publicly** on
[opencaselist.com](https://opencaselist.com/) and camp files published through **OpenEv**. It is
not legal advice. Where a question needs a school, district or lawyer to answer, this policy says
so in [Open questions](#open-questions) rather than guessing.

It is written to be **more restrictive than any plausible reading of the source terms**, because
the terms have not been transcribed yet (see [Sources and terms](#sources-and-terms)). Confirming
them can therefore only relax a rule here. If a confirmed term turns out to be *stricter* than a
rule below, this policy is revised and re-approved before the affected work continues.

## Scope

**In scope**

- The weekly cumulative open-source archives for the HS LD, HS Policy and HS PF caselists
  (`hsld26`, `hspolicy26`, `hspf26` and their successors), however they are obtained — the
  operator's manual download today, the authenticated API client in E34 later.
- OpenEv camp files.
- Everything derived from them: content-addressed source blobs, snapshot manifests, parsed cards
  and fingerprints, position classifications, argument landscape reports, and team files built
  from disclosed or camp cards.
- Every place that data lives: the operator's laptop, the dev evidence bucket, the prod evidence
  bucket, the V1 CLI, and the V2 debate tub.
- Everyone with access: the operator, coaches, and (from V2) the team's debaters.

**Out of scope**

- The team's own cut cards, files and uploads, which are the team's work product.
- Articles and publications retrieved by the article pipeline (E04), which have their own
  fetching rules (robots, paywalls, §19).
- Tabroom results data. It is public and read-only, is not covered here, and must not be joined
  to caselist team codes (see [Personal data](#personal-data)).

## Sources and terms

> **Transcription status: PENDING — this is the one section of this policy that a session cannot
> write.** The OpenCaselist terms of use and privacy pages sit behind a Tabroom login and could
> not be retrieved automatically, and OpenEv camp files carry per-camp licensing notes that only
> a reader with the files in hand can record. The coach reads them, and the exact clauses, the
> exact URLs and the date read are transcribed into the tables below before this policy is
> approved. Nothing below is quoted from a live page yet; the "what we assume" column records the
> conservative assumption the rest of this policy is built on, and every one of them is also an
> entry in [Open questions](#open-questions).

### Source register

| Source | What it is | What we take | How we take it | Terms recorded? |
|---|---|---|---|---|
| OpenCaselist — site | `https://opencaselist.com/` — the high-school and college open-source disclosure wikis, signed in with a Tabroom account | Nothing directly; the site is where the archives and the terms live | Browser, operator's own Tabroom login | ☐ Not yet |
| OpenCaselist — weekly open-source archives | Cumulative per-caselist archives of every open-source document teams have disclosed this season (e.g. `hsld26-0915`) | The archive `.zip`, unpacked into per-school / per-team-code / per-round documents | Manual download today (v1-e30-t03/t06); authenticated API later, gated by this policy (E34) | ☐ Not yet |
| OpenCaselist — API v1 | `https://api.opencaselist.com/` — documented API for caselists, schools, teams, rounds, cites, downloads and OpenEv (architecture proposal §21, reference 11) | Caselist and download listings, archive bytes, OpenEv listings | Not yet used. E34 only, with the operator's own `caselist_token`, rate limited | ☐ Not yet |
| OpenEv camp files | Camp-published evidence files distributed through OpenCaselist's OpenEv section | The camp-file archives and their camp / year / event / title metadata | Manual download today (v1-e30-t04); API later (E34) | ☐ Not yet |

### Clauses to transcribe

For each source the coach records, verbatim and with the URL and the date read:

**OpenCaselist terms of use / privacy pages**

1. The exact URLs of the terms of use and privacy pages, and who operates the site.
2. Any clause about **permitted use of downloaded documents** — is use limited to preparation,
   and is redistribution addressed?
3. Any clause about **automated access, scraping, rate limits or API use**, which gates E34.
4. Any clause about **account sharing** or use of another person's credentials.
5. Any clause about **removal, takedown or the right of a disclosing team to withdraw** a
   document, and the channel for it.
6. Anything the privacy page says about **minors** and about what the site itself publishes
   (school names, team codes, round reports).
7. Any clause about **commercial use**.

**OpenEv**

1. The page or file that states OpenEv's distribution terms, and the date read.
2. Per-camp licensing notes: camps publish under different conditions, and some state terms on
   the first page of the file or on the camp's own site. Record each camp represented in the
   corpus and what, if anything, it says.
3. Whether any camp file carries a licence that is *more* permissive (e.g. explicit permission to
   redistribute) — this policy does not act on that; it only records it.

### Fill-in table (completed at transcription)

| Source | URL read | Date read | Clause (verbatim) | What it means for us |
|---|---|---|---|---|
| | | | | |

### Community disclosure norms

Separate from any written term, the circuit has norms about disclosure that this policy respects
whether or not the written terms require them. These are the coach's account of practice, not
quoted rules, and the coach confirms them at transcription:

- **Disclosure is for preparation.** Teams upload round reports, cites and open-source documents
  so opponents can prepare against them. Using a disclosed document to prepare for, or to
  build files around, a round is the expected use.
- **Disclosure is not publication.** A team that posts a 1AC to a caselist has not published a
  book. Re-hosting archives, posting other teams' documents where the circuit can find them
  outside the caselist, or passing them to people outside your program is outside the norm even
  when the document itself is public.
- **Credit follows the card.** Cards travel through the circuit; keeping the original cite intact
  is both an evidence-ethics rule and the norm. This policy's
  [Attribution](#attribution) rules exist to make that automatic.
- **Withdrawal is respected.** When a team asks for something to come down, it comes down, without
  the requester having to argue for it. See [Removal](#removal).
- **Camp files are gifts with expectations.** OpenEv files are released to the community for use
  in files and rounds, not for resale or re-publication under someone else's name.

## Permitted uses

The corpus may be used for the following, and only these:

| # | Use | Conditions |
|---|---|---|
| 1 | **Team-internal research and scouting** — reading what an opponent has disclosed, before or during a tournament | Team members only. Nothing leaves the team. |
| 2 | **Argument landscape reports** — aggregating the corpus into what positions are being read on the topic, by side, over time (E32) | Circuit-wide reports carry no team codes at all; per-school views are limited by [Personal data](#personal-data). |
| 3 | **Building and "plussing up" team files** — assembling disclosed and camp cards into the team's own files, extending them with new evidence (E33) | Cite kept verbatim, provenance line attached, card marked `FILE_IMPORT`/unverified. Files stay inside the team. |
| 4 | **Parsing, hashing, fingerprinting, deduplication and indexing** of the corpus (E30, E31) | Derived artefacts inherit every rule in this policy, including removal. |
| 5 | **Parser and classifier evaluation** — measuring how well the platform reads real debate documents | Evaluation runs against the corpus in place; evaluation *fixtures* committed to the repository are synthetic (see [Personal data](#personal-data)). |
| 6 | **Operator reporting** — recording import, dedupe and publish results (e.g. `docs/data/caselist-backfill-2026-09.md`) | Aggregate counts only; no school, team code, filename or name in anything committed. |
| 7 | **Model-assisted classification** of disclosed text | Only under [Model provider use](#model-provider-use). |

## Prohibited uses

None of the following is permitted, by anyone, in any environment, regardless of how convenient
it would be:

1. **Public redistribution or re-hosting.** No publishing the archives, the sources, the parsed
   cards or any file built from them to a public bucket, website, CDN, Drive folder, Discord,
   forum, git repository or package index.
2. **Sharing outside the team.** No sending disclosed documents, built files or per-school
   landscape views to another program, another coach, a camp, a judge, or anyone who is not a
   member of this team.
3. **Commercial use.** The corpus is not sold, licensed, bundled into a paid product, or used as
   a selling point for one.
4. **Circumventing OpenCaselist.** No bypassing the `caselist_token` login or any access control;
   no using another person's Tabroom credentials; no sharing the operator's token; no scraping
   `opencaselist.com` HTML in place of the documented API; no ignoring rate limits, `Retry-After`
   or a `401`/`403`.
5. **Presenting disclosed or camp cards as platform-verified.** Cards imported from a file are
   `FILE_IMPORT` and unverified; they never carry a verified status or badge (ADR-0006).
6. **Expanding or re-identifying team codes.** No expanding initials to names, no joining team
   codes to Tabroom entries, school rosters, social media or any other source, in V1 or V2.
7. **Profiling individuals.** The corpus is used to prepare against *positions* and *teams*, never
   to build a dossier on a named debater, and never for anything outside round preparation.
8. **Training or fine-tuning models** on the corpus, or sending it to any provider that trains on
   or retains inputs. See [Model provider use](#model-provider-use).
9. **Committing real data to the repository.** No real caselist or camp files, no excerpts, no
   real school names, team codes, debater names or real disclosure paths in fixtures, tests,
   cassettes, logs, session reports or documentation.
10. **Keeping copies outside the sanctioned stores.** The corpus lives in the operator's local
    evidence store and the dev and prod evidence buckets. Not in email, not in a personal Drive,
    not on a USB stick, not in a chat thread.

## Model provider use

**Decision: yes, disclosed and camp card text may be sent to the configured model provider through
the ModelRouter, under all of the conditions below.** The argument landscape (E32) cannot be built
without it, and the alternative — a human reading 2,000+ documents — is not real.

Conditions, all required:

1. **Only through the ModelRouter** (E05, ADR-0005), to the provider configured for the
   environment (AWS Bedrock). No other provider, no direct SDK call, and — explicitly — no pasting
   disclosed text into a consumer chat interface.
2. **No-training, no-retention terms confirmed in writing for the account before the first
   full-corpus run.** Until that confirmation is recorded here, model classification runs against
   synthetic fixtures only. This is [open question 4](#open-questions) and a
   [gate on E32](#e32--model-classification-of-the-corpus).
3. **Bounded excerpts, never whole documents.** Only items the deterministic stage could not match
   are sent, and each carries a heading path, tag, short cite and a bounded excerpt
   (v1-e32-t02).
4. **No identifiers in the prompt.** School names, team codes, debater names or initials,
   tournament and round labels and file paths are never part of a prompt, a cassette or a cached
   key that a prompt is built from.
5. **The model returns metadata only.** Position ids, confidence and a short rationale. Model
   output never contains or replaces tag, cite or evidence text — the evidence-integrity rule
   (ADR-0006) is absolute and is not relaxed for classification.
6. **Committed cassettes are synthetic.** Recorded fixtures in the repository are generated, not
   captured from the real corpus.
7. **Results are cached** by item fingerprint and prompt version so a weekly rerun re-sends only
   new items, and token spend is reported per run.

## Personal data

Disclosure paths carry personal data about people who may be minors. Treat every team code as
personal data about a minor (architecture proposal §14).

**What personal data the corpus contains**

- **School name** — from the archive's directory structure.
- **Team code** — usually the debaters' initials (`QX`), occasionally longer or containing a
  surname. This is the field that carries identity.
- **Names inside document bodies** — occasionally a debater's or coach's name appears in a header,
  footer, filename or document property.
- **Tournament and round labels** — which, combined with a team code, place a specific pair of
  students at a specific round.

**Rules**

1. **Keep the team code exactly as disclosed, and nothing more.** The domain model has a
   `TeamCode` and deliberately has no `debater_names` field (v1-e30-t02).
2. **Never expand, never join.** Initials are not resolved to names, and team codes are never
   joined to Tabroom entries, rosters, social media or any other source, in V1 or V2.
3. **Never in S3 keys or object metadata.** Sources are stored at content-addressed keys
   (`raw/<caselist>/<sha256>.<ext>`); no school, team code or original filename appears in a key,
   a metadata field or a tag (v1-e30-t05).
4. **Never in logs.** No school, team code, filename or disclosure path in application logs,
   error messages, tracebacks, metrics labels or telemetry — in any environment.
5. **Never in committed artefacts.** Fixtures, cassettes, tests, session reports, runbooks and
   `docs/data/` summaries use fictional schools and team codes (`Maple Grove`, `QX`) and aggregate
   counts.
6. **Never in the removal log or suppression list.** Those carry sha256 values, dates, reason
   codes and request ids only (v1-e30-t07).
7. **Never in a model prompt.** See [Model provider use](#model-provider-use).
8. **Names in document bodies are not extracted.** They are never parsed into a field, indexed as
   a name, or surfaced in a report. They remain where they are, inside a private source document
   visible only to team members.

**Where personal data is allowed to live** — and only here: the local evidence store on the
operator's machine, the `manifests/` prefix of the private dev and prod evidence buckets, the
provenance sidecar of a built file, and the per-school landscape view.

**What a report may show**

| Report | Maximum identity shown |
|---|---|
| Circuit-wide argument landscape (v1-e32-t03) | Nothing. No school, no team code. |
| Per-school and trend views (v1-e32-t04) | **School plus team code, as disclosed. Never more.** |
| Operator import/publish summaries (`docs/data/`) | Aggregate counts only. |
| Built-file provenance line and sidecar (E33) | School, team code, side, tournament, round — inside the team only. |
| Removal log and suppression list (v1-e30-t07) | sha256, date, reason code, request id. |

**Access.** In V1, the operator only. In V2, authenticated members of the team's organization
only, audited — see [the debate tub gate](#v2-e35--debate-tub-v21).

## Retention

A **season** runs 1 August to 31 July and is labelled like `2026-27`.

| Data | Kept for | Deleted by |
|---|---|---|
| Weekly caselist snapshots (source blobs and manifests) | The season they belong to, plus the following season | 31 August after the following season ends — 2026-27 data by **31 August 2028** |
| Parsed cards, fingerprints and classifications derived from them | Same clock as their sources | With their sources |
| OpenEv camp files | The topic year they were cut for, plus the following season | Same rule |
| Per-school landscape views | Same clock as their sources | With their sources |
| Circuit-wide landscape reports (no personal data) | Indefinitely | — |
| Team files built from disclosed cards | Indefinitely (team work product), but subject to [Removal](#removal) flagging | — |
| Removal log and suppression list | Indefinitely — the suppression list must outlive the data it suppresses | — |
| S3 noncurrent object versions | Lifecycle from v1-e29-t03: Standard-IA after 30 days, expire after 365 days in prod and 30 days in dev | Automatically |

- **Removal beats retention.** A removal request purges the object *and all of its noncurrent
  versions immediately* (v1-e30-t07); it does not wait for the lifecycle rule.
- **The annual purge is an operator task**, run each September for the season that has just aged
  out, in dev and prod, with the resulting counts recorded in `docs/data/`.
- **Local copies follow the same clock.** The operator's local evidence store is purged in the
  same run as the buckets.
- Keeping a season longer for year-over-year trend analysis is
  [open question 7](#open-questions) and needs a policy revision, not an exception.

## Attribution

Every disclosed or camp card that reaches a built file carries its origin with it. This is an
evidence-ethics rule first and a traceability rule second: it is what makes
[Removal](#removal) possible at all.

1. **The original cite is kept verbatim.** It is copied from the source document's own runs,
   byte-for-byte, never retyped, re-flowed or re-cased (v1-e33-t02). Correcting someone else's
   cite is not permitted; if it is wrong, the card is re-cut from the original article instead.
2. **A provenance line is added below the cite**, as the only new text:

   ```
   [Disclosed: hsld26 2026-09-15 — Maple Grove QX, Aff vs. Riverbend Invitational Round 4]
   [OpenEv: Cascade Institute 2026 — Policy, Climate Adv CP]
   ```

   Disclosed cards name caselist slug, snapshot date, school, team code, side, tournament and
   round. Camp cards name camp, year, event and file title.
3. **A machine-readable sidecar** accompanies every built file with the same provenance plus card
   fingerprint, source sha256 and element index, at `provenance_mode: FILE_IMPORT` (v1-e33-t02).
   The sidecar is what a removal request is matched against.
4. **Never presented as verified.** A `FILE_IMPORT` card is unverified: no verified status, no
   badge, no implication that the platform checked the card against its source article
   (ADR-0006). If the team wants a verified card, it re-cuts it from the original article, and the
   card then carries *article* provenance instead, with a note that it was found through the
   caselist.
5. **Attribution survives every move.** Copying a card into another file, exporting it, or opening
   it in the V2 debate tub carries the provenance line and sidecar entry with it. A card without
   provenance may not be added to a built file.
6. This is internal credit, not publication credit. Nothing built from the corpus is published, so
   attribution here exists for the team's own ethics, for rebuttal ("this is their card"), and for
   removal.

## Removal

**Anything in the corpus comes out on request, without the requester having to justify it.**

**Who may request removal**

- Any debater or coach from the team whose disclosure it is.
- A school, district or parent acting on their behalf.
- OpenCaselist / site administrators.
- A camp, for its own OpenEv file.
- This team's own coach, for anything imported in error or outside this policy.

**How**

By email to the coach at `<removal contact address — filled in at approval>`
([open question 5](#open-questions)). A request names the school and team code, or the file, or
the tournament and round — whatever the requester has. No reason is required and none is weighed.

**Response times**

| Step | Within |
|---|---|
| Acknowledge the request | 3 business days |
| Source removed from dev and prod, sha256 suppressed | 7 calendar days of the request |
| Affected built files flagged, and rebuilt or withdrawn from use | 7 calendar days of the request |
| Written confirmation to the requester | With the removal, inside the same 7 days |

**What removal does**

- Deletes the source blob and its `Disclosure`, `CampFile` and manifest records locally.
- Deletes `raw/` and `parsed/` objects **and every noncurrent version** from the environment's
  evidence bucket, and rewrites manifests with superseded versions purged.
- Deletes the parsed cards derived from it.
- **Appends the sha256 to the suppression list**, which the importers and the publisher consult, so
  the next cumulative weekly archive cannot bring the file back.
- Flags every built file whose provenance sidecar cites that source, for rebuild or withdrawal.
- Records the removal with request id, date, reason code, environment and sha256 values — and no
  school, team code or name.

**What removal does not do**

- It does not reach copies outside the team. By policy there are none; if one is ever found, that
  is an incident, and it is deleted in the same run and recorded.
- It does not remove the disclosure from OpenCaselist. That is the site's to do, and the requester
  is told so.
- It does not un-debate a round that already happened.

**Shared content.** If the same bytes were disclosed by another team as well, or are also a camp
file, only the requesting team's `Disclosure` records are dropped by default and the blob stays for
the other holder; removing the blob itself requires `--include-shared` and a judgement call by the
coach, who explains the outcome to the requester within the same 7 days.

**Steps:** [docs/runbooks/caselist-removal.md](../runbooks/caselist-removal.md), built around
`debate-research caselist remove --source <sha256> | --team <caselist>/<school>/<team>`
(v1-e30-t07), run against dev and then prod. Until t07 ships, the runbook's manual section is the
procedure.

## Dev environment exception

[ADR-0013](../adr/0013-two-environments-and-dev-main-promotion.md) and
[branching-and-environments.md](../process/branching-and-environments.md) say dev never holds real
student data — synthetic and scrubbed fixtures only. **This policy records one narrow exception.**

**The exception.** The public caselist and OpenEv corpus — including disclosure paths that carry
team codes (debater initials) and occasionally names — may be imported into the operator's local
store and published to the **dev** evidence bucket, for validation before the same store is
published to prod.

**Why it is necessary**

- The parser, the deduplication logic and the landscape pipeline have to work against real volume
  and real shapes: ~2,342 `.docx` and 32 `.pdf` across three cumulative HS LD snapshots, plus
  ~106 OpenEv camp files (v1-e30-t06).
- Synthetic fixtures cannot reproduce what actually breaks the parser: malformed filenames,
  `(1)` and `-2` re-upload suffixes, hyphenated tournament names, missing round labels, tracked
  changes, and the range of Verbatim style profiles in the wild.
- Publishing to prod without a dev rehearsal contradicts the "validated in dev" promotion rule.
  Without this exception, the *only* place the real corpus could be exercised is prod.

**Why it is acceptable**

- The data is already public to anyone with a Tabroom login; dev adds no exposure the source does
  not already have.
- It is **not student account data**. No user records, no credentials, no work product of this
  team's own students.
- Dev access is limited to the team's operators through the `EvidenceOperator` permission set
  (v1-e29-t03), and the dev bucket carries the same controls as prod: all four block-public-access
  flags, SSE-KMS with a customer-managed key, TLS-only bucket policy, no public or CDN origin
  access.

**Limits — all of them binding**

1. **Corpus only.** Caselist archives and OpenEv files. No student account data, no Cognito or
   user-pool data, no team-private files.
2. **Operators only.** No student or general team access to dev, in V1 or V2.
3. **Two locations.** The dev evidence bucket and the operator's local store. No exports, no email
   attachments, no other buckets, no CI artefacts, no third-party tools.
4. **Never CI data.** CI keeps synthetic fixtures only; the real corpus never reaches a CI runner
   (working agreements §1).
5. **Same retention clock as prod**, with dev noncurrent versions expiring after 30 days.
6. **Removals apply to dev and prod together**, dev first, in the same runbook run.
7. **Does not extend to V2.** When the web app and the debate tub reach dev, their user accounts,
   sessions and uploads stay synthetic. This exception covers the evidence corpus and nothing else.
8. **Revisited at approval of each season's backfill.** If the operator's corpus ever stops being
   public — for example if a caselist moves behind a per-school permission — the exception lapses
   and dev goes back to synthetic data.

This is recorded as an exception here rather than as an amendment to ADR-0013; ADR-0013 is
unchanged. If the exception needs to outlive V1, a superseding ADR records it.

## Gates

Downstream work that cannot start, or cannot run for real, until its conditions below are met.

### E34 — automated caselist download (v1.2)

`v1-e34-t01` already forbids starting before this policy is approved. In addition, before the
first automated pull:

1. This policy is **approved** (the [Approval](#approval) section is filled in).
2. The OpenCaselist terms are **transcribed and confirmed**, and nothing in them prohibits
   automated access through the documented API. If they do, E34 is cancelled or narrowed to
   assisted manual download, whatever the terms allow.
3. Access uses the **operator's own** Tabroom account and `caselist_token`. The token is stored in
   the macOS keychain, or a `0600` gitignored file; it is a `SecretStr`, redacted from logs,
   exceptions and event hooks; the password is never stored; the token is never shared.
4. **Politeness is enforced in code**: a configurable minimum interval between requests, one
   download at a time, bounded backoff on 429/502/503/504 honouring `Retry-After`, and no HTML
   scraping. Weekly cadence at most — no polling faster than archives are published.
5. `401`/`403` **stop the run** (`CaselistAuthExpired`) and are never retried.
6. Every downloaded file goes through the importer, so the **suppression list is honoured** and a
   removed file can never be re-downloaded into the store.
7. A **run log and a stale-data warning** (v1-e34-t03) make silent failure visible.
8. The scheduled job runs on the operator's own machine, and the operator remains the accountable
   human for it.

### E32 — model classification of the corpus

1. This policy is approved.
2. The provider's **no-training / no-retention terms are confirmed in writing** and recorded in
   [Sources and terms](#sources-and-terms) ([open question 4](#open-questions)). Until then,
   classification runs against synthetic fixtures only.
3. A scan of the prompt inputs and cassettes for a sample run shows **no school name, team code or
   debater name** (v1-e32-t02 acceptance criterion).
4. The circuit-wide report is verified to contain **no team codes** before it is shared with the
   team.

### v2-e35 — debate tub (v2.1)

1. This policy is approved **and the removal runbook has been exercised end to end at least once**
   in dev and prod.
2. **Team-only access is proven**, not asserted: an authorization matrix over every `/v1/tub` route
   for student, coach and administrator, same and other organization, unauthenticated, and for
   `ACTIVE` and `REMOVED` files (v2-e35-t05).
3. **No public reachability**: buckets keep all block-public-access flags, there is no public or
   CloudFront origin access, only the API role may presign, and downloads use short-lived
   presigned URLs.
4. **Every access is audited.** Download, bulk zip, upload, removal and restore each write an
   append-only record that contains no URLs, tokens, names, team codes, evidence text or IP
   addresses. Audit records are retained **400 days** and then expire.
5. **The takedown flow is wired to the V1 suppression list**; a `REMOVED` file stops listing and
   presigning immediately, and the next weekly snapshot cannot resurrect it.
6. **No sharing surface leaves the organization**: no public links, no cross-organization sharing,
   no "share by link".
7. **Attribution survives into the tub** — provenance is shown with every disclosed or camp card.
8. **Nothing beyond school plus team code** is displayed about any debater, and the tub does not
   offer search by debater.
9. School or district review, if [open question 6](#open-questions) concludes one is needed,
   is complete before students are given accounts.

## Open questions

| # | Question | Who resolves it | What it blocks |
|---|---|---|---|
| 1 | The exact OpenCaselist terms-of-use and privacy URLs and their relevant clauses | Charlie, reading the pages signed in | Approval of this policy; [Sources and terms](#sources-and-terms) |
| 2 | Whether those terms permit automated API access, and at what rate | Charlie | [E34 gate](#e34--automated-caselist-download-v12) |
| 3 | OpenEv's distribution terms and per-camp licensing notes | Charlie, from the files and camp sites | Approval; camp-file handling |
| 4 | Written confirmation that the configured model provider does not train on or retain inputs | Charlie / operator, with the AWS account terms | [E32 gate](#e32--model-classification-of-the-corpus); first full-corpus classification run |
| 5 | The removal contact address to publish in [Removal](#removal) | Charlie | Approval |
| 6 | Whether school or district review is needed before students (who may be minors) get accounts on the V2 tub. This policy does not answer it and is not legal advice | Charlie, with the school | [v2-e35 gate](#v2-e35--debate-tub-v21) |
| 7 | Whether a season's corpus may be kept beyond two seasons for year-over-year trend analysis | Charlie | A revision to [Retention](#retention) |
| 8 | Whether the `EvidenceOperator` permission set needs scoped delete rights for `caselist remove`, or whether removal runs under a separate elevated role | Operator, with v1-e29-t03 and v1-e30-t07 | Executing a real removal — see the runbook |

Every unresolved question is either answered or explicitly accepted as a known gap at approval.

## Review and change control

- This policy is reviewed at the start of each season, and immediately whenever a source's terms
  change, a removal request cannot be honoured as written, or an incident occurs.
- Changes are made by pull request against this file, with the version bumped and the
  [Approval](#approval) section re-recorded. A change that loosens a rule needs the coach's
  approval before it takes effect; a change that tightens one takes effect on merge.
- Downstream specs cite this file by path, not by copying its rules, so there is one source of
  truth.

## Approval

**Until this section records an approval, none of the following may happen:** publishing a
caselist or OpenEv import to any bucket, loading the real corpus into dev, running automated
download, or running model classification over real disclosed text.

| Field | Value |
|---|---|
| Policy version | 1.0 |
| Approved by | _pending_ (Charlie Clark, product owner and head coach) |
| Role | Product owner and head coach |
| Approval date | _pending_ |
| Scope of approval | Sections [Scope](#scope) through [Review and change control](#review-and-change-control) of version 1.0 |
| Open questions resolved or accepted at approval | _pending_ — list the numbers from [Open questions](#open-questions) |

Approval is recorded by editing this table in a pull request, together with the transcribed
clauses in [Sources and terms](#sources-and-terms) and the removal contact address in
[Removal](#removal).

## References

- [docs/runbooks/caselist-removal.md](../runbooks/caselist-removal.md) — the removal procedure.
- [ADR-0013: Two environments and dev→main promotion](../adr/0013-two-environments-and-dev-main-promotion.md)
  — the synthetic-data-only rule this policy takes a narrow exception to.
- [ADR-0006: Exact-source evidence verification](../adr/0006-exact-source-evidence-verification.md)
  — why disclosed cards are never platform-verified.
- [ADR-0005: Bedrock behind a model router](../adr/0005-bedrock-behind-model-router.md) — the only
  path by which disclosed text may reach a model.
- [ADR-0003: S3 as source of truth for raw artifacts](../adr/0003-s3-source-of-truth-for-raw-artifacts.md).
- Architecture proposal
  [§9 Search and Retrieval](../architecture/architecture_proposal.md#9-search-and-retrieval-architecture)
  (opponent data),
  [§13 Opponent intelligence](../architecture/architecture_proposal.md#13-v3-detailed-architecture),
  [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety),
  [§19 Risks and Mitigations](../architecture/architecture_proposal.md#19-risks-and-mitigations),
  [§21 External Service Assumptions](../architecture/architecture_proposal.md#21-external-service-assumptions-and-references).
- Specs that depend on this policy: `plan_specs/v1/e30-caselist-ingestion/` (t03 importer, t05
  publish, t06 backfill, t07 removal), `plan_specs/v1/e32-argument-landscape/t02-position-classification.yaml`,
  `plan_specs/v1/e33-file-builder/t02-lossless-card-writer.yaml`,
  `plan_specs/v1/e34-caselist-sync/t01-caselist-api-client.yaml`,
  `plan_specs/v2/e35-debate-tub/t05-tub-access-and-removal.yaml`.
