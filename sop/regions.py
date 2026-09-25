"""SoP module 4: program-induced regions and conditional transitions."""

from __future__ import annotations

from typing import Any

import numpy as np

from .program import Program
from .scenario import Context


def prototype(profile: dict[str, Any], attribute: str, threshold: float) -> str:
    return "1" if float(profile["standardized_features"][attribute]) >= threshold else "0"


def _probabilities(choices: list[str]) -> list[float]:
    if not choices:
        raise ValueError("A region cannot be empty")
    return [sum(choice == str(code) for choice in choices) / len(choices) for code in range(1, 6)]


def _impurity(
    members: list[dict[str, Any]], program: Program, contexts: dict[int, Context]
) -> float:
    cells = []
    for context in contexts.values():
        for previous in (None, "1", "2", "3", "4", "5"):
            choices = [program.predict(profile, context, previous) for profile in members]
            cells.append(1.0 - max(_probabilities(choices)))
    return float(np.mean(cells))


def _leaf(members: list[dict[str, Any]], program: Program, contexts: dict[int, Context], leaf_id: str) -> dict[str, Any]:
    first = contexts[1]
    initial = _probabilities([program.predict(profile, first, None) for profile in members])
    transitions = {}
    for round_index, context in contexts.items():
        if round_index == 1:
            continue
        transitions[str(round_index)] = [
            _probabilities([program.predict(profile, context, str(previous)) for profile in members])
            for previous in range(1, 6)
        ]
    return {
        "type": "leaf", "leaf_id": leaf_id,
        "member_count": len(members),
        "initial_distribution": initial,
        "transition_matrices": transitions,
    }


def build_regions(
    train_profiles: list[dict[str, Any]],
    programs: dict[str, Program],
    attribute: str,
    threshold: float,
    contexts: dict[int, Context],
) -> dict[str, Any]:
    trees: dict[str, Any] = {}
    for code in ("0", "1"):
        members = [profile for profile in train_profiles if prototype(profile, attribute, threshold) == code]
        if not members:
            raise ValueError(f"No training members for prototype {code}")
        program = programs[code]
        fields = program.static_fields or (attribute,)
        leaf_serial = 0
        leaf_count = 1

        def grow(rows: list[dict[str, Any]], depth: int) -> dict[str, Any]:
            nonlocal leaf_serial, leaf_count
            parent_impurity = _impurity(rows, program, contexts)
            best: tuple[float, str, float, list[dict[str, Any]], list[dict[str, Any]]] | None = None
            if depth < 6 and leaf_count < 8 and len(rows) >= 16:
                for field in fields:
                    values = [float(row["standardized_features"][field]) for row in rows]
                    split = float(np.median(values))
                    left = [row for row in rows if float(row["standardized_features"][field]) < split]
                    right = [row for row in rows if float(row["standardized_features"][field]) >= split]
                    if min(len(left), len(right)) < 8:
                        continue
                    child_impurity = (
                        len(left) * _impurity(left, program, contexts)
                        + len(right) * _impurity(right, program, contexts)
                    ) / len(rows)
                    gain = parent_impurity - child_impurity
                    if gain > 0.002 and (best is None or gain > best[0]):
                        best = (gain, field, split, left, right)
            if best is None:
                leaf_serial += 1
                return _leaf(rows, program, contexts, f"{code}-{leaf_serial:03d}")
            _, field, split, left, right = best
            leaf_count += 1
            return {
                "type": "split", "field": field, "threshold": split,
                "left": grow(left, depth + 1),
                "right": grow(right, depth + 1),
            }

        trees[code] = grow(members, 0)
    return {"selected_attribute": attribute, "prototype_threshold": threshold, "trees": trees}


def assign_leaf(tree: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    node = tree
    while node["type"] == "split":
        value = float(profile["standardized_features"][node["field"]])
        node = node["left"] if value < float(node["threshold"]) else node["right"]
    return node
