import concurrent.futures
import dataclasses
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.gateway import GateError, Gateway

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "overlays"


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name).resolve() / "audit.sqlite3"
        self.now = 1000.0
        self.config = dict(principals={"writer": {"alpha"}, "other": {"alpha"}, "beta_writer": {"beta"}},
                           approvers={"reviewer": {"alpha"}, "writer": {"alpha"}},
                           secret=b"test-only-not-a-production-secret" * 2,
                           overlay_root=FIXTURES, clock=lambda: self.now)
        self.gateway = Gateway(self.db, **self.config)
        self.session = self.gateway.open_session("writer", "alpha", "copilot")
        self.request = {"tool": "delivery.simulate", "client_id": "alpha", "arguments": {
            "destination": "synthetic-review-inbox", "text": "SYNTHETIC draft only."}}

    def approve(self):
        return self.gateway.issue_approval("reviewer", self.session, self.request)

    def test_default_deny_and_no_caller_risk_override(self):
        for request in ({**self.request, "tool": "email.send"}, {**self.request, "risk": "green"},
                        {**self.request, "client_id": "beta"}):
            with self.assertRaises(GateError):
                self.gateway.execute(self.session, request)
        with patch.object(self.gateway, "_dispatch") as dispatch:
            with self.assertRaises(GateError):
                self.gateway.execute(self.session, self.request)
            dispatch.assert_not_called()

    def test_shadow_blocks_even_with_approval_for_copilot(self):
        token = self.approve()
        shadow = self.gateway.open_session("writer", "alpha", "shadow")
        with self.assertRaises(GateError):
            self.gateway.execute(shadow, self.request, token)
        with self.assertRaises(GateError):
            self.gateway.issue_approval("reviewer", shadow, self.request)

    def test_approval_exact_payload_binding_and_replay(self):
        token = self.approve()
        changed = {**self.request, "arguments": {**self.request["arguments"], "text": "Changed content"}}
        with self.assertRaises(GateError):
            self.gateway.execute(self.session, changed, token)
        result = self.gateway.execute(self.session, self.request, token)
        self.assertEqual(result["status"], "simulated_only")
        with self.assertRaises(GateError):
            self.gateway.execute(self.session, self.request, token)

    def test_approval_cannot_transfer_principal_or_session(self):
        token = self.approve()
        for principal in ("other", "writer"):
            other = self.gateway.open_session(principal, "alpha", "copilot")
            with self.assertRaises(GateError):
                self.gateway.execute(other, self.request, token)
        self.gateway.execute(self.session, self.request, token)

    def test_changed_policy_version_invalidates_approval(self):
        token = self.approve()
        with patch("runtime.gateway.POLICY_VERSION", "test-next-policy"):
            with self.assertRaises(GateError):
                self.gateway.execute(self.session, self.request, token)

    def test_expiry_and_independent_approver(self):
        with self.assertRaises(GateError):
            self.gateway.issue_approval("writer", self.session, self.request)
        with self.assertRaises(GateError):
            self.gateway.issue_approval("unknown", self.session, self.request)
        for ttl in (True, 0, -1, 3601, float("nan")):
            with self.assertRaises(GateError):
                self.gateway.issue_approval("reviewer", self.session, self.request, ttl_seconds=ttl)
        token = self.approve()
        self.now += 300
        with self.assertRaises(GateError):
            self.gateway.execute(self.session, self.request, token)

    def test_session_tampering_and_scope_denial(self):
        for change in ({"principal": "beta_writer"}, {"client_id": "beta"}, {"mode": "shadow"}):
            with self.assertRaises(GateError):
                self.gateway.execute(dataclasses.replace(self.session, **change), self.request)
        with self.assertRaises(GateError):
            self.gateway.open_session("writer", "beta")

    def test_malformed_session_and_token_are_audited_denials(self):
        for change in ({"seal": "é"}, {"nonce": "é"}, {"principal": "\ud800"}):
            with self.assertRaises(GateError):
                self.gateway.execute(dataclasses.replace(self.session, **change), self.request)
        for token in ("é", "\ud800", [], None):
            with self.assertRaises(GateError):
                self.gateway.execute(self.session, self.request, token)
        denied = [event for event in self.gateway.audit_events() if event["event"] == "request_denied"]
        self.assertEqual(len(denied), 7)

    def test_revoked_reviewer_cannot_authorize_dispatch(self):
        token = self.approve()
        self.gateway.approvers["reviewer"] = frozenset()
        with patch.object(self.gateway, "_dispatch") as dispatch:
            with self.assertRaises(GateError):
                self.gateway.execute(self.session, self.request, token)
            dispatch.assert_not_called()

    def test_restart_preserves_consumption(self):
        token = self.approve()
        restarted = Gateway(self.db, **self.config)
        restarted.execute(self.session, self.request, token)
        with self.assertRaises(GateError):
            self.gateway.execute(self.session, self.request, token)

    def test_concurrent_replay_exactly_one_dispatch(self):
        token = self.approve()
        def call(_):
            try:
                return self.gateway.execute(self.session, self.request, token)["status"]
            except GateError:
                return "denied"
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(call, range(8)))
        self.assertEqual(results.count("simulated_only"), 1)
        self.assertEqual(results.count("denied"), 7)

    def test_adapter_failure_does_not_restore_approval(self):
        token = self.approve()
        with patch.object(self.gateway, "_dispatch", side_effect=RuntimeError("adapter failed")):
            with self.assertRaises(RuntimeError):
                self.gateway.execute(self.session, self.request, token)
        with self.assertRaises(GateError):
            self.gateway.execute(self.session, self.request, token)

    def test_audit_tamper_fails_closed_before_dispatch(self):
        token = self.approve()
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE audit SET details='{}' WHERE seq=1")
        with patch.object(self.gateway, "_dispatch") as dispatch:
            with self.assertRaises(GateError):
                self.gateway.execute(self.session, self.request, token)
            dispatch.assert_not_called()

    def test_approval_table_tamper_fails_closed(self):
        token = self.approve()
        self.gateway.execute(self.session, self.request, token)
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE approvals SET used=0")
        with self.assertRaises(GateError):
            self.gateway.execute(self.session, self.request, token)

    def test_audit_write_failure_prevents_dispatch(self):
        token = self.approve()
        with patch.object(self.gateway, "_append", side_effect=OSError("disk full")), \
             patch.object(self.gateway, "_dispatch") as dispatch:
            with self.assertRaises(OSError):
                self.gateway.execute(self.session, self.request, token)
            dispatch.assert_not_called()
        # Transaction rollback before durable authorization permits first actual dispatch.
        self.gateway.execute(self.session, self.request, token)

    def test_internal_draft_and_overlay_in_shadow_text_free_audit(self):
        shadow = self.gateway.open_session("writer", "alpha")
        result = self.gateway.execute(shadow, {"tool": "draft.prepare", "client_id": "alpha",
                                              "arguments": {"text": "sensitive synthetic draft"}})
        self.assertFalse(result["externally_usable"])
        overlay = self.gateway.execute(shadow, {"tool": "overlay.read", "client_id": "alpha",
                                               "arguments": {"document": "facts.json"}})
        self.assertIn("ALPHA_ONLY", overlay["canary"])
        events = self.gateway.audit_events()
        self.assertTrue(all(row["details"]["timestamp_utc"].endswith("+00:00") for row in events))
        self.assertTrue(all(row["details"]["policy_version"] == "1.2.0" for row in events))
        audit = json.dumps(events)
        for text in ("sensitive synthetic draft", overlay["canary"], "BETA_ONLY"):
            self.assertNotIn(text, audit)


if __name__ == "__main__":
    unittest.main()
