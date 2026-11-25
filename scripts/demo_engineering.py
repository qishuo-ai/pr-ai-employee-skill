#!/usr/bin/env python3
"""Offline synthetic demonstration; no model call or external delivery."""
import json
import secrets
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.gateway import GateError, Gateway


def demonstrate():
    observations = []
    with tempfile.TemporaryDirectory(prefix="pr-agent-demo-") as temporary:
        gateway = Gateway(Path(temporary).resolve() / "audit.sqlite3",
                          principals={"writer": {"alpha", "beta"}},
                          approvers={"reviewer": {"alpha", "beta"}},
                          secret=secrets.token_bytes(32),
                          overlay_root=ROOT / "examples/overlays")
        shadow = gateway.open_session("writer", "alpha")
        read = {"tool": "overlay.read", "client_id": "alpha",
                "arguments": {"document": "facts.json"}}
        alpha = gateway.execute(shadow, read)
        assert alpha["client_id"] == "alpha" and alpha["synthetic"] is True
        observations.append({"case": "authorized_alpha_read", "outcome": "allowed"})

        def denied(label, session, request, token=None):
            try:
                gateway.execute(session, request, token)
            except GateError as exc:
                observations.append({"case": label, "outcome": "denied", "reason": str(exc)})
            else:
                raise AssertionError(f"Expected denial: {label}")

        denied("cross_client_read", shadow, dict(read, client_id="beta"))
        denied("unknown_tool", shadow, {"tool": "email.send", "client_id": "alpha", "arguments": {}})
        delivery = {"tool": "delivery.simulate", "client_id": "alpha",
                    "arguments": {"destination": "synthetic-review-inbox", "text": "Synthetic approved draft."}}
        denied("shadow_delivery", shadow, delivery)
        copilot = gateway.open_session("writer", "alpha", "copilot")
        denied("missing_approval", copilot, delivery)
        token = gateway.issue_approval("reviewer", copilot, delivery)
        changed = dict(delivery, arguments=dict(delivery["arguments"], text="Changed synthetic draft."))
        denied("changed_draft", copilot, changed, token)
        result = gateway.execute(copilot, delivery, token)
        assert result["status"] == "simulated_only"
        observations.append({"case": "bound_approved_delivery", "outcome": "simulated_only"})
        denied("approval_replay", copilot, delivery, token)
        # Separate beta session retrieves only beta; the alpha session never reads it.
        beta_session = gateway.open_session("writer", "beta")
        beta = gateway.execute(beta_session, dict(read, client_id="beta"))
        assert beta["client_id"] == "beta" and beta["canary"] not in json.dumps(alpha)
        observations.append({"case": "authorized_beta_read", "outcome": "allowed"})
        audit = gateway.audit_events()
        assert all("text" not in event["details"] for event in audit)
        return {"synthetic": True, "external_messages_sent": 0,
                "checks": observations, "verified_audit_events": len(audit)}


if __name__ == "__main__":
    print(json.dumps(demonstrate(), ensure_ascii=False, indent=2))
