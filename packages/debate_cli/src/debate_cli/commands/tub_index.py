"""`debate-research tub index build | publish`: the student search pilot's index (`v1-e39-t02`).

::

    debate-research tub index build --caselist hsld26 --caselist hspf26 --caselist openev
    debate-research tub index build --caselist hsld26 --out ~/tub-index --provenance-limit 5
    DEBATE_ENV=dev debate-research tub index publish --env dev --index <data_dir>/tub-index/<index id>
    DEBATE_ENV=dev debate-research tub index publish --env dev --newest
    DEBATE_ENV=prod debate-research tub index publish --env prod --index <dir> --confirm-prod

`build` reads this machine's parsed store, caselist records and suppression list, and writes one
directory, `<out>/<index id>/`: the SQLite FTS5 file, its gzip object and `manifest.json`. It reads
no bucket and calls no model. `--out` defaults to `<data_dir>/tub-index`, outside every prefix
`store sync` moves, so an index reaches a bucket only through `publish`.

`publish` uploads one built directory to this environment's evidence bucket under
`reports/tub/search/<index id>/` and writes `reports/tub/search/current.json` last. It refuses an
index built under another parser or fingerprint version than this build's, and, by the shrink guard
the weekly stage meets too (`v1-e39-t14`), an index built from a store whose aggregates hold no rows,
or one holding fewer of a store's documents than `caselist.search_index_minimum_share_percent` of
the published index's (90%), or none. `--allow-shrink "<reason>"` publishes a real shrink, such as a
removal; the reason is printed, logged and in the `--json` result, never in the manifest. `--newest` names the
directory instead of `--index`: the newest under `<data_dir>/tub-index`, by the rule the weekly run's
search index stage keeps current
(:func:`~debate_core.application.search_index_refresh.newest_local_index`, `v1-e39-t09`). One of the
two is required, and both together are refused.

Every decision is :class:`~debate_core.application.search_index_build.SearchIndexBuildService`'s and
:class:`~debate_core.application.search_index_publish.SearchIndexPublishService`'s; this is the surface.

## Which bucket

`DEBATE_ENV` names the bucket, as for every command that writes one, and no flag overrides it.
`--env` is a confirmation: it must name the environment `DEBATE_ENV` selected, so a publish typed
for dev never lands in prod because of what the shell happened to export. Writing to prod needs
`--confirm-prod` as well, as `caselist publish` does.

## What it prints

Counts, versions, digests and keys. No school, team code, tournament, round, path or card text: the
manifest holds none, and nothing here reads the index's rows.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from debate_cli.commands.caselist import event_for_caselist
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.search_index_build import (
    BuiltSearchIndex,
    not_cards_by_store,
    not_cards_sentence,
)
from debate_core.application.search_index_publish import (
    ALLOW_SHRINK_FLAG,
    SHRINK_REASON_MAX_LENGTH,
    PublishedSearchIndex,
)
from debate_core.application.search_index_refresh import SEARCH_INDEX_DIRECTORY, newest_local_index
from debate_core.application.settings import Environment, Settings
from debate_core.domain.search_index import DEFAULT_PROVENANCE_LIMIT

__all__ = ["DEFAULT_OUT_DIRECTORY", "build", "build_summary", "publish", "publish_summary"]

DEFAULT_OUT_DIRECTORY = SEARCH_INDEX_DIRECTORY
"""Where `build` writes when `--out` is not given: `<data_dir>/tub-index`, where the weekly run's
search index stage builds too (`v1-e39-t09`), so `publish --index` finds what either built."""

CONFIRM_PROD_FLAG = "--confirm-prod"
NEWEST_FLAG = "--newest"

_PUBLISHABLE = (Environment.DEV, Environment.PROD)


def build(
    ctx: typer.Context,
    caselists: Annotated[
        list[str],
        typer.Option(
            "--caselist",
            help="A store to index: a caselist slug such as hsld26, or openev for camp files. Repeatable.",
        ),
    ],
    out: Annotated[
        Path | None,
        typer.Option(
            "--out", file_okay=False, help="Where to write <index id>/. Default: <data_dir>/tub-index."
        ),
    ] = None,
    provenance_limit: Annotated[
        int,
        typer.Option(
            "--provenance-limit", min=1, help="How many occurrences of a card keep who disclosed them."
        ),
    ] = DEFAULT_PROVENANCE_LIMIT,
) -> None:
    """Build the search pilot's index from this machine's parsed store."""
    cli = cli_context(ctx)
    service = cli.services.search_index_build(event_for_caselist=event_for_caselist)
    target = out if out is not None else cli.services.settings.storage.data_dir / DEFAULT_OUT_DIRECTORY
    cli.output.detail(f"indexing {', '.join(sorted(set(caselists)))} into {target}")
    built = asyncio.run(service.build(caselists, target, provenance_limit=provenance_limit))
    cli.output.success(command_name(ctx), build_summary(built), display=_build_table(built))


def publish(
    ctx: typer.Context,
    env: Annotated[
        Environment,
        typer.Option("--env", help="dev or prod: must be the environment DEBATE_ENV selects."),
    ],
    index: Annotated[
        Path | None,
        typer.Option("--index", exists=True, file_okay=False, help="A directory `tub index build` wrote."),
    ] = None,
    newest: Annotated[
        bool,
        typer.Option(
            NEWEST_FLAG,
            help="The newest index under <data_dir>/tub-index, by the weekly stage's rule. Not with --index.",
        ),
    ] = False,
    confirm_prod: Annotated[
        bool,
        typer.Option(CONFIRM_PROD_FLAG, help="Required to write to the production evidence bucket."),
    ] = False,
    allow_shrink: Annotated[
        str | None,
        typer.Option(
            ALLOW_SHRINK_FLAG,
            metavar="REASON",
            help=(
                "Publish an index the shrink guard refuses, for a real shrink such as a removal: why, "
                "in one line (a request id; no card text or names). Printed and logged, not stored."
            ),
        ),
    ] = None,
) -> None:
    """Publish a built index to this environment's bucket, its pointer last."""
    if allow_shrink is not None and not _one_line(allow_shrink):
        raise typer.BadParameter(
            f"say why in one line of 1 to {SHRINK_REASON_MAX_LENGTH} characters, "
            "such as a removal's request id",
            param_hint=ALLOW_SHRINK_FLAG,
        )
    if newest and index is not None:
        raise typer.BadParameter(
            f"{NEWEST_FLAG} picks the directory --index names; pass one or the other", param_hint=NEWEST_FLAG
        )
    if not newest and index is None:
        raise typer.BadParameter(f"name the index with --index, or pass {NEWEST_FLAG}", param_hint="--index")
    cli = cli_context(ctx)
    _refuse(cli, ctx, _not_this_environment(cli.services.settings, env, confirmed=confirm_prod))
    if index is None:
        index = _newest_built(cli, ctx)
    service = cli.services.search_index_publish()
    cli.output.detail(f"publishing {index.name} to {cli.services.settings.storage.s3.bucket}")
    published = asyncio.run(service.publish(index, allow_shrink=allow_shrink))
    if published.allowed_shrink is not None:
        cli.output.note(f"published past the shrink guard with {ALLOW_SHRINK_FLAG}: {_allowed(published)}")
    cli.output.success(command_name(ctx), publish_summary(published), display=_publish_table(published))


