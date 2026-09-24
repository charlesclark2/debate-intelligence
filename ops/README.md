# ops/

Things the operator installs on their own machine, as opposed to infrastructure Terraform applies
(`infrastructure/`) or documentation that describes a procedure (`docs/runbooks/`).

| Directory | What |
|---|---|
| [`launchd/`](launchd/) | The weekly caselist-sync agent: plist template, wrapper and installer (`v1-e34-t02-scheduled-sync`). Its procedure is [`docs/runbooks/caselist-scheduled-sync.md`](../docs/runbooks/caselist-scheduled-sync.md) |

Nothing here is enabled by installing the repository, and nothing here holds a caselist slug, a
home directory or an AWS account: those are filled in by an installer, on the machine it runs on.
