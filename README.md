# PR Agent｜公关智能员工

> Professional judgment, collaboration and delivery for PR teams.

**Created by Qishuo · Built with Yubai · v1.2.0**

[中文说明](README.zh-CN.md) · [Installation](docs/INSTALL.md) · [Finals demonstration](docs/FINALS.md) · [Actual validation status](docs/VALIDATION.md)

PR Agent is an open-source Skill for public relations, brand communications, automotive launches and agency project work. It turns reusable professional methods into decision rules, specialist roles, playbooks, risk policies and evaluation scenarios. The compatible Skill identifier remains `pr-ai-employee`; the repository remains `pr-ai-employee-skill`.

## v1.2.0: finals engineering

- **28 fully synthetic evaluation scenarios:** commitments, factual claims, crisis, privacy, client isolation, platform work, prompt injection, approval binding and useful low-risk drafting. The original 22 E/T scenarios remain a separate qualitative regression set.
- **Reproducible A/B runner:** same requested model/settings/task/response contract, separate sessions, randomized scheduling, frozen prompts and source code, actual outputs, raw event logs and explicit failed attempts.
- **Separate human judgment:** deterministic contract checks do not stand in for a six-dimension blinded human rubric. Human ratings remain pending until real independent reviewers submit them.
- **Reference execution gateway:** deny-by-default dispatch, strict schemas, client authorization before loading overlays, expiring single-use approval bound to exact action/content/session, and authenticated transactional audit.
- **Anonymized real-work evidence:** four retrospective workstreams and seven extracted delivery episodes, with receipt counts kept separate from quality acceptance. [Cases and reproducible counts](docs/REAL-WORLD-EVIDENCE.md).
- **Shadow metrics:** exact Unicode edit distance, human first-pass acceptance, risk misses and AI/reviewer latency, with missing-data denominators and synthetic/observed groups kept separate.

The historical **38.7/95.7** and **42/94, 35/97, 39/96** scores are illustrative, not independently verified measurements. They are not a baseline, target or result of this release. Synthetic demonstrations do not establish real client deployment performance.

## Start here

```bash
git clone https://github.com/qishuo-ai/pr-ai-employee-skill.git
cd pr-ai-employee-skill
python3 scripts/validate-role-library.py
python3 scripts/check_release.py
python3 -m unittest discover -s tests -v
python3 scripts/demo_engineering.py
```

The reference runtime and tests use Python 3.9+ on POSIX (Linux/macOS), with no third-party Python dependencies. The demo sends **zero external messages**. Live A/B evaluation additionally needs a compatible, authenticated Codex CLI and an accessible model; follow the [evaluation protocol](evals/README.md).

Load `SKILL.md`, the risk policy and task-relevant playbooks into your agent. Installing the Markdown Skill alone does **not** enforce permissions or install an agent service. Integrators must place all actual tool adapters behind an authenticated host boundary; see [engineering integration](docs/ENGINEERING.md).

## Professional capabilities

| Capability | Working method |
|---|---|
| PR strategy | Identify the business problem, evidence, strategic choice, mechanism and measurement. |
| Client service | Interpret the real need, control commitments and propose feasible next steps. |
| Pitch and proposal | Combine strategic reasoning with owners, dependencies, budgets and acceptance criteria. |
| Automotive communications | Verify market/model/version-specific facts before using specifications or superlatives. |
| Crisis response | Separate known/unknown facts, draft holding lines and escalate to authorized people. |
| Project delivery | Track ownership, deadlines, dependencies, change requests and delivery evidence. |
| Independent review | Keep the draft author separate from the reviewer; identify unavailable review honestly. |

## Team and routing

Five core roles form the backbone: Project Lead, Strategy Director, Content & Messaging Officer, Project Ops and Independent Reviewer. Twenty optional specialist cards cover research, media/KOL, social strategy, platforms, creative production, analytics, commercial proposals and AI workflows.

Use the [role directory](roles/README.md), [routing playbook](playbooks/team-routing.md) and [declarative registry](roles/registry.json) to choose relevant roles. Role names do not grant publishing, outreach, purchase or approval authority. A single model changing perspectives is not independent review.