def build_summary(built: BuiltSearchIndex) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `build`: the manifest, where the directory is, and what was left
    out as no card by store and why (`v1-e39-t12`), which the manifest does not hold."""
    return {
        "directory": str(built.directory),
        "manifest": built.manifest.model_dump(mode="json"),
        "not_cards_by_store": not_cards_by_store(built.not_cards),
    }


def publish_summary(published: PublishedSearchIndex) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `publish`: the keys written, in order, the pointer, the index
    it replaced, and what `--allow-shrink` let through (`v1-e39-t14`), `null` when it was not needed."""
    allowed = published.allowed_shrink
    return {
        "index_id": published.index_id,
        "written": [published.object_key, published.manifest_key, published.pointer_key],
        "pointer": published.pointer.model_dump(mode="json"),
        "replaced": published.replaced,
        "allowed_shrink": None
        if allowed is None
        else {
            "reason": allowed.reason,
            "stores": [
                {"store": one.store, "documents": one.documents, "current_documents": one.current_documents}
                for one in allowed.shrinks
            ],
            "current_unreadable": allowed.current_unreadable,
        },
    }


def _one_line(reason: str) -> bool:
    stripped = reason.strip()
    return (
        bool(stripped)
        and "\n" not in stripped
        and "\r" not in stripped
        and len(stripped) <= SHRINK_REASON_MAX_LENGTH
    )


