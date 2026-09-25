#!/usr/bin/env python3
"""Build 64 deterministic artificial input profiles; no WVS records are read."""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def raw_profile(index: int) -> dict[str, int | float]:
    return {
        "X003R": 1 + index % 6,
        "Q260": 1 + (index // 3) % 2,
        "Q273": 1 + (index // 5) % 6,
        "Q274": index % 5,
        "Q275": index % 9,
        "N_REGION_WVS": 1 + index % 8,
        "G_TOWNSIZE": 1 + (index * 3) % 8,
        "Q3": 1 + index % 4,
        "Q46": 1 + (index // 2) % 4,
        "Q55": 1 + (index // 4) % 4,
        "Q57": 1 + index % 2,
        "Y003": -2 + index % 5,
        "I_AUTHORITY": round((index * 7 % 23) / 22, 4),
        "I_NATIONALISM": round((index * 11 % 29) / 28, 4),
        "DEFIANCE": round((index * 13 % 31) / 30, 4),
        "SCEPTICISM": round((index * 17 % 37) / 36, 4),
        "AUTONOMY": round((index * 19 % 41) / 40, 4),
        "EQUALITY": round((index * 23 % 43) / 42, 4),
        "I_DEVOUT": round((index * 29 % 47) / 46, 4),
    }


def build() -> list[dict]:
    raw = [raw_profile(index) for index in range(64)]
    statuses = [{code: "observed" for code in raw[0]} for _ in raw]
    for index, row in enumerate(raw):
        if index % 11 == 0:
            row["Q55"] = 0
            statuses[index]["Q55"] = "missing_or_special_code"
        if index % 17 == 0:
            row["Q273"] = 0
            statuses[index]["Q273"] = "missing_or_special_code"
    codes = tuple(raw[0])
    means = {code: sum(float(row[code]) for row in raw) / len(raw) for code in codes}
    deviations = {
        code: math.sqrt(sum((float(row[code]) - means[code]) ** 2 for row in raw) / len(raw))
        for code in codes
    }
    return [
        {
            "id": f"demo-{index + 1:03d}",
            "synthetic_input": True,
            "raw_features": row,
            "feature_response_status": statuses[index],
            "standardized_features": {
                code: round((float(row[code]) - means[code]) / deviations[code], 10) if deviations[code] > 0 else 0.0
                for code in codes
            },
        }
        for index, row in enumerate(raw)
    ]


if __name__ == "__main__":
    target = ROOT / "demo_profiles.jsonl"
    if target.exists():
        raise SystemExit(f"Refusing to overwrite {target}")
    target.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in build()), encoding="utf-8")
    print(f"Created {target}")
