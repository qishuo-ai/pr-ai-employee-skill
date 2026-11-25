import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from runtime.shadow import (ShadowValidationError, decode_json, levenshtein_distance, prepare_event,
                            read_events, record_event, summarize_events, validate_event)


def sample(**changes):
    event = {
        "schema_version": "1.0", "event_id": "event-001", "client_id": "client-alpha",
        "task_id": "task-001", "provenance": "synthetic", "observed_at": "2026-11-25T10:00:00+08:00",
        "model_id": "synthetic-no-model", "review_state": "completed", "ai_risk": "YELLOW",
        "human_risk": "RED", "ai_latency_ms": 1500, "human_review_latency_ms": 32000,
        "first_pass_accepted": False, "draft_text": "周末交付。", "final_text": "待确认后交付。",
        "supersedes_event_id": None,
    }
    event.update(changes)
    if "event_id" in changes and "task_id" not in changes:
        event["task_id"] = changes["event_id"]
    return event


class DistanceTests(unittest.TestCase):
    def test_known_and_multilingual_distances(self):
        for a, b, expected in [("kitten", "sitting", 3), ("", "", 0), ("", "中文", 2),
                               ("你好", "您好", 1), ("A😀", "A😃", 1),
                               ("é", "e\u0301", 2), ("prefixabcend", "prefixaxcend", 1)]:
            self.assertEqual(levenshtein_distance(a, b), expected)
            self.assertEqual(levenshtein_distance(b, a), expected)

    def test_optimized_algorithm_matches_reference(self):
        from itertools import product
        values = ["".join(chars) for size in range(4) for chars in product("ab", repeat=size)]
        for a in values:
            for b in values:
                matrix = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
                for i in range(len(a) + 1):
                    matrix[i][0] = i
                for j in range(len(b) + 1):
                    matrix[0][j] = j
                for i in range(1, len(a) + 1):
                    for j in range(1, len(b) + 1):
                        matrix[i][j] = min(matrix[i - 1][j] + 1, matrix[i][j - 1] + 1,
                                           matrix[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
                self.assertEqual(levenshtein_distance(a, b), matrix[-1][-1])

    def test_first_pass_does_not_follow_edit_distance(self):
        event = prepare_event(sample(draft_text="Hello", final_text="Hello!", first_pass_accepted=True))
        stats = summarize_events([event])["by_provenance"]["synthetic"]
        self.assertEqual(stats["first_pass"]["rate"], 1)
        self.assertEqual(stats["edit_distance"]["mean"], 1)


class EventTests(unittest.TestCase):
    def test_text_never_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            record_event(path, sample(draft_text="SYNTHETIC_DRAFT_SECRET", final_text="SYNTHETIC_FINAL_SECRET"))
            raw = path.read_text()
            self.assertNotIn("SYNTHETIC_DRAFT_SECRET", raw)
            self.assertNotIn("SYNTHETIC_FINAL_SECRET", raw)
            self.assertNotIn('"draft_text"', raw)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(len(read_events(path)), 1)

    def test_invalid_fields_risks_latency_and_timestamp_rejected(self):
        bad = [{"ai_risk": "pink"}, {"human_risk": []}, {"ai_latency_ms": -1},
               {"ai_latency_ms": True}, {"ai_latency_ms": math.nan}, {"ai_latency_ms": 10 ** 1000},
               {"draft_text": "\ud800"},
               {"human_review_latency_ms": math.inf}, {"schema_version": "2"},
               {"observed_at": "2026-11-25T10:00:00"}, {"observed_at": "yesterday"},
               {"event_id": "customer@example.invalid"}, {"first_pass_accepted": 1},
               {"draft_text": "x" * 10001}, {"extra": "must not be logged"}]
        for changes in bad:
            with self.subTest(changes=repr(changes)[:80]), self.assertRaises(ShadowValidationError):
                prepare_event(sample(**changes))
        event = sample()
        del event["provenance"]
        with self.assertRaises(ShadowValidationError):
            prepare_event(event)

    def test_pending_and_unknown_fields_have_explicit_denominators(self):
        pending = prepare_event(sample(event_id="pending", review_state="pending", final_text=None,
                                       human_risk=None, human_review_latency_ms=None, first_pass_accepted=None))
        unknown = prepare_event(sample(event_id="unknown", human_risk=None, ai_risk=None,
                                       final_text=None, first_pass_accepted=None, ai_latency_ms=None,
                                       human_review_latency_ms=None))
        stats = summarize_events([pending, unknown])["by_provenance"]["synthetic"]
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["completed"], 1)
        for key in ("first_pass", "risk_misses", "edit_distance"):
            self.assertEqual(stats[key]["denominator"], 0)
            self.assertEqual(stats[key]["excluded"], 2)
        self.assertIsNone(stats["first_pass"]["rate"])
        self.assertIsNone(stats["risk_misses"]["rate"])
        self.assertEqual(stats["ai_latency"]["n"], 1)
        self.assertIsNone(stats["human_review_latency"]["mean"])
        with self.assertRaises(ShadowValidationError):
            prepare_event(sample(review_state="pending"))

    def test_duplicate_rejected_without_appending(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            record_event(path, sample())
            before = path.read_bytes()
            with self.assertRaises(ShadowValidationError):
                record_event(path, sample())
            self.assertEqual(path.read_bytes(), before)
            event = prepare_event(sample())
            with self.assertRaises(ShadowValidationError):
                summarize_events([event, event])

    def test_concurrent_duplicate_only_one_record(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            def append(_):
                try:
                    record_event(path, sample())
                    return True
                except ShadowValidationError:
                    return False
            with ThreadPoolExecutor(max_workers=4) as pool:
                self.assertEqual(sum(pool.map(append, range(8))), 1)
            self.assertEqual(len(read_events(path)), 1)

    def test_tampered_or_partial_existing_log_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            event = prepare_event(sample())
            event["text_metrics"]["normalized_edit_distance"] = 0.99
            path.write_text(json.dumps(event) + "\n")
            with self.assertRaises(ShadowValidationError):
                record_event(path, sample(event_id="second"))
            path.write_text('{"partial":')
            with self.assertRaises(ShadowValidationError):
                read_events(path)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "target.jsonl"
            target.touch()
            link = Path(folder) / "link.jsonl"
            link.symlink_to(target)
            with self.assertRaises(ShadowValidationError):
                record_event(link, sample())


    def test_pending_to_completed_counts_task_once(self):
        pending = sample(event_id="pending", task_id="one-task", review_state="pending", final_text=None,
                         human_risk=None, human_review_latency_ms=None, first_pass_accepted=None)
        reviewed = sample(event_id="reviewed", task_id="one-task", supersedes_event_id="pending",
                          observed_at="2026-11-25T10:05:00+08:00")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            record_event(path, pending)
            record_event(path, reviewed)
            result = summarize_events(read_events(path))
            self.assertEqual(result["total_events"], 2)
            self.assertEqual(result["current_task_snapshots"], 1)
            self.assertEqual(result["superseded_events"], 1)
            self.assertEqual(result["by_provenance"]["synthetic"]["ai_latency"]["n"], 1)
            self.assertEqual(result["by_provenance"]["synthetic"]["pending"], 0)
            with self.assertRaises(ShadowValidationError):
                record_event(path, sample(event_id="again", task_id="one-task", supersedes_event_id="pending"))

    def test_review_cannot_change_original_measurements_or_identity(self):
        pending = prepare_event(sample(event_id="pending", task_id="one-task", review_state="pending", final_text=None,
                                       human_risk=None, human_review_latency_ms=None, first_pass_accepted=None))
        for change in ({"ai_risk": "BLACK"}, {"draft_text": "changed"}, {"ai_latency_ms": 1},
                       {"task_id": "different"}, {"client_id": "client-beta"},
                       {"observed_at": "2026-11-24T10:00:00+08:00"}, {"supersedes_event_id": None}):
            details = dict(event_id="reviewed", task_id="one-task", supersedes_event_id="pending")
            details.update(change)
            completed = prepare_event(sample(**details))
            with self.subTest(change=change), self.assertRaises(ShadowValidationError):
                summarize_events([pending, completed])

    def test_strict_json_rejects_duplicate_keys_and_constants(self):
        for value in ('{"ai_risk":"RED","ai_risk":"GREEN"}', '{"value":NaN}', '{"value":Infinity}'):
            with self.assertRaises(ShadowValidationError):
                decode_json(value)

    def test_stored_metric_consistency(self):
        event = prepare_event(sample(draft_text="", final_text=""))
        self.assertEqual(event["text_metrics"]["normalized_edit_distance"], 0)
        for changes in ({"draft_characters": -1}, {"levenshtein_distance": 1},
                        {"draft_sha256": "oops"}, {"extra": True}):
            bad = copy.deepcopy(event)
            bad["text_metrics"].update(changes)
            with self.assertRaises(ShadowValidationError):
                validate_event(bad)


class SummaryTests(unittest.TestCase):
    def test_risk_and_provenance_are_separated(self):
        events = [prepare_event(sample(event_id="s1")),
                  prepare_event(sample(event_id="s2", ai_risk="BLACK", human_risk="RED", first_pass_accepted=True)),
                  prepare_event(sample(event_id="o1", provenance="observed", ai_risk="YELLOW", human_risk="GREEN"))]
        result = summarize_events(events)
        synthetic = result["by_provenance"]["synthetic"]
        self.assertEqual(synthetic["risk_misses"]["misses"], 1)
        self.assertEqual(synthetic["risk_misses"]["severe_misses"], 1)
        self.assertEqual(synthetic["risk_misses"]["rate"], .5)
        self.assertEqual(synthetic["first_pass"]["rate"], .5)
        self.assertEqual(result["by_provenance"]["observed"]["risk_misses"]["misses"], 0)
        self.assertNotIn("first_pass", result)

    def test_empty_summary_never_claims_success(self):
        result = summarize_events([])
        for stats in result["by_provenance"].values():
            self.assertEqual(stats["events"], 0)
            self.assertIsNone(stats["risk_misses"]["rate"])
            self.assertIsNone(stats["first_pass"]["rate"])
            self.assertIsNone(stats["ai_latency"]["p95_nearest_rank"])

    def test_latency_units_and_nearest_rank_percentiles(self):
        events = [prepare_event(sample(event_id=f"e{i}", ai_latency_ms=i * 100)) for i in range(1, 21)]
        latency = summarize_events(events)["by_provenance"]["synthetic"]["ai_latency"]
        self.assertEqual(latency["mean"], 1050)
        self.assertEqual(latency["p50_nearest_rank"], 1000)
        self.assertEqual(latency["p95_nearest_rank"], 1900)
        self.assertEqual(latency["unit"], "ms")

    def test_cli_errors_do_not_echo_private_text(self):
        with tempfile.TemporaryDirectory() as folder:
            input_path = Path(folder) / "input.json"
            input_path.write_text('{"SENSITIVE": invalid}')
            run = subprocess.run([sys.executable, "scripts/shadow_metrics.py", "record", "--input", str(input_path),
                                  "--log", str(Path(folder) / "events.jsonl")], text=True, capture_output=True)
            self.assertEqual(run.returncode, 2)
            self.assertNotIn("SENSITIVE", run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
