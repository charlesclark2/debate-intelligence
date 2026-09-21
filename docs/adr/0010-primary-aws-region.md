# ADR-0010: Primary AWS region (us-east-1) and single-account environment separation

- Status: Accepted
- Date: 2026-09-19
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
  - [§7 Data Architecture](../architecture/architecture_proposal.md#7-data-architecture)
  - [§10 LLM and Retrieval Model Strategy](../architecture/architecture_proposal.md#10-llm-and-retrieval-model-strategy)
  - [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)
  - [§15 Reliability, Observability, and Cost Controls](../architecture/architecture_proposal.md#15-reliability-observability-and-cost-controls)

## Context

Release v1.1 puts disclosed caselist evidence in S3 (epic E29, [ADR-0003](0003-s3-source-of-truth-for-raw-artifacts.md)),
which forces two bootstrap decisions before any bucket is created.

**Region.** The evidence buckets created in `v1-e29-t03-evidence-buckets` are the system of
record and should not have to move later, so the region has to suit not just S3 but the
Bedrock models the ModelRouter will route to ([§10](../architecture/architecture_proposal.md#10-llm-and-retrieval-model-strategy),
[ADR-0005](0005-bedrock-behind-model-router.md)) and the OpenSearch Serverless collections V2
adds ([ADR-0004](0004-opensearch-is-derived-not-authoritative.md)). Cross-region calls between
an S3 bucket and a Bedrock endpoint are legal but add latency and egress cost, and a
reranker that is missing from the region would have to be replaced or called across regions.

**Account structure.** The task spec's primary path is separate dev and prod member accounts.
The existing situation is not a blank slate: an AWS Organization (all features enabled) already
exists with a single account — its own management account — that runs three unrelated personal
projects, and IAM Identity Center is already enabled on it with one user. The account id, the
organization id and the Identity Center instance are recorded in the runbook and supplied to
Terraform as variables, never committed here. Adding member accounts is possible; the product
owner chose not to, to avoid running multi-account billing and a second set of guardrails for a
project with one maintainer.

### Bedrock availability, checked 2026-09-19

Every model in [§10](../architecture/architecture_proposal.md#10-llm-and-retrieval-model-strategy),
from `aws bedrock list-foundation-models` and `aws bedrock list-inference-profiles`, run against
the management account on that date. The ModelRouter routing config does not exist yet (it
arrives with epic E05 in v1.2), so the §10 table is the model list; this table is rechecked when
that config lands.

| §10 task class | Model id | us-east-1 | us-east-2 | us-west-2 |
|---|---|---|---|---|
| Complex reasoning | `anthropic.claude-sonnet-5` | Inference profile (`us.`, `global.`) | Inference profile | Inference profile (`us.`, `global.`) |
| High-volume extraction | `anthropic.claude-haiku-4-5-20251001-v1:0` | Inference profile (`us.`, `global.`) | Inference profile | Inference profile (`us.`, `global.`) |
| Deep offline audit | `anthropic.claude-opus-5` | Inference profile (`us.`, `global.`) | Inference profile | Inference profile (`us.`, `global.`) |
| Embeddings | `amazon.titan-embed-text-v2:0` | On demand | On demand | On demand |
| Reranking | `cohere.rerank-v3-5:0` | On demand | **Absent** | On demand |

The three Claude models are inference-profile only in every candidate region — there is no
on-demand throughput for them — so the router must call the `us.`/`global.` profile id, never the
bare model id. Both system-defined profiles are `ACTIVE` in us-east-1 and us-west-2.

us-east-2 is disqualified: it carries no Cohere Rerank 3.5, and no substitute reranker.

### Supporting services and price, checked 2026-09-19

| | us-east-1 | us-west-2 |
|---|---|---|
| S3 Standard, first 50 TB | $0.023 / GB-month | $0.023 / GB-month |
| OpenSearch Serverless, every OCU type | $0.24 / OCU-hour | $0.24 / OCU-hour |
| OpenSearch Serverless available | Yes | Yes |
| Extra reranker | — | `amazon.rerank-v1:0` |

S3 and OpenSearch Serverless prices come from the AWS Price List API (`aws pricing get-products`,
service codes `AmazonS3` and `AmazonES`) and are identical in the two regions, including the
higher storage tiers. Bedrock per-token rates could **not** be compared programmatically: the
Price List API's `AmazonBedrock` catalogue did not carry entries for Claude Sonnet 5, Haiku 4.5
or Opus 5 on the date of this check, so no rate comparison is recorded here. This does not
change the decision, because both surviving regions expose the identical set of models through
the identical inference-profile mechanism; confirming rates is an operator step in the runbook.

## Decision

**The primary AWS region is `us-east-1`.** Every account-baseline resource, the evidence buckets
in `v1-e29-t03-evidence-buckets`, Terraform state, and V2 resources are created there unless a
service is unavailable, in which case the exception is recorded in the owning task's spec.
Bedrock calls use the `us.`-prefixed cross-region inference profile ids rather than bare model
ids. Region is configuration, never hard-coded in a reusable module.

us-east-1 wins over us-west-2 on one differentiator and ties on the rest: it is where the
operator's existing footprint already lives (the Identity Center session, the default CLI region
and every current bucket), so there is no chance of a bucket or a trail landing in the wrong
region by inheriting a default. Model coverage, OpenSearch Serverless support, S3 price and OCU
price are identical.

**Environments are separated by tag within the single existing account, not by account.**
This is the fallback the E29 t01 spec allows, and it is taken deliberately. It does not change
[ADR-0013](0013-two-environments-and-dev-main-promotion.md): there are still exactly two
environments, `dev` and `prod`, and still no `stage`. What changes is the boundary that enforces
them. The rules that make the fallback safe are binding:

1. **Every resource carries `Environment` = `dev` or `prod` and `Project` = `debate-intelligence`,**
   applied through Terraform `default_tags` (the standard is set in `v1-e29-t02-terraform-bootstrap`).
   A resource without both tags is a defect.
2. **Names carry the environment too.** Every bucket, key alias, role, trail and budget for this
   project is named `debate-<environment>-<purpose>`, so that an IAM policy can separate
   environments by resource-name prefix and not only by tag.
3. **Human access is separated by permission set.** Maintainers reach dev through a permission
   set scoped to `debate-dev-*` resources and prod through a separate, narrower one; the two
   named CLI profiles `debate-dev` and `debate-prod` assume different permission sets against the
   same account id. The least-privilege operator permission set for the evidence buckets is
   defined in `v1-e29-t03-evidence-buckets`.
4. **Prod evidence is never readable by a dev-scoped credential,** enforced by resource-name
   conditions in the permission-set policies rather than by convention.
5. **This account also runs unrelated personal projects.** Nothing in those projects may be given
   access to `debate-prod-*` resources, and the debate budgets and the anomaly monitor filter on
   the `Project` tag so that debate spend stays legible next to the other workloads.

**Revisit trigger.** Split `debate-prod` into its own member account before the platform holds
real student data for anyone outside the product owner's own team, or as soon as a second adult
maintainer needs standing access. The revisit is cheap to act on and expensive to defer: moving
an S3 bucket between accounts means copying every object and rewriting provenance references.

## Consequences

- The evidence buckets in t03 can be created immediately, in us-east-1, without waiting for
  account vending, and the operator keeps one bill and one set of guardrails.
- Isolation between dev and prod is now only as strong as the IAM policies and tags that
  implement rules 1–4. An over-broad `AdministratorAccess` grant, or a resource created by hand
  outside Terraform, silently removes the boundary. The organization CloudTrail in this task is
  what makes such a change auditable after the fact.
- Blast radius is wider than the spec's primary path: a mistake in this account can affect the
  unrelated projects already running in it, and their mistakes can affect debate evidence.
  S3 versioning ([ADR-0003](0003-s3-source-of-truth-for-raw-artifacts.md)) and the noncurrent-version
  lifecycle in t03 are the recovery path.
- Budgets and Cost Anomaly Detection must filter on the `Project` tag to be meaningful, which
  requires the operator to activate `Project` and `Environment` as cost allocation tags in
  Billing — a manual step, recorded in the runbook, that no Terraform can do.
- Pinning us-east-1 accepts the region's larger share of AWS service events. For V1 the system is
  a CLI plus a bucket, so an outage delays work rather than taking a service down; V2 should
  revisit multi-region posture when the API and web app carry real traffic.
- Using cross-region inference profiles means a Bedrock call may be served from another US region.
  That is a data-residency fact worth stating before any student-identifying text is ever sent to
  a model ([§14](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety));
  V1 sends source article text and card selections only.

## Alternatives considered

**us-west-2 as the primary region.** Equally complete on models, identical on price, and usually
the first region to receive new Bedrock capacity — a real argument for a model-heavy product. It
lost because it would split this project from the operator's existing us-east-1 footprint, and
the default-region mistakes that causes (a bucket or trail created in the wrong region by an
unset `AWS_REGION`) are exactly the kind of thing this baseline exists to prevent. If Bedrock
capacity in us-east-1 becomes a practical constraint, a successor ADR moves the model calls to
us-west-2 while leaving the evidence buckets where they are; the ModelRouter makes that a
configuration change.

**us-east-2.** Ruled out on availability, not preference: no Cohere Rerank 3.5 and no alternative
reranker, which would force cross-region reranking on every search.

**Separate dev and prod member accounts (the spec's primary path).** The stronger design, and
what the revisit trigger above returns to. An account boundary cannot be undone by an IAM
mistake, keeps student data away from unrelated personal projects, and makes per-environment
spend unambiguous. Not chosen now because the product owner did not want to run multi-account
billing, root-user lockdown and guardrails three times over for a single-maintainer project at
v1.1 scale.

**Control Tower or an account factory.** Would deliver the multi-account baseline with guardrails
already wired. Rejected as disproportionate: it adds a standing monthly cost and a large set of
managed resources to an Organization that would hold three accounts.

## References

- [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture),
  [§10 LLM and Retrieval Model Strategy](../architecture/architecture_proposal.md#10-llm-and-retrieval-model-strategy)
- [ADR-0003: S3 as the source of truth for raw source snapshots and files](0003-s3-source-of-truth-for-raw-artifacts.md)
- [ADR-0004: OpenSearch is a derived index, not an authoritative store](0004-opensearch-is-derived-not-authoritative.md)
- [ADR-0005: Amazon Bedrock accessed through a ModelRouter abstraction](0005-bedrock-behind-model-router.md)
- [ADR-0013: Two environments (dev, prod) and dev→main promotion](0013-two-environments-and-dev-main-promotion.md) — unchanged by this record
- [`plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml)
- [docs/runbooks/aws-account-baseline.md](../runbooks/aws-account-baseline.md) — how the baseline is reproduced
