"""`scripts/check_links.py`: the offline Markdown link and anchor checker.

Each test writes a small documentation tree in a temporary directory, so a fixture can hold a
deliberately broken link without breaking the repository's own check. The expected messages and
the expected heading slugs are written by hand.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import check_links
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

Capture = pytest.CaptureFixture[str]

TARGET = """# Target

## A Heading

## Repeated heading

## Repeated heading
"""


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    """A tree with one valid target document to link at."""
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "target.md").write_text(TARGET)
    return root


def write(root: Path, name: str, body: str) -> None:
    (root / name).write_text(body)


def problems(root: Path) -> list[str]:
    return check_links.check(root)


# --------------------------------------------------------------------------------------------
# links that are broken
# --------------------------------------------------------------------------------------------


def test_a_missing_file_target_is_reported(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\nSee [the plan](sub/no-such-file.md).\n")
    assert problems(docs) == ["page.md:3: sub/no-such-file.md does not exist"]


def test_a_missing_anchor_is_reported(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\nSee [a section](sub/target.md#no-such-heading).\n")
    assert problems(docs) == [
        "page.md:3: sub/target.md#no-such-heading has no heading matching #no-such-heading"
    ]


def test_a_missing_anchor_in_the_same_file_is_reported(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\nSee [below](#not-here).\n")
    assert problems(docs) == ["page.md:3: #not-here has no heading matching #not-here"]


def test_a_target_outside_the_repository_is_reported(docs: Path, tmp_path: Path) -> None:
    (tmp_path / "elsewhere.md").write_text("# Elsewhere\n")
    write(docs, "page.md", "# Page\n\nSee [outside](../elsewhere.md).\n")
    assert problems(docs) == ["page.md:3: ../elsewhere.md resolves outside the repository"]


def test_an_image_with_a_missing_file_is_reported(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\n![A diagram](diagrams/flow.png)\n")
    assert problems(docs) == ["page.md:3: diagrams/flow.png does not exist"]


def test_a_reference_definition_with_a_missing_file_is_reported(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\nSee [the plan][plan].\n\n[plan]: sub/no-such-file.md\n")
    assert problems(docs) == ["page.md:5: sub/no-such-file.md does not exist"]


def test_every_broken_link_is_listed_not_just_the_first(docs: Path) -> None:
    write(
        docs,
        "page.md",
        "# Page\n\n[one](a.md)\n\n[two](b.md)\n\n[three](sub/target.md#nope)\n",
    )
    assert problems(docs) == [
        "page.md:3: a.md does not exist",
        "page.md:5: b.md does not exist",
        "page.md:7: sub/target.md#nope has no heading matching #nope",
    ]


def test_a_link_wrapped_across_lines_is_found_on_the_line_it_starts(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\nSee [the plan\nfor next year](sub/gone.md) for details.\n")
    assert problems(docs) == ["page.md:3: sub/gone.md does not exist"]


# --------------------------------------------------------------------------------------------
# links that resolve
# --------------------------------------------------------------------------------------------


def test_a_relative_file_and_anchor_resolve(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\nSee [a heading](sub/target.md#a-heading).\n")
    assert problems(docs) == []


def test_an_anchor_in_the_same_file_resolves(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\n## Open questions\n\nSee [the questions](#open-questions).\n")
    assert problems(docs) == []


def test_repeated_headings_get_the_suffixes_github_gives_them(docs: Path) -> None:
    body = "# Page\n\n[first](sub/target.md#repeated-heading)\n[second](sub/target.md#repeated-heading-1)\n"
    write(docs, "page.md", body)
    assert problems(docs) == []


def test_a_directory_target_resolves(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\nSee [the folder](sub).\n")
    assert problems(docs) == []


def test_a_url_encoded_target_is_decoded_before_it_is_looked_up(docs: Path) -> None:
    (docs / "sub" / "two words.md").write_text("# Two words\n")
    write(docs, "page.md", "# Page\n\nSee [it](sub/two%20words.md).\n")
    assert problems(docs) == []


def test_a_link_title_after_the_target_is_not_part_of_it(docs: Path) -> None:
    write(docs, "page.md", '# Page\n\nSee [it](sub/target.md "The target").\n')
    assert problems(docs) == []


# --------------------------------------------------------------------------------------------
# links that are not checked
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    [
        "https://example.org/missing.md",
        "http://example.org/missing.md",
        "mailto:nobody@example.org",
        "tel:+15550100",
    ],
)
def test_absolute_urls_are_left_alone(docs: Path, target: str) -> None:
    write(docs, "page.md", f"# Page\n\nSee [it]({target}).\n")
    assert problems(docs) == []


@pytest.mark.parametrize("target", ["/", "/events/", "/faq/"])
def test_root_absolute_website_routes_are_left_alone(docs: Path, target: str) -> None:
    write(docs, "page.md", f"# Page\n\nSee [it]({target}).\n")
    assert problems(docs) == []


@pytest.mark.parametrize("target", ["../../{{SPEC}}", "{{TASK}}.md", "docs/{{NAME}}/index.md"])
def test_template_placeholder_targets_are_left_alone(docs: Path, target: str) -> None:
    write(docs, "page.md", f"# Page\n\nSee [it]({target}).\n")
    assert problems(docs) == []


def test_links_inside_a_code_span_are_left_alone(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\nWrite `[text](sub/no-such-file.md)` like this.\n")
    assert problems(docs) == []


def test_links_inside_a_fenced_code_block_are_left_alone(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\n```markdown\n[text](sub/no-such-file.md)\n```\n")
    assert problems(docs) == []


def test_links_inside_a_tilde_fenced_block_are_left_alone(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\n~~~\n[text](sub/no-such-file.md)\n~~~\n")
    assert problems(docs) == []


def test_a_fence_inside_a_longer_fence_does_not_end_it(docs: Path) -> None:
    body = "# Page\n\n````markdown\n```bash\n[text](sub/no-such-file.md)\n```\n````\n"
    write(docs, "page.md", body)
    assert problems(docs) == []


def test_links_inside_an_html_comment_are_left_alone(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\n<!-- [text](sub/no-such-file.md) -->\n")
    assert problems(docs) == []


def test_a_heading_inside_a_code_block_is_not_an_anchor(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\n```bash\n# Not a heading\n```\n\n[x](#not-a-heading)\n")
    assert problems(docs) == ["page.md:7: #not-a-heading has no heading matching #not-a-heading"]


def test_an_anchor_into_a_file_that_is_not_markdown_is_not_checked(docs: Path) -> None:
    (docs / "sub" / "spec.yaml").write_text("name: something\n")
    write(docs, "page.md", "# Page\n\nSee [it](sub/spec.yaml#whatever).\n")
    assert problems(docs) == []


# --------------------------------------------------------------------------------------------
# heading slugs
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "slug"),
    [
        ("A Heading", "a-heading"),
        ("5. AWS Cloud Architecture", "5-aws-cloud-architecture"),
        ("§17 Deployment", "17-deployment"),
        ("What's new?", "whats-new"),
        ("v1.0 — Foundation & verified evidence core", "v10--foundation--verified-evidence-core"),
        ("Snake_case and kebab-case", "snake_case-and-kebab-case"),
        ("Removal on request", "removal-on-request"),
    ],
)
def test_heading_slugs_follow_githubs_rules(heading: str, slug: str) -> None:
    assert check_links.slugify(heading) == slug


@pytest.mark.parametrize(
    ("heading", "anchor"),
    [
        ("## The `verify` command", "the-verify-command"),
        ("## The [architecture](../architecture/proposal.md) proposal", "the-architecture-proposal"),
        ("## **Bold** and *italic*", "bold-and-italic"),
        ("###### Six hashes", "six-hashes"),
    ],
)
def test_inline_markup_in_a_heading_does_not_reach_its_anchor(heading: str, anchor: str) -> None:
    assert anchor in check_links.anchors_in(f"{heading}\n")


def test_an_html_anchor_is_an_anchor(docs: Path) -> None:
    write(docs, "page.md", '# Page\n\n<a id="the-spot"></a>\n\n[jump](#the-spot)\n')
    assert problems(docs) == []


# --------------------------------------------------------------------------------------------
# which files are checked
# --------------------------------------------------------------------------------------------


def test_only_tracked_files_are_checked_in_a_git_repository(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\nSee [it](sub/target.md).\n")
    write(docs, "scratch.md", "# Scratch\n\nSee [it](sub/no-such-file.md).\n")
    for command in (["init", "-q"], ["add", "page.md", "sub/target.md"]):
        subprocess.run(["git", *command], cwd=docs, check=True, capture_output=True)

    listed = [p.name for p in check_links.tracked_markdown(docs)]
    assert listed == ["page.md", "target.md"]
    assert problems(docs) == []


def test_every_markdown_file_is_checked_when_git_cannot_list_them(docs: Path) -> None:
    write(docs, "page.md", "# Page\n\nSee [it](sub/no-such-file.md).\n")
    assert [p.name for p in check_links.tracked_markdown(docs)] == ["page.md", "target.md"]
    assert problems(docs) == ["page.md:3: sub/no-such-file.md does not exist"]


# --------------------------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------------------------


def test_the_command_exits_zero_and_counts_what_it_checked(docs: Path, capsys: Capture) -> None:
    write(docs, "page.md", "# Page\n\n[a](sub/target.md) [b](sub/target.md#a-heading)\n")
    assert check_links.main(["--root", str(docs)]) == 0
    assert capsys.readouterr().out == "OK: 2 relative links and anchors in 2 Markdown files\n"


def test_the_command_exits_one_and_lists_every_broken_link(docs: Path, capsys: Capture) -> None:
    write(docs, "page.md", "# Page\n\n[a](gone.md)\n\n[b](sub/target.md#nope)\n")
    assert check_links.main(["--root", str(docs)]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "page.md:3: gone.md does not exist",
        "page.md:5: sub/target.md#nope has no heading matching #nope",
    ]
    assert "2 broken link(s) in 2 Markdown files" in captured.err


def test_the_list_option_prints_the_files_it_would_check(docs: Path, capsys: Capture) -> None:
    write(docs, "page.md", "# Page\n")
    assert check_links.main(["--list", "--root", str(docs)]) == 0
    assert capsys.readouterr().out == "page.md\nsub/target.md\n"


# --------------------------------------------------------------------------------------------
# the real repository
# --------------------------------------------------------------------------------------------


def test_the_repository_has_no_broken_links() -> None:
    assert check_links.check(REPO_ROOT) == []


def test_the_repository_check_reads_every_tracked_markdown_file() -> None:
    listed = check_links.tracked_markdown(REPO_ROOT)
    tracked = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", "*.md"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.split()
    assert [p.relative_to(REPO_ROOT).as_posix() for p in listed] == sorted(tracked)


def test_the_repository_has_anchors_to_verify() -> None:
    """A guard on the guard: if no link carried an anchor, the anchor rule would be untested here."""
    with_anchors = [
        link
        for path in check_links.tracked_markdown(REPO_ROOT)
        for link in check_links.links_in(path.read_text())
        if check_links.is_checkable(link.target) and "#" in link.target
    ]
    assert len(with_anchors) > 100
