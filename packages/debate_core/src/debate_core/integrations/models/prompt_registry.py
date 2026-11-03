"""The prompt registry: every prompt file under `prompts/`, validated, compiled and rendered.

A generative call names a prompt by id and version (:class:`~debate_core.domain.model_contracts.ModelPrompt`)
and never carries wording of its own. :class:`PromptRegistry` holds the wording: one reviewed file
per version, in the format `prompts/README.md` documents (v1-e05-t04-prompt-registry).

## Loading (ac1, ac5)

:meth:`PromptRegistry.load` reads every `*.md` file under a directory, at any depth, except files
named `README.md`. Each must open with a YAML front matter block that
:class:`~debate_core.domain.prompt_spec.PromptSpec` accepts. The registry refuses, naming the file:

* a file with no front matter, front matter that is not a YAML mapping, or a key given twice;
* a key `PromptSpec` refuses: a prompt id that cannot name a fixture directory, a version that is not
  `MAJOR.MINOR.PATCH`, a scoring task class, a changelog with no entry for the file's version;
* an `output_schema` that does not resolve to a Pydantic model, or that names one by a re-export
  rather than where it is defined, because the path is part of every fixture key;
* a body that does not compile, reads another template, or has malformed turn markers;
* two files with the same prompt id and version.

Every check runs when the registry is loaded, so a bad file fails the first test or command that
loads prompts, not the first call that happens to use it.

## Resolving

:meth:`PromptRegistry.get` returns an exact version, draft or released, or :data:`LATEST`: the highest
released version by number. :meth:`PromptRegistry.prompt` builds the `ModelPrompt` for a call,
pinned to the exact version it resolved.

## Rendering (ac2)

:meth:`PromptRegistry.render` is a `ModelPrompt` → :class:`~debate_core.domain.model_contracts.RenderedPrompt`
function, the renderer a real router is given. It refuses (:class:`PromptRenderError`) a variable
the template names that the call did not give, one the call gave that the template never names,
anything the template fails on, and a prompt that names `latest` instead of a version. The output
depends on nothing but the template and the variables: mappings are rendered with their keys sorted,
nothing is escaped, and the `random` filter and the `lipsum` function are removed.
"""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml
from jinja2 import StrictUndefined, Template, TemplateError, meta
from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel, JsonValue, ValidationError
from pydantic_core import ErrorDetails

from debate_core.domain.model_contracts import ModelPrompt, RenderedPrompt
from debate_core.domain.prompt_spec import PromptSpec
from debate_core.integrations.models.errors import (
    PromptRegistryError,
    PromptRenderError,
    UnknownPromptError,
)

__all__ = [
    "DEFAULT_PROMPT_DIRECTORY",
    "LATEST",
    "PROMPT_FILE_SUFFIX",
    "README_NAME",
    "SYSTEM_MARKER",
    "USER_MARKER",
    "PromptRegistry",
    "RegisteredPrompt",
    "load_prompt_file",
    "resolve_schema",
]

DEFAULT_PROMPT_DIRECTORY: Final = Path("prompts")
"""Where the prompt files are committed, relative to the repository root."""

PROMPT_FILE_SUFFIX: Final = ".md"
"""Every file with this suffix under the prompt directory is a prompt, except a README."""

README_NAME: Final = "README.md"
"""A file of this name documents its directory and is never loaded as a prompt."""

LATEST: Final = "latest"
"""Asks :meth:`PromptRegistry.get` for the highest released version of a prompt."""

SYSTEM_MARKER: Final = "<!-- system -->"
"""A line holding only this opens a body's system turn."""

USER_MARKER: Final = "<!-- user -->"
"""A line holding only this opens the user turn of a body that has a system turn."""

_FENCE: Final = "---"

_RENDER_FAILURES: Final = (TemplateError, TypeError, ValueError, ArithmeticError)
"""What a template can raise on a call's values; each is reported as a `PromptRenderError`."""


def _environment() -> SandboxedEnvironment:
    environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
    # Both produce different text on every call, and a prompt's text must depend only on its inputs.
    del environment.filters["random"]  # pyright: ignore[reportUnknownMemberType] - Jinja2 types it loosely
    del environment.globals["lipsum"]  # pyright: ignore[reportUnknownMemberType]
    return environment


