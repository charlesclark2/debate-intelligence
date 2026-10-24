"""`config/landscape/released.yaml` read, checked against the taxonomy files, and written (`v1-e32-t08`).

The lock file records, per topic and released version, each position id with its kind and side
(:class:`~debate_core.domain.landscape_release.ReleaseLock`). Two callers:

* :func:`released_id_findings` is the check `tests/config/test_landscape_released_ids.py` runs on
  every pull request. It loads the whole configuration through
  :class:`~debate_core.integrations.landscape.yaml_taxonomy_repository.YamlTaxonomyRepository`, so
  every rule of `v1-e32-t01` holds first (a taxonomy file's version equal to `topics.yaml`'s among
  them), then returns one message per break of a release rule, each naming the file, the id and
  the rule. It reads the committed files only: no network, no git history.
* :func:`write_release` is `scripts/release_landscape_taxonomy.py`: it adds one topic's merged
  taxonomy to the lock at the version given, refusing a version the file is not at, a version
  already in the lock, and a configuration the check refuses, so a lock never records a break.

A missing lock file is refused, not read as empty: a deleted lock would otherwise pass every check.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import ValidationError

from debate_core.application.ports.taxonomy_repository import TaxonomyConfigError
from debate_core.domain.landscape import GENERIC_TOPIC_ID, Taxonomy
from debate_core.domain.landscape_release import (
    ReleaseFinding,
    ReleaseLock,
    TaxonomyRelease,
    merged_into_findings,
    release_findings,
)
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    GENERIC_FILE,
    TAXONOMY_DIRECTORY,
    YamlTaxonomyRepository,
    load_taxonomy_file,
    read_config_file,
)

__all__ = [
    "RELEASED_FILE",
    "load_release_lock",
    "released_id_findings",
    "render_release_lock",
    "write_release",
]

RELEASED_FILE: Final = "released.yaml"

_HEADER: Final = """\
# The position ids published landscape reports have released, per topic and taxonomy version: each
# id with its kind and side, the topic's own positions and generic.yaml's for its event, and a sha256
# of those positions (a hash, no text). Written by scripts/release_landscape_taxonomy.py when a report
# under a new version is first published; never edited by hand. The check in
# tests/config/test_landscape_released_ids.py refuses a taxonomy that deletes one of these ids,
# changes its kind or side, or edits a released version's positions without a bump.
# docs/guides/landscape-taxonomy.md says when the operator writes it.
"""


def load_release_lock(path: Path) -> ReleaseLock:
    """Read and check the lock file; a missing one is refused rather than read as empty."""
    if not path.is_file():
        raise TaxonomyConfigError(
            str(path), "does not exist; it is committed, with `releases: []` until a report is published"
        )
    try:
        return ReleaseLock.model_validate(read_config_file(path))
    except ValidationError as error:
        raise TaxonomyConfigError(str(path), str(error)) from error


def render_release_lock(lock: ReleaseLock) -> str:
    """The text of the lock file for `lock`, header first; what :func:`load_release_lock` reads."""
    lines = [_HEADER.rstrip("\n"), "schema_version: 1"]
    if not lock.releases:
        lines.append("releases: []")
    else:
        lines.append("releases:")
    for release in lock.releases:
        lines += [
            f"  - topic_id: {release.topic_id}",
            f"    taxonomy_version: {release.taxonomy_version}",
            f"    positions_digest: {release.positions_digest}",
            "    positions:",
        ]
        lines += [
            f"      - {{id: {one.id}, kind: {one.kind.value}, side: {one.side.value}}}"
            for one in release.positions
        ]
    return "\n".join(lines) + "\n"


class _Configuration:
    """The repository, the lock and each taxonomy file as written, read from one `config/landscape/`."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.repository = YamlTaxonomyRepository.load(directory)
        self.lock_path = directory / RELEASED_FILE
        self.lock = load_release_lock(self.lock_path)
        taxonomy_directory = directory / TAXONOMY_DIRECTORY
        self.files = {
            path.stem: load_taxonomy_file(path) for path in sorted(taxonomy_directory.glob("*.yaml"))
        }

    def file_of(self, finding: ReleaseFinding) -> str:
        """The file to edit for `finding`: the one holding the position now, or the topic's own."""
        topic_file = self.directory / TAXONOMY_DIRECTORY / f"{finding.topic_id}.yaml"
        own = self.files.get(finding.topic_id)
        generic = self.files.get(GENERIC_TOPIC_ID)
        if finding.position_id is None or (own is not None and _holds(own, finding.position_id)):
            return str(topic_file)
        if generic is not None and _holds(generic, finding.position_id):
            return str(self.directory / TAXONOMY_DIRECTORY / GENERIC_FILE)
        return f"{topic_file} (with {GENERIC_FILE} merged in)"

    def messages(self) -> list[str]:
        topics = {
            topic.id: self.repository.taxonomy(topic.id)
            for topic in self.repository.topic_map().topics
            if topic.taxonomy_version is not None
        }
        found = [f"{self.file_of(one)}: {one.message}" for one in release_findings(self.lock, topics)]
        for stem, taxonomy in self.files.items():
            path = self.directory / TAXONOMY_DIRECTORY / f"{stem}.yaml"
            found += [f"{path}: {one.message}" for one in merged_into_findings(taxonomy)]
        return found


def _holds(taxonomy: Taxonomy, position_id: str) -> bool:
    return any(one.id == position_id for one in taxonomy.positions)


def released_id_findings(directory: Path) -> list[str]:
    """Every break of the release rules under `directory`, each naming the file, the id and the rule.

    A configuration that fails `v1-e32-t01`'s checks raises
    :class:`~debate_core.application.ports.taxonomy_repository.TaxonomyConfigError` naming the file.
    """
    return _Configuration(directory).messages()


def write_release(directory: Path, topic_id: str, version: str) -> TaxonomyRelease:
    """Add `topic_id`'s merged taxonomy to the lock at `version`, and write the lock file.

    Refused, writing nothing, when the configuration breaks a release rule, when the topic's file
    is not at `version`, or when `version` is already in the lock.
    """
    configuration = _Configuration(directory)
    problems = configuration.messages()
    if problems:
        raise TaxonomyConfigError(
            str(configuration.lock_path),
            "not written, because the configuration breaks the released ids:\n" + "\n".join(problems),
        )
    taxonomy = configuration.repository.taxonomy(topic_id)
    try:
        updated = configuration.lock.with_release(taxonomy, version)
    except ValueError as error:
        raise TaxonomyConfigError(str(configuration.lock_path), f"not written: {error}") from error
    configuration.lock_path.write_text(render_release_lock(updated), encoding="utf-8")
    return updated.releases[-1]
