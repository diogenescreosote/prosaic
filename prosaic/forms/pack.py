"""The form pack interface.

A pack is the unit of jurisdiction- and practice-area-specific knowledge:
a set of form definitions, each declaring its number and title, the
packaged blank PDF, the type of its context object, and the mapping from
the case model plus that context to concrete field values. The engine
knows how to fill AcroForms; only packs know what any field means.

Contexts carry the per-filing decisions a case model cannot know (which
party files, what a declaration says, the date of signing). Each form
declares its context type and checks it at runtime, so a pack stays a
plain data structure while misuse fails loudly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources

from prosaic.forms.acroform import fill_acroform
from prosaic.model import Matter


class FormValidationError(ValueError):
    """The matter or context lacks something the form requires."""

    def __init__(self, form_number: str, problems: list[str]) -> None:
        self.form_number = form_number
        self.problems = problems
        super().__init__(f"{form_number}: " + "; ".join(problems))


class FormContextError(TypeError):
    """A form was invoked with the wrong context type."""


@dataclass(frozen=True, slots=True)
class FilledForm:
    """The result of rendering one form: the values written and the PDF."""

    number: str
    title: str
    values: dict[str, str | bool]
    pdf: bytes


@dataclass(frozen=True, slots=True)
class Form:
    """One form of a pack."""

    number: str
    title: str
    package: str
    resource: str
    context_type: type[object]
    build_values: Callable[[Matter, object], dict[str, str | bool]]

    def blank(self) -> bytes:
        return resources.files(self.package).joinpath(self.resource).read_bytes()

    def fill(self, matter: Matter, context: object) -> FilledForm:
        values = self.build_values(matter, context)
        return FilledForm(
            number=self.number,
            title=self.title,
            values=values,
            pdf=fill_acroform(self.blank(), values),
        )


def define_form[C](
    *,
    number: str,
    title: str,
    package: str,
    resource: str,
    context_type: type[C],
    build: Callable[[Matter, C], dict[str, str | bool]],
) -> Form:
    """Wrap a typed builder as a ``Form``.

    The adapter is where static typing meets the registry: builders keep
    their precise context parameter, and the runtime check here is what
    makes calling through the type-erased ``Form`` safe.
    """

    def build_values(matter: Matter, context: object) -> dict[str, str | bool]:
        if not isinstance(context, context_type):
            raise FormContextError(
                f"{number} takes a {context_type.__name__}, got {type(context).__name__}"
            )
        return build(matter, context)

    return Form(
        number=number,
        title=title,
        package=package,
        resource=resource,
        context_type=context_type,
        build_values=build_values,
    )


@dataclass(frozen=True, slots=True)
class FormPack:
    """A named collection of forms for one jurisdiction and practice area."""

    name: str
    jurisdiction: str
    forms: tuple[Form, ...]

    def form(self, number: str) -> Form:
        for candidate in self.forms:
            if candidate.number == number:
                return candidate
        raise KeyError(number)
