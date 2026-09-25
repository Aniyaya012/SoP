"""Read and validate reviewer-owned profiles and eight-round decisions."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

DECISIONS = ("1", "2", "3", "4", "5")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Every JSONL row must be an object: {path}")
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_profiles(path: Path, feature_schema: Path) -> list[dict[str, Any]]:
    schema = json.loads(feature_schema.read_text(encoding="utf-8"))
    codes = {str(item["code"]) for item in schema["features"]}
    if len(codes) != 19:
        raise ValueError("The WVS profile schema must contain 19 distinct fields")
    profiles = read_jsonl(path)
    if len(profiles) < 2:
        raise ValueError("At least two profiles are required")
    identifiers: set[str] = set()
    for profile in profiles:
        identifier = profile.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("Profile IDs must be unique nonempty strings")
        identifiers.add(identifier)
        for field in ("raw_features", "feature_response_status", "standardized_features"):
            values = profile.get(field)
            if not isinstance(values, dict) or set(values) != codes:
                raise ValueError(f"Profile {identifier} needs all 19 {field} fields")
        for code in codes:
            raw = profile["raw_features"][code]
            standardized = profile["standardized_features"][code]
            if isinstance(raw, bool) or isinstance(standardized, bool):
                raise ValueError(f"Profile {identifier} has an invalid numeric value for {code}")
            if not all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in (raw, standardized)):
                raise ValueError(f"Profile {identifier} has an invalid numeric value for {code}")
            if profile["feature_response_status"][code] not in {"observed", "missing_or_special_code"}:
                raise ValueError(f"Profile {identifier} has an invalid response status for {code}")
    return profiles


def split_profiles(profiles: list[dict[str, Any]], train_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not 1 <= train_count < len(profiles):
        raise ValueError("--train-count must leave at least one train and one validation profile")
    ordered = sorted(profiles, key=lambda row: hashlib.sha256(row["id"].encode()).hexdigest())
    return ordered[:train_count], ordered[train_count:]


def validate_decision_rows(
    rows: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    round_index: int,
    previous: dict[str, str] | None,
) -> dict[str, str]:
    expected_ids = {row["id"] for row in profiles}
    decisions: dict[str, str] = {}
    for row in rows:
        agent_id = str(row.get("agent_id") or "")
        choice = str(row.get("decision") or "")
        prior = row.get("previous_decision")
        if agent_id not in expected_ids or agent_id in decisions:
            raise ValueError(f"Invalid or duplicate agent ID in round {round_index}: {agent_id}")
        if choice not in DECISIONS:
            raise ValueError(f"Invalid choice in round {round_index}: {choice}")
        if round_index == 1 and prior is not None:
            raise ValueError("Round 1 previous_decision must be null")
        if round_index > 1 and (previous is None or str(prior) != previous[agent_id]):
            raise ValueError(f"Round {round_index} previous_decision does not match the prior round for {agent_id}")
        decisions[agent_id] = choice
    if set(decisions) != expected_ids:
        raise ValueError(f"Round {round_index} is incomplete")
    return decisions


def load_reference(root: Path, profiles: list[dict[str, Any]], round_count: int) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    previous = None
    for round_index in range(1, round_count + 1):
        path = root / f"round_{round_index:03d}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"Missing local reference decisions: {path}")
        previous = validate_decision_rows(read_jsonl(path), profiles, round_index, previous)
        result[round_index] = previous
    return result
