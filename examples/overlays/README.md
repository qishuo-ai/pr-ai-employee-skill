# Synthetic Client Overlay / 虚构双客户隔离例子

Everything in this directory is invented test data. It contains no real client, contract, price, strategy, credential or private repository content.

此处数据完全虚构，不来自真实客户或 `qishuo-pr-brain`。两个客户分别有独立的事实卡和测试 canary：

| Client | Fictional business | Canary |
| --- | --- | --- |
| `alpha` | Aurora Example Mobility / 极光示例出行 | `ALPHA_ONLY_SYNTHETIC_7f83` |
| `beta` | Boreal Example Hospitality / 北境示例旅居 | `BETA_ONLY_SYNTHETIC_9c21` |

The host binds a session to one authorized client. An Alpha session can load Alpha facts; requesting Beta is rejected **before a file is opened**, even if the prompt says the other client gave permission. The model receives only the selected overlay. A trusted host may create a separate Beta session for a principal whose ACL allows Beta; the two contexts must not be combined.

宿主先绑定登录身份与客户，模型只能请求已绑定客户。Alpha 会话不能根据输入中的“授权说明”改读 Beta；另一个客户须通过可信宿主创建独立会话。不要把两个 overlay 一并放入模型上下文来演示“隔离”。

```python
from pathlib import Path
import secrets
import tempfile
from runtime import Gateway, GateError

with tempfile.TemporaryDirectory() as temp:
    gateway = Gateway(
        Path(temp).resolve() / "audit.sqlite3",
        principals={"writer": {"alpha"}},
        approvers={"reviewer": {"alpha"}},
        secret=secrets.token_bytes(32),
        overlay_root=Path("examples/overlays").resolve(),
    )
    session = gateway.open_session("writer", "alpha")  # trusted host only
    alpha = gateway.execute(session, {
        "tool": "overlay.read", "client_id": "alpha",
        "arguments": {"document": "facts.json"},
    })
    assert "ALPHA_ONLY" in alpha["canary"]
    try:
        gateway.execute(session, {
            "tool": "overlay.read", "client_id": "beta",
            "arguments": {"document": "facts.json"},
        })
    except GateError:
        print("Cross-client read blocked before loading Beta")
```

The in-memory random secret above is suitable only for a disposable demo. A real host must securely persist its signing key and audit database, authenticate identities, and enforce this gateway on every tool path. See [engineering boundaries and limitations](../../docs/ENGINEERING.md).
