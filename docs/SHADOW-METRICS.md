# Shadow Mode measurement / 影子模式指标

This module measures saved observations; it does not contact clients, run a model, authorize a release, or certify that a reviewer is independent. Public examples are **synthetic demonstrations**, including an intentional risk miss. There are **zero observed production events** in this repository. The historical illustrative 38.7/95.7 scores are not inputs to these metrics.

本模块统计已记录的影子观察，不发送客户消息、不调用模型、不授权发布，也不验证审核人的独立性。公开示例全部为**合成演示数据**，其中故意包含一条风险漏判，用于验证指标计算。仓库尚无真实生产观察；历史示意分数 38.7/95.7 不进入统计。

## Run / 运行

Python 3.9+ on macOS/Linux; standard library only. The file lock uses POSIX `flock`.

```bash
python3 scripts/shadow_metrics.py report --log examples/shadow/synthetic-events.jsonl
python3 -m unittest discover -s tests -p test_shadow.py -v
```

The committed `examples/shadow/synthetic-metrics.json` is generated from the four synthetic records. Its first-pass denominator is **2**, with **1** acceptance; risk comparison denominator is **2**, with **1** underclassification. These demonstrate arithmetic only. Pending/unknown fields cannot count as success. Synthetic and observed events always receive separate metric groups, even when supplied in one private log.

已提交的指标 JSON 由四条合成记录计算：一次通过率分母 **2**、通过 **1**；风险比较分母 **2**、漏判 **1**。这些仅验证计算，不代表模型或业务效果。待审核、未知项不记为通过；合成与实测数据始终分开统计。

To append a demonstration to a **private directory you own**, copy `examples/shadow/synthetic-record-input.json` to that directory and run:

```bash
python3 scripts/shadow_metrics.py record --input /absolute/private/demo-input.json --log /absolute/private/shadow-events.jsonl
python3 scripts/shadow_metrics.py report --log /absolute/private/shadow-events.jsonl
```

Use a real private path. Do not place observed logs, raw inputs, draft/final text, client identifiers, or report exports in this public repository. The command prints only safe record status; errors do not echo source text or paths. Input files are not deleted automatically: the operator must apply their private retention policy.

请使用真实的私有路径。实测日志、原始输入、草稿/定稿、客户标识及报告均不进入公开仓库。录入命令仅输出记录状态，错误不回显输入文本或路径。工具不会自动删除输入文件，操作者应按私有保存期限处理。

## Event contract / 记录口径

Every input field is required; unavailable values use JSON `null`. Unknown fields, duplicate JSON keys, invalid risks, negative/non-finite latencies, unsupported schema versions and duplicate event IDs are rejected.

| Field | Meaning / 含义 |
| --- | --- |
| `schema_version` | Exactly `1.0` / 固定版本 |
| `event_id`, `client_id`, `task_id` | Pseudonymous 1–64 character identifiers, letters/digits/underscore/dash/dot only / 脱敏标识，不填真实客户或个人信息 |
| `provenance` | `synthetic` or `observed`; never infer provenance from a filename / 合成或实际观察，必须显式填写 |
| `observed_at` | ISO 8601 with timezone / 含时区时间戳 |
| `model_id` | Safe model/runtime identifier; do not include credentials / 模型标识 |
| `review_state` | `pending` or `completed` / 待审核或已审核 |
| `ai_risk`, `human_risk` | `GREEN`, `YELLOW`, `RED`, `BLACK`, or `null` / AI 与人工风险判断 |
| `ai_latency_ms` | Measured model elapsed time, milliseconds; null if unmeasured / 模型耗时，单位毫秒 |
| `human_review_latency_ms` | Measured active human review/editing time, milliseconds; excludes queue waiting; null if unmeasured / 人工实际审核修改耗时，不含排队等待 |
| `first_pass_accepted` | Human-labelled boolean or null; independent of textual edit distance / 人工标记一次通过与否，不从编辑距离推导 |
| `draft_text`, `final_text` | Transient local strings (max 10,000 Unicode code points each) or null / 仅录入时使用的本地文本 |
| `supersedes_event_id` | Null for a new task, or ID of its pending record when completing review / 新任务为空；后续审核完成时引用待审核记录 |

