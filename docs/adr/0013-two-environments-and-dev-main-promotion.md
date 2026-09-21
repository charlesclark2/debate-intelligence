# ADR-0013: Two environments (dev, prod) and dev→main promotion

- Status: Accepted
- Date: 2026-09-17
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§4 Technology Stack](../architecture/architecture_proposal.md#4-technology-stack)
  - [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
  - [§17 Deployment and Evolution Plan](../architecture/architecture_proposal.md#17-deployment-and-evolution-plan)

## Context

The architecture proposal plans three environments: the Terraform row in
[§4](../architecture/architecture_proposal.md#4-technology-stack) promises "repeatable
dev/stage/prod environments", and the AWS services in
[§5](../architecture/architecture_proposal.md#5-aws-cloud-architecture) would be stood up
once per environment. For a team of one product owner plus AI assistance, a separate
`stage` environment would double the pre-production cost (AWS accounts, Cognito pools,
domains, model spend) and add another promotion hop without catching problems that a
properly gated dev environment cannot.

What does need to hold is that nothing reaches the team before it has run somewhere real.
The branching model, the environment table and the promotion gates are written up in
[docs/process/branching-and-environments.md](../process/branching-and-environments.md),
which is the authoritative, operational version of this decision.

## Decision

There are exactly two environments, **dev** and **prod**, each tied to a long-lived branch:

- `main` is production. `dev` is the development environment and the GitHub default branch.
- Task branches merge into `dev`; `dev` is promoted to `main` through a promotion PR. Hotfixes
  branch from `main`, are still deployed to and validated in dev, and are back-merged into `dev`.
- A promotion can merge only after the `dev` head has been deployed to dev and passed the
  gates listed in the process doc ("validated in dev").
- The same split applies to V1 (pre-release vs stable CLI builds) and to V2+ AWS (separate
  dev and prod accounts/state, identity pools and domains).

The `stage` environment in §4 (and the per-environment AWS footprint implied by §5) is
**superseded**: dev is the pre-production validation environment. The proposal text is not
edited; this ADR records the change.

The branch rules, merge methods, environment table, GitHub rulesets and release tagging are
not restated here; see
[docs/process/branching-and-environments.md](../process/branching-and-environments.md).

## Consequences

- One pre-production environment to pay for, secure and keep in sync instead of two.
- Dev carries the full validation burden. The automated `validate-dev` smoke suite and the
  promotion checklist must keep growing with each release, since no later environment will
  catch what they miss.
- Dev never holds real student data (synthetic and scrubbed fixtures only), so
  prod-scale load and disaster-recovery exercises have to run in dev against seeded
  synthetic data.
- Task specs that mention environments (AWS account baseline, Terraform bootstrap, OIDC deploy,
  Cognito pools, app hosting, promotion pipeline, load testing, backups/DR) plan for dev and
  prod only, and cite this ADR.
- Using merge commits for `dev`→`main` promotions keeps the two branches on a shared history.
  In exchange, `main` does not have linear history.

## Alternatives considered

- **Three environments (dev, stage, prod) as in the proposal.** Rejected for now. It adds cost
  and an extra promotion hop, and at this team size stage would be dev with a delay. It can
  be reintroduced by a superseding ADR if the user base or compliance needs justify it.
- **Single environment with trunk-based deploys to prod.** Rejected. Students (who may be
  minors, §14) would see changes before they had run anywhere real, which conflicts with the
  "validated in dev" rule.
- **Ephemeral per-PR preview environments instead of a standing dev.** Not seriously
  considered for V1, since the CLI has no hosted surface. It could complement dev in V2+ web work
  but does not replace a stable integration environment.

## References

- [docs/process/branching-and-environments.md](../process/branching-and-environments.md)
  (authoritative workflow).
- [§4 Technology Stack](../architecture/architecture_proposal.md#4-technology-stack): the
  `dev/stage/prod` Terraform row this ADR supersedes.
- [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
- [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)
- [§17 Deployment and Evolution Plan](../architecture/architecture_proposal.md#17-deployment-and-evolution-plan)
- [ADR-0009: Async job architecture](0009-async-job-architecture.md): the V2 AWS services
  deployed once per environment.
