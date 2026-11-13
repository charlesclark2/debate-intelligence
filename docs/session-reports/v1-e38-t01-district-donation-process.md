# Session report: v1-e38-t01-district-donation-process

| | |
|---|---|
| Task | `v1-e38-t01-district-donation-process` — District donation process |
| Spec | [`plan_specs/v1/e38-donations/t01-district-donation-process.yaml`](../../plan_specs/v1/e38-donations/t01-district-donation-process.yaml) |
| Epic / release | `v1-e38-donations` / `v1.6` |
| Branch | `task/v1-e38-t01-district-donation-process` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This session did the first plan node and stopped, as the PM's context of 2026-11-13 asked:
it wrote the question list for the district business office and the activities director, and
[`docs/policies/donations.md`](../policies/donations.md) as a version 0.1 draft skeleton. It also
drafted the email for Charlie to send. The skeleton follows caselist-data-use.md: a status table,
the "not legal or tax advice" statement near the top, Scope, the fourteen questions, an empty
confirmation register, and empty District process, Receipts and tax acknowledgments, Required
wording and Restrictions sections. **No payment URL, payee or wording is recorded**, because the
district has confirmed nothing yet. The other three nodes wait on the district's written reply and
on Charlie's approval, so **the task Goal stays `InProgress`** and ac1 to ac6 are NOT RUN. The PM
should look first at the [email to send](#email-to-send) and at the
[question list](#question-list-for-the-district).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `questions-and-skeleton` | Done | Question list and policy skeleton committed (`0919fd0`) |
| `district-conversation` | Not started | Waits on Charlie sending the email and the district's written reply |
| `policy-sections` | Not started | Depends on `district-conversation` |
| `approval` | Not started | Depends on `policy-sections`; needs Charlie's approval |

## Question list for the district

These are the questions in the policy's
[Questions for the district](../policies/donations.md#questions-for-the-district) section, with
the same numbers the confirmation register uses.

| # | Short name | Question |
|---|---|---|
| 1 | Online giving | Is there an online payment portal for gifts to the debate team's activity account? The exact link; whether it goes straight to the account or the donor picks it from a list, and under what name |
| 2 | Giving by check | The exact payee, the memo line that designates the debate account, and where to mail or drop off a check |
| 3 | Account name | How the district wants the activity account named on the website |
| 4 | Other methods | Whether online or check is preferred, and whether any other method is accepted or should not be offered |
| 5 | Receipts | Who issues receipts and tax acknowledgments, whether they are automatic, and how a donor asks for one |
| 6 | Tax wording | What, if anything, the site may say about tax treatment: the district's exact words, or say nothing and refer donors to the business office |
| 7 | Required or prohibited wording | Wording a donation page must include, and wording it must not use |
| 8 | Gifts for one student | Whether a gift may be earmarked for an individual student, or must go to the team as a whole |
| 9 | Gift-acceptance thresholds | Whether a gift above some amount needs approval or a gift-acceptance form, and who approves it |
| 10 | In-kind gifts | Whether gifts of goods or services are accepted, and through whom |
| 11 | Employer matching | Whether employer matching gifts are accepted, and what a donor's employer should be told or whom to contact |
| 12 | Booster group | How gifts to the district account relate to any parent booster group; whether the site should mention one |
| 13 | Thanking donors publicly | Any district rule about naming or thanking donors publicly |
| 14 | Changes | Who tells the team if the portal link, payee or required wording changes |

Questions 1 to 12 are the spec's list. Questions 13 and 14 are added; see
[Decisions and assumptions](#decisions-and-assumptions).

## Email to send

Written for: the district business office and the activities director, sent by Charlie from his
own account.

**Recommendation: one email addressed to both.** The questions overlap: the booster
relationship, required wording and thanking donors could belong to either office. One thread
lets each answer their own part, shows each what the other said, so they cannot contradict each
other unnoticed, and gives Charlie one dated written record to keep. If Charlie would rather send
two, questions 1 to 6, 9, 10, 11 and 14 go to the business office, and 7, 8, 12 and 13 to the
activities director, each email keeping the numbering below.

The email contains no student's name, no team member's name and no money figures. The bracketed
parts are for Charlie to fill in.

```text
Subject: Debate team donations: questions about gifts to the activity account

Hi [business office contact] and [activities director],

The debate team's website (wfbdebate.org) will soon have a page where parents and
supporters can give to the team's activity account. The site will only link to the
district's own payment method, or give check instructions. It will never take payments,
card details or donor information itself, and it will say nothing about receipts or taxes
beyond what you tell us.

So that the page says exactly what the district wants, could you answer the questions
below in writing? A reply to this email is perfect. Some are probably for the business
office and some for the activities office, so please answer whichever are yours. "Not sure"
or "ask someone else" is a fine answer.

Giving
1. Is there an online payment portal for gifts to the debate team's activity account? If
   so, what is the exact link we should use? Does it go straight to the debate account, or
   does the donor choose it from a list, and under what name?
2. For a gift by check: who should it be made out to, what should go on the memo line, and
   where should it be mailed or dropped off?
3. How should we name the team's activity account on the page?
4. Do you prefer online or check? Is any other way of giving accepted, or one we should not
   offer?

Receipts and taxes
5. Who issues receipts and tax acknowledgments? Does a donor get one automatically, and if
   not, how do they ask for one?
6. What, if anything, may the page say about whether a gift is tax-deductible? We would use
   your exact wording, or say nothing and point donors to the business office.

Wording
7. Is there wording the page must include, or wording it must not use?

Limits
8. Can a gift be set aside for one particular student (for example, that student's fees or
   travel), or must gifts go to the team as a whole?
9. Does a gift above a certain amount need approval or a gift-acceptance form?
10. Do you accept gifts of goods or services (supplies, food, travel, judging), and through
    whom?
11. Do you accept employer matching gifts? If so, what should a donor tell their employer,
    or whom should they contact?
12. How do gifts to the district account relate to a parent booster group? Should the page
    mention one, or keep the two separate?

Other
13. Is there a district rule about thanking donors publicly by name? We would only list a
    donor with their written permission.
14. If the payment link, payee or wording changes later, who will let us know?

If it is easier to talk, I am glad to meet, but I would still be grateful for a short
written reply afterward so I have the answers on file.

Thank you,
[Your name]
[Your title]
```

When the replies come back, Charlie keeps them outside the repository. The resumed session needs,
for each answer: the answer as written (the payment link, payee and memo line copied exactly),
the role of the person who answered, the date and the channel (email, letter, meeting with a
written follow-up). It does not need anyone's email address or any account number, and these
should not be pasted into the session.

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — answers recorded with role, date and channel; written confirmation kept outside the repository | NOT RUN | Needs the district's written reply. The register exists with every row "Open: not yet answered", and its introduction says Charlie keeps the written confirmation outside the repository |
| ac2 — District process gives the approved payment method exactly as confirmed | NOT RUN | Needs the district's written reply (questions 1 to 4). The section says nothing is recorded until confirmed |
| ac3 — Receipts and tax acknowledgments section; "not legal or tax advice" near the top | NOT RUN | The statement is in the opening paragraphs (line 18); the receipts section waits on questions 5 and 6 |
| ac4 — Required wording, Restrictions and Platform boundaries sections | NOT RUN | Waits on questions 6 to 12; Platform boundaries is written in the `policy-sections` node |
| ac5 — Donor recognition rules | NOT RUN | Written in the `policy-sections` node, after question 13 is answered |
| ac6 — Charlie's approval recorded, linked from docs/README.md, change control | NOT RUN | `approval` node: needs Charlie's sign-off. The link from docs/README.md comes from the refresh workflow after merge |
| `questions-and-skeleton`: Policy skeleton states it is not legal or tax advice | PASS | `grep -n "not legal or tax advice" docs/policies/donations.md` → `18:**It is not legal or tax advice.** ...` |
| `district-conversation`: District process section present | NOT RUN | `grep -n "^## District process" docs/policies/donations.md` → line 122 already matches, because the PM asked for an empty section per answer. The heading of an empty section is not evidence; judge the node by its custom criterion |
| `district-conversation`: District confirmation recorded | NOT RUN | Needs Charlie and the district's written reply |
| `policy-sections`: Receipts, Platform boundaries, Donor recognition sections present | NOT RUN | The Receipts heading exists, empty, in the skeleton. Platform boundaries and Donor recognition are not written yet, so those two checks fail today, as they should |
| `approval`: Policy linked from docs index; Approval section present | NOT RUN | No Approval section yet. docs/README.md is not edited in a task |
| `approval`: Charlie approves the donations policy | NOT RUN | Needs Charlie's approval |

## Checks run

| Command | Result |
|---|---|
| `uv run scripts/check_links.py` | `OK: 3844 relative links and anchors in 663 Markdown files` |
| `uv run scripts/check_command_blocks.py` | `OK: no # comments in 703 shell code blocks in 258 Markdown files` |
| `uv run scripts/docs_index.py --check-descriptions` | `All 72 indexed documents under docs/ have a description` |

The final checks before commit are in [Final checks](#final-checks).

## Files changed

- `docs/policies/donations.md`: new, the version 0.1 draft skeleton and the question list.
- `docs/session-reports/v1-e38-t01-district-donation-process.md`: this report.

## Deviations from the spec

None. Stopping after the first node is the PM's instruction of 2026-11-13, not a scope change.

## Decisions and assumptions

- **Two questions beyond the spec's list.** Question 13 (a district rule on thanking donors) is
  asked because the Donor recognition section (ac5) sets public-facing rules and the district may
  have one. Question 14 (who tells the team of a change) is asked because ac6 makes a new payment
  URL a version bump, and the team can only make one if it hears of the change.
- **Roles, not names, in the register.** ac1 asks for the role of each person consulted, so the
  register has an "Answered by (role)" column. The website publishing policy names the activities
  director; this policy does not need to, and the email leaves both names for Charlie to fill in.
- **Platform boundaries and Donor recognition are not in the skeleton.** They are the team's own
  rules, not district answers, and belong to the `policy-sections` node. Leaving them out keeps
  that node's two section checks failing until the sections are written.
- **Booster fundraising is out of scope** in the skeleton, as the spec says, unless the answer to
  question 12 brings it in.

## Operator follow-ups

Nothing to run.

**Coach action:** send the [email](#email-to-send) to the district business office and the
activities director, and keep the replies outside the repository. When they come back, resume this
task (`scripts/task resume`) and give the session each answer with the role, date and channel.

## Follow-up work

- [`docs/policies/website-publishing.md`](../policies/website-publishing.md) describes
  `docs/policies/donations.md` as "not yet written" in its Scope table and its References. It now
  exists as a draft. Correcting it is an edit to an approved policy (a version bump and a
  re-recorded approval), so this session left it alone; it fits best with this task's `approval`
  node, once donations.md is approved. The PM decides.

## Final checks

Run on the final tree, with this report written.

| Command | Result |
|---|---|
| `uv run scripts/validate_specs.py` | `OK: 684 files, 41 epics, 621 tasks, 22 releases` |
| `uv run ruff check` / `uv run ruff format --check` | `All checks passed!` / `2107 files already formatted` |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| pyright | Not run: no Python changed, so there is no changed package to check |
| `uv run scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 703 shell code blocks in 260 Markdown files (1 session reports changed since origin/dev)` |
| `uv run scripts/check_links.py` | `OK: 3868 relative links and anchors in 664 Markdown files` |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | **Stopped at its 115-second limit, no result.** The selection is 50 of 762 test files, reached through generic edges from the three changed files: the task spec (through `scripts/affected_tests.py` and the CI selection tests, including `test_ci_workflow_test_job.py`, which collects the whole suite several times), this report (through `scripts/task_helper.py`) and the documentation checks. Under the PM's ruling of 2026-10-19 a selection over about two minutes is left to the pull request's CI, with no operator hand-off |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q tests/docs/test_check_links.py tests/scripts/test_docs_index.py tests/scripts/test_check_command_blocks.py tests/architecture/test_single_interpreter_source.py tests/specs/test_validate_specs.py` | `276 passed in 4.54s`: the tests that read the new policy, this report and the spec |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
