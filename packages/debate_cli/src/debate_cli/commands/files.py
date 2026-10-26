"""`debate-research files`: build an evidence file from a recipe, check it, suggest a draft, publish it.

::

    debate-research files build ~/.debate-research/dev/files/recipes/nhi/politics-da-answers.yaml
    debate-research files build <recipe> --out ~/e33-files --allow-draft
    debate-research files check ~/.debate-research/dev/files/built/nhi/politics-da-answers.docx
    debate-research files suggest --caselist hspolicy26 --position politics-da --top 10
    DEBATE_ENV=dev debate-research files publish --env dev ~/.debate-research/dev/files/built/nhi --dry-run
    DEBATE_ENV=prod debate-research files publish --env prod <built.docx> --confirm-prod

Every decision is the services' (`v1-e33-t03`): :class:`~debate_core.application.file_build_service.
FileBuildService` for `build` and `check`, which runs the
:class:`~debate_core.application.file_quality_service.FileQualityService` the container wires
(`v1-e33-t04`), :class:`~debate_core.application.file_suggest_service.FileSuggestService` for
`suggest`, and :class:`~debate_core.application.file_publish_service.FilePublishService` for `publish`
(`v1-e33-t05`). This module parses the options and :mod:`debate_cli.presenters.files_presenter` renders;
the exit codes are documented there and in each command's `--help`.

Only `publish` reaches a bucket, and nothing reaches a model. Built files and their sidecars hold card
text and who disclosed each card, so neither a built file nor a draft is ever written inside a git
working tree.

## `publish`: which bucket

As for `tub index publish`, `DEBATE_ENV` names the bucket and no flag overrides it: `--env` must name
the environment `DEBATE_ENV` selected, and writing to prod needs `--confirm-prod` as well. In bucket
mode a publish holds the bucket's run lock while it writes (ADR-0020 (4)); `--dry-run` takes nothing,
builds no bucket client, and lists the keys each file would be written to.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from debate_cli.bucket_lock import run_holding_the_bucket_lock
from debate_cli.commands.caselist import _snapshot_date  # pyright: ignore[reportPrivateUsage]
from debate_cli.commands.landscape import _config_dir  # pyright: ignore[reportPrivateUsage]
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CliOutput, CommandFailure, OutputMode
from debate_cli.presenters.files_presenter import (
    Rendered,
    build_rendered,
    check_rendered,
    publish_rendered,
    refused_request,
    suggest_rendered,
    unattributed_lines,
)
from debate_core.application.file_build_service import BuildFileRequest, UnattributedCard
from debate_core.application.file_publish_service import PublishRequest, built_files_in
from debate_core.application.file_suggest_service import SuggestRefused, SuggestRequest
from debate_core.application.landscape_run import LandscapeRequestRefused
from debate_core.application.settings import Environment, Settings
from debate_core.domain.caselist import Side

__all__ = ["BUILD_HELP", "CHECK_HELP", "PUBLISH_HELP", "SUGGEST_HELP", "build", "check", "publish", "suggest"]

CONFIRM_PROD_FLAG = "--confirm-prod"

_PUBLISHABLE = (Environment.DEV, Environment.PROD)

_JSON_HELP = "Write one machine-readable JSON object to stdout."

BUILD_HELP = (
    "Build an evidence file from a recipe: <name>.docx, its .provenance.json, and its quality report.\n\n"
    "Exit 0: built, and every quality check passed or only warned.\n\n"
    "Exit 1: the recipe does not load or resolve (every error listed), the parsed store was made by "
    "another parser or fingerprint version, a source is missing (with the `store get` that fetches it), "
    "the writer refuses a card, or a quality check FAILs (the files are kept).\n\n"
    "Exit 2: a draft without --allow-draft, or an --out inside a git working tree."
)
"""`files build --help`; its docstring is set to it, so Rich wraps each paragraph whole."""

CHECK_HELP = (
    "Check a built evidence file and write its .quality.json and .quality.md beside it, building "
    "nothing.\n\n"
    "Exit 0: every check passed or only warned. Exit 1: a check FAILs, named, with what explains it "
    "when that is known."
)

SUGGEST_HELP = (
    "Write a draft recipe from the landscape's most-read cards for a position: status draft, no tags, "
    "and no model called.\n\n"
    "Exit 0: the draft is written. Exit 1: the landscape report cannot be built.\n\n"
    "Exit 2: a caselist, snapshot, position or side the landscape does not have, or a draft path "
    "that is taken or inside a git working tree."
)

PUBLISH_HELP = (
    "Publish built evidence files that PASS their quality checks to this environment's evidence bucket, "
    "under files/<topic>/<side>/<position>/<slug>/<recipe hash>/.\n\n"
    "PATH is a built .docx, or a directory of them, each with its .provenance.json and .quality.json "
    "beside it. A file whose report is missing, for other bytes, or FAIL, or that was built from a draft "
    "recipe, is refused and nothing of it is uploaded; a warning never blocks.\n\n"
    "Exit 0: every file PUBLISHED, SKIPPED (already in the bucket, byte for byte), or, with --dry-run, "
    "WOULD_PUBLISH.\n\n"
    "Exit 1: a file was REFUSED, named with its failing checks; an object did not land as sent; or "
    "--env is not the environment DEBATE_ENV selects, or is prod without --confirm-prod."
)


def build(
    ctx: typer.Context,
    recipe: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="The recipe's YAML file (v1-e33-t01).")
    ],
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            file_okay=False,
            help="Write here. Default: <data dir>/files/built/<topic>/. Never inside a git working tree.",
        ),
    ] = None,
    allow_draft: Annotated[
        bool, typer.Option("--allow-draft", help="Build a status: draft recipe; its header will say DRAFT.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help=_JSON_HELP)] = False,
) -> None:
    cli = _context(ctx, json_output)
    service = cli.services.file_build()
    result = asyncio.run(
        service.build(
            BuildFileRequest(recipe, out_dir=out, allow_draft=allow_draft),
            on_unattributed=lambda cards: _note_unattributed(cli, cards),
        )
    )
    _report(cli, ctx, build_rendered(result))


def check(
    ctx: typer.Context,
    file: Annotated[
        Path,
        typer.Argument(
            exists=True, dir_okay=False, help="A built .docx, with its .provenance.json beside it."
        ),
    ],
    json_output: Annotated[bool, typer.Option("--json", help=_JSON_HELP)] = False,
) -> None:
    cli = _context(ctx, json_output)
    result = asyncio.run(cli.services.file_build().check(file))
    _report(cli, ctx, check_rendered(result))


def suggest(
    ctx: typer.Context,
    caselist: Annotated[str, typer.Option("--caselist", help="Caselist slug, e.g. hspolicy26.")],
    position: Annotated[str, typer.Option("--position", help="Position id, as the landscape names it.")],
    side: Annotated[
        Side | None,
        typer.Option("--side", case_sensitive=False, help="The file's side. Default: the position's."),
    ] = None,
    snapshot: Annotated[
        str | None, typer.Option("--snapshot", help="The weekly snapshot, YYYY-MM-DD. Default: the newest.")
    ] = None,
    top: Annotated[int, typer.Option("--top", min=1, help="How many of the most-read cards to draft.")] = 10,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            dir_okay=False,
            help=(
                "Where to write the draft. "
                "Default: <data dir>/files/recipes/<topic>/<position>-<side>-draft.yaml."
            ),
        ),
    ] = None,
    config_dir: Annotated[
        Path | None,
        typer.Option(
            "--config-dir",
            file_okay=False,
            help="The directory holding topics.yaml. Default: config/landscape in this checkout.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help=_JSON_HELP)] = False,
) -> None:
    cli = _context(ctx, json_output)
    request = SuggestRequest(
        caselist=caselist, position=position, side=side, snapshot=_day(snapshot), top=top, out=out
    )
    service = cli.services.file_suggest(config_dir=_config_dir(config_dir))
    try:
        result = asyncio.run(service.suggest(request))
    except (SuggestRefused, LandscapeRequestRefused) as refused:
        _end(cli, ctx, refused_request(refused, known=refused.known, hint=_hint_of(refused)))
    _report(cli, ctx, suggest_rendered(result))


def publish(
    ctx: typer.Context,
    path: Annotated[
        Path,
        typer.Argument(exists=True, help="A built .docx, or a directory of them (not its subdirectories)."),
    ],
    env: Annotated[
        Environment,
        typer.Option("--env", help="dev or prod: must be the environment DEBATE_ENV selects."),
    ],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Check each file and list its keys; write nothing, call no S3.")
    ] = False,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required to write to the production evidence bucket.")
    ] = False,
    recipes: Annotated[
        Path | None,
        typer.Option(
            "--recipes",
            exists=True,
            file_okay=False,
            help="Where the recipes are, <dir>/<name>.yaml. Default: <data dir>/files/recipes/<topic>/.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help=_JSON_HELP)] = False,
) -> None:
    cli = _context(ctx, json_output)
    settings = cli.services.settings
    refusal = _not_this_environment(settings, env, confirmed=confirm_prod or dry_run)
    if refusal is None and not built_files_in(path):
        refusal = CommandFailure(
            code="NO_BUILT_FILES",
            message=f"no built .docx in {path}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"path": str(path)},
            hint="Build one with `debate-research files build <recipe>`.",
        )
    if refusal is not None:
        _end(cli, ctx, refusal)
    bucket = str(settings.storage.s3.bucket)
    request = PublishRequest(path, recipes_dir=recipes, dry_run=dry_run)
    service = cli.services.file_publish()
    if dry_run:
        cli.output.detail(
            f"dry run: checking {path} against the {env.value} bucket {bucket}; nothing is written"
        )
        result = asyncio.run(service.run(request))
    else:
        cli.output.detail(f"publishing {path} to the {env.value} bucket {bucket}")
        result = run_holding_the_bucket_lock(cli, "files publish", lambda: service.run(request))
    _report(cli, ctx, publish_rendered(result, environment=env.value, bucket=bucket))


build.__doc__ = BUILD_HELP
check.__doc__ = CHECK_HELP
suggest.__doc__ = SUGGEST_HELP
publish.__doc__ = PUBLISH_HELP


def _context(ctx: typer.Context, json_output: bool) -> CliContext:
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    return cli


def _not_this_environment(settings: Settings, env: Environment, *, confirmed: bool) -> CommandFailure | None:
    """Why `files publish` will not write to `env`'s bucket, or None: as `tub index publish` refuses."""
    running = settings.environment
    if env not in _PUBLISHABLE:
        return CommandFailure(
            code="ENVIRONMENT_NOT_SYNCABLE",
            message=f"`files publish` writes to dev or prod, not {env.value}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": env.value},
        )
    if env is not running:
        return CommandFailure(
            code="ENVIRONMENT_MISMATCH",
            message=f"--env {env.value} names another environment than DEBATE_ENV selects ({running.value})",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"requested": env.value, "environment": running.value},
            hint=f"Run it with DEBATE_ENV={env.value}, or with --env {running.value}.",
        )
    if not settings.storage.s3.bucket:
        return CommandFailure(
            code="EVIDENCE_STORE_NOT_CONFIGURED",
            message=f"the {running.value} environment names no evidence bucket",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": running.value},
            hint="Set storage.s3.bucket for this environment (config/profiles/<env>.toml).",
        )
    if running is Environment.PROD and not confirmed:
        return CommandFailure(
            code="CONFIRMATION_REQUIRED",
            message=(
                "refusing to publish to the production evidence bucket without "
                f"{CONFIRM_PROD_FLAG}: {settings.storage.s3.bucket}"
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": running.value, "bucket": settings.storage.s3.bucket},
            hint=f"Publish to dev first, then run it again with {CONFIRM_PROD_FLAG}.",
        )
    return None


def _day(snapshot: str | None) -> date | None:
    return _snapshot_date(snapshot) if snapshot is not None else None


def _hint_of(refused: Exception) -> str | None:
    hint = getattr(refused, "hint", None)
    if isinstance(hint, str):
        return hint
    edit = getattr(refused, "file_to_edit", None)
    return f"Edit {edit}." if isinstance(edit, str) else None


def _note_unattributed(cli: CliContext, cards: Sequence[UnattributedCard]) -> None:
    for line in unattributed_lines(cards):
        cli.output.note(line)


def _report(cli: CliContext, ctx: typer.Context, rendered: Rendered) -> None:
    """The result, then, for an outcome that failed, its failure and its exit code."""
    if rendered.failure is None or not cli.output.is_json:
        cli.output.success(command_name(ctx), rendered.payload, display=rendered.display)
    if rendered.failure is not None:
        _end(cli, ctx, rendered.failure)


def _end(cli: CliContext, ctx: typer.Context, failure: CommandFailure) -> NoReturn:
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)
