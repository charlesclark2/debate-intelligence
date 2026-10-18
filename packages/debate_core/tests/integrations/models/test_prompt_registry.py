"""The prompt registry: loading prompt files, resolving versions, rendering (v1-e05-t04-prompt-registry).

ac1: every `prompts/**/*.md` file is loaded, and a duplicate (prompt_id, version), an invalid version
or an output schema that is not a Pydantic model is refused. ac2: a missing variable is a
`PromptRenderError`, and the same inputs always render the same text. ac5: a prompt id that cannot
name a fixture directory is refused.

Expected texts and front matter are written out by hand from the files they describe.
"""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from debate_core.domain.model_contracts import ModelPrompt, RenderedPrompt, TaskClass
from debate_core.domain.prompt_spec import ChangelogEntry, PromptSpec, PromptStatus
from debate_core.integrations.models._recorded_files import safe_directory_name
from debate_core.integrations.models.errors import (
    PromptRegistryError,
    PromptRenderError,
    UnknownPromptError,
)
from debate_core.integrations.models.prompt_registry import LATEST, PromptRegistry
from debate_core.testing.contracts.model_router import ContractPassage

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]

type PromptWriter = Callable[..., Path]
"""The `write_prompt` fixture of this directory's conftest."""
SAMPLE_PROMPTS = REPOSITORY_ROOT / "tests" / "fixtures" / "prompts"
SAMPLE_FILE = SAMPLE_PROMPTS / "example" / "select-passage.md"


def load(directory: Path) -> PromptRegistry:
    return PromptRegistry.load(directory)


# Loading ---------------------------------------------------------------------------------------


def test_the_sample_prompt_loads_with_its_front_matter_schema_and_variables() -> None:
    registry = load(SAMPLE_PROMPTS)

    [prompt] = registry.prompts
    assert prompt.path == SAMPLE_FILE
    assert prompt.spec == PromptSpec(
        prompt_id="example.select-passage",
        version="1.0.0",
        status=PromptStatus.RELEASED,
        task_class=TaskClass.HIGH_VOLUME,
        output_schema="debate_core.testing.contracts.model_router.ContractPassage",
        owner="v1-e05-model-router",
        changelog=(
            ChangelogEntry(
                version="1.0.0",
                date=datetime.date(2026, 10, 17),
                summary="The worked example of the prompt file format. Only tests load it.",
            ),
        ),
    )
    assert prompt.schema is ContractPassage
    assert prompt.variables == frozenset({"tag"})


def test_the_repository_prompts_directory_loads() -> None:
    registry = load(REPOSITORY_ROOT / "prompts")

    for prompt in registry.prompts:
        assert prompt.path.is_relative_to(REPOSITORY_ROOT / "prompts")


def test_every_markdown_file_under_the_directory_is_loaded_except_readmes(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("top.md", prompt_id="area.top")
    write_prompt("card/select.md", prompt_id="card.select")
    write_prompt("card/deeper/still/markup.md", prompt_id="card.markup", version="2.1.0")
    (prompt_dir / "README.md").write_text("# Prompts\n\nNo front matter here.\n", encoding="utf-8")
    (prompt_dir / "card" / "README.md").write_text("# Card prompts\n", encoding="utf-8")
    (prompt_dir / "card" / "notes.txt").write_text("not a prompt\n", encoding="utf-8")

    registry = load(prompt_dir)

    assert [(p.spec.prompt_id, p.spec.version) for p in registry.prompts] == [
        ("area.top", "1.0.0"),
        ("card.markup", "2.1.0"),
        ("card.select", "1.0.0"),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Just a body, no front matter.\n",
        "\n---\nprompt_id: x\n---\nbody\n",
        "---\nprompt_id: never.closed\nversion: 1.0.0\n",
        "",
    ],
    ids=["no-front-matter", "front-matter-not-first", "never-closed", "empty-file"],
)
def test_a_markdown_file_without_front_matter_is_refused_naming_it(prompt_dir: Path, text: str) -> None:
    path = prompt_dir / "stray.md"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.source == str(path)
    assert str(path) in str(caught.value)


