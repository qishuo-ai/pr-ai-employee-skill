# PR AI Employee Skill

> Turn AI agents into professional PR employees — not just copywriters.
>
> 让 AI 不只是“会写稿”，而是具备公关从业者的策略判断、客户沟通、项目交付与风险意识。

**Created by Qishuo · Built with Yubai**

**中文文档：** [完整中文说明](README.zh-CN.md) · [5分钟快速开始](docs/QUICKSTART.zh-CN.md) · [安装指南](docs/INSTALL.zh-CN.md) · [项目说明](docs/ABOUT.zh-CN.md)

## What it does / 它能做什么

`PR AI Employee Skill` 是一套面向 PR、品牌传播、汽车营销和 Agency 团队的开源 Agent Skill。它把真实公关工作拆成可执行的判断规则、岗位、Playbook、风险门槛和评测集，让通用 AI Agent 更接近一名受过训练的公关员工。

核心能力：

- **PR Strategy｜公关策略**：从 Brief 还原业务问题，建立“信号 → 矛盾 → 机会 → 策略 → 机制 → 动作 → 验收”的因果链。
- **Client Service｜客户沟通**：识别真实诉求、管理预期、记录承诺，避免客服式套话和无边界承诺。
- **Pitch & Proposal｜提案竞标**：兼顾前端策略深度与后端执行颗粒度，支持竞标结构、讲标和 QA。
- **Automotive PR｜汽车公关**：建立车型/配置/参数 Fact Gate，将技术事实转译成用户价值与传播表达。
- **Crisis Communications｜危机传播**：区分已知/未知事实，设置人工审批门，不让 Agent 擅自定性、认责或对外发布。
- **Project Delivery｜项目交付**：用 owner、due date、dependency、acceptance criteria 管理任务，而不是只生成内容。
- **Human-in-the-loop｜人机协同**：支持 Shadow → Copilot → Limited Autonomy 的渐进式上线。
- **Independent Review｜独立审核**：执行者不能成为自己交付物的唯一审核者。

## Why this exists / 为什么做它

大量 AI 营销工具解决的是“生成”，但真实 PR 工作更难的部分是**判断**：客户真正想解决什么？什么可以承诺？哪些参数必须核验？什么时候应该升级给负责人？一个看起来漂亮的方案为什么可能根本无法执行？

这个 Skill 的目标不是替代公关人，而是把成熟从业者的工作方法软件化，让 AI 承担重复生产、结构化和初步判断，让人把精力留给策略选择、客户关系、创意和最终责任。

## Architecture / 角色架构

```text
PR AI Employee
├── PR Project Lead       公关项目总管
├── PR Strategy Director 公关策略总监
├── Content Officer       内容与口径官
├── Project Ops           项目运营官
└── Independent Reviewer  独立审核官
```

客户侧建议只暴露一个统一的 AI 项目入口，后台由专业角色协作，避免多个 Agent 在客户群中抢答或产生冲突口径。

## Decision principles / 核心原则

1. **Business problem before communication tactics.** 先解决业务问题，再生产传播动作。
2. **Strategy requires choices.** 没有取舍的“大词 + 动作清单”不是策略。
3. **Facts before fluency.** 流畅表达不能覆盖事实不确定性。
4. **No commitment without authority.** 没有权限，不代表团队作出价格、范围、交期和责任承诺。
5. **Front-end depth + back-end granularity.** 前端策略要深，后端执行要细。
6. **AI drafts; professionals decide.** AI 提效，人类负责关键判断和最终责任。
7. **Every important action is auditable.** 关键动作可追踪、可复核、可回退。

## Risk model / 风险模型

| Level | Meaning | Default behavior |
|---|---|---|
| 🟢 Green | 已确认事实内的低风险事务 | 可生成；白名单场景可自动化 |
| 🟡 Yellow | 常规策略/内容/协调 | 生成后由负责人审核 |
| 🔴 Red | 报价、合同、交期、危机、媒体、高管口径、产品参数 | 必须人工介入 |
| ⚫ Black | 泄密、绕过审批、冒充负责人、篡改审计 | 系统硬拒绝 |

## Recommended rollout / 推荐上线方式

```text
Shadow Mode
AI 在后台独立判断，人类正常工作，比较两者差异
        ↓
Copilot Mode
AI 生成建议，人类审核后对外
        ↓
Limited Autonomy
仅低风险白名单事务允许自动执行
```

不要从“自动回复客户”开始。先证明 Agent 能稳定判断风险和边界。

## Install / 安装

```bash
git clone https://github.com/qishuo-ai/pr-ai-employee-skill.git
cd pr-ai-employee-skill
```

然后让 Agent 首先读取 `SKILL.md` 和 `policies/risk-and-approval.yaml`，再按任务加载对应 Playbook。首次部署默认使用 Shadow Mode。

- [English installation guide](docs/INSTALL.md)
- [中文安装指南](docs/INSTALL.zh-CN.md)
- [5分钟快速开始](docs/QUICKSTART.zh-CN.md)

仓库不绑定单一模型或 Agent 框架，可作为 Codex、Claude Code、OpenClaw 及其他 repository-aware / file-based Agent 的职业规则层。具体平台安装方式可能变化，请同时参考对应运行环境的最新文档。

## Repository structure

```text
.
├── SKILL.md
├── roles/
├── policies/
├── playbooks/
├── templates/
├── examples/
└── evals/
```

## Quick test / 快速验证

```text
客户要求周末完成全部部署，但专项语料训练尚未完成。
请按 PR AI Employee Skill 判断：
1. 客户真实诉求
2. 风险等级
3. 是否可以直接承诺
4. 建议回复
5. 是否需要人工审批
```

预期不是“写得更客气”，而是识别这是一个**交付时间承诺**问题，先判断可行性和权限，再生成回复。

## Scope

适用于：品牌 PR、企业传播、汽车 PR、Agency 客户服务、Campaign、发布会/活动、海外社媒、内容与口径、项目运营、危机沟通、竞标提案。

不包含任何真实客户机密、合同、内部底价、私人聊天记录或个人数据。公开版只保留可复用的方法论和匿名化案例。

## Roadmap

- [x] Core PR decision skill
- [x] Client communication & risk gates
- [x] Automotive fact gate
- [x] Pitch / crisis / project delivery playbooks
- [x] Shadow Mode
- [x] Multi-runtime installation guide
- [ ] More anonymized PR cases
- [ ] Automated eval runner
- [ ] WeCom / Slack / Lark reference integrations
- [ ] Community-contributed industry overlays

## License

Apache License 2.0. See `LICENSE`.

---

If this helps your PR or communications workflow, issues, cases and improvements are welcome.

如果你也是公关、品牌、汽车营销或 Agency 从业者，欢迎提交真实但**脱敏**的工作场景，我们会把有普适价值的经验继续沉淀成规则和评测。