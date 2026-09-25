# SoP 审稿运行包

SoP 在 WVS 地铁化学袭击场景中的运行路径。默认输入是 64 条**人工构造**的示例档案，不是 WVS 受访者；示例 z-score 也只相对这 64 条人工档案计算。包内没有预先生成的 LLM 决策、编译程序、轨迹或实验结果。

## 默认规模与流程

- 64 名智能体、8 轮事件；每名智能体每轮调用一次审稿人指定的 LLM，生成本地参考决策。
- 固定按智能体 ID 的哈希排序划分 48 名行为编译智能体和 16 名程序选择智能体；这不是论文测试集。
- 默认最多 2 个原型，区域划分的最小叶节点为 8 人。这些是小规模运行的演示参数，不代表论文实验设置。
- 模块 1 用 LLM 提出因素对并做受控 2×2 预决策；模块 2 从训练决策归纳规则；模块 3 生成、校验并拟合决策程序；模块 4 编译区域与条件转移矩阵；模块 5 传播八轮区域状态。
- 八轮事件上下文各异，当前场景下模块 5 通常得到八个单轮块。

默认路径需要 64 × 8 次参考决策 API 请求，模块 1 至 3 还会请求同一 API。程序不计算或报告调用费用、token 用量、耗时或论文评价指标。

## 直接运行人工示例

需要 Python 3.9+ 和 OpenAI 兼容的 Chat Completions API。密钥只从环境变量读取；命令行参数中的 URL 应为以 `/v1` 结尾的 API 根地址。

```bash
python -m pip install -r requirements.txt
export OPENAI_API_KEY='填写你自己的密钥'
python run_sop.py \
  --api-base-url https://api.openai.com/v1 \
  --model 你的模型名称
```

默认读取 `examples/demo_profiles.jsonl`，在 `local_runs/demo/` 写入审稿人本地的参考决策和方法产物。网络中断后可用原命令加 `--resume` 复用**已完整保存的参考决策轮次**；尚未完成的轮次和模块 1 至 3 会重新请求 API。输入档案、模型和 API 地址必须保持一致。默认并发为 8，可用 `--concurrency` 调小。运行成功后会生成 `module1.json`、`module2.json`、`module3.json`、`module4.json`、`module5.json`。这些文件仅在审稿人本地生成，不随代码包提交。

也可以先用 `--check-inputs` 仅校验示例档案、八轮事件和事件特征；该操作不发起 API 请求。

## 使用自行下载的完整 WVS 数据

先按 [WVS 获取说明](scenario/wvs_subway/download_wvs_wave7.md)下载官方 ZIP，然后生成本地档案：

```bash
python scenario/wvs_subway/prepare_wvs_population.py \
  --source scenario/wvs_subway/data/raw/F00011356-WVS_Cross-National_Wave_7_csv_v6_0.zip \
  --output local_inputs/wvs_profiles.jsonl
python run_sop.py \
  --profiles local_inputs/wvs_profiles.jsonl \
  --output-dir local_runs/wvs \
  --api-base-url https://api.openai.com/v1 \
  --model 你的模型名称
```

准备脚本默认无放回生成 64 名档案。可用 `--population-size` 改变档案人数；方法入口的默认 48/16 划分适用于 64 名档案，其他人数需用 `--train-count` 指定训练人数。完整 WVS 数据不会自动下载，也不会随审稿包上传。

## 文件说明

- `run_sop.py`：唯一运行入口。
- `examples/demo_profiles.jsonl`：64 条人工示例输入；`examples/build_demo_profiles.py` 说明其生成方法。
- `sop/`：API 请求、参考决策生成与校验、五模块方法。
- `scenario/wvs_subway/`：WVS 字段、八轮事件、事件数值特征、提示词和官方数据准备脚本。
- `tests/`：不连接外部 API 的最小运行检查。

本包不包含三个对照方法、论文实验入口、评价代码、实验配置网格、计算成本计数、真实 WVS 原始数据或本项目既有运行结果。

代码采用 Apache 2.0 许可，见本目录的 `LICENSE`。WVS 数据另受其官方使用条件约束。
