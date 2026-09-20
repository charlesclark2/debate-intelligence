# ADR-0014: Debate file editor and format reference

- Status: Proposed <!-- Proposed | Accepted | Deprecated | Superseded by ADR-NNNN (link to the replacement file) -->
- Date: 2026-09-20
- Deciders: Charlie Clark (pending — see [Decision](#decision))
- Architecture references: [§6 Repository and service boundaries](../architecture/architecture_proposal.md#6-repository-and-service-boundaries), [§13 V3 detailed architecture](../architecture/architecture_proposal.md#13-v3-detailed-architecture), [§16 Testing and evaluation strategy](../architecture/architecture_proposal.md#16-testing-and-evaluation-strategy), [§18 Key architecture decisions](../architecture/architecture_proposal.md#18-key-architecture-decisions-adrs)

## Context

Every debate file this platform reads or writes is a Word `.docx` shaped by
[Verbatim](https://github.com/ashtarcommunications/verbatim), the Word add-in most US teams use.
Verbatim is the de facto format standard, but it is a Word macro project: Windows-first, no
Chromebook story, and nothing a program can call. Before the epic defines a style profile (t02),
writes a parser (t03) and a lossless writer (v1-e33-t02), it has to say what it is compatible
*with*, and whether the team has an editor other than Word.

[CardMirror](https://github.com/ant981228/cardmirror) is a free, open-source ProseMirror editor
that reads and writes Verbatim-compatible `.docx` losslessly, runs on macOS, Windows, Linux and in
a browser, and exposes a real TypeScript API (`fromDocx`, `toDocx`, `schema`). That makes it three
different things at once — a possible editor for our debaters, a machine-readable reference for
Verbatim's conventions, and a possible component of the V2 web app — and each one has a different
answer.

The evidence is in [docs/architecture/cardmirror-evaluation.md](../architecture/cardmirror-evaluation.md),
reviewed at commit `bc92e6bd99cb9b3ce97ddacfa2362100db96360e` (CardMirror 1.11.0). In summary:

* **The document model lines up with ours.** Its `pocket` / `hat` / `block` / `tag` /
  `cite_paragraph` / `card_body` / `analytic` / `undertag` nodes map onto the `StructuralUnit` enum
  t02 defines, and its `PSTYLE_TO_NODE` and `MARK_TO_RSTYLE` tables are a second, independent
  reading of Verbatim's style ids that we can check ourselves against.
* **The round-trip holds on styled files.** In synthetic probes, a conventional Verbatim card kept
  its text, heading levels, cite styling, underline, highlight and bold, and the export carries
  canonical Verbatim style ids. Underline is dual-encoded by design (named `StyleUnderline` in body
  slots, direct `<w:u>` in structural slots, both on body runs on export) — a rule our parser has to
  know. Hard page breaks lose their page type, `<w:sectPr>` is normalized away, and tracked changes
  are resolved rather than preserved.
* **Non-Verbatim files stay flat.** A heading expressed only as an outline level, without the
  Verbatim formatting signature, is not promoted to a heading; a file with neither styles nor
  outline levels imports as loose paragraphs. Our parser faces the same wall, and CardMirror's
  thresholds are a good starting point for t02's heuristics.
* **The license is PolyForm Noncommercial 1.0.0.** Debaters using the app, and us running its
  importer/exporter in operator tooling, are both plainly permitted. Linking to it from our web app
  carries no obligation at all. *Embedding* it in our web app is permitted only for as long as this
  platform is noncommercial — the license looks at our purpose, not at where the code sits.
* **The paid tier is narrow.** A Debate Decoded membership is required only for card sharing and for
  starting relay-backed co-editing sessions. Editing, import, export, read mode, send-to-speech and
  plugins are free and fully offline.
* **It is young and has one maintainer.** The repository was created in May 2026; desktop builds are
  unsigned. That is a real operational risk for a tournament-day tool, and it is not a risk at all
  for using the project as a format reference.

## Decision

Two questions, answered separately.

**1. Is CardMirror a compatibility target for the files we produce?**

> _Charlie's answer:_ ______________________

**Recommended: yes.** Every file this platform writes — built files from the E33 file builder,
exports from the V2 card editor — should survive a CardMirror `fromDocx` / `toDocx` round-trip with
no structural differences, checked with
[`scripts/cardmirror-roundtrip/`](../../scripts/cardmirror-roundtrip/README.md). This costs almost
nothing: CardMirror's round-trip contract is Verbatim fidelity, so a file that survives it is a file
Verbatim users can open. It is the cheapest available proof that our writer produces real debate
files rather than something that merely looks right.

**2. Is CardMirror the team's editor this season?**

> _Charlie's answer (mandated / allowed / not this season):_ ______________________

**Recommended: allowed, not mandated.** Debaters who want it — particularly anyone on a Chromebook,
a Mac, or a school machine that cannot run Word macros — should be told it exists, told to keep
backups, and told to use the desktop build rather than the web edition at tournaments. Mandating it
for the whole team this season bets tournament-day reliability on a five-month-old, one-maintainer
project with unsigned builds. Nothing in this platform depends on the answer either way.

**Scope of what this ADR settles regardless of those answers:**

* **We do not embed or fork CardMirror.** The V2 card editor and V3 file upload build on our own
  surface. If embedding is ever reconsidered, it is a new ADR, and it starts with a written
  commercial-license conversation with the author.
* **"Open in CardMirror" in the debate tub (v2-e35-t04) is a download plus a hand-off hint or a deep
  link.** Both are outside the license's reach; neither needs anyone's permission.
* **The Node round-trip harness is never run in CI.** Not in the PR path, not in `validate-dev`, not
  nightly. It is operator tooling: it needs a `node_modules` tree pulled from GitHub and files that
  must never enter this repository. The Python comparison script's own tests, which build synthetic
  `.docx` files, do run in CI. If this ever changes, it changes in a new ADR first.
* **CardMirror's schema is a documented input to t02's style profile,** recorded in the mapping table
  in the evaluation note, not copied into code. We read it; we do not depend on it.

## Consequences

* **[t02, the style profile](../../plan_specs/v1/e31-debate-file-parsing/t02-verbatim-style-profile.yaml):**
  the profile records the CardMirror schema names beside our own, must state the dual underline
  encoding rule (and that a body run may carry both encodings at once), and can use CardMirror's
  outline-level thresholds as the starting point for its heuristic classifier.
* **[v1-e33-t02, the lossless writer](../../plan_specs/v1/e33-file-builder/t02-lossless-card-writer.yaml):**
  its CardMirror check is now unconditional if question 1 is answered yes — a built file
  round-trips through this harness with no structural differences, run by the operator, not in CI.
* **[v2-e35-t04, the debate tub](../../plan_specs/v2/e35-debate-tub/t04-tub-ui.yaml):** "Open in
  CardMirror" is scoped as a download plus hand-off hint or deep link, with no license obligation and
  no embedded code.
* **The V2 card editor and [v3-e20 file upload](../../plan_specs/v3/e20-file-intelligence/epic.yaml):**
  we carry the cost of our own editor surface. In exchange, this platform's licensing stays
  independent of what it becomes commercially.
* **A pinned dependency drifts.** The evaluation and the harness pin CardMirror 1.11.0. Re-running
  the harness against a newer release before each major file-format change keeps the compatibility
  claim honest; nothing breaks if we skip it, we just stop knowing.
* **Tracked changes do not survive CardMirror.** Any debater using it loses revision history on
  files they open and re-save. Worth saying out loud to the team if the answer to question 2 is
  "allowed" or "mandated".

## Alternatives considered

**Adopt CardMirror as the team editor and embed it in the V2 web app.** This is the tempting
option: a finished, well-designed debate editor is months of work we would not have to do. Rejected
because the PolyForm Noncommercial license makes the embedding permitted only while this platform is
noncommercial, and that is precisely the variable we cannot fix today. Discovering the constraint
mid-V2, with the editor embedded, is the expensive version of this conversation. Linking is
unconstrained and gets most of the student-facing benefit.

**Fork CardMirror for the team.** Permitted by the license, and technically attractive — the schema
and importer are exactly what we want. Rejected because a fork is a maintenance commitment to a
30 MB TypeScript editor, and because it inherits the same commercial-use limit as embedding while
adding the burden of tracking upstream.

**Treat Verbatim alone as the format standard and ignore CardMirror.** This is the status quo and it
is not unreasonable — Verbatim is what the community actually uses. Rejected because CardMirror is
the only machine-readable, testable reading of Verbatim's conventions that exists. Ignoring it means
our only compatibility check is opening files in Word by hand.

**Run the round-trip harness in CI.** Rejected against the CI budget in
[working-agreements.md §1](../process/working-agreements.md#1-ci-stays-light): it needs an npm
install from GitHub and real debate files, neither of which belongs in a five-minute PR check. The
comparison script's synthetic tests give us the regression coverage that matters.

## References

- [docs/architecture/cardmirror-evaluation.md](../architecture/cardmirror-evaluation.md) — the schema
  mapping, API notes, plugin-bridge findings, subscription features, license review and round-trip
  results this decision rests on.
- [CardMirror](https://github.com/ant981228/cardmirror) at `bc92e6bd99cb9b3ce97ddacfa2362100db96360e`
  (1.11.0); [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/).
- [Verbatim](https://github.com/ashtarcommunications/verbatim).
- [`v1-e31-t01-cardmirror-evaluation`](../../plan_specs/v1/e31-debate-file-parsing/t01-cardmirror-evaluation.yaml),
  the spike this ADR concludes, and [epic E31](../../plan_specs/v1/e31-debate-file-parsing/epic.yaml).
- [ADR-0006](0006-exact-source-evidence-verification.md) — evidence integrity. CardMirror does not
  cut cards and nothing here changes those rules.
