<!-- docs-index: How a gift reaches the debate team's district activity account: the district's confirmed process, receipts, wording, restrictions and donor recognition -->
# Donations policy

| | |
|---|---|
| Policy version | 0.1 (draft) |
| Status | **Draft, not approved.** The questions below have not yet been answered by the district. Nothing in this document is a rule yet, no payment destination is recorded, and the donate page (`v1-e38-t02`) may not link to anything until the [district's answers](#confirmation-register) are recorded and Charlie has approved a version of this policy |
| Owner | Charlie Clark (product owner and head coach) |
| Written by | v1-e38-t01-district-donation-process implementation session, 2026-11-12 |
| Applies to | Gifts from parents and supporters to the debate team's activity account held by the school district, and everything the public team website says or links to about them |
| Approved by | Not yet approved |
| Next review | Start of the 2027-28 season, or sooner if the district changes its payment method, account, receipts or required wording |

This policy records how a gift reaches the Whitefish Bay debate team's activity account at the
school district, **exactly as the district's business office and the activities director confirm
it in writing**, and the rules the team website follows when it asks for one.

**It is not legal or tax advice.** Nothing here says how a gift is treated for tax purposes, and
nothing here speaks for the district on that question. Receipts and tax acknowledgments are the
district's to issue and to word; where the district has not answered a question, this policy
records it as open rather than guessing.

The district owns the account and the rules for giving to it. This policy repeats what the
district said; it never infers, extends or softens it. An answer that has not been confirmed in
writing is an [open question](#open-questions), not a rule.

## Scope

**In scope**

- Gifts to the debate team's activity account held by the school district: how a donor gives
  (online payment portal and/or check), how the gift is designated to the debate team, who issues
  receipts and tax acknowledgments, the wording the district requires or prohibits, and the
  district's restrictions on gifts.
- What the public team website at `wfbdebate.org` says about giving and where it links: the donate
  page (`v1-e38-t02`) and opt-in donor recognition (`v1-e38-t03`), in the dev preview and in prod.

**Out of scope, and covered elsewhere**

| Subject | Where it lives |
|---|---|
| Fundraising by a parent booster group, its accounts and its own receipts | Not covered, unless the district's answer to [question 12](#questions-for-the-district) brings it in. The site does not raise money for a booster group under this policy |
| What the website may publish about students, and the website side of donations (no payment forms, no donor data, no gift amounts) | [`docs/policies/website-publishing.md`](website-publishing.md), including its [Donations](website-publishing.md#donations) section. This policy cites it rather than copying it |
| The donate page's code and its build-time link check | `v1-e38-t02` |
| The donor recognition section and its opt-in validation | `v1-e38-t03` |

## Questions for the district

Charlie sends these to the district business office and the activities director, from his own
account, and asks for the answers in writing. Each one is open until a written answer is entered
in the [Confirmation register](#confirmation-register).

**Payment method**

1. **Online giving.** Is there an online payment portal where a supporter can give to the debate
   team's activity account? If so, what is the exact link the team website should use, and does
   it go straight to the debate team's account, or does the donor choose the account from a list
   (and under what name)?
2. **Giving by check.** For a gift by check: the exact payee, what to write on the memo line so the
   gift reaches the debate team's account, and where to mail it or drop it off.
3. **Account name.** How the district wants the debate team's activity account named on the
   website.
4. **Other methods.** Whether the district prefers online or check, and whether any other method
   (cash, card in person) is accepted or should not be offered.

**Receipts and tax acknowledgments**

5. **Receipts.** Who issues receipts and tax acknowledgments for gifts to the account, whether a
   donor receives one automatically, and how a donor asks for one.
6. **Tax wording.** What, if anything, the website may say about the tax treatment of a gift: the
   district's exact wording, or an instruction to say nothing and refer donors to the business
   office. The team will not describe tax treatment in its own words.

**Wording**

7. **Required or prohibited wording.** Any wording the district requires on a page that asks for
   gifts (for example, about the district or about how gifts are used), and any wording it does not
   allow.

**Restrictions**

8. **Gifts for one student.** Whether a gift may be earmarked to benefit an individual student
   (one student's fees or travel), or must go to the team as a whole.
9. **Gift-acceptance thresholds.** Whether a gift above some amount needs approval or a
   gift-acceptance form, and who approves it.
10. **In-kind gifts.** Whether gifts of goods or services (supplies, food, travel, judging) are
    accepted, and through whom.
11. **Employer matching.** Whether the district accepts employer matching gifts, and what a donor's
    employer should be told, or whom the donor should contact.
12. **Booster group.** How gifts to the district account relate to any parent booster group, and
    whether the website should mention a booster group or keep the two separate.

**Recognition and changes**

13. **Thanking donors publicly.** Any district rule about naming or thanking donors publicly.
14. **Changes.** Who will tell the team if the portal link, payee or required wording changes.

## Confirmation register

Each row records a district answer: the question, the answer as the district gave it, the role of
the person who answered, the date and the channel. **The written confirmation itself (the reply
email or letter) is kept by Charlie outside this repository.** No district email address, account
number or donor name is ever entered here.

| # | Question | Answer | Answered by (role) | Date | Channel |
|---|---|---|---|---|---|
| 1 | Online giving | Open: not yet answered | | | |
| 2 | Giving by check | Open: not yet answered | | | |
| 3 | Account name | Open: not yet answered | | | |
| 4 | Other methods | Open: not yet answered | | | |
| 5 | Receipts | Open: not yet answered | | | |
| 6 | Tax wording | Open: not yet answered | | | |
| 7 | Required or prohibited wording | Open: not yet answered | | | |
| 8 | Gifts for one student | Open: not yet answered | | | |
| 9 | Gift-acceptance thresholds | Open: not yet answered | | | |
| 10 | In-kind gifts | Open: not yet answered | | | |
| 11 | Employer matching | Open: not yet answered | | | |
| 12 | Booster group | Open: not yet answered | | | |
| 13 | Thanking donors publicly | Open: not yet answered | | | |
| 14 | Changes | Open: not yet answered | | | |

## District process

Not yet confirmed. **No payment URL, payee, memo line or delivery instruction is recorded until
the district has confirmed it in writing** ([questions 1 to 4](#questions-for-the-district)). When
it has, this section gives it exactly as the district sent it, and it is the only source the
donate page's configuration (`v1-e38-t02`) may use.

## Receipts and tax acknowledgments

Not yet confirmed ([questions 5 and 6](#questions-for-the-district)). Whatever the district
answers, coaches and the platform never issue a receipt or a tax acknowledgment.

## Required wording

Not yet confirmed ([questions 6 and 7](#questions-for-the-district)). The district's wording is
recorded here verbatim once it is confirmed in writing.

## Restrictions

Not yet confirmed ([questions 8 to 12](#questions-for-the-district)).

## Open questions

Every question in [Questions for the district](#questions-for-the-district) is open until its row in
the [Confirmation register](#confirmation-register) records a written answer. Until then each one
blocks the donate page (`v1-e38-t02`) from linking to any payment destination.

## References

- [docs/policies/website-publishing.md](website-publishing.md): what the website may publish, and
  its [Donations](website-publishing.md#donations) section on what the site may do.
- [docs/policies/caselist-data-use.md](caselist-data-use.md): the style this policy follows.
- Architecture proposal
  [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety).
- Specs that depend on this policy: `plan_specs/v1/e38-donations/` (t02 donation page, t03 donor
  recognition).
