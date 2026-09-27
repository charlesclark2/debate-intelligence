"""The fixture spec tree that the `scripts/validate_specs.py` and `scripts/spec_index.py` tests share.

`minimal_valid/` is a complete little repository root: two releases, two epics, three tasks and a
hand-written ROADMAP.md. A test copies it to a temporary directory and breaks one thing at a time.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "minimal_valid"

RELEASE_V10 = "plan_specs/releases/v1.0.yaml"
RELEASE_V11 = "plan_specs/releases/v1.1.yaml"
EPIC_E01 = "plan_specs/v1/e01-minimal-foundation/epic.yaml"
TASK_T01 = "plan_specs/v1/e01-minimal-foundation/t01-first-step.yaml"
TASK_T02 = "plan_specs/v1/e01-minimal-foundation/t02-second-step.yaml"
TASK_LATER = "plan_specs/v1/e02-minimal-followup/t01-later-step.yaml"
ROADMAP = "ROADMAP.md"


class Tree:
    """A copy of the fixture spec tree that a test can break in one place."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self, rel: str) -> str:
        return (self.path / rel).read_text()

    def write(self, rel: str, text: str) -> None:
        (self.path / rel).write_text(text)

    def edit(self, rel: str, old: str, new: str, *, count: int = 1) -> None:
        """Replace `old` with `new`, failing loudly if the fixture no longer contains `old`."""
        text = self.read(rel)
        assert old in text, f"{rel} no longer contains {old!r}; update the fixture or the test"
        self.write(rel, text.replace(old, new, count) if count else text.replace(old, new))

    def drop_document(self, rel: str, kind: str) -> None:
        """Remove the YAML document of the given kind from a multi-document file."""
        parts = self.read(rel).split("\n---\n")
        kept = [p for p in parts if not re.search(rf"^kind: {kind}$", p, re.M)]
        assert len(kept) < len(parts), f"{rel} has no {kind} document"
        self.write(rel, "\n---\n".join(kept))

    def drop_lines(self, rel: str, first: str, last: str) -> None:
        """Remove everything from the line containing `first` up to the next occurrence of `last`."""
        text = self.read(rel)
        start = text.index(first)
        end = text.index(last, start)
        self.write(rel, text[:start] + text[end:])


def copy_fixture(tmp_path: Path) -> Tree:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    return Tree(root)


def write_release(tree: Tree, version: str, epic_name: str) -> None:
    """Add a syntactically valid release file for `version` that references `epic_name`."""
    slug = version.replace(".", "-")
    labels = (
        "  labels:\n"
        "    planspec.io/kind: release\n"
        f"    debate/major-version: {version.split('.')[0]}\n"
        f"    debate/release: {version}\n"
    )
    documents = [
        "apiVersion: planspec.io/v1alpha1\n"
        "kind: Goal\n"
        "metadata:\n"
        f"  name: release-{slug}\n"
        f"{labels}"
        "  annotations:\n"
        f"    debate/title: {version} — Added by a test\n"
        "spec:\n"
        "  description: A release written by a test.\n"
        "  acceptanceCriteria:\n"
        "  - id: ac1\n"
        "    description: Everything in it is done.\n"
        "status:\n"
        "  phase: Pending\n",
        "apiVersion: planspec.io/v1alpha1\n"
        "kind: Gate\n"
        "metadata:\n"
        f"  name: release-{slug}-gate\n"
        f"{labels}"
        "spec:\n"
        "  description: Review gate.\n"
        "  acceptanceCriteria:\n"
        "  - id: reviewed\n"
        "    description: Reviewed.\n"
        "status:\n"
        "  phase: Pending\n",
        "apiVersion: planspec.io/v1alpha1\n"
        "kind: Plan\n"
        "metadata:\n"
        f"  name: release-{slug}-plan\n"
        f"{labels}"
        "spec:\n"
        "  description: Epic graph.\n"
        "  goalRef:\n"
        f"    name: release-{slug}\n"
        "  graph:\n"
        "    nodes:\n"
        "    - id: epic\n"
        "      kind: External\n"
        "      name: The epic\n"
        "      inputs:\n"
        f"        goalRef: {epic_name}\n",
    ]
    tree.write(f"plan_specs/releases/{version}.yaml", "---\n" + "---\n".join(documents))