A pending record must have null human labels, review latency and final text. Completed records may still have unknown fields; each metric reports its own eligible denominator and excluded count. For a later review, append a new event with the same task/client/provenance and `supersedes_event_id` pointing to the existing pending event. Preserve the original model ID, AI risk, latency and draft. Only one pending→completed transition is allowed; completed records cannot be silently replaced. Aggregate metrics count the current task snapshot once and report superseded-event counts. A retry is a new task/attempt ID.

待审核记录的人工判断、审核耗时和定稿必须为空；已审核记录仍可存在未知项，各指标独立披露有效分母与排除数量。后续审核使用新事件 ID，保留同一任务、客户、来源及原始 AI 数据，显式引用待审核事件。仅允许一次待审核→已审核转换；不静默覆盖已完成记录。汇总只计算任务当前状态，另报被替代事件数量。重新生成的尝试使用新任务/尝试 ID。

## Metric definitions / 指标定义

- **Edit distance:** exact Levenshtein insertion/deletion/substitution distance over Unicode code points, without normalization. Normalized distance is `distance / max(len(draft), len(final))`; empty/empty is `0`. Missing either text gives `null`. Chinese, emoji and combining marks follow the same rule. This is a text-change measure, not a quality score.
- **First-pass rate:** human `true` labels divided by completed records with a non-null first-pass label. Minor punctuation edits can coexist with human acceptance. A zero denominator produces `null`, never 100%.
- **Risk misses:** `ai_risk < human_risk` under the ordinal order GREEN < YELLOW < RED < BLACK, among completed records with both labels. Severe misses apply the same comparison where human risk is RED/BLACK, with their own denominator. Overclassification is not counted as a miss; overall classification accuracy is a separate question. Missing labels are excluded, not treated as safe.
- **Latency:** separate AI and human-review series, in milliseconds, with sample count, excluded count, arithmetic mean, nearest-rank p50 and p95. AI latency can be measured before review completes. Human latency needs a completed review.

编辑距离衡量修改量而非事实正确性；一次通过率依赖人工记录；风险漏判按人工标签的相对等级计算，严重漏判分母单列；延迟分别记录模型生成与人工实际审核修改耗时。所有指标保留空值，不用缺失值推导成功。

## Privacy and operational limits / 隐私与边界

The stored JSONL contains SHA-256 hashes, character counts and derived distances, **no draft or final text**. File creation uses mode `0600`; symlinks at the log file itself are refused; appends validate existing records and use an advisory lock plus `fsync`. Parent directories must be trusted. This is a local POSIX utility, not a multi-tenant hosted service or an encrypted audit ledger. Text hashes can reveal short predictable messages through guessing; treat hashes, pseudonyms and timestamps as sensitive metadata. JSONL is not tamper-evident: a valid-looking rewrite is not detectable by this measurement module. Use the gateway's audit system and suitable storage controls for execution evidence.

JSONL 仅保存文本哈希、字符数和距离，不保存草稿或定稿正文。文件权限为 `0600`；拒绝日志文件本身是符号链接；写入前验证已有记录并加锁落盘。父目录需可信。这是本地 POSIX 工具，不是多租户服务或加密审计系统。短文本可能被通过哈希猜测，因此元数据也应保密。合法格式的整段篡改无法由本模块识别；执行证据应结合网关审计与适当存储控制。

`observed` is an operator-supplied assertion, not cryptographic proof of a real business trial. Independent human review and factual usefulness still need separate evidence. Several weeks of representative observed tasks, predefined acceptance thresholds and explicit human authorization are needed before considering any deployment-mode change. Passing unit tests or replaying this synthetic fixture does not establish production readiness.