Selected methods were adapted from [agency-agents-zh](https://github.com/jnMetaCode/agency-agents-zh). The [integration record](docs/AGENCY-AGENTS-INTEGRATION.zh-CN.md), pinned source manifest and retained [MIT notice](licenses/agency-agents-zh-MIT.txt) document attribution. No upstream commands or unverified KPI claims are treated as project facts.

## Risk and rollout

| Risk | Typical work | Default |
|---|---|---|
| GREEN | Confirmed facts and low-risk internal tasks | Draft; automation needs an explicit whitelist. |
| YELLOW | Strategy, content and ordinary coordination | Human review before external use. |
| RED | Pricing, contracts, delivery commitments, crisis, media, executive quotes, specifications | Authorized human approval. |
| BLACK | Cross-client leakage, credentials, fabricated facts, impersonation, audit/approval bypass | Refuse; permission does not make a prohibited operation valid. |

Begin in **Shadow Mode**: AI drafts independently while people handle the work, then compare judgments and corrections. **Copilot** requires human review before external use. **Limited autonomy** is a future, separately authorized deployment decision for explicitly whitelisted tasks; this reference implementation does not provide that mode or real messaging adapters.

The [Shadow implementation](docs/SHADOW-METRICS.md) records measurable observations without storing draft/final text. Hashes and identifiers remain sensitive metadata, so observed logs belong in an authorized private location.

## Demonstrable boundaries

The [two-client example](examples/overlays/README.md) uses invented Alpha/Beta knowledge. Authorization occurs before file access. The [offline demo](scripts/demo_engineering.py) shows allowed client reads, denied cross-client access, unknown-tool rejection, Shadow blocking, content-bound approval and replay rejection.

The gateway is a reference library, not an operating-system sandbox. Host authentication, credential isolation and routing every adapter through it are integration responsibilities. A process owner/key holder can bypass the library; local audit chains require external anchors to detect whole-database rollback. Schema validation cannot establish semantic truth. Read [Security](SECURITY.md) and [engineering limitations](docs/ENGINEERING.md).

## Evidence and privacy

Read [actual validation](docs/VALIDATION.md) for the precise tested revision, CLI/model request, run coverage, observed failures and limitations. Code tests, deterministic model checks, independent human ratings and real deployment metrics are separate evidence classes.

No private `qishuo-pr-brain` files, customer conversations, contracts, commercial terms, credentials or personal data are required by this repository. Evaluation fixtures are wholly synthetic. Raw client records must never be committed here. Separately authorized, generalized historical text summaries live in `data/retrospective/`; their evidence and identity mapping stay private, and their counts are not prospective Shadow scores. Public raw A/B outputs can weaken later blinding; reviewers should use only their private packet until ratings are locked.

## Repository

```text
SKILL.md       Professional protocol
roles/         Five core roles and twenty specialists
policies/      Risk and automotive fact policies
playbooks/     Business workflows
templates/     Judgment, handoff and delivery templates
runtime/       Gateway, client overlays and Shadow metrics
scripts/       Evaluation, scoring, demo and validation commands
tests/         Offline engineering regressions
examples/      Synthetic examples
evals/         Scenarios, rubric and reviewed run evidence
docs/          Integration, installation and validation
```

## Remaining validation

- Independent human grading of blinded model outputs.
- Repeated fresh runs and broader client-authorized private evaluation.
- Real Shadow observations with predeclared acceptance criteria.
- Authenticated production adapters and operational controls before external use.

The November 29, 2026 slide deadline and December 9 eight-minute finals presentation guide the [demonstration outline](docs/FINALS.md). This update delivers the Skill and engineering evidence, not a slide deck.

## License

Apache License 2.0; see [LICENSE](LICENSE). Adapted role methods retain upstream MIT attribution in [NOTICE](NOTICE) and [licenses/agency-agents-zh-MIT.txt](licenses/agency-agents-zh-MIT.txt).