def _allowed(published: PublishedSearchIndex) -> str:
    """What `--allow-shrink` let through, and why, as the detail line and the table's caption say it."""
    allowed = published.allowed_shrink
    assert allowed is not None
    passed = (
        "; ".join(one.sentence for one in allowed.shrinks)
        if allowed.shrinks
        else allowed.current_unreadable or "nothing"
    )
    return f"{passed} in index {published.replaced or 'none'}; reason: {allowed.reason}"


def _not_this_environment(settings: Settings, env: Environment, *, confirmed: bool) -> CommandFailure | None:
    running = settings.environment
    if env not in _PUBLISHABLE:
        return CommandFailure(
            code="ENVIRONMENT_NOT_SYNCABLE",
            message=f"`tub index publish` writes to dev or prod, not {env.value}",
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


def _newest_built(cli: CliContext, ctx: typer.Context) -> Path:
    """The directory `--newest` names, or the command refused for want of one."""
    out = cli.services.settings.storage.data_dir / DEFAULT_OUT_DIRECTORY
    found = newest_local_index(out)
    if found is None:
        _refuse(
            cli,
            ctx,
            CommandFailure(
                code="NO_BUILT_SEARCH_INDEX",
                message=f"no built search index under {out}",
                exit_code=ExitCode.DOMAIN_FAILURE,
                details={"directory": str(out)},
                hint="Build one with `debate-research tub index build`, or let the weekly run build it.",
            ),
        )
        raise AssertionError("unreachable")  # pragma: no cover - _refuse exits
    cli.output.detail(f"the newest index under {out} is {found.directory.name}")
    return found.directory


def _refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


def _build_table(built: BuiltSearchIndex) -> TableSpec:
    manifest = built.manifest
    counts = manifest.counts
    rows = [[name, str(documents)] for name, documents in sorted(counts.documents_by_store.items())]
    return TableSpec(
        columns=["Store", "Documents"],
        rows=rows,
        title=f"Search index {manifest.index_id}: {counts.documents} documents",
        caption=(
            f"{counts.occurrences} occurrences of {counts.occurrence_rows_read} rows read; "
            f"{counts.suppressed_occurrences} suppressed, {counts.clusters_left_out} clusters left out, "
            f"{not_cards_sentence(built.not_cards)}. "
            f"SQLite file {manifest.sqlite_file.bytes:,} bytes, "
            f"gzip object {manifest.gzip_object.bytes:,} bytes. "
            f"Parser {manifest.parser_version}, {manifest.fingerprint_version}, "
            f"SQLite {manifest.sqlite_version}."
        ),
    )


def _publish_table(published: PublishedSearchIndex) -> TableSpec:
    return TableSpec(
        columns=["Written", "Key"],
        rows=[
            ["1", published.object_key],
            ["2", published.manifest_key],
            ["3", published.pointer_key],
        ],
        title=f"Search index {published.index_id} published",
        caption=(
            f"current.json names {published.index_id}; object sha256 {published.pointer.object_sha256[:12]}."
            + (
                f" Past the shrink guard with {ALLOW_SHRINK_FLAG}: {_allowed(published)}."
                if published.allowed_shrink is not None
                else ""
            )
        ),
    )
