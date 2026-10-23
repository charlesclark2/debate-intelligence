<!-- docs-index: The student search pilot's evidence: early sessions, the promotion checklist, the beta and the go or no-go -->
# Student search pilot: what happened

The record of the student search pilot (E39, v1.7): who used it in which environment, as counts,
what the promotion to prod did, the coach's beta and the student pilot, and the decision for the
whole team. It never holds a name, a username, a quotation with an identity, or card text
(data-use policy, E39 gate items 8 and 9). `v1-e39-t10` completes it; the PM started it on
2026-10-22 so that the early evidence is not lost.

## Early evidence, before the beta

| Date | Environment | What happened | Recorded by |
|---|---|---|---|
| 2026-10-22 | dev | The coach gave **2** debaters dev accounts. Both signed in and searched on their own school Chromebooks, on the school's network, without help. This is the first sign that the school's web filter lets the pilot's hosts through, for dev's hostnames only. Their dev accounts are not carried to prod. | PM, from the coach's report |
| 2026-10-22 | dev | The weekly agent run `20261022T052044Z` published index `767b9c7c056b80cb`: 52,059 documents, 839,438,336 SQLite bytes, 314,054,035 gzip bytes. | PM |

## The promotion to prod

Each item of [the runbook's promotion list](../runbooks/evidence-search.md#promoting-the-pilot-to-prod),
ticked yes or no with its date, before the coach's beta (`v1-e39-t10` ac7).

| Item | Done | Date | Notes |
|---|---|---|---|
| 1. `dev` promoted to `main` | | | |
| 2. Prod's `owner.auto.tfvars` checked | | | |
| 3. Step 11 in full, nothing destroyed | | | |
| 4. `v1-e29-t08`'s prod plan | | | |
| 5. Prod's suppression list exists | | | |
| 6. Prod's parsed store current | | | |
| 7. Prod's first index published | | | |
| 8. `v1-e39-t07`'s prod removal exercise | | | |
| 9. Superseded parsed directories retired in prod | | | |
| 10. The request to school IT | | | |
| 11. The beta's prod accounts created | | | |

## The coach's beta

Written by `v1-e39-t10`.

## The student pilot, and the decision

Written by `v1-e39-t10`.
