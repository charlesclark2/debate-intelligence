# Caselist and OpenEv data-use policy

| | |
|---|---|
| Policy version | 1.1 |
| Status | **Approved**, version 1.1, 2026-09-19. See [Approval](#approval). |
| Owner | Charlie Clark (product owner and head coach) |
| Written by | v1-e30-t01-caselist-data-use-policy implementation session, 2026-09-19 |
| Applies to | Everything the platform collects from OpenCaselist and OpenEv, and everything derived from it, in every environment |
| Approved by | Charlie Clark, product owner and head coach, 2026-09-19 (versions 1.0 and 1.1) |
| Next review | Start of the 2027-28 season, or sooner if a source's terms change |

This is the policy that governs how the Debate Intelligence Platform collects, stores, uses and
removes evidence that **other teams disclose publicly** on
[opencaselist.com](https://opencaselist.com/) and camp files published through **OpenEv**. It is
not legal advice. Where a question needs a school, district or lawyer to answer, this policy says
so in [Open questions](#open-questions) rather than guessing.

It is written to be **more restrictive than the source terms require**. The OpenCaselist Terms &
Conditions were read on 2026-09-19 and are recorded in [Sources and terms](#sources-and-terms);
no term in them is stricter than a rule below. The OpenCaselist privacy page and OpenEv's
distribution terms have not been read, and were accepted as known gaps at approval
([open questions](#open-questions) 1 and 3). If a term read later turns out to be *stricter* than
a rule here, this policy is revised and re-approved before the affected work continues.

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

> **Read 2026-09-19; privacy page and OpenEv terms still open.** The OpenCaselist Terms &
> Conditions at <https://opencaselist.com/terms> are public and were read on 2026-09-19; every
> clause that bears on this policy is in the [clause register](#clause-register) below, and
> Charlie confirmed the register at approval. Two sources remain unread: the OpenCaselist privacy
> page, and OpenEv's distribution terms together with the per-camp licensing notes carried in the
> files themselves. Both were accepted as known gaps at version 1.0
> ([open questions](#open-questions) 1 and 3) and are recorded here when read.

### Source register

| Source | What it is | What we take | How we take it | Terms recorded? |
|---|---|---|---|---|
| OpenCaselist — site and terms | `https://opencaselist.com/` — the high-school and college open-source disclosure wikis, browsed with a Tabroom account; Terms & Conditions at `https://opencaselist.com/terms` | Nothing directly; the site is where the archives and the terms live | Browser, operator's own Tabroom login | ☑ Terms & Conditions read 2026-09-19. ☐ Privacy page — [open question 1](#open-questions) |
| OpenCaselist — weekly open-source archives | Cumulative per-caselist archives of every open-source document teams have disclosed this season (e.g. `hsld26-0915`) | The archive `.zip`, unpacked into per-school / per-team-code / per-round documents | Manual download today (v1-e30-t03/t06); authenticated API later, gated by this policy (E34) | ☑ Covered by the site Terms & Conditions, read 2026-09-19 |
| OpenCaselist — API v1 | `https://api.opencaselist.com/` — documented API for caselists, schools, teams, rounds, cites, downloads and OpenEv (architecture proposal §21, reference 11) | Caselist and download listings, archive bytes, OpenEv listings | Not yet used. E34 only, with the operator's own `caselist_token`, at most 10 file downloads per minute | ☑ Covered by the site Terms & Conditions, read 2026-09-19, and the maintainer's confirmation of scheduled downloads (clause 12) |
| OpenEv camp files | Camp-published evidence files distributed through OpenCaselist's OpenEv section | The camp-file archives and their camp / year / event / title metadata | Manual download today (v1-e30-t04); API later (E34) | ☐ Not yet — [open question 3](#open-questions) |

### Clause register

OpenCaselist **Terms & Conditions**, <https://opencaselist.com/terms>, read **2026-09-19**.
Clauses are paraphrased; phrases in quotation marks are the site's own wording.

| # | Clause | What it says | What it means for us |
|---|---|---|---|
| 1 | Your Stuff | Uploaders keep ownership of their files; the site gets rights to store, archive and display them | The disclosing team owns its documents. The site's rights are the site's and are not passed on to us — nothing here licenses us to redistribute anything. This is the written basis for [Removal](#removal) being unconditional |
| 2 | Your Responsibilities | Don't copy, upload, download or share content unless you have the right to; content may be protected by others' intellectual property rights; the site is not responsible for user content | The clause that matters most to us. Downloading to prepare is the purpose teams disclose for; sharing beyond the team is not ours to do. This is the written backing for [Prohibited uses](#prohibited-uses) 1–3. The "others' intellectual property rights" point also reaches the *publishers* of the evidence inside a disclosed card, which is why [Attribution](#attribution) keeps the original cite intact and never presents a card as ours |
| 3 | Our Stuff | No rights in the Services, or in other users' content, are granted | There is no implied licence. Our use rests on the disclosure norm and on these terms, not on any grant from the site |
| 4 | Acceptable Use — rate limits | No downloading beyond set rate limits, "manual or automated" | Rate limits bind a human with a browser exactly as they bind a script. The terms state no rate; the maintainer set it at **10 file downloads per minute** (clause 12). That limit binds E34's client and the operator's manual downloads alike |
| 5 | Acceptable Use — security | No circumventing security or authentication; no accessing non-public areas | [Prohibited uses](#prohibited-uses) 4. The operator's own Tabroom login and nothing else |
| 6 | Acceptable Use — load | No overloading the service | One download at a time, bounded backoff, weekly cadence at most ([E34 gate](#e34--automated-caselist-download-v12) 4) |
| 7 | Acceptable Use — interfaces | No accessing, searching or creating accounts except through "publicly supported interfaces"; scraping and bulk account creation are the examples given | Settles one question and opens another. Scraping `opencaselist.com` HTML is out, which this policy already prohibited. The maintainer confirmed that scheduled archive downloads through the documented API at `api.opencaselist.com` are acceptable (clause 12) |
| 8 | Acceptable Use — commercial | No selling the Services | [Prohibited uses](#prohibited-uses) 3 |
| 9 | Acceptable Use — others' rights | No violating others' privacy or rights | The written backing for [Personal data](#personal-data). Team codes are treated as personal data about people who may be minors |
| 10 | Termination | Access may be suspended at the site's discretion | Access is a privilege, not an entitlement. A `401`/`403` stops the run and is escalated to Charlie, never worked around ([E34 gate](#e34--automated-caselist-download-v12) 5) |
| 11 | Modifications | The terms may change, and continued use means acceptance | The terms are re-read at the start of each season and whenever the site announces a change — see [Review and change control](#review-and-change-control) |
| 12 | Maintainer confirmation (not part of the published terms) | Asked by Charlie through the site's Contact channel; the maintainer replied on 2026-09-19 that scheduled downloads of the weekly archives through the API are acceptable, with a rate limit of **10 file downloads per minute** | Resolves [open question 2](#open-questions) and satisfies [E34 gate](#e34--automated-caselist-download-v12) item 2. The client's default stays below the limit (8 per minute) and cannot be configured above 10. Charlie keeps the maintainer's reply on file; it is not committed |

**Assessment.** No term read on 2026-09-19 is stricter than a rule in this policy; the
[Prohibited uses](#prohibited-uses) already cover every relevant Acceptable Use item. The two
things the terms leave unstated, the download rate and whether the API may be used for scheduled
downloads, were answered by the maintainer on 2026-09-19 (clause 12).

### Still to read

Recorded in the clause register above when read, with URL and date.

**OpenCaselist privacy page** ([open question 1](#open-questions), accepted as a known gap at
version 1.0)

1. What it says about **minors**.
2. What it says the site itself **publishes** — school names, team codes, round reports.
3. Any **removal, takedown or withdrawal** channel the site offers a disclosing team, and how it
   relates to [Removal](#removal).

**OpenEv** ([open question 3](#open-questions), accepted as a known gap at version 1.0)

1. The page or file that states OpenEv's distribution terms, and the date read.
2. Per-camp licensing notes: camps publish under different conditions, and some state terms on
   the first page of the file or on the camp's own site. Record each camp represented in the
   corpus and what, if anything, it says.
3. Whether any camp file carries a licence that is *more* permissive (for example explicit
   permission to redistribute). This policy does not act on that; it only records it.

### Community disclosure norms

Separate from any written term, the circuit has norms about disclosure that this policy respects
whether or not the written terms require them. These are the coach's account of practice rather
than quoted rules, and Charlie confirmed them at approval on 2026-09-19:

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

By email to the coach at **ctcb57@gmail.com**. A request names the school and team code, or the
file, or the tournament and round — whatever the requester has. No reason is required and none is
weighed.

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
2. **The maintainer has confirmed scheduled downloads.** Satisfied 2026-09-19 (clause 12 of the
   [clause register](#clause-register)): scheduled weekly archive downloads through the API are
   acceptable at **no more than 10 file downloads per minute**. The client defaults to 8 per minute,
   refuses a configuration above 10, and counts every file download (archives and OpenEv files)
   against the same limit. If the maintainer later withdraws or changes this, E34 stops until the
   policy is revised.
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

Status as recorded at the version 1.1 approval on 2026-09-19. **Accepted** means Charlie
knowingly approved the policy without the answer; **open** means the answer is still needed
before the thing it gates.

| # | Question | Status | Who resolves it | What it blocks |
|---|---|---|---|---|
| 1 | What the OpenCaselist **privacy page** says about minors, about what the site itself publishes (school names, team codes, round reports), and about a withdrawal channel. The Terms & Conditions were read on 2026-09-19; the privacy page was not | **Accepted as a known gap**, 2026-09-19 | Charlie, when he next reads it | Nothing. Recorded in [Sources and terms](#sources-and-terms) when read |
| 2 | Two points the Terms & Conditions leave unstated: **(a)** the download rate limit, which is binding "manual or automated" but is never given as a number; **(b)** whether the documented API at `api.opencaselist.com` is a "publicly supported interface" for *scheduled* downloads | **Resolved** 2026-09-19 — the maintainer confirmed scheduled archive downloads through the API are acceptable, rate limit 10 file downloads per minute (clause 12) | Charlie | — |
| 3 | **OpenEv's distribution terms** and the per-camp licensing notes carried in the files | **Accepted as a known gap**, 2026-09-19 | Charlie, from the files and the camp sites | Nothing today — we redistribute nothing, so the risk is low. Revisit if camp files are ever handled differently from disclosures |
| 4 | Confirmation that the model provider does not retain or train on our inputs: the **AWS Bedrock data-protection documentation** (Bedrock does not store prompts or completions and does not use them to train models), recorded here by URL and date read, **plus** a check that no model-invocation logging to a third-party destination is enabled in the account | **Open** | Operator, from the AWS documentation and the account's Bedrock settings | [E32 gate](#e32--model-classification-of-the-corpus). Not a blocker for this approval; it blocks the first full-corpus classification run |
| 5 | The removal contact address to publish in [Removal](#removal) | **Resolved** 2026-09-19 — `ctcb57@gmail.com` | Charlie | — |
| 6 | Whether school or district review is needed before students (who may be minors) get accounts on the V2 tub. This policy does not answer it and is not legal advice | **Open until V2** | Charlie, with the school | [v2-e35 gate](#v2-e35--debate-tub-v21) item 9 |
| 7 | Whether a season's corpus may be kept beyond two seasons for year-over-year trend analysis | **Resolved** 2026-09-19 — no; the two-season clock in [Retention](#retention) stands | Charlie | — |
| 8 | Whether the `EvidenceOperator` permission set needs scoped delete rights for `caselist remove`, or whether removal runs under a separate elevated role | **Resolved by a spec change to v1-e29-t03 / v1-e30-t07 (PM)** | PM, in a separate specs pull request | Executing a real removal — see the [runbook](../runbooks/caselist-removal.md#manual-procedure-until-v1-e30-t07-ships) |

## Review and change control

- This policy is reviewed at the start of each season, and immediately whenever a source's terms
  change, a removal request cannot be honoured as written, or an incident occurs.
- Changes are made by pull request against this file, with the version bumped and the
  [Approval](#approval) section re-recorded. A change that loosens a rule needs the coach's
  approval before it takes effect; a change that tightens one takes effect on merge.
- Downstream specs cite this file by path, not by copying its rules, so there is one source of
  truth.

## Approval

**Version 1.1 of this policy is approved.** Publishing caselist and OpenEv imports, loading the
real corpus into dev, model classification over real disclosed text, and automated download (E34)
are unblocked, each still subject to its own conditions in [Gates](#gates). Version 1.1 records
the maintainer's confirmation of scheduled API downloads and the 10-per-minute rate limit.

The standing rule for every future version: until this table records an approval of that version,
nothing this policy governs may happen under it.

| Field | Value |
|---|---|
| Policy version | 1.1 (1.0 approved earlier the same day) |
| Approved by | Charlie Clark |
| Role | Product owner and head coach |
| Approval date | 2026-09-19 |
| Scope of approval | Sections [Scope](#scope) through [Review and change control](#review-and-change-control) of version 1.1, including the [clause register](#clause-register) read 2026-09-19 and the [community disclosure norms](#community-disclosure-norms), both confirmed by Charlie |
| Open questions resolved at approval | **5** — removal contact address is `ctcb57@gmail.com`. **7** — two-season retention stands. **8** — resolved by a PM spec change to v1-e29-t03 / v1-e30-t07. **2** (version 1.1) — maintainer confirmed scheduled API downloads at 10 file downloads per minute |
| Open questions accepted as known gaps | **1** — OpenCaselist privacy page unread. **3** — OpenEv distribution and per-camp terms unread |
| Open questions left open | **4** — Bedrock data-protection terms, an E32 gate. **6** — school or district review, before V2 student accounts |

A later version is approved by editing this table in a pull request, with the version bumped in
the header and in [Review and change control](#review-and-change-control).

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