@pytest.mark.parametrize(
    "front_matter",
    ["- a list\n- not a mapping\n", "just a string\n", "prompt_id: [unclosed\n"],
    ids=["list", "scalar", "invalid-yaml"],
)
def test_front_matter_that_is_not_a_yaml_mapping_is_refused(
    prompt_dir: Path, write_prompt: PromptWriter, front_matter: str
) -> None:
    path = write_prompt("bad.md", front_matter=front_matter)

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.source == str(path)


def test_a_front_matter_key_given_twice_is_refused(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    path = write_prompt(
        "bad.md",
        front_matter=(
            "prompt_id: card.select\nversion: 1.0.0\nversion: 1.1.0\nstatus: draft\ntask_class: high_volume\n"
            f"output_schema: {ContractPassage.__module__}.ContractPassage\nowner: v1-e05-model-router\n"
            "changelog:\n  - version: 1.0.0\n    date: 2026-10-17\n    summary: x\n"
        ),
    )

    with pytest.raises(PromptRegistryError, match="given twice") as caught:
        load(prompt_dir)

    assert caught.value.source == str(path)


def test_two_files_with_the_same_prompt_and_version_are_refused_naming_both(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    first = write_prompt("card/select.md", prompt_id="card.select", version="1.0.0")
    second = write_prompt(
        "card/select-copy.md", prompt_id="card.select", version="1.0.0", body="Other {{ tag }}\n"
    )

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    message = str(caught.value)
    assert "card.select@1.0.0" in message
    assert str(first) in message
    assert str(second) in message


def test_the_same_id_at_two_versions_and_two_ids_at_one_version_are_both_allowed(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("card/select.md", prompt_id="card.select", version="1.0.0")
    write_prompt("card/select@1.1.0.md", prompt_id="card.select", version="1.1.0")
    write_prompt("card/markup.md", prompt_id="card.markup", version="1.0.0")

    assert len(load(prompt_dir).prompts) == 3


def test_a_duplicate_is_refused_when_the_registry_is_built_from_prompts_directly(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("one.md", prompt_id="card.select")
    [prompt] = load(prompt_dir).prompts

    with pytest.raises(PromptRegistryError, match=r"card\.select@1\.0\.0"):
        PromptRegistry([prompt, prompt])


@pytest.mark.parametrize(
    "version",
    [
        "1.0",
        "1",
        "v1.0.0",
        "01.0.0",
        "1.02.0",
        "1.0.00",
        "1.0.0-rc.1",
        "1.0.0+build.5",
        "1.0.0.0",
        "1..0",
        "a.b.c",
        "'1.0.0 '",
        "' 1.0.0'",
        "'-1.0.0'",
        "latest",
    ],
)
def test_an_invalid_version_is_refused_naming_the_file_and_the_field(
    prompt_dir: Path, write_prompt: PromptWriter, version: str
) -> None:
    path = write_prompt("bad.md", version=version, changelog_version="1.0.0")

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.source == str(path)
    assert caught.value.field == "version"


def test_an_unquoted_yaml_number_is_not_mistaken_for_a_version(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("bad.md", version="1.0", changelog_version="'1.0'")

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.field == "version"


@pytest.mark.parametrize("version", ["0.0.0", "0.1.0", "1.0.10", "10.20.30", "'2.0.0'"])
def test_a_major_minor_patch_version_is_accepted(
    prompt_dir: Path, write_prompt: PromptWriter, version: str
) -> None:
    write_prompt("ok.md", version=version)

    [prompt] = load(prompt_dir).prompts
    assert prompt.spec.version == version.strip("'")


@pytest.mark.parametrize(
    "output_schema",
    [
        "no_such_package.models.Answer",
        "debate_core.testing.contracts.model_router.NoSuchModel",
        "debate_core.testing.contracts.model_router.VALID_ANSWER",
        "debate_core.testing.contracts.model_router.StructuredAnswer",
        "debate_core.testing.contracts.model_router",
        "ContractPassage",
        "pydantic.BaseModel",
        "debate_core.testing.contracts.model_router.ContractPassage.paragraph_id",
    ],
    ids=[
        "missing-module",
        "missing-name",
        "not-a-class",
        "a-dataclass",
        "a-module",
        "no-module",
        "the-base-class-itself",
        "an-attribute-of-a-model",
    ],
)
def test_an_output_schema_that_is_not_a_pydantic_model_is_refused(
    prompt_dir: Path, write_prompt: PromptWriter, output_schema: str
) -> None:
    path = write_prompt("bad.md", output_schema=output_schema)

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.source == str(path)
    assert caught.value.field == "output_schema"
    assert output_schema in str(caught.value)


def test_an_output_schema_named_by_a_re_export_is_refused_naming_where_it_is_defined(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    # `debate_core.domain` re-exports ResolvedRoute, which is defined in debate_core.domain.model_contracts.
    write_prompt("bad.md", output_schema="debate_core.domain.ResolvedRoute")

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.field == "output_schema"
    assert "debate_core.domain.model_contracts.ResolvedRoute" in str(caught.value)


GOOD_IDS = ["card.select", "Card_2", "9lives", "a-b.c_d", "x", "model.repair"]
BAD_IDS = [
    "'.hidden'",
    "'-leading-dash'",
    "_leading_underscore",
    "card/select",
    "'card\\select'",
    "card select",
    "'..'",
    "'card:select'",
    "carte.sélection",
    '"card.select\\t"',
    "'card*'",
    "''",
]


@pytest.mark.parametrize("prompt_id", BAD_IDS)
def test_a_prompt_id_that_cannot_name_a_directory_is_refused(
    prompt_dir: Path, write_prompt: PromptWriter, prompt_id: str
) -> None:
    path = write_prompt("bad.md", prompt_id=prompt_id)

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.source == str(path)
    assert caught.value.field == "prompt_id"


@pytest.mark.parametrize("prompt_id", GOOD_IDS)
def test_a_prompt_id_of_letters_digits_dots_underscores_and_dashes_is_accepted(
    prompt_dir: Path, write_prompt: PromptWriter, prompt_id: str
) -> None:
    write_prompt("ok.md", prompt_id=prompt_id)

    [prompt] = load(prompt_dir).prompts
    assert prompt.spec.prompt_id == prompt_id


@pytest.mark.parametrize("prompt_id", ["card.select", ".hidden", "-x", "card/select", "card select", "é"])
def test_the_registry_and_the_fixture_directories_apply_one_id_rule(prompt_id: str) -> None:
    def accepted_by_registry() -> bool:
        try:
            PromptSpec.model_validate(
                {
                    "prompt_id": prompt_id,
                    "version": "1.0.0",
                    "status": "draft",
                    "task_class": "high_volume",
                    "output_schema": "a.B",
                    "owner": "v1-e05-model-router",
                    "changelog": [{"version": "1.0.0", "date": "2026-10-17", "summary": "x"}],
                }
            )
        except ValueError:
            return False
        return True

    def accepted_by_fixture_directories() -> bool:
        try:
            safe_directory_name(prompt_id)
        except ValueError:
            return False
        return True

    assert accepted_by_registry() == accepted_by_fixture_directories()


@pytest.mark.parametrize("task_class", ["embeddings", "rerank", "creative_writing"])
def test_a_task_class_that_does_not_generate_text_is_refused(
    prompt_dir: Path, write_prompt: PromptWriter, task_class: str
) -> None:
    write_prompt("bad.md", task_class=task_class)

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.field == "task_class"


def test_the_changelog_must_describe_the_files_own_version(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("bad.md", version="1.1.0", changelog_version="1.0.0")

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.field == "changelog"


@pytest.mark.parametrize(
    "missing", ["prompt_id", "version", "status", "task_class", "output_schema", "owner", "changelog"]
)
def test_every_front_matter_key_is_required(
    prompt_dir: Path, write_prompt: PromptWriter, missing: str
) -> None:
    lines = {
        "prompt_id": "prompt_id: card.select\n",
        "version": "version: 1.0.0\n",
        "status": "status: draft\n",
        "task_class": "task_class: high_volume\n",
        "output_schema": f"output_schema: {ContractPassage.__module__}.ContractPassage\n",
        "owner": "owner: v1-e05-model-router\n",
        "changelog": "changelog:\n  - version: 1.0.0\n    date: 2026-10-17\n    summary: x\n",
    }
    del lines[missing]
    write_prompt("bad.md", front_matter="".join(lines.values()))

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.field == missing


def test_an_unknown_front_matter_key_is_refused_naming_it(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt(
        "bad.md",
        front_matter=(
            "prompt_id: card.select\nversion: 1.0.0\nstatus: draft\ntask_class: high_volume\n"
            f"output_schema: {ContractPassage.__module__}.ContractPassage\nowner: v1-e05-model-router\n"
            "changelog:\n  - version: 1.0.0\n    date: 2026-10-17\n    summary: x\n"
            "temperature: 0.2\n"
        ),
    )

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.field == "temperature"


# Template bodies --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "Choose for {{ tag \n",
        "{% if tag %}never closed\n",
        "{{ tag | no_such_filter }}\n",
        "{{ [1, 2] | random }}\n",
    ],
    ids=["unclosed-expression", "unclosed-block", "unknown-filter", "random-filter"],
)
def test_a_template_that_does_not_compile_is_refused_at_load(
    prompt_dir: Path, write_prompt: PromptWriter, body: str
) -> None:
    path = write_prompt("bad.md", body=body)

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.source == str(path)


@pytest.mark.parametrize(
    "body",
    [
        "{% include 'other.md' %}\n",
        "{% extends 'base.md' %}\n",
        "{% import 'macros.md' as m %}{{ m.x() }}\n",
        "{% from 'macros.md' import x %}{{ x() }}\n",
    ],
    ids=["include", "extends", "import", "from-import"],
)
def test_a_template_that_reads_another_file_is_refused_at_load(
    prompt_dir: Path, write_prompt: PromptWriter, body: str
) -> None:
    write_prompt("bad.md", body=body)

    with pytest.raises(PromptRegistryError, match="another template"):
        load(prompt_dir)


@pytest.mark.parametrize(
    "body",
    [
        "<!-- user -->\nUser {{ tag }}\n<!-- system -->\nSystem\n",
        "<!-- system -->\nSystem {{ tag }}\n",
        "<!-- system -->\nA\n<!-- system -->\nB\n<!-- user -->\nC {{ tag }}\n",
        "<!-- system -->\nA\n<!-- user -->\nB {{ tag }}\n<!-- user -->\nC\n",
        "Preamble\n<!-- system -->\nA\n<!-- user -->\nB {{ tag }}\n",
        "<!-- system -->\nA {{ tag }}\n<!-- user -->\n   \n",
        "   \n\n",
    ],
    ids=[
        "user-before-system",
        "system-without-user",
        "two-system-markers",
        "two-user-markers",
        "text-before-system",
        "blank-user-turn",
        "blank-body",
    ],
)
def test_a_body_whose_sections_are_malformed_is_refused_at_load(
    prompt_dir: Path, write_prompt: PromptWriter, body: str
) -> None:
    path = write_prompt("bad.md", body=body)

    with pytest.raises(PromptRegistryError) as caught:
        load(prompt_dir)

    assert caught.value.source == str(path)


def test_a_body_with_no_markers_is_the_user_turn_alone(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    write_prompt("plain.md", prompt_id="plain", body="\nOnly a user turn about {{ tag }}.\n\n")

    rendered = load(prompt_dir).render(
        ModelPrompt(prompt_id="plain", prompt_version="1.0.0", variables={"tag": "x"})
    )

    assert rendered == RenderedPrompt(user="Only a user turn about x.")


# Resolving versions ------------------------------------------------------------------------------


@pytest.fixture
def versioned(prompt_dir: Path, write_prompt: PromptWriter) -> PromptRegistry:
    """card.select at 1.2.0, 1.9.0 and 1.10.0, released, and 2.0.0, a draft; card.draft-only, a draft."""
    for version in ("1.2.0", "1.9.0", "1.10.0"):
        write_prompt(
            f"card/select@{version}.md",
            prompt_id="card.select",
            version=version,
            body=f"v{version} {{{{ tag }}}}\n",
        )
    write_prompt("card/select@2.0.0.md", prompt_id="card.select", version="2.0.0", status="draft")
    write_prompt("card/draft-only.md", prompt_id="card.draft-only", version="0.1.0", status="draft")
    return load(prompt_dir)


def test_get_returns_the_exact_version_asked_for_even_a_draft(versioned: PromptRegistry) -> None:
    assert versioned.get("card.select", "1.9.0").spec.version == "1.9.0"
    assert versioned.get("card.select", "2.0.0").spec.status is PromptStatus.DRAFT


def test_latest_is_the_highest_released_version_by_number(versioned: PromptRegistry) -> None:
    assert versioned.get("card.select").spec.version == "1.10.0"
    assert versioned.get("card.select", LATEST).spec.version == "1.10.0"


def test_latest_of_a_prompt_with_no_released_version_is_refused(versioned: PromptRegistry) -> None:
    with pytest.raises(UnknownPromptError, match=r"card\.draft-only"):
        versioned.get("card.draft-only")


@pytest.mark.parametrize(
    ("prompt_id", "version"), [("card.unknown", LATEST), ("card.unknown", "1.0.0"), ("card.select", "1.3.0")]
)
def test_an_unknown_prompt_or_version_is_refused_naming_it(
    versioned: PromptRegistry, prompt_id: str, version: str
) -> None:
    with pytest.raises(UnknownPromptError) as caught:
        versioned.get(prompt_id, version)

    assert prompt_id in str(caught.value)


def test_prompt_builds_a_model_prompt_pinned_to_the_version_latest_resolved_to(
    versioned: PromptRegistry,
) -> None:
    prompt = versioned.prompt("card.select", {"tag": "Warming kills"})

    assert prompt == ModelPrompt(
        prompt_id="card.select", prompt_version="1.10.0", variables={"tag": "Warming kills"}
    )
    assert versioned.prompt("card.select", {"tag": "x"}, version="1.2.0").prompt_version == "1.2.0"


def test_prompt_checks_the_variables_so_a_call_site_fails_even_where_nothing_renders(
    versioned: PromptRegistry,
) -> None:
    with pytest.raises(PromptRenderError, match="tag"):
        versioned.prompt("card.select", {"tags": "Warming kills"})


# Rendering --------------------------------------------------------------------------------------


def test_rendering_the_sample_gives_the_hand_written_system_and_user_text() -> None:
    registry = load(SAMPLE_PROMPTS)

    rendered = registry.render(
        ModelPrompt(
            prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": "Warming kills"}
        )
    )

    assert rendered == RenderedPrompt(
        system=(
            "You choose one passage from a numbered list of paragraphs.\n"
            "Answer with the paragraph's number and the character offsets where the passage starts "
            "and ends.\n"
            "Never copy any of the paragraph's words into your answer."
        ),
        user="Choose the passage that best supports this tag: Warming kills",
    )


@pytest.mark.parametrize(
    "body",
    [
        "Tag: {{ tag }}\n",
        "{% if tag %}A tag was given{% endif %}\n",
        "{% for paragraph in tag %}{{ paragraph }}{% endfor %}\n",
        "{{ tag | default('none') }}\n",
        "<!-- system -->\nAbout {{ tag }}\n<!-- user -->\nAnswer.\n",
    ],
    ids=["expression", "condition", "loop", "default-filter", "system-turn"],
)
def test_a_missing_variable_raises_prompt_render_error_naming_it(
    prompt_dir: Path, write_prompt: PromptWriter, body: str
) -> None:
    write_prompt("p.md", prompt_id="card.select", body=body)
    registry = load(prompt_dir)

    with pytest.raises(PromptRenderError) as caught:
        registry.render(ModelPrompt(prompt_id="card.select", prompt_version="1.0.0", variables={}))

    assert caught.value.prompt_id == "card.select"
    assert caught.value.prompt_version == "1.0.0"
    assert "tag" in caught.value.reason


def test_a_missing_key_inside_a_variable_raises_prompt_render_error(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt("p.md", prompt_id="card.select", body="Paragraph {{ tag.number }}: {{ tag.label }}\n")
    registry = load(prompt_dir)

    with pytest.raises(PromptRenderError, match="label"):
        registry.render(
            ModelPrompt(prompt_id="card.select", prompt_version="1.0.0", variables={"tag": {"number": 3}})
        )


def test_a_variable_the_template_never_uses_is_refused(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    write_prompt("p.md", prompt_id="card.select")
    registry = load(prompt_dir)

    with pytest.raises(PromptRenderError, match="tags"):
        registry.render(
            ModelPrompt(prompt_id="card.select", prompt_version="1.0.0", variables={"tag": "x", "tags": "y"})
        )


def test_a_call_must_name_the_exact_version_it_renders(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    write_prompt("p.md", prompt_id="card.select")
    registry = load(prompt_dir)

    with pytest.raises(PromptRenderError, match="exact version"):
        registry.render(ModelPrompt(prompt_id="card.select", prompt_version=LATEST, variables={"tag": "x"}))


def test_rendering_an_unregistered_prompt_is_refused(prompt_dir: Path) -> None:
    with pytest.raises(UnknownPromptError, match=r"card\.select"):
        load(prompt_dir).render(ModelPrompt(prompt_id="card.select", prompt_version="1.0.0"))


def test_a_mapping_renders_the_same_whatever_order_its_keys_were_given_in(
    prompt_dir: Path, write_prompt: PromptWriter
) -> None:
    write_prompt(
        "p.md",
        prompt_id="card.select",
        body="{% for key, value in tag.items() %}{{ key }}={{ value }};{% endfor %}\n",
    )
    registry = load(prompt_dir)

    def render(mapping: dict[str, object]) -> RenderedPrompt:
        return registry.render(
            ModelPrompt.model_validate(
                {"prompt_id": "card.select", "prompt_version": "1.0.0", "variables": {"tag": mapping}}
            )
        )

    forwards = render({"alpha": 1, "beta": {"y": 2, "x": 1}, "gamma": 3})
    backwards = render({"gamma": 3, "beta": {"x": 1, "y": 2}, "alpha": 1})
    assert forwards == backwards == RenderedPrompt(user="alpha=1;beta={'x': 1, 'y': 2};gamma=3;")


def test_rendering_is_deterministic_across_registries_and_calls() -> None:
    prompt = ModelPrompt(
        prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": "Warming kills"}
    )

    first = load(SAMPLE_PROMPTS)
    renders = [first.render(prompt) for _ in range(3)] + [load(SAMPLE_PROMPTS).render(prompt)]

    assert all(render == renders[0] for render in renders)


def test_rendering_is_deterministic_across_interpreters_and_hash_seeds() -> None:
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from debate_core.domain.model_contracts import ModelPrompt\n"
        "from debate_core.integrations.models.prompt_registry import PromptRegistry\n"
        "registry = PromptRegistry.load(Path(sys.argv[1]))\n"
        "prompt = ModelPrompt(prompt_id='example.select-passage', prompt_version='1.0.0',"
        " variables={'tag': 'Warming kills'})\n"
        "print(registry.render(prompt).model_dump_json())\n"
    )
    outputs: set[str] = set()
    for seed in ("0", "4242"):
        completed = subprocess.run(
            [sys.executable, "-c", script, str(SAMPLE_PROMPTS)],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        outputs.add(completed.stdout)

    in_process = load(SAMPLE_PROMPTS).render(
        ModelPrompt(
            prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": "Warming kills"}
        )
    )
    assert outputs == {in_process.model_dump_json() + "\n"}


def test_variables_are_rendered_verbatim_not_escaped(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    write_prompt("p.md", prompt_id="card.select", body="Tag: {{ tag }}\n")
    registry = load(prompt_dir)

    rendered = registry.render(
        ModelPrompt(
            prompt_id="card.select", prompt_version="1.0.0", variables={"tag": '<b>A & B</b> "quoted"'}
        )
    )

    assert rendered.user == 'Tag: <b>A & B</b> "quoted"'


def test_a_template_cannot_reach_python_internals(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    write_prompt("p.md", prompt_id="card.select", body="{{ tag.__class__.__mro__ }}\n")
    registry = load(prompt_dir)

    with pytest.raises(PromptRenderError):
        registry.render(ModelPrompt(prompt_id="card.select", prompt_version="1.0.0", variables={"tag": "x"}))


def test_a_template_has_no_random_text_generator(prompt_dir: Path, write_prompt: PromptWriter) -> None:
    write_prompt("p.md", prompt_id="card.select", body="{{ lipsum(1) }}\n")
    registry = load(prompt_dir)

    with pytest.raises(PromptRenderError, match="lipsum"):
        registry.render(ModelPrompt(prompt_id="card.select", prompt_version="1.0.0", variables={}))


def test_the_registry_render_is_a_prompt_renderer_for_a_real_router() -> None:
    renderer: Callable[[ModelPrompt], RenderedPrompt] = load(SAMPLE_PROMPTS).render
    rendered = renderer(
        ModelPrompt(prompt_id="example.select-passage", prompt_version="1.0.0", variables={"tag": "x"})
    )
    assert isinstance(rendered, RenderedPrompt)