_ENVIRONMENT: Final = _environment()
_GLOBAL_NAMES: Final = frozenset[str](
    _ENVIRONMENT.globals  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
)
"""Names a template reads from the environment (`range`, `dict`, ...), not from the call."""


@dataclass(frozen=True, slots=True)
class RegisteredPrompt:
    """One version of one prompt: its front matter, its body, the schema it answers and its templates."""

    spec: PromptSpec
    """The validated front matter."""
    path: Path
    """The file it was loaded from."""
    body: str
    """The text after the front matter, exactly as read, with `\\n` line endings."""
    schema: type[BaseModel]
    """The Pydantic model `spec.output_schema` names."""
    variables: frozenset[str]
    """Every variable the template names. A call gives exactly these."""
    system_template: Template | None = field(repr=False, compare=False)
    """The compiled system turn, when the body has one."""
    user_template: Template = field(repr=False, compare=False)
    """The compiled user turn."""

    @property
    def body_sha256(self) -> str:
        """The SHA-256 of the body's UTF-8 text, as `prompts/prompts.lock.json` records it."""
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()

    @property
    def label(self) -> str:
        """`prompt_id@version`, how errors and the lock name this prompt."""
        return f"{self.spec.prompt_id}@{self.spec.version}"

    def render(self, variables: Mapping[str, JsonValue]) -> RenderedPrompt:
        """The text of this prompt with `variables`; a `PromptRenderError` if they do not fit it."""
        missing = sorted(self.variables - variables.keys())
        unexpected = sorted(variables.keys() - self.variables)
        if missing or unexpected:
            problems: list[str] = []
            if missing:
                problems.append(f"missing variable(s) {', '.join(missing)}")
            if unexpected:
                problems.append(f"variable(s) the template never uses: {', '.join(unexpected)}")
            raise PromptRenderError(self.spec.prompt_id, self.spec.version, "; ".join(problems))
        context = {name: _canonical(value) for name, value in sorted(variables.items())}
        try:
            system = self.system_template.render(context).strip() if self.system_template else None
            user = self.user_template.render(context).strip()
        except _RENDER_FAILURES as error:
            raise PromptRenderError(self.spec.prompt_id, self.spec.version, str(error)) from error
        if not user:
            raise PromptRenderError(self.spec.prompt_id, self.spec.version, "the user turn rendered empty")
        return RenderedPrompt(user=user, system=system or None)


class PromptRegistry:
    """Every registered prompt, keyed by prompt id and version, each pair at most once."""

    def __init__(self, prompts: Iterable[RegisteredPrompt]) -> None:
        self._prompts: dict[tuple[str, str], RegisteredPrompt] = {}
        for prompt in prompts:
            key = (prompt.spec.prompt_id, prompt.spec.version)
            first = self._prompts.get(key)
            if first is not None:
                raise PromptRegistryError(
                    f"{prompt.label} is defined twice, in {first.path} and in {prompt.path}; a changed "
                    "prompt is a new version, not a second file with the same one",
                    field="version",
                    source=str(prompt.path),
                )
            self._prompts[key] = prompt

    @classmethod
    def load(cls, directory: Path) -> PromptRegistry:
        """Every prompt file under `directory`, at any depth; README files are skipped."""
        paths = sorted(
            path
            for path in directory.rglob(f"*{PROMPT_FILE_SUFFIX}")
            if path.name != README_NAME and path.is_file()
        )
        return cls(load_prompt_file(path) for path in paths)

    @property
    def prompts(self) -> tuple[RegisteredPrompt, ...]:
        """Every registered prompt, ordered by id and then by version number."""
        return tuple(sorted(self._prompts.values(), key=lambda p: (p.spec.prompt_id, p.spec.version_key)))

    def get(self, prompt_id: str, version: str = LATEST) -> RegisteredPrompt:
        """`prompt_id` at `version`, or at its highest released version for :data:`LATEST`.

        Raises :class:`UnknownPromptError` when there is no such prompt or version, or when `latest`
        is asked of a prompt with no released version.
        """
        versions = [prompt for (pid, _), prompt in self._prompts.items() if pid == prompt_id]
        if not versions:
            raise UnknownPromptError(f"no prompt {prompt_id!r} is registered", field="prompt_id")
        if version == LATEST:
            released = [prompt for prompt in versions if prompt.spec.is_released]
            if not released:
                raise UnknownPromptError(
                    f"prompt {prompt_id!r} has no released version, so it has no latest; "
                    "ask for a draft by its exact version",
                    field="version",
                )
            return max(released, key=lambda prompt: prompt.spec.version_key)
        found = self._prompts.get((prompt_id, version))
        if found is None:
            known = ", ".join(
                prompt.spec.version for prompt in sorted(versions, key=lambda p: p.spec.version_key)
            )
            raise UnknownPromptError(
                f"prompt {prompt_id!r} has no version {version!r}; registered: {known}", field="version"
            )
        return found

    def prompt(
        self, prompt_id: str, variables: Mapping[str, JsonValue] | None = None, *, version: str = LATEST
    ) -> ModelPrompt:
        """The `ModelPrompt` a call runs: `prompt_id` at the exact version `version` resolves to.

        The variables are checked against the template here, by rendering it once, so a call site
        that gives the wrong ones fails under the fake and replay routers too, which never render.
        """
        registered = self.get(prompt_id, version)
        given = dict(variables or {})
        registered.render(given)
        return ModelPrompt(prompt_id=prompt_id, prompt_version=registered.spec.version, variables=given)

    def render(self, prompt: ModelPrompt) -> RenderedPrompt:
        """The text `prompt` sends: the renderer a real router is given.

        Raises :class:`PromptRenderError` when the variables do not fit, and when the prompt names
        `latest`: a call records the exact version it ran, in its fixture key and its provenance.
        """
        if prompt.prompt_version == LATEST:
            raise PromptRenderError(
                prompt.prompt_id,
                prompt.prompt_version,
                "a call must name the exact version it runs; build it with PromptRegistry.prompt",
            )
        return self.get(prompt.prompt_id, prompt.prompt_version).render(prompt.variables)


