# Documentation index

| Where | What |
|---|---|
| [architecture/architecture_proposal.md](architecture/architecture_proposal.md) | V1–V3 system architecture proposal |
| [architecture/ports-and-adapters.md](architecture/ports-and-adapters.md) | The ten ports, the constructor-injection pattern, and how to add an adapter |
| [architecture/cardmirror-evaluation.md](architecture/cardmirror-evaluation.md) | CardMirror schema, API, license and round-trip evidence behind ADR-0014 |
| [architecture/cardmirror-upstream-issues.md](architecture/cardmirror-upstream-issues.md) | CardMirror defects found during the evaluation, drafted for upstream and not filed |
| [adr/](adr/README.md) | Architecture decision records |
| [process/working-agreements.md](process/working-agreements.md) | Project rules: light CI, operator hand-off for long commands, doc locations, naming |
| [process/branching-and-environments.md](process/branching-and-environments.md) | `main` = prod, `dev` = development; promotion rules |
| [process/task-workflow.md](process/task-workflow.md) | `scripts/task`: start → session → PM review → PR → finish |
| [process/session-report-template.md](process/session-report-template.md) | Template for session reports |
| [policies/caselist-data-use.md](policies/caselist-data-use.md) | Data-use policy for OpenCaselist disclosures and OpenEv camp files |
| [policies/website-publishing.md](policies/website-publishing.md) | What may be published on the public team website: student names and photos, results, branding, accessibility, third parties, donations, removal on request |
| [runbooks/aws-account-baseline.md](runbooks/aws-account-baseline.md) | Building and verifying the AWS account baseline: identity, audit, budgets |
| [runbooks/terraform-bootstrap.md](runbooks/terraform-bootstrap.md) | Creating the Terraform state buckets and the dev/prod environment roots |
| [runbooks/caselist-removal.md](runbooks/caselist-removal.md) | Removing a caselist or OpenEv source on request |
| [runbooks/team-website.md](runbooks/team-website.md) | Standing up the team website's hosting, domains and publisher credentials |
| [session-reports/](session-reports/README.md) | One report per completed task |
| [runbooks/](runbooks/) | Operational procedures run by the operator |
| [../plan_specs/README.md](../plan_specs/README.md) | PlanSpec conventions |
| [../ROADMAP.md](../ROADMAP.md) | Releases, epics and tasks with status |

`policies/` and `runbooks/` were added by the caselist data-use policy task and will grow with
the epics that need them. Directories still to come as they are needed: `guides/` (student and
coach guides) and `data/` (data models, access patterns, and recorded results of operator-run data
jobs such as the caselist backfill and the removal register). See the directory table in
[working-agreements.md](process/working-agreements.md#3-documentation-lives-in-predictable-places).
