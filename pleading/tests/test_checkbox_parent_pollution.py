"""Checking a checkbox must not write /V on a shared parent node.

JC forms group unrelated fields under one parent (one such form's Li1
holds a name text field beside a group of checkboxes). PDF children inherit a
missing /V from their parent, so a /V='/1' written on the group node made
every untouched sibling text field display '1'. The /V belongs on the
nearest node with its own /T -- the field itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pypdf.generic import DictionaryObject, NameObject, TextStringObject

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from form_fill import _checkbox_field_node


def _node(name=None, parent=None):
    d = DictionaryObject()
    if name is not None:
        d[NameObject("/T")] = TextStringObject(name)
    if parent is not None:
        d[NameObject("/Parent")] = parent
    return d


def test_widget_with_own_T_is_the_field():
    group = _node("Li1")
    cb = _node("Petitioner_cb1", parent=group)
    assert _checkbox_field_node(cb) is cb


def test_bare_widget_defers_to_named_ancestor():
    field = _node("cb_field")
    widget = _node(parent=field)
    assert _checkbox_field_node(widget) is field


def test_group_parent_never_receives_V():
    group = _node("Li1")
    sibling_text = _node("NameOfParty_ft", parent=group)
    cb = _node("Petitioner_cb1", parent=group)
    target = _checkbox_field_node(cb)
    target[NameObject("/V")] = NameObject("/1")
    assert "/V" not in group, "group node polluted: siblings would inherit '1'"
    assert "/V" not in sibling_text


if __name__ == "__main__":
    test_widget_with_own_T_is_the_field()
    test_bare_widget_defers_to_named_ancestor()
    test_group_parent_never_receives_V()
    print("checkbox parent-pollution tests passed")