def load_prompt_file(path: Path) -> RegisteredPrompt:
    """One prompt file, validated and compiled; a `PromptRegistryError` naming the file if it is not one."""
    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise PromptRegistryError(f"{path} could not be read: {error}", source=source) from error
    front_matter, body = _split_front_matter(path, text)
    spec = _parse_spec(path, front_matter)
    try:
        schema = resolve_schema(spec.output_schema)
    except ValueError as error:
        raise PromptRegistryError(
            f"{path}: output_schema: {error}", field="output_schema", source=source
        ) from error
    system_source, user_source = _split_turns(path, body)
    system_template, system_variables = (
        _compile(path, system_source) if system_source is not None else (None, frozenset[str]())
    )
    user_template, user_variables = _compile(path, user_source)
    return RegisteredPrompt(
        spec=spec,
        path=path,
        body=body,
        schema=schema,
        variables=system_variables | user_variables,
        system_template=system_template,
        user_template=user_template,
    )


def resolve_schema(dotted_path: str) -> type[BaseModel]:
    """The Pydantic model at `dotted_path` (`module.QualifiedName`); a `ValueError` saying why not.

    The path must be where the class is defined, `f"{cls.__module__}.{cls.__qualname__}"`, which is
    what a request records as its schema (`ModelRequest.build`). A re-exported path names the same
    class but a different fixture key, so it is refused with the defining path in the message.
    """
    parts = dotted_path.split(".")
    for split in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:split])
        try:
            target: object = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name is not None and (
                module_name == error.name or module_name.startswith(f"{error.name}.")
            ):
                continue
            raise ValueError(f"{dotted_path!r} names a module that fails to import: {error}") from error
        break
    else:
        raise ValueError(f"no module of {dotted_path!r} can be imported")
    for name in parts[split:]:
        try:
            target = getattr(target, name)
        except AttributeError:
            raise ValueError(f"{dotted_path!r} does not exist: {target!r} has no {name!r}") from None
    if not isinstance(target, type) or not issubclass(target, BaseModel) or target is BaseModel:
        raise ValueError(f"{dotted_path!r} is not a Pydantic model")
    defined_at = f"{target.__module__}.{target.__qualname__}"
    if defined_at != dotted_path:
        raise ValueError(
            f"{dotted_path!r} is a re-export of {defined_at}; name the schema where it is defined, "
            "because the path is part of every fixture key"
        )
    return target


