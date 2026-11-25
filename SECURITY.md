# Security Policy

请不要在 Issue、PR 或公开文件中提交：

- 客户未公开资料
- API Key / Token / 密码
- 合同、内部报价与底价
- 客户群原始聊天记录
- 可识别个人的敏感信息

如果你发现公开仓库中存在真实客户机密或凭证，请优先联系仓库维护者处理，不要继续扩散。

## Reference runtime boundary / 参考运行时边界

All tool adapters must be behind the gateway. The host must authenticate callers, set client ACLs and operating mode, protect approval authority and keys, and restrict process/filesystem/network access. Model output is untrusted input. The included delivery adapter is a local simulation and has no real messaging credentials.

SQLite transactions provide local replay protection and a hash-linked audit trail. Protect the database and signing key outside the model's reach; an administrator who can rewrite both state and audit anchors can defeat local protections. Production integrations need external audit anchoring, credential isolation, authenticated approval UI, idempotent external operations and an operational review.

Public evaluation fixtures and logs must be synthetic. Raw logs may contain prompt and response content; do not commit real client runs. `.gitignore` is an accidental-commit aid, not a data-loss prevention system. The private `qishuo-pr-brain` is not an input to this public repository's tests or demonstrations.
