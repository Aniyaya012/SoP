"""Generate the reviewer-local eight-round reference decisions."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .api import ChatAPI
from .data import DECISIONS, read_jsonl, sha256_file, validate_decision_rows, write_json, write_jsonl
from .scenario import reference_messages


async def collect_reference(
    api: ChatAPI,
    profiles: list[dict[str, Any]],
    events: list[dict[str, Any]],
    explanation: str,
    output_root: Path,
    profile_path: Path,
    scenario_root: Path,
    *,
    resume: bool,
) -> None:
    reference_root = output_root / "reference"
    manifest_path = reference_root / "input_manifest.json"
    manifest = {
        "profile_sha256": sha256_file(profile_path),
        "event_sha256": sha256_file(scenario_root / "scenario_stages.jsonl"),
        "feature_prompt_sha256": sha256_file(scenario_root / "prompts" / "wvs_feature_explanation_prompt_zh.md"),
        "feature_schema_sha256": sha256_file(scenario_root / "wvs_feature_schema.json"),
        "model": api.model,
        "api_url": api.url,
    }
    if manifest_path.exists():
        if not resume:
            raise FileExistsError(f"Local reference already exists; use --resume or another --output-dir: {reference_root}")
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("--resume inputs or API settings do not match this local reference")
    else:
        if resume and reference_root.exists() and any(reference_root.iterdir()):
            raise ValueError("Cannot resume reference data without an input manifest")
        write_json(manifest_path, manifest)

    previous: dict[str, str] | None = None
    for round_index in range(1, len(events) + 1):
        path = reference_root / f"round_{round_index:03d}.jsonl"
        if path.exists():
            previous = validate_decision_rows(read_jsonl(path), profiles, round_index, previous)
            continue

        async def decide(profile: dict[str, Any]) -> dict[str, Any]:
            agent_id = profile["id"]
            prior = previous[agent_id] if previous is not None else None
            messages = reference_messages(profile, events, round_index, prior, explanation)
            for _ in range(3):
                response = await api.ask(messages, max_tokens=500)
                decision = str(response.get("decision") or "")
                if decision in DECISIONS:
                    return {"agent_id": agent_id, "round": round_index, "decision": decision, "previous_decision": prior}
            raise ValueError(f"API returned no valid decision for {agent_id} in round {round_index}")

        rows = await asyncio.gather(*(decide(profile) for profile in profiles))
        previous = validate_decision_rows(rows, profiles, round_index, previous)
        write_jsonl(path, rows)