def _split_front_matter(path: Path, text: str) -> tuple[str, str]:
    """`(front matter, body)`. The body is everything after the closing `---` line."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != _FENCE:
        raise PromptRegistryError(
            f"{path} does not open with a `---` front matter line, so it is not a prompt file; "
            f"only {README_NAME} files may sit under the prompt directory without one",
            source=str(path),
        )
    for index in range(1, len(lines)):
        if lines[index].rstrip("\n") == _FENCE:
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise PromptRegistryError(f"{path}: the front matter is never closed with a `---` line", source=str(path))


class _UniqueKeyLoader(yaml.SafeLoader):
    """YAML's safe loader, except that a mapping that gives one key twice is an error, not the last value."""


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    seen: set[object] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)  # pyright: ignore[reportUnknownMemberType]
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"the key {key!r} is given twice", key_node.start_mark
            )
        seen.add(key)
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def _parse_spec(path: Path, front_matter: str) -> PromptSpec:
    source = str(path)
    try:
        document: Any = yaml.load(front_matter, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise PromptRegistryError(
            f"{path}: the front matter is not valid YAML: {error}", source=source
        ) from error
    if not isinstance(document, dict):
        raise PromptRegistryError(
            f"{path}: the front matter must be a YAML mapping, not a {type(document).__name__}",
            source=source,
        )
    try:
        return PromptSpec.model_validate(document)
    except ValidationError as error:
        problems = error.errors()
        first = ".".join(str(part) for part in problems[0]["loc"])
        details = "; ".join(_describe(problem) for problem in problems)
        raise PromptRegistryError(f"{path}: {details}", field=first, source=source) from error


def _describe(problem: ErrorDetails) -> str:
    """One validation problem as `key: message (got value)`, the value shown only when it is a scalar."""
    where = ".".join(str(part) for part in problem["loc"])
    value = problem.get("input")
    shown = f" (got {value!r})" if isinstance(value, str | int | float | bool) else ""
    return f"{where}: {problem['msg']}{shown}"


def _split_turns(path: Path, body: str) -> tuple[str | None, str]:
    """`(system source or None, user source)`, by the marker lines; refuses any other arrangement."""
    lines = body.splitlines(keepends=True)
    markers = [
        (index, line.strip())
        for index, line in enumerate(lines)
        if line.strip() in (SYSTEM_MARKER, USER_MARKER)
    ]
    if not markers:
        system, user = None, body
    else:
        if [marker for _, marker in markers] != [SYSTEM_MARKER, USER_MARKER]:
            raise PromptRegistryError(
                f"{path}: a body with a system turn has one `{SYSTEM_MARKER}` line and then one "
                f"`{USER_MARKER}` line; this one has {', '.join(marker for _, marker in markers)}",
                source=str(path),
            )
        (system_at, _), (user_at, _) = markers
        if "".join(lines[:system_at]).strip():
            raise PromptRegistryError(
                f"{path}: text before `{SYSTEM_MARKER}` belongs to no turn; the marker opens the body",
                source=str(path),
            )
        system = "".join(lines[system_at + 1 : user_at])
        user = "".join(lines[user_at + 1 :])
        if not system.strip():
            raise PromptRegistryError(f"{path}: the system turn is empty", source=str(path))
    if not user.strip():
        raise PromptRegistryError(f"{path}: the user turn is empty", source=str(path))
    return system, user


def _compile(path: Path, template_source: str) -> tuple[Template, frozenset[str]]:
    """The compiled template, and the variables it reads from the call."""
    try:
        tree = _ENVIRONMENT.parse(template_source)
        if any(True for _ in meta.find_referenced_templates(tree)):
            raise PromptRegistryError(
                f"{path}: the template reads another template (include, extends or import); "
                "a prompt is one reviewed file",
                source=str(path),
            )
        template = _ENVIRONMENT.from_string(template_source)
    except TemplateError as error:
        raise PromptRegistryError(
            f"{path}: the template does not compile: {error}", source=str(path)
        ) from error
    variables = meta.find_undeclared_variables(tree) - _GLOBAL_NAMES
    return template, frozenset(variables)


def _canonical(value: JsonValue) -> JsonValue:
    """`value` with every mapping's keys in sorted order, so iteration order cannot reach the text."""
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value
