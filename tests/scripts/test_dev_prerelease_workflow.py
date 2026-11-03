"""Which steps of `dev-prerelease.yml` run, for a superseded commit and for every other (v1-e01-t36).

GitHub's own evaluation of a step's `if:` cannot run offline, so this reads the workflow file and
evaluates each condition with a small evaluator of the expression forms the file uses: step outputs,
string literals, `==`, `!=`, `&&`, `||`, `!`, parentheses and the status functions. A step with no
status function in its condition runs only while every earlier step succeeded, as on GitHub; every
scenario here has every step succeed, so that is always true. An output a step did not write, or a
step that was skipped, reads as the empty string.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "dev-prerelease.yml"

CLAIM_COMMAND = 'python3 scripts/release_version.py claim --source "$VERSION_SOURCE" --sha "$HEAD_SHA"'
"""The claim's command line. The YAML runs from the default branch but the script from the commit
being tagged, so a commit merged before a script change runs the new YAML with the old script: a new
flag here would fail every such run."""

TOKEN = re.compile(r"\s*(?:(\|\||&&|==|!=|!|\(|\)|,)|'((?:[^']|'')*)'|([A-Za-z_][\w.-]*))")


def evaluate(expression: str, outputs: Mapping[str, Mapping[str, str]]) -> bool:
    """Whether a step's `if:` holds, given the outputs of the steps that ran before it."""
    tokens: list[tuple[str, str]] = []
    position = 0
    text = expression.strip().removeprefix("${{").removesuffix("}}")
    while text[position:].strip():
        match = TOKEN.match(text, position)
        assert match, f"cannot read {text[position:]!r} in {expression!r}"
        operator, literal, name = match.groups()
        if operator:
            tokens.append(("op", operator))
        elif literal is not None:
            tokens.append(("str", literal.replace("''", "'")))
        else:
            tokens.append(("name", name))
        position = match.end()

    def peek() -> tuple[str, str] | None:
        return tokens[0] if tokens else None

    def take() -> tuple[str, str]:
        return tokens.pop(0)

    def either() -> str | bool:
        left = both()
        while peek() == ("op", "||"):
            take()
            right = both()
            left = left if truthy(left) else right
        return left

    def both() -> str | bool:
        left = comparison()
        while peek() == ("op", "&&"):
            take()
            right = comparison()
            left = right if truthy(left) else left
        return left

    def comparison() -> str | bool:
        left = negation()
        while peek() in (("op", "=="), ("op", "!=")):
            _, operator = take()
            right = negation()
            equal = str(left).lower() == str(right).lower()
            left = equal if operator == "==" else not equal
        return left

    def negation() -> str | bool:
        if peek() == ("op", "!"):
            take()
            return not truthy(negation())
        return primary()

    def primary() -> str | bool:
        kind, value = take()
        if (kind, value) == ("op", "("):
            inner = either()
            assert take() == ("op", ")")
            return inner
        if kind == "str":
            return value
        assert kind == "name", f"unexpected {value!r} in {expression!r}"
        if peek() == ("op", "("):
            take()
            assert take() == ("op", ")"), f"{value}() takes no arguments here"
            assert value in {"always", "success"}, f"{value}() is not modelled"
            return True
        parts = value.split(".")
        assert parts[0] == "steps" and parts[2] == "outputs", f"{value} is not modelled"
        return outputs.get(parts[1], {}).get(parts[3], "")

    result = either()
    assert not tokens, f"unread {tokens} in {expression!r}"
    return truthy(result)


def truthy(value: str | bool) -> bool:
    return value if isinstance(value, bool) else value != ""


def publish_steps() -> list[dict[str, object]]:
    flow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return flow["jobs"]["publish"]["steps"]


def step_name(step: Mapping[str, object]) -> str:
    return str(step.get("name") or step.get("uses"))


def steps_that_run(written: Mapping[str, Mapping[str, str]]) -> list[str]:
    """The steps that run when each step writes the outputs in `written`, in order."""
    outputs: dict[str, Mapping[str, str]] = {}
    ran = []
    for step in publish_steps():
        condition = step.get("if")
        if condition is None or evaluate(str(condition), outputs):
            ran.append(step_name(step))
            if "id" in step:
                outputs[str(step["id"])] = written.get(str(step["id"]), {})
    return ran


