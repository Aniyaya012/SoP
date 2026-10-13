# SoP Reviewer Package

**English** | [简体中文](README.zh-CN.md)

This package provides the workflow for running SoP in the WVS subway chemical attack scenario. The default inputs are 64 **manually constructed** example profiles, not WVS respondents. The example z-scores are computed from these 64 artificial profiles. The package does not include pregenerated LLM decisions, compiled decision programs, or trajectories.

## Default Scale and Workflow

- 64 agents and 8 event rounds. Each agent calls the reviewer-selected LLM once per round to generate local reference decisions.
- Agents are sorted by the hash of their IDs and deterministically split into 48 behavior-compilation agents (training set) and 16 program-selection agents (validation set).
- The defaults allow at most 2 prototypes, with a minimum leaf size of 8 agents for region partitioning. These parameters are intended for a small demonstration run and do not represent the experimental settings in the paper.
- Module 1 uses the LLM to propose factor pairs and conduct controlled 2 x 2 predecision tests; Module 2 induces rules from training decisions; Module 3 generates, validates, and fits decision programs; Module 4 compiles regions and conditional transition matrices; Module 5 propagates region states across eight rounds.
- The event context differs across the eight rounds, so Module 5 typically produces eight single-round time blocks in this scenario.

The default workflow requires 64 x 8 API requests for reference decisions. Modules 1 through 3 make additional requests to the same API.

## Run the Artificial Examples

Python 3.9+ and an OpenAI-compatible Chat Completions API are required. The API key is read only from an environment variable. The URL supplied on the command line should be the API base URL ending in `/v1`.

```bash
python -m pip install -r requirements.txt
export OPENAI_API_KEY='your-api-key'
python run_sop.py \
  --api-base-url https://api.openai.com/v1 \
  --model your-model-name
```

By default, the runner reads `examples/demo_profiles.jsonl` and writes reference decisions and method outputs to `local_runs/demo/` on the reviewer's machine. After a network interruption, rerun the same command with `--resume` to reuse **reference-decision rounds that have been fully saved**. Incomplete rounds and Modules 1 through 3 will make API requests again. The input profiles, model, and API base URL must remain the same. The default concurrency is 8; use `--concurrency` to reduce it. A successful run generates `module1.json`, `module2.json`, `module3.json`, `module4.json`, and `module5.json`. These files are generated locally and are not included in the code package.

You can also use `--check-inputs` first to validate only the example profiles, the eight event rounds, and the event features. This operation makes no API requests.

## Use a Locally Downloaded Full WVS Dataset

Download the official ZIP file by following the [WVS download guide (in Chinese)](scenario/wvs_subway/download_wvs_wave7.md), then generate local profiles:

```bash
python scenario/wvs_subway/prepare_wvs_population.py \
  --source scenario/wvs_subway/data/raw/F00011356-WVS_Cross-National_Wave_7_csv_v6_0.zip \
  --output local_inputs/wvs_profiles.jsonl
python run_sop.py \
  --profiles local_inputs/wvs_profiles.jsonl \
  --output-dir local_runs/wvs \
  --api-base-url https://api.openai.com/v1 \
  --model your-model-name
```

The preparation script samples 64 profiles without replacement by default. Use `--population-size` to change the number of profiles. The runner's default 48/16 split applies to 64 profiles; for other population sizes, specify the training count with `--train-count`. The full WVS dataset is not downloaded automatically and is not included in the reviewer package.

## Files

- `run_sop.py`: The sole entry point for running the method.
- `examples/demo_profiles.jsonl`: 64 artificial example inputs; `examples/build_demo_profiles.py` shows how they are generated.
- `sop/`: API requests, reference-decision generation and validation, and the five-module method.
- `scenario/wvs_subway/`: WVS fields, eight event rounds, numerical event features, prompts, and a preparation script for the official WVS dataset.

The code is licensed under Apache 2.0; see [LICENSE](LICENSE). WVS data is separately subject to its official conditions of use.
