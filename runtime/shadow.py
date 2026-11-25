"""Privacy-preserving Shadow Mode events and exact, reproducible metrics.

This is an offline measurement utility. It does not run a model, send messages,
prove reviewer independence, or authorize a change from Shadow to Copilot.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "1.0"
RISKS = {"GREEN": 0, "YELLOW": 1, "RED": 2, "BLACK": 3}
MAX_TEXT_CHARACTERS = 10_000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_INPUT_FIELDS = {
    "schema_version", "event_id", "client_id", "task_id", "provenance",
    "observed_at", "model_id", "review_state", "ai_risk", "human_risk",
    "ai_latency_ms", "human_review_latency_ms", "first_pass_accepted",
    "draft_text", "final_text", "supersedes_event_id",
}
_TEXT_FIELDS = {"draft_sha256", "final_sha256", "draft_characters", "final_characters",
                "levenshtein_distance", "normalized_edit_distance"}
_STORED_FIELDS = (_INPUT_FIELDS - {"draft_text", "final_text"}) | {"text_metrics"}


class ShadowValidationError(ValueError):
    """Invalid event; errors deliberately do not echo input values."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ShadowValidationError(message)


def _number(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _common(event: Mapping[str, Any], fields: set[str]) -> None:
    _require(isinstance(event, dict), "event must be a JSON object")
    _require(set(event) == fields, "event fields must exactly match the schema")
    _require(event["schema_version"] == SCHEMA_VERSION, "unsupported schema_version")
    for field in ("event_id", "client_id", "task_id", "model_id"):
        _require(isinstance(event[field], str) and bool(_ID.fullmatch(event[field])),
                 f"{field} must be a pseudonymous identifier of 1–64 safe characters")
    prior = event["supersedes_event_id"]
    _require(prior is None or (isinstance(prior, str) and bool(_ID.fullmatch(prior))),
             "supersedes_event_id must be null or a safe identifier")
    _require(prior != event["event_id"], "event cannot supersede itself")
    _require(event["provenance"] in ("synthetic", "observed"), "invalid provenance")
    _require(event["review_state"] in ("pending", "completed"), "invalid review_state")
    stamp = event["observed_at"]
    _require(isinstance(stamp, str), "observed_at must be an ISO 8601 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        _require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
                 "observed_at must include a timezone")
    except (ValueError, OverflowError):
        raise ShadowValidationError("observed_at must be an ISO 8601 timestamp with timezone") from None
    for field in ("ai_risk", "human_risk"):
        _require(event[field] is None or (isinstance(event[field], str) and event[field] in RISKS),
                 f"invalid {field}")
    for field in ("ai_latency_ms", "human_review_latency_ms"):
        _require(event[field] is None or _number(event[field]), f"invalid {field}")
    _require(event["first_pass_accepted"] is None or type(event["first_pass_accepted"]) is bool,
             "first_pass_accepted must be boolean or null")
    if event["review_state"] == "pending":
        for field in ("human_risk", "human_review_latency_ms", "first_pass_accepted"):
            _require(event[field] is None, f"pending event cannot contain {field}")


def levenshtein_distance(first: str, second: str) -> int:
    """Exact insertion/deletion/substitution count over Unicode code points.

    No NFC normalization, byte conversion, word tokenization, or approximation.
    Common prefix/suffix trimming saves work without changing the answer.
    """
    if first == second:
        return 0
    prefix = 0
    end = min(len(first), len(second))
    while prefix < end and first[prefix] == second[prefix]:
        prefix += 1
    first, second = first[prefix:], second[prefix:]
    suffix = 0
    end = min(len(first), len(second))
    while suffix < end and first[-suffix - 1] == second[-suffix - 1]:
        suffix += 1
    if suffix:
        first, second = first[:-suffix], second[:-suffix]
    if len(first) < len(second):
        first, second = second, first
    previous = list(range(len(second) + 1))
    for i, char in enumerate(first, 1):
        current = [i]
        for j, other in enumerate(second, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (char != other)))
        previous = current
    return previous[-1]


