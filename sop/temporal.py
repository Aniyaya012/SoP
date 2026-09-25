"""SoP module 5: context-aware blocks and region-mass propagation."""

from __future__ import annotations

from typing import Any

import numpy as np

from .regions import assign_leaf, prototype
from .scenario import Context


def plan_blocks(contexts: dict[int, Context]) -> list[dict[str, int]]:
    ordered = sorted(contexts)
    if not ordered:
        raise ValueError("Temporal propagation requires events")
    blocks: list[dict[str, int]] = []
    start = ordered[0]
    for round_index in ordered[1:]:
        if contexts[round_index].signature != contexts[start].signature:
            blocks.append({"start_round": start, "end_round": round_index - 1})
            start = round_index
    blocks.append({"start_round": start, "end_round": ordered[-1]})
    return blocks


def propagate(
    profiles: list[dict[str, Any]],
    region_registry: dict[str, Any],
    contexts: dict[int, Context],
) -> dict[str, Any]:
    trees = region_registry["trees"]
    attribute = region_registry["selected_attribute"]
    threshold = float(region_registry["prototype_threshold"])
    groups: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        code = prototype(profile, attribute, threshold)
        leaf = assign_leaf(trees[code], profile)
        key = leaf["leaf_id"]
        if key not in groups:
            groups[key] = {"leaf": leaf, "population": 0, "mass": None}
        groups[key]["population"] += 1

    round_masses: dict[str, list[float]] = {}
    for round_index in sorted(contexts):
        aggregate = np.zeros(5, dtype=np.float64)
        for group in groups.values():
            leaf = group["leaf"]
            if round_index == 1:
                mass = group["population"] * np.asarray(leaf["initial_distribution"], dtype=np.float64)
            else:
                matrix = np.asarray(leaf["transition_matrices"][str(round_index)], dtype=np.float64)
                if matrix.shape != (5, 5) or not np.allclose(matrix.sum(axis=1), 1.0):
                    raise ValueError("Invalid region transition matrix")
                mass = group["mass"] @ matrix
            group["mass"] = mass
            aggregate += mass
        if not np.isclose(aggregate.sum(), len(profiles)):
            raise ValueError("Region mass was not conserved")
        round_masses[str(round_index)] = aggregate.tolist()
    return {"time_blocks": plan_blocks(contexts), "population_masses": round_masses}
