"""Fixed WVS subway scenario and the original eight-round decision prompt."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .data import DECISIONS, read_jsonl

OPTION_TEXT = {
    "1": "Fully support the current government response and trust that the government will handle the crisis properly.",
    "2": "Generally support the government response, but ask for more transparency and public participation.",
    "3": "Stay neutral and wait for more information before deciding.",
    "4": "Have substantial doubts about the government response and ask for reassessment.",
    "5": "Completely distrust the government's handling capacity and demand an independent third-party investigation.",
}
SYSTEM_PROMPT = "You are a rational decision maker. Make a judgment based on your background, experience, and all known information."
EVENT_FIELDS = (
    "severity", "uncertainty", "security_restriction", "economic_disruption", "transparency",
    "accountability", "rights_protection", "international_scrutiny", "reopening_pressure",
)
CUMULATIVE_FIELDS = ("severity", "uncertainty", "economic_disruption", "transparency", "accountability")


@dataclass(frozen=True)
class Context:
    round: int
    stage_id: str
    title: str
    current: dict[str, float]
    cumulative: dict[str, float]

    @property
    def signature(self) -> tuple[float, ...]:
        return tuple(self.current[name] for name in EVENT_FIELDS) + tuple(self.cumulative[name] for name in CUMULATIVE_FIELDS)


def load_scenario(root: Path) -> tuple[list[dict[str, Any]], dict[int, Context], dict[str, str]]:
    events = read_jsonl(root / "scenario_stages.jsonl")
    if len(events) != 8 or [row.get("round") for row in events] != list(range(1, 9)):
        raise ValueError("Scenario must have eight consecutive events")
    features = json.loads((root / "event_features.json").read_text(encoding="utf-8"))
    definitions, values = features["definitions"], features["stage_values"]
    if set(definitions) != set(EVENT_FIELDS):
        raise ValueError("Scenario event feature definitions do not match the method")
    history: dict[str, list[float]] = {name: [] for name in CUMULATIVE_FIELDS}
    contexts: dict[int, Context] = {}
    for event in events:
        stage_id = str(event["stage_id"])
        current = {name: float(values[stage_id][name]) for name in EVENT_FIELDS}
        if any(not 0 <= value <= 1 for value in current.values()):
            raise ValueError(f"Invalid event feature for {stage_id}")
        for name in CUMULATIVE_FIELDS:
            history[name].append(current[name])
        cumulative = {name: sum(series) / len(series) for name, series in history.items()}
        contexts[int(event["round"])] = Context(int(event["round"]), stage_id, str(event["title"]), current, cumulative)
    return events, contexts, definitions


def reference_messages(profile: dict[str, Any], events: list[dict[str, Any]], round_index: int, previous: str | None, explanation: str) -> list[dict[str, str]]:
    if previous is not None and previous not in DECISIONS:
        raise ValueError("Invalid previous choice")
    prior = (
        "No previous attitude is available because this is the first round."
        if previous is None else f"Your previous-round choice was {previous}. {OPTION_TEXT[previous]}"
    )
    history = "\n\n".join(
        f"Event {item['round']} - {item['title']}:\n{item['stage_text']}"
        for item in events if int(item["round"]) <= round_index
    )
    # A country-specific region code has no shared cross-country meaning.
    visible = {
        field: {key: value for key, value in profile[field].items() if key != "N_REGION_WVS"}
        for field in ("raw_features", "feature_response_status", "standardized_features")
    }
    if profile.get("synthetic_input") is True:
        explanation += (
            "\n\n本次为人工示例档案。standardized_features 仅相对这 64 条人工档案标准化，"
            "不代表完整 WVS 样本的总体位置；不得将示例智能体视为真实 WVS 受访者。"
        )
    lines = [
        "You are an ordinary online user following this event.", explanation,
        "Agent profile:",
        "raw_features: " + json.dumps(visible["raw_features"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "feature_response_status: " + json.dumps(visible["feature_response_status"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "standardized_features (z-scores): " + json.dumps(visible["standardized_features"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "Previous attitude:", prior,
        f"Known event history through round {round_index}:", history,
        "Please choose one option from the following mutually exclusive list:",
        "\n".join(f"{code}. {OPTION_TEXT[code]}" for code in DECISIONS),
        "Decision requirements: consider your own background and standpoint; consider all previous events rather than only the current message; your view may change as the event develops.",
        'Return JSON only: {"decision":"1","reasoning":"brief reason grounded in the agent profile"}',
    ]
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "\n\n".join(lines)}]
