#!/usr/bin/env python3
"""Run the reviewer-facing SoP method from artificial or locally prepared WVS profiles."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sop.api import ChatAPI
from sop.behavior import compile_behavior
from sop.data import load_profiles, load_reference, split_profiles, write_json
from sop.reference import collect_reference
from sop.regions import build_regions
from sop.scenario import load_scenario
from sop.temporal import propagate

ROOT = Path(__file__).resolve().parent
SCENARIO = ROOT / "scenario" / "wvs_subway"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, default=ROOT / "examples" / "demo_profiles.jsonl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "local_runs" / "demo")
    parser.add_argument("--train-count", type=int, default=48)
    parser.add_argument("--api-base-url", default="https://api.openai.com/v1")
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--check-inputs", action="store_true", help="Validate inputs without API calls or local outputs")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> Path:
    profiles_path = args.profiles.expanduser().resolve()
    profiles = load_profiles(profiles_path, SCENARIO / "wvs_feature_schema.json")
    events, contexts, definitions = load_scenario(SCENARIO)
    train_profiles, validation_profiles = split_profiles(profiles, args.train_count)
    if args.check_inputs:
        print(f"Inputs valid: {len(profiles)} profiles, {len(train_profiles)} train, {len(validation_profiles)} validation, {len(events)} rounds")
        return args.output_dir
    if not args.model:
        raise ValueError("--model is required unless --check-inputs is used")
    output_root = args.output_dir.expanduser().resolve()
    if output_root.exists() and any(output_root.iterdir()) and not args.resume:
        raise FileExistsError(f"Output directory is not empty; use --resume or another --output-dir: {output_root}")
    explanation = (SCENARIO / "prompts" / "wvs_feature_explanation_prompt_zh.md").read_text(encoding="utf-8").strip()
    if not explanation:
        raise ValueError("WVS feature explanation prompt is empty")
    async with ChatAPI(args.api_base_url, args.model, args.api_key_env, args.concurrency) as api:
        await collect_reference(api, profiles, events, explanation, output_root, profiles_path, SCENARIO, resume=args.resume)
        reference = load_reference(output_root / "reference", profiles, len(events))
        attribute, threshold, programs = await compile_behavior(
            api, train_profiles, validation_profiles, reference, contexts, events, definitions,
            SCENARIO / "prompts" / "sop_compilation_prompts_zh.json", output_root,
        )
    registry = build_regions(train_profiles, programs, attribute, threshold, contexts)
    write_json(output_root / "module4.json", registry)
    write_json(output_root / "module5.json", propagate(profiles, registry, contexts))
    return output_root


def main() -> int:
    try:
        args = arguments()
        result = asyncio.run(run(args))
        if not args.check_inputs:
            print(f"SoP method completed: {result}")
        return 0
    except Exception as exc:
        print(f"SoP run failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
