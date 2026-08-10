"""Reading and filling AcroForm PDFs.

Judicial Council forms are AcroForms, some AES-encrypted with an empty user
password, with field appearances left to the viewer. Filling therefore
decrypts with the empty password when needed, writes values through pypdf,
and regenerates appearances so the text is visible in any conforming viewer.

Text fields take strings. Button fields (checkboxes and radio groups) take
their on-state name: ``True`` selects the single on-state of a plain
checkbox, and a radio group with several on-states requires the explicit
state string, because a bare ``True`` would be ambiguous.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pypdf import PdfReader, PdfWriter

_READ_ONLY = 1 << 0
_PUSHBUTTON = 1 << 16


class UnknownFormFieldError(KeyError):
    """A value was supplied for a field the form does not have."""


class FieldValueError(ValueError):
    """A value does not fit its field: wrong type, or not an on-state."""


class FieldKind(StrEnum):
    TEXT = "text"
    BUTTON = "button"


@dataclass(frozen=True, slots=True)
class FormFieldInfo:
    """One fillable field of a form."""

    name: str
    kind: FieldKind
    on_states: frozenset[str]
    tooltip: str


def _open(pdf: bytes) -> PdfReader:
    reader = PdfReader(io.BytesIO(pdf))
    if reader.is_encrypted:
        reader.decrypt("")
    return reader


def _button_states(field: Mapping[str, Any]) -> frozenset[str]:
    # A plain checkbox reports its states directly; a radio group keeps one
    # on-state per kid widget, so collect from both places. pypdf exposes
    # field dictionaries untyped, hence the Any.
    states = {str(state) for state in field.get("/_States_") or ()}
    for kid in field.get("/Kids") or ():
        appearances = kid.get_object().get("/AP")
        if appearances and "/N" in appearances:
            states.update(str(key) for key in appearances["/N"].get_object())
    return frozenset(states) - {"/Off"}


def read_fields(pdf: bytes) -> dict[str, FormFieldInfo]:
    """The fillable fields of a form, excluding read-only text and push buttons."""
    result: dict[str, FormFieldInfo] = {}
    for name, field in (_open(pdf).get_fields() or {}).items():
        field_type = field.get("/FT")
        flags = int(field.get("/Ff") or 0)
        tooltip = str(field.get("/TU") or "")
        if field_type == "/Tx" and not flags & _READ_ONLY:
            result[name] = FormFieldInfo(name, FieldKind.TEXT, frozenset(), tooltip)
        elif field_type == "/Btn" and not flags & _PUSHBUTTON:
            states = _button_states(field)
            if states:
                result[name] = FormFieldInfo(name, FieldKind.BUTTON, states, tooltip)
    return result


def _button_state(info: FormFieldInfo, value: str | bool) -> str:
    if value is False:
        return "/Off"
    if value is True:
        if len(info.on_states) == 1:
            return next(iter(info.on_states))
        raise FieldValueError(
            f"{info.name} has states {sorted(info.on_states)}; "
            "pass the explicit state instead of True"
        )
    if value in info.on_states:
        return value
    raise FieldValueError(f"{value!r} is not an on-state of {info.name}: {sorted(info.on_states)}")


def fill_acroform(pdf: bytes, values: Mapping[str, str | bool]) -> bytes:
    """Fill ``values`` into the form and return the new PDF.

    Every key must name a fillable field and every value must fit it;
    anything else raises rather than producing a silently incomplete form.
    """
    fields = read_fields(pdf)
    unknown = sorted(set(values) - set(fields))
    if unknown:
        raise UnknownFormFieldError(f"form has no fillable fields named {unknown}")

    resolved: dict[str, str] = {}
    for name, value in values.items():
        info = fields[name]
        if info.kind is FieldKind.TEXT:
            if not isinstance(value, str):
                raise FieldValueError(f"{name} is a text field; got {value!r}")
            resolved[name] = value
        else:
            resolved[name] = _button_state(info, value)

    writer = PdfWriter(clone_from=_open(pdf))
    for page in writer.pages:
        writer.update_page_form_field_values(page, resolved, auto_regenerate=True)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def read_filled_values(pdf: bytes) -> dict[str, str]:
    """Current values of all fillable fields, as stored in the PDF."""
    return {
        name: str((_open(pdf).get_fields() or {})[name].get("/V") or "")
        for name in read_fields(pdf)
    }
