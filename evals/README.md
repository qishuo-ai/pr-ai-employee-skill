# Evaluation / 行为评测

v1.2.0 has three distinct collections. File counts are not experimental sample counts.

| Collection / 题集 | Count | Status / 用途 |
|---|---:|---|
| `finals-scenarios.jsonl` F01–F28 | 28 | Fully synthetic, executable A/B suite / 完全合成、可自动运行 |
| `eval-set.jsonl` E01–E10 | 10 | Original qualitative regression cases / 原有定性回归 |
| `team-routing-evals.jsonl` T01–T12 | 12 | Role/handoff regression cases / 岗位与交接回归 |

The finals suite covers GREEN 4, YELLOW 9, RED 8 and BLACK 7 cases. It includes commitments, scope changes, automotive facts, crisis, privacy, client isolation, role handoffs, platform adaptation, useful low-risk tasks, prompt injection, approval binding and fabricated evidence. All clients, tasks and context are fictional; no customer files or private repository are inputs.

决赛题集是 28 个合成场景，保留的 22 个旧场景没有被删减。不得把 50 个文件记录说成 50 个已完成的模型实验。实际调用、原始输出、失败与限制见 [验证记录](../docs/VALIDATION.md)。

## Reproduce / 复跑

Read [the complete protocol and human rubric](RUBRIC.md). Use Python 3.9+, an authenticated compatible Codex CLI and an explicitly accessible model. The recorded successful run uses CLI 0.172.0 and requested model `gpt-6-astra` with `low` reasoning. No new API key is required when using an existing Codex login.

The following optional scoped install reproduces the tested CLI without replacing a global installation:

```bash
npm install --prefix artifacts/tooling --ignore-scripts --no-audit --no-fund @openai/codex@0.172.0
export PATH="$PWD/artifacts/tooling/node_modules/.bin:$PATH"
codex --version
```

Reuse an existing authenticated Codex login; do not copy credentials into the repository.

```bash
python3 scripts/run_evals.py --output artifacts/plan-01 --model gpt-6-astra --dry-run
python3 scripts/run_evals.py --output artifacts/smoke-new --model gpt-6-astra --scenario F09 --jobs 2
python3 scripts/run_evals.py --output artifacts/finals-new --model gpt-6-astra --reasoning-effort low --jobs 4 --timeout 240
```

Each directory must be new. `--dry-run` is planning only. There are no automatic retries. Four workers affect elapsed time and latency; reported latency includes startup, network and inference. The seed fixes scheduling, not model sampling. A is generic Codex PR assistance; B adds snapshotted Skill, policies and relevant roles/playbooks. Both receive the same task, schema and model settings in fresh sessions. Expected labels and qualitative grading criteria are withheld from the model.

The runner stores complete prompts, actual event streams, raw responses, per-call checks, code/input snapshots, hashes, revision/dirty status, CLI version and settings. It disables tool surfaces and inherited project/Skill instructions. A declared action is not evidence that an action was executed; [gateway tests](../docs/ENGINEERING.md) supply separate execution evidence.

## Human review / 人工盲评

`blind-review/` contains counterbalanced X/Y pairs and blank ratings. Give only that packet and [the rubric](RUBRIC.md) to at least two independent human reviewers. Keep `holdback/` private until ratings lock. Random item IDs and a private random blinding seed are separate from the public scheduling seed.

The six dimensions are scored 0–4 with evidence; hard failures and reviewer disagreement are reported separately. The [scorer](../scripts/score_evals.py) rejects incomplete or invalid ratings, but cannot authenticate reviewer identity. **No human quality score exists until real people submit ratings.**

公开原始 A/B 输出可能让评委通过文字匹配猜出组别。盲评者应在锁定评分前只看私有盲评包，不看公开证据；若无法确保，应另做未公开的新运行并披露盲法限制。模型评分不能冒充真人盲评。

## Publication and evidence / 发布与证据

By default, artifacts remain in ignored local storage. After inspecting synthetic source and outputs:

```bash
python3 scripts/export_eval_evidence.py --run artifacts/finals-new --output evals/results/your-reviewed-run --reviewed-synthetic
```

The exporter preserves raw events and responses byte-for-byte, normalizes only the local executable path in per-call metadata, writes source/export hashes, and excludes reviewer packets and decoding keys. Heuristic credential/path checks do not prove anonymity; real client runs must stay private.

Historical **38.7/95.7** and **42/94, 35/97, 39/96** are illustrative figures without independently verifiable raw experiments here. They are not this suite's baseline, target or achieved result. Deterministic checks measure declared contract adherence; they cannot establish factual truth, PR usefulness or production safety. Synthetic Shadow examples are not customer deployment outcomes.

## Original E/T regressions / 原有回归

For a legacy case, load the Skill and relevant policies/roles in a clean session and submit only `scenario`, never `must`, `must_not` or expected roles. Respect declared unavailable tools, evidence and permissions. Save full outputs and real tool logs in a private workspace. An independent reviewer marks requirements PASS / FAIL / NOT_OBSERVABLE with evidence. Missing evidence is not a pass; role-name lists are not collaboration evidence, and an author changing personas is not independent review. Report E/T results separately from the automated F suite.
