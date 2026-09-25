"""SoP modules 1–3: factor pretests, rules, and decision programs."""

from __future__ import annotations

import asyncio
import json
import math
from collections import defaultdict
from pathlib import Path
from string import Template
from typing import Any

import numpy as np

from .api import ChatAPI
from .data import DECISIONS, write_json
from .program import Program, STATIC_FIELDS, fit_program, normalizers, validate_source
from .scenario import CUMULATIVE_FIELDS, EVENT_FIELDS, Context


def _messages(templates: dict[str, Any], name: str, **values: str) -> list[dict[str, str]]:
    item = templates[name]
    return [
        {"role": "system", "content": Template(item["system"]).substitute(values)},
        {"role": "user", "content": Template(item["user"]).substitute(values)},
    ]


def _prototype(profile: dict[str, Any], attribute: str, threshold: float) -> str:
    return "1" if float(profile["standardized_features"][attribute]) >= threshold else "0"


def _cases(
    profiles: list[dict[str, Any]],
    reference: dict[int, dict[str, str]],
    contexts: dict[int, Context],
    attribute: str,
    threshold: float,
) -> dict[str, list[tuple[dict[str, Any], Context, str | None, str]]]:
    result: dict[str, list[tuple[dict[str, Any], Context, str | None, str]]] = {"0": [], "1": []}
    for profile in profiles:
        agent_id = profile["id"]
        code = _prototype(profile, attribute, threshold)
        for round_index, context in sorted(contexts.items()):
            previous = None if round_index == 1 else reference[round_index - 1][agent_id]
            result[code].append((profile, context, previous, reference[round_index][agent_id]))
    return result


def _rule_case(item: tuple[dict[str, Any], Context, str | None, str], attribute: str) -> dict[str, Any]:
    profile, context, previous, target = item
    keys = sorted({attribute, "SCEPTICISM", "I_AUTHORITY", "Q55", "EQUALITY"})
    return {
        "round": context.round,
        "previous": previous,
        "event": context.current,
        "attributes": {key: profile["standardized_features"][key] for key in keys},
        "decision": target,
    }


def _clean_rules(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if isinstance(item, str) and item.strip()))