def prepare_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Consume local draft/final text transiently; return a text-free event."""
    _common(event, _INPUT_FIELDS)
    draft, final = event["draft_text"], event["final_text"]
    for field, value in (("draft_text", draft), ("final_text", final)):
        _require(value is None or (isinstance(value, str) and len(value) <= MAX_TEXT_CHARACTERS),
                 f"{field} must be null or at most {MAX_TEXT_CHARACTERS} Unicode characters")
        if value is not None:
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ShadowValidationError(f"{field} must contain valid Unicode scalar values") from None
    if event["review_state"] == "pending":
        _require(final is None, "pending event cannot contain final_text")
    distance = None if draft is None or final is None else levenshtein_distance(draft, final)
    denominator = max(len(draft or ""), len(final or ""))
    metrics = {
        "draft_sha256": None if draft is None else hashlib.sha256(draft.encode("utf-8")).hexdigest(),
        "final_sha256": None if final is None else hashlib.sha256(final.encode("utf-8")).hexdigest(),
        "draft_characters": None if draft is None else len(draft),
        "final_characters": None if final is None else len(final),
        "levenshtein_distance": distance,
        "normalized_edit_distance": None if distance is None else (distance / denominator if denominator else 0.0),
    }
    result = {key: value for key, value in event.items() if key not in ("draft_text", "final_text")}
    result["text_metrics"] = metrics
    validate_event(result)
    return result


def validate_event(event: Mapping[str, Any]) -> None:
    """Validate stored events, including consistency of derived metric fields."""
    _common(event, _STORED_FIELDS)
    metrics = event["text_metrics"]
    _require(isinstance(metrics, dict) and set(metrics) == _TEXT_FIELDS,
             "text_metrics fields must exactly match the schema")
    for prefix in ("draft", "final"):
        digest, size = metrics[f"{prefix}_sha256"], metrics[f"{prefix}_characters"]
        _require((digest is None) == (size is None), "text hash and length availability must agree")
        if size is not None:
            _require(type(size) is int and 0 <= size <= MAX_TEXT_CHARACTERS, "invalid text length")
            _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                     "invalid text hash")
    if event["review_state"] == "pending":
        _require(metrics["final_characters"] is None, "pending event cannot contain final metrics")
    distance, normalized = metrics["levenshtein_distance"], metrics["normalized_edit_distance"]
    a, b = metrics["draft_characters"], metrics["final_characters"]
    if a is None or b is None:
        _require(distance is None and normalized is None, "missing text requires null distance")
    else:
        _require(type(distance) is int and abs(a - b) <= distance <= max(a, b), "invalid edit distance")
        expected = distance / max(a, b) if max(a, b) else 0.0
        _require(_number(normalized) and math.isclose(normalized, expected, rel_tol=1e-12, abs_tol=1e-12),
                 "normalized distance does not match distance and lengths")
        if metrics["draft_sha256"] == metrics["final_sha256"]:
            _require(a == b and distance == 0, "identical hashes require equal lengths and zero distance")


def decode_json(text: str) -> Any:
    """Strict JSON: duplicate fields and non-finite constants are rejected."""
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate JSON field")
            result[key] = value
        return result
    def constant(_value):
        raise ShadowValidationError("non-finite JSON constant")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def _parse_lines(lines: Iterable[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, line in enumerate(lines, 1):
        _require(bool(line.strip()), f"blank log record at line {number}")
        try:
            event = decode_json(line)
        except (ValueError, TypeError):
            raise ShadowValidationError(f"invalid JSON record at line {number}") from None
        validate_event(event)
        _require(event["event_id"] not in seen, "duplicate event_id")
        seen.add(event["event_id"])
        events.append(event)
    _current_snapshots(events)
    return events


def _current_snapshots(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate review lineage and return one current snapshot per task."""
    by_id: dict[str, dict[str, Any]] = {}
    current: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in events:
        _require(event["event_id"] not in by_id, "duplicate event_id")
        key = (event["provenance"], event["client_id"], event["task_id"])
        prior_id = event["supersedes_event_id"]
        if prior_id is None:
            _require(key not in current, "task already exists; completed review must explicitly supersede pending event")
        else:
            prior = by_id.get(prior_id)
            _require(prior is not None, "superseded event must appear earlier in the log")
            _require(current.get(key) is prior, "superseded event must be the current snapshot of the same task")
            _require(prior["review_state"] == "pending" and event["review_state"] == "completed",
                     "only pending-to-completed review transitions are allowed")
            for field in ("model_id", "ai_risk", "ai_latency_ms"):
                _require(event[field] == prior[field], "review cannot change original AI measurement")
            for field in ("draft_sha256", "draft_characters"):
                _require(event["text_metrics"][field] == prior["text_metrics"][field],
                         "review cannot change original AI draft")
            previous_time = dt.datetime.fromisoformat(prior["observed_at"].replace("Z", "+00:00"))
            current_time = dt.datetime.fromisoformat(event["observed_at"].replace("Z", "+00:00"))
            _require(current_time >= previous_time, "review timestamp cannot precede pending observation")
        by_id[event["event_id"]] = event
        current[key] = event
    return list(current.values())


