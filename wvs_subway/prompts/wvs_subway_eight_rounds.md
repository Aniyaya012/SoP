# WVS 八轮地铁危机场景提示词

本文给出审稿包使用的固定场景与决策提示，不包含真实人口画像、模型回答或运行结果。英文事件内容保留原文。

默认人工示例档案的 z-score 相对 64 条人工档案计算。实际请求会额外注明这一点；自行准备的 WVS 档案则按完整清洗后的 WVS 来源池标准化。

运行时事件来自同级上层的 `scenario_stages.jsonl`，共同提示和上一轮状态规则由 `sop/scenario.py` 构造。

## 逐轮使用方式

- 共八轮，每个参与者每轮作出一次选择。
- 第 r 轮提供第 1 至第 r 轮的全部事件文本，按顺序累计；不提供未来事件。
- 第一轮不提供先前态度；第二至第八轮仅提供该参与者上一轮的选择及选项文本，不提供完整历史选择序列。
- 每轮提供当前参与者 18 个可解释 WVS 字段的数值画像及固定字段说明，不提供 `N_REGION_WVS`、其他参与者的态度或社交网络信息。
- 下面八段是每轮新增的场景文本。完整请求还需要共同提示、画像、上一轮选择和累计事件。

## 共同 System 提示

```text
You are a rational decision maker. Make a judgment based on your background, experience, and all known information.
```

## 共同 User 提示模板

尖括号中的内容是文档占位符，使用时替换成相应输入。字段说明取自同目录的 `wvs_feature_explanation_prompt_zh.md`。

```text
You are an ordinary online user following this event.

<WVS 字段解释原文>

Agent profile:
raw_features: <当前参与者的清洗后原始字段值 JSON>
feature_response_status: <当前参与者各字段回答状态 JSON>
standardized_features (z-scores): <当前参与者标准化字段值 JSON>

Previous attitude:
<第一轮提示或上一轮选择提示>

Known event history through round <r>:
<第 1 至第 r 轮累计事件文本>

Please choose one option from the following mutually exclusive list:
1. Fully support the current government response and trust that the government will handle the crisis properly.
2. Generally support the government response, but ask for more transparency and public participation.
3. Stay neutral and wait for more information before deciding.
4. Have substantial doubts about the government response and ask for reassessment.
5. Completely distrust the government's handling capacity and demand an independent third-party investigation.

Decision requirements: consider your own background and standpoint; consider all previous events rather than only the current message; your view may change as the event develops.

Return JSON only: {"decision":"1","reasoning":"brief reason grounded in the agent profile"}
```

最后一行的 JSON 为现有提示中的格式示例，`decision` 的有效取值为字符串 `"1"` 至 `"5"`，不是固定选择 `"1"`。

第一轮的先前态度提示原文：

```text
No previous attitude is available because this is the first round.
```

第二至第八轮的先前态度提示格式：

```text
Your previous-round choice was <上一轮选项编号>. <对应选项的英文全文>
```

累计事件中的每一项均使用 `Event <轮次> - <标题>:` 开头，后接场景正文；事件之间空一行。以下代码块已包含这一前缀，可按轮次依次拼接。

## 第一轮：地铁毒气事件

```text
Event 1 - Subway gas attack:
Subway gas attack. During the morning rush hour, a suspected toxic-gas leak occurs on a subway platform. Twelve people die, more than 200 are hospitalized, and more than 30 are in critical condition. The subway line is shut down and panic spreads. Social media circulates competing explanations: a terrorist attack, a chemical leak, or an accident caused by aging subway infrastructure.
```

## 第二轮：官方定性

```text
Event 2 - Official classification:
Official classification. Police classify the event as an organized terrorist attack and identify a suspect described as an outsider with extremist views. Anonymous claims suggest the suspect may instead be a dismissed subway maintenance worker seeking revenge. Officials announce a special task force and ask residents not to spread rumors.
```

## 第三轮：全市安保升级

```text
Event 3 - Citywide security escalation:
Citywide security escalation. The government launches a top-level counter-terror response: subway passengers must arrive 30 minutes early for security checks, temporary checkpoints appear at malls and schools, and migrant workers must re-register identity information. Some residents ask whether the registration policy is discriminatory. Officials frame the measures as temporary public-safety protections.
```

## 第四轮：经济冲击

```text
Event 4 - Economic shock:
Economic shock. One week later, subway ridership falls by 60%, businesses along the line lose half their revenue, and some foreign firms consider reducing investment. The city announces subsidies, but large chain firms receive more than small shops. Delivery workers become essential while their labor protections remain weak. Officials state that recovery funds will prioritize small firms and individual businesses.
```

## 第五轮：内部报告泄露

```text
Event 5 - Leaked internal report:
Leaked internal report. A leaked subway safety audit claims that engineers warned about serious ventilation defects three months before the attack, but management postponed repairs because of budget constraints. The subway company calls the document fake but provides no counter-evidence. Victims' families demand a thorough investigation. Officials say they are verifying the document.
```

## 第六轮：国际反应

```text
Event 6 - International reaction:
International reaction. Several countries issue travel warnings and some flights are suspended. An international human-rights organization calls for protection of citizens' rights to information and safety. The foreign ministry rejects politicization of a security incident. Domestic opinion divides between supporting the official stance and welcoming international supervision.
```

## 第七轮：问责风暴

```text
Event 7 - Accountability storm:
Accountability storm. The provincial discipline commission investigates the subway group chairman. Public attention shifts to why only one person is being investigated, as media summarize seven major safety accidents in five years and a pattern of temporary dismissal followed by return to office. Families' lawsuits are delayed pending the criminal investigation. Officials promise a thorough disciplinary and judicial process.
```

## 第八轮：重建争议

```text
Event 8 - Reconstruction dispute:
Reconstruction dispute. After one month of shutdown, two camps emerge: an efficiency camp wants rapid reopening to stop economic losses, while a safety camp demands complete safety upgrades even if reopening is delayed by three months. Residents face a trade-off between commute convenience and safety doubts. The city announces a hearing, but the selection of hearing representatives is itself questioned.
```