async def compile_behavior(
    api: ChatAPI,
    train_profiles: list[dict[str, Any]],
    validation_profiles: list[dict[str, Any]],
    reference: dict[int, dict[str, str]],
    contexts: dict[int, Context],
    events: list[dict[str, Any]],
    event_definitions: dict[str, str],
    prompt_file: Path,
    output_root: Path,
) -> tuple[str, float, dict[str, Program]]:
    templates = json.loads(prompt_file.read_text(encoding="utf-8"))
    scenario = "\n".join(f"{row['round']}. {row['title']}: {row['stage_text']}" for row in events)
    pair_request = _messages(
        templates, "module1_pairs", scenario=scenario,
        event_definitions=json.dumps(event_definitions, ensure_ascii=False),
        attributes=json.dumps(STATIC_FIELDS, ensure_ascii=False),
    )
    pairs: list[dict[str, str]] = []
    for _ in range(3):
        pair_payload = await api.ask(pair_request)
        seen: set[tuple[str, str]] = set()
        pairs = []
        for item in pair_payload.get("pairs", []):
            if not isinstance(item, dict):
                continue
            event, attribute = str(item.get("event") or ""), str(item.get("attribute") or "")
            if event in EVENT_FIELDS and attribute in STATIC_FIELDS and (event, attribute) not in seen:
                pairs.append({"event": event, "attribute": attribute, "reason": str(item.get("reason") or "")})
                seen.add((event, attribute))
        if len(pairs) >= 2:
            break
    if len(pairs) < 2:
        raise ValueError("Module 1 API response must contain at least two valid candidate pairs")
    pairs = pairs[:4]
    medians = {
        code: float(np.median([float(profile["standardized_features"][code]) for profile in train_profiles]))
        for code in STATIC_FIELDS
    }

    async def predecision(pair: dict[str, str], round_index: int, event_level: float, attribute_level: float) -> str:
        context = contexts[round_index]
        event = dict(context.current)
        event[pair["event"]] = event_level
        attributes = dict(medians)
        attributes[pair["attribute"]] = attribute_level
        previous = None if round_index == 1 else ("3" if round_index == 4 else "4")
        request = _messages(
            templates, "module1_decision",
            event=json.dumps(event, ensure_ascii=False, sort_keys=True),
            cumulative=json.dumps(context.cumulative, ensure_ascii=False, sort_keys=True),
            profile=json.dumps(attributes, ensure_ascii=False, sort_keys=True),
            previous=str(previous),
        )
        for _ in range(3):
            payload = await api.ask(request, max_tokens=300)
            decision = str(payload.get("decision") or "")
            if decision in DECISIONS:
                return decision
        raise ValueError("Module 1 API returned no valid predecision")

    scores: dict[str, list[float]] = defaultdict(list)
    for pair in pairs:
        values = np.asarray([float(row["standardized_features"][pair["attribute"]]) for row in train_profiles])
        low, high = np.quantile(values, [0.25, 0.75]).tolist()
        if math.isclose(low, high):
            continue
        jobs = [
            predecision(pair, round_index, event_level, attribute_level)
            for round_index in (1, 4, 7)
            for event_level in (0.1, 0.9)
            for attribute_level in (low, high)
        ]
        decisions = await asyncio.gather(*jobs)
        changes = [float(decisions[index] != decisions[index + 1]) for index in range(0, len(decisions), 2)]
        magnitudes = [abs(int(decisions[index]) - int(decisions[index + 1])) / 4 for index in range(0, len(decisions), 2)]
        scores[pair["attribute"]].append(0.7 * float(np.mean(changes)) + 0.3 * float(np.mean(magnitudes)))
    if not scores:
        raise ValueError("Module 1 found no variable candidate attributes")
    attribute = sorted(scores, key=lambda name: (-float(np.mean(scores[name])), name))[0]
    threshold = medians[attribute]
    train_cases = _cases(train_profiles, reference, contexts, attribute, threshold)
    if any(not train_cases[code] for code in ("0", "1")):
        raise ValueError("The selected prototype attribute did not divide the training population")
    write_json(output_root / "module1.json", {
        "selected_attribute": attribute,
        "prototype_threshold": threshold,
        "candidate_pairs": pairs,
        "pretest_rounds": [1, 4, 7],
    })

    rules_by_prototype: dict[str, list[str]] = {"0": [], "1": []}
    for code in ("0", "1"):
        cases = train_cases[code]
        budget = min(len(cases), max(1, int(math.floor(0.2 * len(cases)))))
        cursor = 0
        while cursor < budget:
            size = 32 if cursor == 0 else 16
            batch = cases[cursor : min(cursor + size, budget)]
            cursor += len(batch)
            request = _messages(
                templates, "module2_rules", prototype=code,
                attribute_rule=f"{attribute} {'>=' if code == '1' else '<'} {threshold}",
                cases=json.dumps([_rule_case(item, attribute) for item in batch], ensure_ascii=False),
            )
            rules = []
            for _ in range(3):
                payload = await api.ask(request, max_tokens=1800)
                rules = _clean_rules(payload.get("rules"))
                if rules:
                    break
            for rule in rules:
                if rule not in rules_by_prototype[code]:
                    rules_by_prototype[code].append(rule)
    consolidated = await api.ask(_messages(
        templates, "module2_consolidate", rules=json.dumps(rules_by_prototype, ensure_ascii=False)
    ), max_tokens=1800)
    global_rules = _clean_rules(consolidated.get("global_rules"))
    shared_rules = _clean_rules(consolidated.get("shared_rules"))
    specific = consolidated.get("prototype_rules", {})
    if not isinstance(specific, dict):
        specific = {}
    for code in ("0", "1"):
        specific[code] = _clean_rules(specific.get(code)) or rules_by_prototype[code]
    if not (global_rules or shared_rules or any(specific.values())):
        raise ValueError("Module 2 API produced no usable rules")
    write_json(output_root / "module2.json", {
        "global_rules": global_rules,
        "shared_rules": shared_rules,
        "prototype_rules": specific,
    })

    bounds = normalizers(train_profiles)
    validation_cases = _cases(validation_profiles, reference, contexts, attribute, threshold)
    programs: dict[str, Program] = {}
    for code in ("0", "1"):
        all_rules = global_rules + shared_rules + specific[code]
        request = _messages(
            templates, "module3_programs", prototype=code,
            rules=json.dumps(all_rules, ensure_ascii=False),
            attributes=json.dumps(STATIC_FIELDS),
            event_fields=json.dumps(EVENT_FIELDS),
            cumulative_fields=json.dumps(CUMULATIVE_FIELDS),
        )
        sources = []
        for _ in range(3):
            payload = await api.ask(request, max_tokens=3000)
            for item in payload.get("candidates", []):
                if not isinstance(item, dict) or not isinstance(item.get("source"), str):
                    continue
                try:
                    validate_source(item["source"])
                except (SyntaxError, ValueError):
                    continue
                if item["source"] not in sources:
                    sources.append(item["source"])
            if sources:
                break
        if not sources:
            raise ValueError(f"Module 3 API produced no valid program for prototype {code}")
        choices: list[tuple[float, float, Program]] = []
        for index, source in enumerate(sources[:2]):
            program, train_objective = fit_program(source, train_cases[code], bounds, seed=20260924 + int(code) * 2 + index)
            subset = {profile["id"]: profile for profile in validation_profiles if _prototype(profile, attribute, threshold) == code}
            if subset:
                errors = []
                for profile in subset.values():
                    previous = None
                    for round_index, context in sorted(contexts.items()):
                        previous = program.predict(profile, context, previous)
                        errors.append(previous != reference[round_index][profile["id"]])
                selection = float(np.mean(errors))
            else:
                selection = train_objective
            choices.append((selection, train_objective, program))
        choices.sort(key=lambda item: (item[0], item[1], len(item[2].source)))
        programs[code] = choices[0][2]
    write_json(output_root / "module3.json", {code: program.payload() for code, program in programs.items()})
    return attribute, threshold, programs
