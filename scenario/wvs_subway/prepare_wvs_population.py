#!/usr/bin/env python3
"""Prepare local SoP profiles from a personally obtained WVS Wave 7 CSV ZIP."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
import zipfile
from contextlib import contextmanager
from io import TextIOWrapper
from pathlib import Path
from typing import Iterator

SCENARIO_ROOT = Path(__file__).resolve().parent
FEATURE_CODES = tuple(item["code"] for item in json.loads((SCENARIO_ROOT / "wvs_feature_schema.json").read_text(encoding="utf-8"))["features"])


@contextmanager
def csv_rows(source: Path) -> Iterator[csv.DictReader]:
    if source.suffix.lower() == ".csv":
        with source.open(encoding="utf-8-sig", newline="") as handle:
            yield csv.DictReader(handle)
        return
    if source.suffix.lower() != ".zip":
        raise ValueError("WVS source must be a CSV or ZIP containing the official CSV")
    with zipfile.ZipFile(source) as archive:
        for name in sorted(archive.namelist()):
            if not name.lower().endswith(".csv"):
                continue
            with archive.open(name) as binary:
                with TextIOWrapper(binary, encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    if set(FEATURE_CODES).issubset({str(column).strip().upper() for column in reader.fieldnames or []}):
                        yield reader
                        return
    raise ValueError("No CSV in the ZIP contains all 19 required WVS fields")


def clean(code: str, source_value: str | None) -> tuple[int | float, str]:
    try:
        value = float(str(source_value).strip())
        valid = math.isfinite(value) and (value >= 0 or code == "Y003" and value in {-2.0, -1.0})
    except (TypeError, ValueError):
        valid = False
        value = 0.0
    if not valid:
        return 0, "missing_or_special_code"
    return (int(value) if value.is_integer() else value), "observed"


def record(source_row: dict[str, str | None], index: int) -> dict:
    normalized = {str(key).strip().lstrip("\ufeff").upper(): value for key, value in source_row.items() if key is not None}
    values = {code: clean(code, normalized.get(code)) for code in FEATURE_CODES}
    return {
        "source_row_index": index,
        "raw_features": {code: values[code][0] for code in FEATURE_CODES},
        "feature_response_status": {code: values[code][1] for code in FEATURE_CODES},
    }


def build(source: Path, output: Path, count: int, seed: int, mode: str) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    if count < 2 or count > 1_000_000:
        raise ValueError("Population size must be between 2 and 1,000,000")
    source_count = 0
    means = {code: 0.0 for code in FEATURE_CODES}
    m2 = {code: 0.0 for code in FEATURE_CODES}
    with csv_rows(source) as reader:
        if not set(FEATURE_CODES).issubset({str(column).strip().upper() for column in reader.fieldnames or []}):
            raise ValueError("WVS CSV does not contain all 19 required fields")
        for row in reader:
            source_count += 1
            values = record(row, source_count + 1)["raw_features"]
            for code in FEATURE_CODES:
                value = float(values[code])
                delta = value - means[code]
                means[code] += delta / source_count
                m2[code] += delta * (value - means[code])
    if source_count == 0:
        raise ValueError("WVS CSV has no respondent rows")
    if mode == "without_replacement" and count > source_count:
        raise ValueError("Requested more profiles than WVS rows; use --sampling-mode with_replacement")
    rng = random.Random(seed)
    if mode == "without_replacement":
        selected = set(rng.sample(range(source_count), count))
        multiplicities = {index: 1 for index in selected}
    else:
        multiplicities: dict[int, int] = {}
        for _ in range(count):
            index = rng.randrange(source_count)
            multiplicities[index] = multiplicities.get(index, 0) + 1
    profiles = []
    with csv_rows(source) as reader:
        for index, row in enumerate(reader):
            repeat = multiplicities.get(index, 0)
            if repeat == 0:
                continue
            prepared = record(row, index + 2)
            zscores = {}
            for code in FEATURE_CODES:
                deviation = math.sqrt(max(0.0, m2[code] / source_count))
                zscores[code] = round((float(prepared["raw_features"][code]) - means[code]) / deviation, 10) if deviation > 1e-12 else 0.0
            for _ in range(repeat):
                profiles.append({
                    "id": f"wvs-{len(profiles) + 1:06d}",
                    **prepared,
                    "standardized_features": zscores,
                })
    if len(profiles) != count:
        raise RuntimeError("Population selection did not produce the requested size")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in profiles), encoding="utf-8")
    temporary.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("local_inputs/wvs_profiles.jsonl"))
    parser.add_argument("--population-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sampling-mode", choices=("without_replacement", "with_replacement"), default="without_replacement")
    args = parser.parse_args()
    try:
        build(args.source, args.output, args.population_size, args.seed, args.sampling_mode)
        print(f"Prepared {args.population_size} local WVS profiles at {args.output}")
        return 0
    except Exception as exc:
        print(f"WVS preparation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