def _open_private_log(path: str | Path, *, create: bool):
    path = Path(path)
    # Refuse a symlink at the log itself. Parent directories must be trusted;
    # system aliases such as macOS /var -> /private/var are supported.
    _require(not path.is_symlink(), "log file cannot be a symlink")
    flags = os.O_RDWR if create else os.O_RDONLY
    if create:
        flags |= os.O_CREAT
    flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        _require(stat.S_ISREG(os.fstat(fd).st_mode), "log must be a regular file")
        if create:
            os.fchmod(fd, 0o600)
        return os.fdopen(fd, "r+" if create else "r", encoding="utf-8")
    except Exception:
        os.close(fd)
        raise


def record_event(log_path: str | Path, event: Mapping[str, Any]) -> dict[str, Any]:
    """Append one unique event under an advisory process lock (POSIX).

    Existing log records are validated first. No text or arbitrary metadata is
    written. Caller owns access control and private retention of the log.
    """
    prepared = prepare_event(event)
    with _open_private_log(log_path, create=True) as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            existing = _parse_lines(stream)
            _current_snapshots(existing + [prepared])
            stream.seek(0, os.SEEK_END)
            if stream.tell():
                stream.seek(stream.tell() - 1)
                _require(stream.read(1) == "\n", "log must end with a newline")
                stream.seek(0, os.SEEK_END)
            stream.write(json.dumps(prepared, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
    return prepared


def read_events(log_path: str | Path) -> list[dict[str, Any]]:
    with _open_private_log(log_path, create=False) as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        try:
            return _parse_lines(stream)
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _latency(values: list[float], total: int) -> dict[str, Any]:
    ordered = sorted(values)
    return {"unit": "ms", "n": len(values), "excluded": total - len(values),
            "mean": _mean(values),
            "p50_nearest_rank": ordered[math.ceil(.5 * len(values)) - 1] if values else None,
            "p95_nearest_rank": ordered[math.ceil(.95 * len(values)) - 1] if values else None}


def _summarize_group(events: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [e for e in events if e["review_state"] == "completed"]
    accepted = [e["first_pass_accepted"] for e in completed if e["first_pass_accepted"] is not None]
    pairs = [e for e in completed if e["ai_risk"] is not None and e["human_risk"] is not None]
    severe = [e for e in pairs if RISKS[e["human_risk"]] >= RISKS["RED"]]
    misses = sum(RISKS[e["ai_risk"]] < RISKS[e["human_risk"]] for e in pairs)
    severe_misses = sum(RISKS[e["ai_risk"]] < RISKS[e["human_risk"]] for e in severe)
    edited = [e["text_metrics"] for e in completed if e["text_metrics"]["levenshtein_distance"] is not None]
    return {
        "events": len(events), "completed": len(completed), "pending": len(events) - len(completed),
        "first_pass": {"accepted": sum(accepted), "denominator": len(accepted),
                       "excluded": len(events) - len(accepted), "rate": _mean(accepted)},
        "edit_distance": {"unit": "Unicode code points", "denominator": len(edited),
                          "excluded": len(events) - len(edited),
                          "mean": _mean([e["levenshtein_distance"] for e in edited]),
                          "mean_normalized": _mean([e["normalized_edit_distance"] for e in edited]),
                          "normalization": "distance / max(draft_characters, final_characters); empty/empty = 0"},
        "risk_misses": {"misses": misses, "denominator": len(pairs),
                        "excluded": len(events) - len(pairs), "rate": misses / len(pairs) if pairs else None,
                        "severe_misses": severe_misses, "severe_denominator": len(severe),
                        "severe_rate": severe_misses / len(severe) if severe else None},
        "ai_latency": _latency([e["ai_latency_ms"] for e in events if e["ai_latency_ms"] is not None], len(events)),
        "human_review_latency": _latency([e["human_review_latency_ms"] for e in completed
                                          if e["human_review_latency_ms"] is not None], len(events)),
    }


def summarize_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    events = list(events)
    seen: set[str] = set()
    for event in events:
        validate_event(event)
        _require(event["event_id"] not in seen, "duplicate event_id")
        seen.add(event["event_id"])
    snapshots = _current_snapshots(events)
    return {
        "schema_version": SCHEMA_VERSION,
        "measurement": "shadow_observations_not_an_autonomy_authorization",
        "total_events": len(events),
        "current_task_snapshots": len(snapshots),
        "superseded_events": len(events) - len(snapshots),
        # No pooled success rate: synthetic data can never inflate observed metrics.
        "by_provenance": {kind: _summarize_group([e for e in snapshots if e["provenance"] == kind])
                          for kind in ("synthetic", "observed")},
        "limitations": ["Human labels are supplied, not independently verified by this utility.",
                        "Edit distance measures textual changes, not factual correctness or usefulness.",
                        "Risk misses compare supplied ordinal labels; omitted risks require human review.",
                        "Hashes and pseudonymous identifiers are sensitive metadata; keep observed logs private.",
                        "This utility does not measure production performance without observed events."],
    }
