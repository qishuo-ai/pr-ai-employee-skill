"""Strict historical evidence counts, separate from observed Shadow metrics.

Consumes an already-prepared public object; never reads private evidence,
executes artifacts, proves attribution, or infers quality from receipt.
"""
from __future__ import annotations

from decimal import Decimal
import json
import math
import re
from typing import Any

SCHEMA_VERSION = "1.0"
STUDY_TYPE = "retrospective"
SOURCE_VERIFICATION = "maintainer_private_evidence_not_independently_verified"
QUALITY_FIELDS = {"first_pass_rate", "mean_edit_distance", "risk_miss_rate", "ai_latency_ms"}
ROOT_FIELDS = {"schema_version", "study_type", "source_verification", "quality_metrics", "cases", "episodes"}
CASE_FIELDS = {"case_id", "title", "scope", "evidence_summary", "learning_points", "gaps"}
EPISODE_FIELDS = {"episode_id", "case_id", "request_seen", "submission_seen",
                  "receipt_acknowledged", "quality_accepted", "chat_elapsed_minutes"}
OBSERVATION_FIELDS = ("request_seen", "submission_seen", "receipt_acknowledged")
IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")
# Heuristics catch source pointers, not all identifying prose.
PRIVATE_POINTER = re.compile(r"https?://|file://|sandbox:|/(?:Users|home|private|var|tmp)/|[A-Za-z]:\\|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


class RetrospectiveValidationError(ValueError):
    """Errors omit input values, excerpts and filesystem paths."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RetrospectiveValidationError(message)


def exact_fields(value: Any, expected: set[str], label: str) -> None:
    require(isinstance(value, dict) and set(value) == expected,
            label + " must contain exactly the documented fields")


def identifier(value: Any) -> None:
    require(isinstance(value, str) and bool(IDENTIFIER.fullmatch(value)),
            "identifiers must be lowercase pseudonyms of 1–48 safe characters")


def public_text(value: Any) -> None:
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= 5000,
            "case text must be nonempty and at most 5000 characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise RetrospectiveValidationError("case text must contain valid Unicode") from None
    require(not PRIVATE_POINTER.search(value), "case text cannot contain source URLs, email addresses or local paths")


def decode_json(text: str) -> Any:
    """Reject duplicate keys and non-finite JSON constants at every depth."""
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise RetrospectiveValidationError("non-finite JSON constant")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (json.JSONDecodeError, UnicodeError):
        raise RetrospectiveValidationError("invalid JSON input") from None


def validate_dataset(data: Any) -> None:
    exact_fields(data, ROOT_FIELDS, "dataset")
    require(data["schema_version"] == SCHEMA_VERSION, "unsupported schema_version")
    require(data["study_type"] == STUDY_TYPE, "only retrospective study_type is accepted")
    require(data["source_verification"] == SOURCE_VERIFICATION, "unsupported source verification claim")
    exact_fields(data["quality_metrics"], QUALITY_FIELDS, "quality_metrics")
    require(all(value is None for value in data["quality_metrics"].values()),
            "historical evidence cannot supply quality or model-latency metrics")
    cases, episodes = data["cases"], data["episodes"]
    require(isinstance(cases, list) and 1 <= len(cases) <= 1000, "cases must contain 1–1000 records")
    require(isinstance(episodes, list) and len(episodes) <= 10000, "episodes must contain at most 10000 records")
    case_ids = set()
    for case in cases:
        exact_fields(case, CASE_FIELDS, "case")
        identifier(case["case_id"])
        require(case["case_id"] not in case_ids, "duplicate case_id")
        case_ids.add(case["case_id"])
        for field in ("title", "scope"):
            public_text(case[field])
        for field in ("evidence_summary", "learning_points", "gaps"):
            values = case[field]
            require(isinstance(values, list) and 1 <= len(values) <= 50,
                    "case evidence, learnings and gaps must each contain 1–50 text entries")
            for value in values:
                public_text(value)
    episode_ids = set()
    for episode in episodes:
        exact_fields(episode, EPISODE_FIELDS, "episode")
        identifier(episode["episode_id"])
        identifier(episode["case_id"])
        require(episode["episode_id"] not in episode_ids, "duplicate episode_id; repeated tasks must not be recounted")
        episode_ids.add(episode["episode_id"])
        require(episode["case_id"] in case_ids, "episode references unknown case")
        for field in OBSERVATION_FIELDS:
            require(episode[field] is None or type(episode[field]) is bool,
                    "observed evidence flags must be boolean or null")
        require(episode["quality_accepted"] is None,
                "receipt is not quality acceptance; quality_accepted must remain null")
        minutes = episode["chat_elapsed_minutes"]
        if minutes is not None:
            require(type(minutes) in (int, float), "chat elapsed minutes must be numeric or null")
            try:
                valid = math.isfinite(minutes) and minutes >= 0
            except OverflowError:
                valid = False
            require(valid, "chat elapsed minutes must be finite and nonnegative")
            require(episode["request_seen"] is True and episode["submission_seen"] is True,
                    "chat duration requires visible request and submission anchors")


def evidence_counts(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Count confirmed evidence; false and unknown remain separate."""
    counts = {}
    for field in OBSERVATION_FIELDS:
        counts[field] = {
            "confirmed": sum(item[field] is True for item in episodes),
            "not_seen": sum(item[field] is False for item in episodes),
            "unknown": sum(item[field] is None for item in episodes),
        }
    return counts


def chat_intervals(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [{"episode_id": item["episode_id"], "minutes": item["chat_elapsed_minutes"]}
            for item in episodes if item["chat_elapsed_minutes"] is not None]
    values = [row["minutes"] for row in rows]
    # Decimal prevents overflowing an intermediate sum of finite measurements.
    mean = float(sum((Decimal(str(value)) for value in values), Decimal(0))/Decimal(len(values))) if values else None
    return {
        "measurement": "visible_chat_request_to_submission_span",
        "unit": "minutes",
        "is_ai_latency": False,
        "is_active_human_work_time": False,
        "measured_episodes": len(values),
        "unknown_episodes": len(episodes)-len(values),
        "mean": mean,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "observations": rows,
        "limits": "Chat spans can include queueing, parallel work and waiting; they do not measure generation speed, human labor or time saved.",
    }


def summarize_dataset(data: Any) -> dict[str, Any]:
    validate_dataset(data)
    cases, episodes = data["cases"], data["episodes"]
    per_case = []
    for case in cases:
        rows = [episode for episode in episodes if episode["case_id"] == case["case_id"]]
        per_case.append({"case_id": case["case_id"], "episodes": len(rows),
                         "receipt_counts": evidence_counts(rows)})
    return {
        "schema_version": SCHEMA_VERSION,
        "study_type": STUDY_TYPE,
        "measurement": "historical_business_evidence_counts_not_observed_shadow_performance",
        "source_verification": SOURCE_VERIFICATION,
        "externally_independently_verified": False,
        "case_count": len(cases),
        "episode_count": len(episodes),
        "cases_with_episodes": sum(row["episodes"] > 0 for row in per_case),
        "receipt_counts": evidence_counts(episodes),
        "by_case": per_case,
        "chat_elapsed": chat_intervals(episodes),
        "quality_accepted": None,
        "quality_metrics": {name: None for name in sorted(QUALITY_FIELDS)},
        "contributes_to_observed_shadow_metrics": False,
        "limitations": [
            "Evidence summaries and attribution are supplied by the maintainer; private originals are not inspected or independently certified by this tool.",
            "A submitted file or receipt acknowledgement is not quality acceptance, first-pass success or a verified risk judgment.",
            "Unknown fields remain unknown; historical records are never pooled with synthetic evaluations or observed Shadow events.",
            "Chat elapsed time is not model latency, active human work time or measured time saved.",
            "Duplicate IDs are rejected. The maintainer must assign stable IDs to prevent the same underlying task being renamed and recounted.",
            "Structural pointer checks do not prove anonymization; names, brands, project clues and indirect identifiers require maintainer review.",
        ],
    }
