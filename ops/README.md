# ops/

Things the operator installs on their own machine, as opposed to infrastructure Terraform applies
(`infrastructure/`) or documentation that describes a procedure (`docs/runbooks/`).

| Directory | What |
|---|---|
| [`launchd/`](launchd/) | The weekly caselist-sync agent: plist template, wrapper and installer (`v1-e34-t02-scheduled-sync`). Its procedure is [`docs/runbooks/caselist-scheduled-sync.md`](../docs/runbooks/caselist-scheduled-sync.md) |
| [`caselist_run/`](caselist_run/) | The weekly cloud run's image: its Dockerfile and the offline check of a built image (`v1-e40-t03-run-image-and-schedule`). `scripts/caselist_run_deploy.sh` builds, checks and pushes it; its procedure is [`docs/runbooks/caselist-cloud-run.md`](../docs/runbooks/caselist-cloud-run.md) |

Nothing here is enabled by installing the repository, and nothing here holds a caselist slug, a
home directory or an AWS account: those are filled in by an installer, on the machine it runs on.
