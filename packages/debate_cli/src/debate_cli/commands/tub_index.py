"""`debate-research tub index build | publish`: the student search pilot's index (`v1-e39-t02`).

::

    debate-research tub index build --caselist hsld26 --caselist hspf26 --caselist openev
    debate-research tub index build --caselist hsld26 --out ~/tub-index --provenance-limit 5
    DEBATE_ENV=dev debate-research tub index publish --env dev --index <data_dir>/tub-index/<index id>
    DEBATE_ENV=prod debate-research tub index publish --env prod --index <dir> --confirm-prod

`build` reads this machine's parsed store, caselist records and suppression list, and writes one
directory, `<out>/<index id>/`: the SQLite FTS5 file, its gzip object and `manifest.json`. It reads
no bucket and calls no model. `--out` defaults to `<data_dir>/tub-index`, outside every prefix
`store sync` moves, so an index reaches a bucket only through `publish`.

`publish` uploads one built directory to this environment's evidence bucket under
`reports/tub/search/<index id>/` and writes `reports/tub/search/current.json` last. It refuses an
index built under another parser or fingerprint version than this build's.

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
from debate_core.application.search_index_build import BuiltSearchIndex
from debate_core.application.search_index_publish import PublishedSearchIndex
from debate_core.application.search_index_refresh import SEARCH_INDEX_DIRECTORY
from debate_core.application.settings import Environment, Settings
from debate_core.domain.search_index import DEFAULT_PROVENANCE_LIMIT, SearchIndexManifest

__all__ = ["DEFAULT_OUT_DIRECTORY", "build", "build_summary", "publish", "publish_summary"]

DEFAULT_OUT_DIRECTORY = SEARCH_INDEX_DIRECTORY
"""Where `build` writes when `--out` is not given: `<data_dir>/tub-index`, where the weekly run's
search index stage builds too (`v1-e39-t09`), so `publish --index` finds what either built."""

CONFIRM_PROD_FLAG = "--confirm-prod"

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
    cli.output.success(command_name(ctx), build_summary(built), display=_build_table(built.manifest))


def publish(
    ctx: typer.Context,
    index: Annotated[
        Path,
        typer.Option("--index", exists=True, file_okay=False, help="A directory `tub index build` wrote."),
    ],
    env: Annotated[
        Environment,
        typer.Option("--env", help="dev or prod: must be the environment DEBATE_ENV selects."),
    ],
    confirm_prod: Annotated[
        bool,
        typer.Option(CONFIRM_PROD_FLAG, help="Required to write to the production evidence bucket."),
    ] = False,
) -> None:
    """Publish a built index to this environment's bucket, its pointer last."""
    cli = cli_context(ctx)
    _refuse(cli, ctx, _not_this_environment(cli.services.settings, env, confirmed=confirm_prod))
    service = cli.services.search_index_publish()
    cli.output.detail(f"publishing {index.name} to {cli.services.settings.storage.s3.bucket}")
    published = asyncio.run(service.publish(index))
    cli.output.success(command_name(ctx), publish_summary(published), display=_publish_table(published))


def build_summary(built: BuiltSearchIndex) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `build`: the manifest, and where the directory is."""
    return {"directory": str(built.directory), "manifest": built.manifest.model_dump(mode="json")}


def publish_summary(published: PublishedSearchIndex) -> dict[str, JsonValue]:
    """The `--json` envelope's `data` for `publish`: the keys written, in order, and the pointer."""
    return {
        "index_id": published.index_id,
        "written": [published.object_key, published.manifest_key, published.pointer_key],
        "pointer": published.pointer.model_dump(mode="json"),
    }


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


def _refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


def _build_table(manifest: SearchIndexManifest) -> TableSpec:
    counts = manifest.counts
    rows = [[name, str(documents)] for name, documents in sorted(counts.documents_by_store.items())]
    return TableSpec(
        columns=["Store", "Documents"],
        rows=rows,
        title=f"Search index {manifest.index_id}: {counts.documents} documents",
        caption=(
            f"{counts.occurrences} occurrences of {counts.occurrence_rows_read} rows read; "
            f"{counts.suppressed_occurrences} suppressed, {counts.clusters_left_out} clusters left out. "
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
        ),
    )
