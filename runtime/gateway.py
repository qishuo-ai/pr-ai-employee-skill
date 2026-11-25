"""Deny-by-default reference gateway. Only host code may mint sessions/approvals.

Model-facing integration exposes execute only. No network/message adapters ship.
"""
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

from .overlay import load_overlay
from .schemas import IDENTIFIER, SchemaError, validate, validate_request


POLICY_VERSION = "1.2.0"


class GateError(PermissionError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Session:
    principal: str
    client_id: str
    mode: str
    nonce: str = field(repr=False)
    seal: str = field(repr=False)


# Risk and effect are host-owned constants; a model cannot downgrade either.
TOOL_POLICY = {
    "overlay.read": {"risk": "green", "effect": "read"},
    "draft.prepare": {"risk": "yellow", "effect": "internal"},
    "delivery.simulate": {"risk": "red", "effect": "external"},
}


class Gateway:
    def __init__(self, db_path, *, principals, approvers, secret, overlay_root, clock=time.time):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("host secret requires at least 32 random bytes")
        self.secret = secret
        self.principals = {key: frozenset(value) for key, value in principals.items()}
        self.approvers = {key: frozenset(value) for key, value in approvers.items()}
        for identity, clients in list(self.principals.items()) + list(self.approvers.items()):
            validate(identity, IDENTIFIER)
            for client in clients:
                validate(client, IDENTIFIER)
        self.overlay_root = Path(overlay_root).absolute()
        self.db_path = Path(db_path).absolute()
        self.clock = clock
        if self.db_path.is_symlink() or any(p.is_symlink() for p in self.db_path.parents):
            raise GateError("database path symlink denied")
        existed = self.db_path.exists()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if existed and not {"audit", "approvals", "metadata"}.issubset(tables):
                raise GateError("existing database schema invalid")
            if not existed:
                conn.executescript("""
                    CREATE TABLE audit(seq INTEGER PRIMARY KEY, event TEXT NOT NULL,
                      details TEXT NOT NULL, previous TEXT NOT NULL, signature TEXT NOT NULL);
                    CREATE TABLE approvals(token_hash TEXT PRIMARY KEY, binding TEXT NOT NULL,
                      expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
                    CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                """)
                conn.execute("INSERT INTO metadata VALUES ('schema', '1')")
                self._append(conn, "initialized", {"schema": 1})
            self._verify(conn)
        os.chmod(self.db_path, 0o600)

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _mac(self, value):
        return hmac.new(self.secret, canonical(value).encode(), hashlib.sha256).hexdigest()

    def _verify(self, conn):
        try:
            if conn.execute("SELECT value FROM metadata WHERE key='schema'").fetchone() != ("1",):
                raise GateError("audit metadata invalid")
            previous = "0" * 64
            rows = conn.execute("SELECT seq,event,details,previous,signature FROM audit ORDER BY seq")
            count = 0
            approval_state = {}
            for seq, event, details, recorded_previous, signature in rows:
                count += 1
                if seq != count or recorded_previous != previous:
                    raise GateError("audit chain invalid")
                expected = self._mac([seq, event, details, previous])
                if not hmac.compare_digest(signature, expected):
                    raise GateError("audit integrity failure")
                previous = signature
                decoded = json.loads(details)
                if event == "approval_issued":
                    approval_state[decoded["token_hash"]] = [decoded["binding"], decoded["expires"], 0]
                elif event == "approval_consumed":
                    token_hash = decoded["token_hash"]
                    if token_hash not in approval_state or approval_state[token_hash][2]:
                        raise GateError("approval audit state invalid")
                    approval_state[token_hash][2] = 1
            actual = {row[0]: list(row[1:]) for row in conn.execute("SELECT * FROM approvals")}
            if actual != approval_state:
                raise GateError("approval state differs from authenticated audit")
            if count == 0:
                raise GateError("audit missing")
        except sqlite3.Error as exc:
            raise GateError("audit unavailable") from exc

    def _append(self, conn, event, details):
        row = conn.execute("SELECT seq,signature FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        seq, previous = (row[0] + 1, row[1]) if row else (1, "0" * 64)
        payload = canonical({**details, "timestamp_utc": datetime.fromtimestamp(
            self.clock(), timezone.utc).isoformat(), "policy_version": POLICY_VERSION})
        conn.execute("INSERT INTO audit VALUES (?,?,?,?,?)",
                     (seq, event, payload, previous, self._mac([seq, event, payload, previous])))

    @contextmanager
    def _transaction(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def open_session(self, principal, client_id, mode="shadow"):
        """Trusted host entrypoint after authenticating principal; never a model tool."""
        validate(principal, IDENTIFIER)
        validate(client_id, IDENTIFIER)
        if client_id not in self.principals.get(principal, ()) or mode not in ("shadow", "copilot"):
            raise GateError("session scope denied")
        nonce = secrets.token_hex(24)
        seal = self._mac(["session", principal, client_id, mode, nonce])
        return Session(principal, client_id, mode, nonce, seal)

    def _check_session(self, session):
        if not isinstance(session, Session) or any(not isinstance(getattr(session, field), str)
                for field in ("principal", "client_id", "mode", "nonce", "seal")):
            raise GateError("trusted session required")
        try:
            validate(session.principal, IDENTIFIER)
            validate(session.client_id, IDENTIFIER)
        except SchemaError as exc:
            raise GateError("session identity invalid") from exc
        if (session.mode not in ("shadow", "copilot") or
                re.fullmatch(r"[0-9a-f]{48}", session.nonce) is None or
                re.fullmatch(r"[0-9a-f]{64}", session.seal) is None):
            raise GateError("session seal invalid")
        expected = self._mac(["session", session.principal, session.client_id, session.mode, session.nonce])
        if not hmac.compare_digest(session.seal, expected):
            raise GateError("session integrity failure")
        if session.client_id not in self.principals.get(session.principal, ()):
            raise GateError("session scope revoked")
        if session.mode not in ("shadow", "copilot"):
            raise GateError("unsupported mode")

    def _prepare(self, session, request):
        self._check_session(session)
        # Detach from caller-owned mutable objects before binding or dispatch.
        try:
            request = json.loads(canonical(request))
            validate_request(request)
        except (TypeError, ValueError) as exc:
            raise GateError("request schema denied") from exc
        if request["client_id"] != session.client_id:
            raise GateError("cross-client request denied")
        policy = TOOL_POLICY[request["tool"]]
        if policy["effect"] == "external" and session.mode == "shadow":
            raise GateError("shadow forbids external effects")
        binding = digest({"request": request, "principal": session.principal,
                          "client": session.client_id, "mode": session.mode,
                          "session": session.nonce, "risk": policy["risk"],
                          "effect": policy["effect"], "policy_version": POLICY_VERSION})
        return request, policy, binding

    def issue_approval(self, approver, session, request, ttl_seconds=300):
        """Trusted approval service after human review of this exact request.

        The caller must authenticate approver independently. Never expose this
        method or the signing secret to the model or untrusted request handlers.
        """
        request, policy, binding = self._prepare(session, request)
        if (approver == session.principal or
                session.client_id not in self.approvers.get(approver, ())):
            raise GateError("independent approver required")
        if policy["effect"] != "external":
            raise GateError("approval only for gated external-class actions")
        if (isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, (int, float)) or
                not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= 3600):
            raise GateError("approval expiry invalid")
        token = secrets.token_urlsafe(32)
        token_hash = digest(token)
        expires = self.clock() + ttl_seconds
        with self._transaction() as conn:
            conn.execute("INSERT INTO approvals VALUES (?,?,?,0)", (token_hash, binding, expires))
            self._append(conn, "approval_issued", {"token_hash": token_hash, "binding": binding,
                          "approver_hash": digest(approver), "expires": expires})
        return token

    def _issuer_still_authorized(self, conn, token_hash, session):
        allowed = {digest(identity) for identity, clients in self.approvers.items()
                   if session.client_id in clients and identity != session.principal}
        for (details,) in conn.execute("SELECT details FROM audit WHERE event='approval_issued'"):
            issued = json.loads(details)
            if issued["token_hash"] == token_hash:
                return issued["approver_hash"] in allowed
        return False

    def execute(self, session, request, approval_token=None):
        try:
            request, policy, binding = self._prepare(session, request)
        except GateError:
            # Never log invalid request fields, customer text or authentication material.
            with self._transaction() as conn:
                self._append(conn, "request_denied", {"reason": "invalid_scope_schema_or_mode"})
            raise
        with self._transaction() as conn:
            if policy["effect"] == "external":
                token_hash = digest(approval_token) if (isinstance(approval_token, str) and
                    re.fullmatch(r"[A-Za-z0-9_-]{43}", approval_token) is not None) else ""
                row = conn.execute("SELECT binding,expires,used FROM approvals WHERE token_hash=?",
                                   (token_hash,)).fetchone()
                if (row is None or row[0] != binding or row[1] <= self.clock() or row[2] or
                        not self._issuer_still_authorized(conn, token_hash, session)):
                    self._append(conn, "request_denied", {"reason": "approval_invalid", "binding": binding})
                    # Commit denial; no dispatch occurs.
                    conn.commit()
                    raise GateError("valid unexpired unused bound approval required")
                conn.execute("UPDATE approvals SET used=1 WHERE token_hash=? AND used=0", (token_hash,))
                self._append(conn, "approval_consumed", {"token_hash": token_hash, "binding": binding})
            # Durable authorization + one-use consumption precede dispatch. A crash
            # may leave an unknown outcome; never auto-retry with the same approval.
            self._append(conn, "dispatch_authorized", {"binding": binding, "tool": request["tool"],
                         "risk": policy["risk"], "mode": session.mode,
                         "client_hash": digest(session.client_id), "principal_hash": digest(session.principal)})
        try:
            result = self._dispatch(session, request)
        except Exception as exc:
            with self._transaction() as conn:
                self._append(conn, "dispatch_failed", {"binding": binding, "exception_type": type(exc).__name__})
            raise
        with self._transaction() as conn:
            self._append(conn, "dispatch_completed", {"binding": binding, "result_hash": digest(result)})
        return result

    def _dispatch(self, session, request):
        tool, arguments = request["tool"], request["arguments"]
        if tool == "overlay.read":
            return load_overlay(self.overlay_root,
                                authorized_clients=self.principals[session.principal],
                                session_client=session.client_id, requested_client=request["client_id"],
                                document=arguments["document"])
        if tool == "draft.prepare":
            return {"status": "internal_draft", "text": arguments["text"], "externally_usable": False}
        if tool == "delivery.simulate":
            # Intentionally no send/web/network implementation. This demonstrates
            # the boundary with a local receipt, never actual communication.
            return {"status": "simulated_only", "delivery_id": secrets.token_hex(16),
                    "destination": arguments["destination"], "content_hash": digest(arguments["text"])}
        raise GateError("tool denied by default")

    def audit_events(self):
        with self._transaction() as conn:
            return [{"seq": row[0], "event": row[1], "details": json.loads(row[2]),
                     "previous": row[3], "signature": row[4]}
                    for row in conn.execute("SELECT * FROM audit ORDER BY seq")]
