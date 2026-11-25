# Finals demonstration / 决赛工程演示

Version 1.2.0 · PR Agent｜公关智能员工

This release prepares engineering evidence for the November 29, 2026 slide deadline and December 9, 2026 eight-minute presentation. It does not create the presentation. 本次只更新 Skill 与工程证据，不制作 PPT。

## What to demonstrate / 演示内容

1. Run `python3 scripts/demo_engineering.py`. Show a permitted single-client read, a rejected cross-client read, a blocked Shadow delivery, a valid approved Copilot simulation, a changed-draft rejection and a replay rejection. No message is sent to a customer.
2. Open the [actual validation record](VALIDATION.md). Distinguish automated code tests, actual model runs, human grading and real deployment evidence.
3. Open the [evaluation protocol](../evals/README.md): 28 synthetic cases, same model and response contract, isolated A/B sessions, full output/log evidence. Show an actual failure as well as a pass; a structural pass does not establish good PR judgment.
4. Show the [Shadow metrics](SHADOW-METRICS.md) with the synthetic fixture, then run `python3 scripts/retrospective_report.py` for the separate [real-work casebook](REAL-WORLD-EVIDENCE.md). Explain that receipts and chat spans are historical observations, while prospective quality metrics remain unavailable.

Suggested eight-minute allocation: 1 minute problem and Skill, 3 minutes gate demonstration, 2 minutes actual evaluation evidence and one failure, 1 minute Shadow metrics, 1 minute limitations and next validation. This is an engineering demo outline, not a slide deck or speech script.

## Claims that evidence supports / 可用表述

- “We implemented and tested a reference execution boundary.” / 已实现并测试参考执行边界。
- “The suite contains 28 synthetic scenarios; actual run coverage is listed in the validation record.” / 题集有 28 个合成场景，实际覆盖以运行记录为准。
- “Deterministic checks are reproducible; human PR-quality grading remains separate.” / 自动检查可复跑，公关质量由独立人工另行评分。

Do not claim that historical illustrative 38.7/95.7 scores were independent tests, synthetic Shadow events are real clients, a local hash chain is administrator-proof, or a sample gateway secures tools that bypass it. Do not state a human first-pass rate before observing real independently reviewed work.

## Private/public boundary / 公私边界

`qishuo-pr-brain` remains private and is not needed by any command here. Never import its files, raw customer conversations, commercial details or credentials into this repository or model-run snapshots. The anonymous historical casebook contains separately authorized generalized text only; originals and identity mappings remain private. Synthetic Alpha/Beta fixtures are invented examples, not renamed real clients. Keep real Shadow records in the client's authorized private environment; commit only reviewed, explicitly releasable aggregates.

## Next evidence / 后续证据

Have reviewers who did not author the prompts independently grade the blinded packet, record disagreements and adjudication, then unlock the mapping. Run a separately consented private Shadow pilot with representative tasks and predeclared promotion criteria. No calendar deadline or passing test automatically authorizes autonomous external actions.
