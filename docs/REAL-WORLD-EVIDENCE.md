# Real-work evidence / 真实业务历史证据

This release adds **four anonymized workstreams** reconstructed from real project materials, with the owner's authorization to publish sanitized summaries. They are **retrospective evidence**, not synthetic examples, prospective Shadow observations, independent quality scores, or proof of model causality.

本次经资料提供者授权，公开四类真实业务的匿名文字案例：空间视觉改稿、海外内容制作、公开信息研究、翻译校对。它们是**历史回溯证据**，不是新增合成评测、前瞻 Shadow 观测或独立质量成绩。

## What is counted / 统计什么

The [casebook](../data/retrospective/cases.json) contains four workstreams and seven explicitly extracted delivery episodes from the research/translation screenshots. The seven episodes do **not** cover every task in the four workstreams. The [generated report](../data/retrospective/summary.json) counts only these records:

| Observation / 观察 | Count / 数量 | Meaning / 含义 |
| --- | ---: | --- |
| Anonymized workstreams / 匿名业务类别 | 4 | Case coverage, not four trials / 覆盖范围，不是四次实验 |
| Extracted delivery episodes / 已提取交付片段 | 7 | A visible file card/submission, not possession or verification of the attachment / 可见提交，不等于取得或验证附件 |
| Visible requests / 可见需求 | 6 | One episode lacks its original request / 一项缺原始需求 |
| Receipt acknowledgements / 收件回应 | 4 | Receipt or thanks, not quality approval / 收到或致谢，不是质量验收 |
| Chat-span observations / 聊天跨度记录 | 3 | 237, 194, 415 minutes; not AI or human labor time / 分钟间隔，不是模型或人工工时 |
| Eligible prospective Shadow observations / 可计前瞻 Shadow 观测 | 0 | No independently frozen AI/human comparison / 缺独立冻结的 AI 与人工对照 |

First-pass rate, edit distance, risk-miss rate and AI latency remain **null**, not zero or 100%. A file card does not demonstrate content correctness; a sender's completion claim is not customer acceptance. Repeated views of the same submission are counted once. Report formats and image variants are not independent successes.

一次通过率、修改量、风险漏判率、AI 延迟均为 **null**。收件、赞许、格式确认、质量验收和对外发布是不同状态。重叠截图中的同一提交仅计一次；同一报告的多格式文件不计作多次成功。

The three spans come from request and submission markers on the same displayed day, at minute resolution. Calendar dates, names and original filenames are withheld. The source screenshots lack a verified year/timezone and may omit intervening work. These spans include waiting and coordination; there is no baseline for time saved. The casebook also retains follow-ups, an updated delivery estimate, ongoing revisions and missing evidence, rather than selecting only favorable outcomes.

三个间隔仅来自同一显示日期内的需求和提交时间标记。原截图缺可验证年份/时区，可能遗漏中间过程；间隔包含等待与协作，没有节省时间的对照基线。案例同时保留催办、估时更新、改稿和证据缺口。

## Reproduce / 复核

```bash
python3 scripts/retrospective_report.py --input data/retrospective/cases.json
python3 scripts/retrospective_report.py --input data/retrospective/cases.json --check data/retrospective/summary.json
python3 -m unittest discover -s tests -p test_retrospective.py -v
```

The separate retrospective schema rejects fabricated quality fields and does not write to the [Shadow log](SHADOW-METRICS.md). The existing synthetic A/B run and its 28 paired scenarios are unchanged. Counting historical records is deterministic; it does not independently authenticate the private evidence or authorship.

历史统计使用独立 Schema 与脚本，拒绝补造质量字段，不写入 `observed` Shadow 日志，也不增加既有 28 个合成 A/B 场景的样本数。程序复算验证的是输入记录的结构及统计，不是对私有原始资料、制作人或事实内容的外部认证。

## Provenance and publication / 来源与公开范围

- The owner states that some materials were produced by colleagues using the Skill and some with an assistant. Exact artifact-to-author/model/Skill-version attribution is incomplete. The record does not establish how much of an outcome was caused by the Skill.
- Original screenshots, avatars, speakers, customers, brands, research-subject names, project dates, filenames, cloud links/access codes, private paths, thread IDs and original-source hashes are **not published**. The public casebook is a manually generalized text derivative, not a redacted screenshot export.
- Original evidence and the private mapping remain outside the public repository. Owner authorization covers the sanitized case summaries only; it does not grant runtime tool approvals or authorize sending client messages.
- Several historical reports contain source names but lack recovered direct web links/browsing logs. Some screenshot attachments, audio, final subtitles and review outcomes are unavailable. These limitations remain visible.
- Public reviewers can reproduce the aggregate calculation from the anonymous records. They cannot independently inspect the private originals through this repository. This is not a third-party-certified benchmark or a claim that re-identification is impossible.

资料提供者说明产出来源混合；目前无法逐项绑定制作者、模型和 Skill 版本。公开版只保留工作类型、关键判断、观察和缺口，不发布原截图、原附件或身份映射，也不证明 Skill 的因果贡献。原始资料由维护者私有保存；公开可复核的是匿名记录的统计，不能据此宣称第三方认证。

## When actual Shadow metrics become available / 何时能计实测指标

For a new authorized task, freeze the pre-feedback input and AI output before the human outcome is shown; record the actual model/version, timers, reference risk, first-review result and real draft/final edits. Keep the source material private, retain denominators and missing values, and apply the [Shadow measurement contract](SHADOW-METRICS.md). Historical replay can test useful judgment, but it must retain its retrospective label even when a fresh model run is added.

新任务应在看到人工处理结果前冻结输入和 AI 输出，再记录真实模型、计时、人工风险标签、首次审核结果及实际改动。历史回放即使补跑新模型，也仍叫历史回放，不能追认为当时已完成的前瞻 Shadow。
