# 快速开始｜5分钟把它装进你的 AI Agent

## 方式一：文件型 Skill

如果你的 Agent 支持 Skills / Instructions 文件：

1. 把本仓库克隆到本地。
2. 将 `SKILL.md` 作为核心 Skill 载入。
3. 根据任务按需加载：
   - `playbooks/`：业务打法
   - `policies/`：风险与事实门
   - `roles/`：岗位分工
   - `templates/`：结构化输出
4. 首次使用保持 Shadow Mode，不直接向客户发送任何内容。

## 方式二：Codex / Coding Agent

可直接给 Agent：

```text
请读取当前仓库的 SKILL.md，并把它作为后续所有公关任务的职业判断规则。
遇到客户沟通、提案竞标、汽车公关、危机或项目管理任务时，按需读取 playbooks/ 与 policies/。
默认运行在 Shadow Mode：禁止直接对客发送，红色事项必须标记 HUMAN_REQUIRED。
```

## 方式三：其他 Agent 框架

把 `SKILL.md` 放进 system / developer instruction 层，或作为高优先级知识文件加载。

建议不要一次性把所有文件塞入上下文。先加载核心规则，再根据任务调用对应 Playbook。

## 测试你的 Agent

使用：

```text
客户要求周末完成部署，但专项内容还没有训练完。
请按 PR AI Employee Skill 输出：
- 客户真实诉求
- 风险等级
- 判断
- 建议回复
- 是否需要真人审批
```

合格结果必须识别为交期承诺风险，而不是只润色客户回复。

## 生产环境建议

- 客户数据按项目/客户隔离。
- 汽车参数必须接官方资料或事实库。
- 报价、合同、交期、危机等高风险动作设置程序化审批，不要只靠 Prompt。
- 保留 Agent 输入、判断、引用资料、草稿、审核人和最终输出的审计记录。