CHECKOUT = "actions/checkout@v7"
CLAIM = "Claim the next vX.Y.Z-dev.N by pushing its tag at the head commit"
SKIP_PUBLISHED = "Skip a commit whose pre-release is already published"
BUILD = [
    "astral-sh/setup-uv@v10.2.0",
    "Install Python from .python-version",
    "Stamp the version, build info and bundled configuration",
    "Build the debate_core and debate_cli wheels",
    "Refuse wheels that are not exactly what should ship",
    "Write SHA256SUMS",
    "Install the build as its users will and check it can import everything it wires",
    "Publish the GitHub pre-release",
]
DISPATCH_AND_PRUNE = ["Ask validate-dev to validate this build", "Keep the newest 30 dev pre-releases"]
SUMMARY = "Summary"
SUPERSEDED_SUMMARY = "Summary of a superseded commit"

CLAIMED = {
    "tag": "v1.1.0-dev.138",
    "version": "1.1.0.dev138",
    "number": "138",
    "target": "1.1.0",
    "sha": "e" * 40,
    "reused": "false",
}
SUPERSEDED = {"superseded": "true", "sha": "f" * 40, "superseded_by": "0" * 40}


def test_a_superseded_commit_runs_nothing_after_the_claim_but_its_summary() -> None:
    assert steps_that_run({"claim": SUPERSEDED}) == [CHECKOUT, CLAIM, SUPERSEDED_SUMMARY]


def test_a_superseded_run_would_build_publish_and_dispatch_nothing_whatever_a_later_step_wrote() -> None:
    """Even a stray `published=false` cannot start the build: the gate is on the claim's output."""
    ran = steps_that_run({"claim": SUPERSEDED, "existing": {"published": "false"}})

    assert not set(ran) & {SKIP_PUBLISHED, *BUILD, *DISPATCH_AND_PRUNE, SUMMARY}


@pytest.mark.parametrize("claimed", [CLAIMED, {**CLAIMED, "reused": "true"}], ids=["new", "reused"])
def test_the_next_commits_pre_release_runs_every_step_as_before(claimed: dict[str, str]) -> None:
    ran = steps_that_run({"claim": claimed, "existing": {"published": "false"}})

    assert ran == [CHECKOUT, CLAIM, SKIP_PUBLISHED, *BUILD, *DISPATCH_AND_PRUNE, SUMMARY]


def test_a_commit_already_published_still_skips_the_build_and_re_dispatches() -> None:
    ran = steps_that_run({"claim": CLAIMED, "existing": {"published": "true"}})

    assert ran == [CHECKOUT, CLAIM, SKIP_PUBLISHED, *DISPATCH_AND_PRUNE, SUMMARY]


def test_the_claim_command_line_is_unchanged() -> None:
    [claim] = [step for step in publish_steps() if step.get("id") == "claim"]

    assert str(claim["run"]).strip().splitlines()[-1] == CLAIM_COMMAND


def test_the_superseded_summary_names_devs_head() -> None:
    [summary] = [step for step in publish_steps() if step_name(step) == SUPERSEDED_SUMMARY]

    assert summary["env"] == {
        "SUPERSEDED_SHA": "${{ steps.claim.outputs.sha }}",
        "SUPERSEDED_BY": "${{ steps.claim.outputs.superseded_by }}",
    }
    assert "$SUPERSEDED_BY" in str(summary["run"]) or "${SUPERSEDED_BY}" in str(summary["run"])


@pytest.mark.parametrize(
    ("expression", "outputs", "expected"),
    [
        ("steps.claim.outputs.superseded != 'true'", {}, True),
        ("steps.claim.outputs.superseded != 'true'", {"claim": {"superseded": "true"}}, False),
        ("always() && steps.claim.outputs.tag != ''", {}, False),
        ("always() && steps.claim.outputs.tag != ''", {"claim": {"tag": "v1"}}, True),
        ("!(steps.a.outputs.x == 'y') || steps.a.outputs.z", {"a": {"x": "y", "z": "1"}}, True),
        ("!(steps.a.outputs.x == 'y') || steps.a.outputs.z", {"a": {"x": "y"}}, False),
    ],
)
def test_the_evaluator_reads_conditions_as_github_does(
    expression: str, outputs: dict[str, dict[str, str]], expected: bool
) -> None:
    assert evaluate(expression, outputs) is expected
