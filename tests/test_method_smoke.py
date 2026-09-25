"""A network-free whole-method check using synthetic responses."""

from __future__ import annotations

import asyncio
import argparse
import csv
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
import run_sop
from sop.api import ChatAPI
from sop.data import load_profiles
from sop.program import validate_source
from scenario.wvs_subway.prepare_wvs_population import build as prepare_wvs

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenario" / "wvs_subway"
PROFILES = ROOT / "examples" / "demo_profiles.jsonl"


class FakeAPI:
    model = "local-smoke"
    url = "https://local.invalid/v1/chat/completions"

    def __init__(self, *_args):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    async def ask(self, messages, *, max_tokens=1400):
        system = messages[0]["content"]
        user = messages[1]["content"]
        if system.startswith("You are a rational decision maker"):
            round_index = int(user.split("Known event history through round ")[1].split(":", 1)[0])
            agent = int(user.split('"X003R":')[1].split(",", 1)[0])
            return {"decision": str(1 + (round_index + agent) % 5)}
        if "因素分析器" in system:
            return {"pairs": [
                {"event": "uncertainty", "attribute": "SCEPTICISM"},
                {"event": "accountability", "attribute": "Q55"},
                {"event": "transparency", "attribute": "EQUALITY"},
                {"event": "security_restriction", "attribute": "AUTONOMY"},
            ]}
        if "受控预决策" in system:
            payload = json.loads(user.split("标准化个体属性：")[1].split("\n")[0])
            event = json.loads(user.split("当前事件：")[1].split("\n")[0])
            value = payload["SCEPTICISM"] + event["uncertainty"]
            return {"decision": str(2 if value < 0.5 else 4)}
        if "自然语言规则归纳" in system:
            return {"rules": ["较高的怀疑性和不确定性可能增加疑虑。"]}
        if "决策规则整理" in system:
            return {"global_rules": ["上一轮选择可能影响下一轮。"], "shared_rules": [], "prototype_rules": {"0": ["保持可更新的决策。"], "1": ["保持可更新的决策。"]}}
        if "决策程序结构生成" in system:
            return {"candidates": [
                {"source": "def score(x, event, cumulative, previous_choice, previous_missing, p):\n    return p[0] + p[1] * x['SCEPTICISM'] + p[2] * event['uncertainty'] + p[3] * previous_choice"},
                {"source": "def score(x, event, cumulative, previous_choice, previous_missing, p):\n    base = p[0] + p[1] * x['SCEPTICISM'] + p[2] * previous_choice\n    if event['accountability'] >= 0.5:\n        return base + p[3] * event['accountability']\n    return base"},
            ]}
        raise AssertionError(f"Unexpected prompt: {system}")


class MethodSmokeTest(unittest.TestCase):
    def test_openai_compatible_request(self):
        def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer reviewer-test-key")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "reviewer-model")
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"decision":"3"}'}}]})

        async def task():
            async with ChatAPI("https://local.invalid/v1", "reviewer-model", "REVIEWER_TEST_KEY", 2) as api:
                await api.client.aclose()
                api.client = httpx.AsyncClient(
                    transport=httpx.MockTransport(respond),
                    headers={"Authorization": "Bearer reviewer-test-key"},
                )
                return await api.ask([{"role": "user", "content": "Choose"}])

        with patch.dict(os.environ, {"REVIEWER_TEST_KEY": "reviewer-test-key"}):
            self.assertEqual(asyncio.run(task()), {"decision": "3"})

    def test_generated_program_rejects_import(self):
        with self.assertRaises(ValueError):
            validate_source("def score(x, event, cumulative, previous_choice, previous_missing, p):\n    import os\n    return p[0]")

    def test_complete_synthetic_path(self):
        profiles = load_profiles(PROFILES, SCENARIO / "wvs_feature_schema.json")
        self.assertEqual(len(profiles), 64)
        self.assertTrue(any(
            profile["feature_response_status"]["Q55"] == "missing_or_special_code"
            for profile in profiles
        ))
        with tempfile.TemporaryDirectory() as temporary, patch.object(run_sop, "ChatAPI", FakeAPI):
            root = Path(temporary)
            args = argparse.Namespace(
                profiles=PROFILES,
                output_dir=root,
                train_count=48,
                api_base_url="https://local.invalid/v1",
                model="local-smoke",
                api_key_env="FAKE_KEY",
                concurrency=8,
                resume=False,
                check_inputs=False,
            )
            asyncio.run(run_sop.run(args))
            result = json.loads((root / "module5.json").read_text(encoding="utf-8"))
            self.assertEqual(len(result["time_blocks"]), 8)
            self.assertEqual(len(result["population_masses"]), 8)
            for mass in result["population_masses"].values():
                self.assertAlmostEqual(sum(mass), 64)
            for index in range(1, 6):
                self.assertTrue((root / f"module{index}.json").is_file())
            with self.assertRaises(FileExistsError):
                asyncio.run(run_sop.run(args))
            args.resume = True
            asyncio.run(run_sop.run(args))

    def test_wvs_input_preparation(self):
        codes = [item["code"] for item in json.loads((SCENARIO / "wvs_feature_schema.json").read_text(encoding="utf-8"))["features"]]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            csv_path = root / "wave7.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=codes)
                writer.writeheader()
                for index in range(80):
                    row = {code: index % 7 for code in codes}
                    row["Y003"] = -2 if index == 0 else index % 5 - 2
                    row["Q55"] = -1 if index == 0 else index % 4 + 1
                    writer.writerow(row)
            archive_path = root / "wave7.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.write(csv_path, arcname="official.csv")
            output = root / "profiles.jsonl"
            prepare_wvs(archive_path, output, 64, 42, "without_replacement")
            profiles = load_profiles(output, SCENARIO / "wvs_feature_schema.json")
            self.assertEqual(len(profiles), 64)
            self.assertEqual(len({row["source_row_index"] for row in profiles}), 64)
            self.assertTrue(all(row["raw_features"]["Y003"] >= -2 for row in profiles))
            with self.assertRaises(FileExistsError):
                prepare_wvs(archive_path, output, 64, 42, "without_replacement")
