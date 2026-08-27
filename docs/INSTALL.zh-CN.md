# 安装说明

这个仓库本质上是一套文本型 Agent Skill，不依赖固定模型。

## 通用安装

1. 克隆仓库。
2. 将 `SKILL.md` 作为最高优先级的职业规则文件加载。
3. 根据任务类型选择对应 `playbooks/`。
4. 始终同时加载 `policies/` 中的风险和事实门。
5. 首次部署运行在 Shadow Mode。

## 建议的加载顺序

```text
SKILL.md
→ policies/risk-and-approval.yaml
→ 对应 playbook
→ 对应 role
→ templates
```

## 不推荐

- 把所有真实客户资料直接写进公开 Skill。
- 只复制 SKILL.md 的一小段 Prompt 而删除风险门。
- 首次接入客户群就开启全自动回复。
- 让同一个 Agent 同时生产、审核、批准自己的高风险输出。
