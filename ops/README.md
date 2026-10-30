# ops/

Things the operator installs on their own machine, as opposed to infrastructure Terraform applies
(`infrastructure/`) or documentation that describes a procedure (`docs/runbooks/`).

| Directory | What |
|---|---|
| [`launchd/`](launchd/) | The weekly caselist-sync agent: plist template, wrapper and installer (`v1-e34-t02-scheduled-sync`). Its procedure is [`docs/runbooks/caselist-scheduled-sync.md`](../docs/runbooks/caselist-scheduled-sync.md). Unloaded at the cutover (`v1-e40-t06`) and kept for a fallback week |
| [`caselist_run/`](caselist_run/) | The weekly cloud run's image: its Dockerfile and the offline check of a built image (`v1-e40-t03-run-image-and-schedule`). `scripts/caselist_run_deploy.sh` builds, checks and pushes it; its procedure is [`docs/runbooks/caselist-cloud-run.md`](../docs/runbooks/caselist-cloud-run.md). Also the cutover's comparison of a cloud run with the Mac's offline reproduction of it, `compare_cloud_run.py` (`v1-e40-t06`), run as [`docs/runbooks/caselist-cutover.md`](../docs/runbooks/caselist-cutover.md) step 7 says. And `start_backfile_import.py` (`v1-e40-t09`), which starts one backfile import by hand on the run's task definition, never scheduled: [`caselist-cloud-run.md`, "Backfile imports"](../docs/runbooks/caselist-cloud-run.md#backfile-imports). And `check_image_plan.py` (`v1-e40-t15`), which checks a new image's saved plan as JSON before the PM reads it: [`caselist-cloud-run.md`, "A new image, later"](../docs/runbooks/caselist-cloud-run.md#a-new-image-later) |

Nothing here is enabled by installing the repository, and nothing here holds a home directory or an
AWS account: those are filled in by an installer, on the machine it runs on. Nor a caselist slug:
the weekly run's caselists are `caselist.sync_caselists` in the environment's profile
(`config/profiles/`, ADR-0020 (5)).
