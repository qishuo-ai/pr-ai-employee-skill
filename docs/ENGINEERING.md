# Executable boundaries / 可执行门禁

This Python 3.9+ standard-library runtime is a small, testable reference boundary. It does not turn a Markdown skill into a production sandbox. No email, chat, publication, purchase or network adapter ships in this repository.

本运行时将部分规则变成执行前检查，可用单元测试证明。它是参考实现，不是生产沙箱；仓库没有真实邮件、聊天、发布、购买或网络适配器。

## Trust boundary / 信任边界

A trusted host authenticates users, owns the principal-to-client ACL, chooses the mode, protects a random secret (at least 32 bytes), and calls `open_session`. Only `execute(session, request, approval_token)` is exposed to model-requested tool calls. The host must also authenticate the human reviewer before calling `issue_approval`; that method is **not** a model tool or proof that a person clicked approve. Tool responses must return only to the authenticated session.

可信宿主负责登录认证、客户 ACL、运行模式、密钥与审核人身份。`open_session` 和 `issue_approval` 仅供宿主调用；不能交给模型，也不能直接接受请求正文里的“我是审核人”。模型只能提交执行请求。会话经 HMAC 绑定身份、客户、模式与随机 nonce，篡改会话会被拒绝。人类审核界面与身份系统仍需接入。

Strict requests contain exactly `tool`, `client_id`, and `arguments`. No request field can supply risk, principal, mode, approval status, file path or an alternative destination. Tools not listed below are denied.

| Tool | Host-owned risk | Effect | Conditions |
| --- | --- | --- | --- |
| `overlay.read` | green | read | Bound client ACL; only `facts.json`; synthetic schema |
| `draft.prepare` | yellow | internal | Returns a draft marked `externally_usable: false` |
| `delivery.simulate` | red | external-class simulation | Copilot + exact bound approval; returns a local receipt only |

`delivery.simulate` deliberately exercises the same gate that a future outbound adapter would need. Its receipt says `simulated_only`; it never delivers a message. Risk is determined by the host's tool policy, not by the model's risk label. This is conservative effect gating, not semantic detection of every risky sentence. Product facts and brand claims still need source verification and human review.

## Approval and dispatch / 审批与执行

An approval binds the canonical request (including full text and destination), tool, client, principal, session nonce, risk, effect, mode and `POLICY_VERSION`. It expires within one hour and requires a different, authorized reviewer. Tokens are stored as hashes. The issuer’s current client ACL is rechecked at consumption, so a removed reviewer permission cannot authorize dispatch. Changing content, client, session, identity or policy invalidates the token.

审批精确绑定内容、工具、客户、身份、会话、风险、模式和策略版本；最长一小时、单次使用。审批人必须与起草身份不同且拥有该客户权限。更改文案不能沿用旧审批；Shadow 模式无论有无 token 都阻断外部动作。

SQLite `BEGIN IMMEDIATE` serializes authorization and token consumption. Authenticated audit records and consumed approval state commit **before** dispatch. Concurrent calls and ordinary process restarts cannot reuse a consumed token. An adapter exception or a crash after authorization leaves the token consumed; an unknown outcome requires human reconciliation and a new approval, never an automatic retry. This is at-most-once dispatch, not guaranteed delivery or exactly-once effects.

## Audit / 审计

Each audit entry includes server UTC time, policy version, event type, hashes and a keyed chain signature. The approval table is reconciled against the authenticated audit history before every transaction; editing its expiry/binding/used flag fails closed. Failed validation, failed dispatch and completion are separate events. Failure to persist authorization prevents dispatch.

审计不保存客户正文、审批 token 或密钥；保存请求及结果摘要、客户/身份摘要、工具、风险和模式。正文变化可核验，但摘要不是匿名化保证，低熵值仍可能被猜测。生产日志仍应保留在有访问控制的私有环境。

Limitations: the host process, its key holder and filesystem owner are trusted. A compromised host can bypass this library. A valid rollback/truncation of the entire database to an older authenticated snapshot is not detected without an external signed checkpoint or append-only remote audit store. Protect the database and key separately, use a trusted clock, and add deployment-specific authentication, tenant storage, sandboxing and retention before production. Audit storage failure **after** a dispatch cannot undo an effect; reconcile an authorized event lacking completion rather than assuming success.

限制：进程、密钥持有者和文件系统管理员属于可信边界，不能宣称本库可防范它们。完整旧数据库快照回滚/合法尾部截断需要外部检查点才能检测。时钟、鉴权、沙箱、远端审计锚点和保留期限需要部署层补齐。执行后审计失败不能撤销已发生动作。

## Client overlay / 客户隔离

[Two synthetic clients](../examples/overlays/README.md) demonstrate pre-read authorization. The loader checks the requested client against the signed session and host ACL **before opening any client file**. It allowlists `facts.json`, rejects traversal and symlinks, opens with directory file descriptors and `O_NOFOLLOW`, rejects non-regular files (including FIFOs), limits file size, and validates the embedded client label and synthetic schema. It fails closed on systems lacking the necessary POSIX flags.

两个客户完全虚构，并各含一个独立 canary。隔离在读取之前实施，不是让模型读到另一客户后“承诺不泄露”。示例不读取私有 `qishuo-pr-brain`。宿主若自行把不同客户文本拼在一起，或给模型额外文件/网络工具，本库无法替代宿主的数据隔离。

Configured root/database paths are trusted, absolute, symlink-free paths. On macOS, resolve a trusted temporary directory first (`Path(tempdir).resolve()`) because `/var` may be a system symlink. Client document symlinks remain forbidden. Protect configured roots from filesystem-owner replacement; this library is not an adversarial mount namespace.

## Verify / 验证

```bash
python3 -m unittest discover -s tests -v
python3 scripts/demo_engineering.py
```

Tests exercise schema rejection, tool denial, session tampering, cross-client reads before file open, symlink/FIFO attacks, approval changes, expiry, replay, concurrent consumption, restart, adapter failure, audit tampering and disk-write failure. Passing these tests proves the tested software behaviors; it does not establish a model's business judgment quality or production readiness.
