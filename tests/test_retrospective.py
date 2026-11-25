"""Synthetic schema/count fixtures; no private case data or real quality labels."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from runtime.retrospective import (RetrospectiveValidationError, SOURCE_VERIFICATION,
    QUALITY_FIELDS, decode_json, summarize_dataset, validate_dataset)
from runtime.shadow import ShadowValidationError, read_events, summarize_events, validate_event

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("retrospective_cli", ROOT/"scripts/retrospective_report.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def sample():
    return {
        "schema_version": "1.0",
        "study_type": "retrospective",
        "source_verification": SOURCE_VERIFICATION,
        "quality_metrics": {key: None for key in QUALITY_FIELDS},
        "cases": [{
            "case_id": f"case-{number:03}", "title": "匿名工作示例",
            "scope": "用于验证统计契约的合成测试材料。",
            "evidence_summary": ["测试输入包含任务与交付状态。"],
            "learning_points": ["收到文件不等于质量验收。"],
            "gaps": ["没有独立质量审核。"],
        } for number in range(1, 5)],
        "episodes": [{
            "episode_id": f"episode-{number:03}",
            "case_id": f"case-{(number-1)%4+1:03}",
            "request_seen": True if number <= 6 else None,
            "submission_seen": True if number <= 5 else False,
            "receipt_acknowledged": True if number <= 3 else (False if number == 4 else None),
            "quality_accepted": None,
            "chat_elapsed_minutes": [237, 194, 415][number-1] if number <= 3 else None,
        } for number in range(1, 8)],
    }


class RetrospectiveTests(unittest.TestCase):
    def test_four_cases_seven_episodes_and_receipts_are_counts_only(self):
        report = summarize_dataset(sample())
        self.assertEqual(4, report["case_count"])
        self.assertEqual(7, report["episode_count"])
        self.assertEqual({"confirmed": 3, "not_seen": 1, "unknown": 3},
                         report["receipt_counts"]["receipt_acknowledged"])
        self.assertEqual({"confirmed": 6, "not_seen": 0, "unknown": 1},
                         report["receipt_counts"]["request_seen"])
        self.assertEqual({"confirmed": 5, "not_seen": 2, "unknown": 0},
                         report["receipt_counts"]["submission_seen"])
        self.assertIsNone(report["quality_accepted"])
        self.assertTrue(all(v is None for v in report["quality_metrics"].values()))
        self.assertFalse(report["externally_independently_verified"])
        self.assertFalse(report["contributes_to_observed_shadow_metrics"])

    def test_chat_span_never_becomes_model_latency_or_time_saved(self):
        report = summarize_dataset(sample())
        intervals = report["chat_elapsed"]
        self.assertEqual([237, 194, 415], [row["minutes"] for row in intervals["observations"]])
        self.assertEqual(3, intervals["measured_episodes"])
        self.assertEqual(4, intervals["unknown_episodes"])
        self.assertEqual(282.0, intervals["mean"])
        self.assertEqual(194, intervals["minimum"])
        self.assertEqual(415, intervals["maximum"])
        self.assertFalse(intervals["is_ai_latency"])
        self.assertFalse(intervals["is_active_human_work_time"])
        self.assertIsNone(report["quality_metrics"]["ai_latency_ms"])

    def test_unknown_or_no_episodes_remain_unknown_not_success(self):
        data = sample()
        for row in data["episodes"]:
            for key in ("request_seen", "submission_seen", "receipt_acknowledged"):
                row[key] = None
            row["chat_elapsed_minutes"] = None
        report = summarize_dataset(data)
        self.assertEqual(7, report["receipt_counts"]["receipt_acknowledged"]["unknown"])
        self.assertEqual(0, report["receipt_counts"]["receipt_acknowledged"]["confirmed"])
        self.assertIsNone(report["chat_elapsed"]["mean"])
        data["episodes"] = []
        report = summarize_dataset(data)
        self.assertEqual(4, report["case_count"])
        self.assertEqual(0, report["episode_count"])
        self.assertEqual(0, report["cases_with_episodes"])
        self.assertIsNone(report["quality_metrics"]["first_pass_rate"])

    def test_quality_metrics_and_receipt_conversion_rejected(self):
        for key in QUALITY_FIELDS:
            data = sample()
            data["quality_metrics"][key] = 0
            with self.subTest(metric=key), self.assertRaises(RetrospectiveValidationError):
                validate_dataset(data)
        for accepted in (True, False, 1, 0, "approved"):
            data = sample()
            data["episodes"][0]["quality_accepted"] = accepted
            with self.subTest(accepted=accepted), self.assertRaises(RetrospectiveValidationError):
                validate_dataset(data)

    def test_observed_synthetic_and_external_attestation_rejected(self):
        for kind in ["observed", "synthetic", "prospective"]:
            data = sample()
            data["study_type"] = kind
            with self.subTest(kind=kind), self.assertRaises(RetrospectiveValidationError):
                validate_dataset(data)
        data = sample()
        data["provenance"] = "observed"
        with self.assertRaises(RetrospectiveValidationError):
            validate_dataset(data)
        data = sample()
        data["source_verification"] = "independently_certified"
        with self.assertRaises(RetrospectiveValidationError):
            validate_dataset(data)

    def test_duplicate_case_task_and_invalid_reference_rejected(self):
        for change in ["case", "episode", "reference"]:
            data = sample()
            if change == "case":
                data["cases"].append(copy.deepcopy(data["cases"][0]))
            elif change == "episode":
                data["episodes"].append(copy.deepcopy(data["episodes"][0]))
            else:
                data["episodes"][0]["case_id"] = "unknown-case"
            with self.subTest(change=change), self.assertRaises(RetrospectiveValidationError):
                validate_dataset(data)

    def test_negative_nan_infinite_boolean_and_unanchored_duration_rejected(self):
        for value in [-1, math.nan, math.inf, -math.inf, True, "237", 10**1000]:
            data = sample()
            data["episodes"][0]["chat_elapsed_minutes"] = value
            with self.subTest(value=repr(value)[:50]), self.assertRaises(RetrospectiveValidationError):
                validate_dataset(data)
        for field in ["request_seen", "submission_seen"]:
            data = sample()
            data["episodes"][0][field] = None
            with self.subTest(field=field), self.assertRaises(RetrospectiveValidationError):
                validate_dataset(data)

    def test_zero_and_finite_large_duration_are_valid_without_overflow(self):
        data = sample()
        data["episodes"][0]["chat_elapsed_minutes"] = 0
        report = summarize_dataset(data)
        self.assertEqual(0, report["chat_elapsed"]["minimum"])
        for episode in data["episodes"][:3]:
            episode["chat_elapsed_minutes"] = 1e308
        report = summarize_dataset(data)
        self.assertTrue(math.isfinite(report["chat_elapsed"]["mean"]))

    def test_extra_missing_invalid_type_and_unicode_rejected(self):
        for mutation in [
            lambda d: d.update(extra="not allowed"),
            lambda d: d["episodes"][0].update(ai_latency_ms=10),
            lambda d: d["cases"][0].pop("gaps"),
            lambda d: d["episodes"][0].update(receipt_acknowledged=1),
            lambda d: d["cases"][0].update(title="\ud800"),
            lambda d: d["cases"][0].update(evidence_summary=[]),
            lambda d: d["cases"][0].update(case_id="Someone@example.invalid"),
        ]:
            data = sample()
            mutation(data)
            with self.assertRaises(RetrospectiveValidationError):
                validate_dataset(data)

    def test_public_text_pointer_rejection_does_not_echo_private_input(self):
        for value in ["/Users/sentinel/private.docx", "https://example.invalid/private",
                      "person@example.invalid", r"C:\sentinel\private.docx"]:
            data = sample()
            data["cases"][0]["scope"] = value
            with self.assertRaises(RetrospectiveValidationError) as raised:
                validate_dataset(data)
            self.assertNotIn(value, str(raised.exception))

    def test_strict_json_duplicate_keys_and_nonfinite_constants(self):
        for text in ['{"study_type":"retrospective","study_type":"observed"}',
                     '{"nested":{"flag":true,"flag":false}}',
                     '{"duration":NaN}', '{"duration":Infinity}', '{"broken":}']:
            with self.subTest(text=text), self.assertRaises(RetrospectiveValidationError):
                decode_json(text)

    def test_retrospective_cannot_enter_observed_shadow_schema(self):
        before = summarize_events(read_events(ROOT/"examples/shadow/synthetic-events.jsonl"))
        data = sample()
        report = summarize_dataset(data)
        with self.assertRaises(ShadowValidationError):
            validate_event(data["episodes"][0])
        with self.assertRaises(ShadowValidationError):
            summarize_events([report])
        after = summarize_events(read_events(ROOT/"examples/shadow/synthetic-events.jsonl"))
        self.assertEqual(before, after)
        self.assertEqual(0, after["by_provenance"]["observed"]["events"])
        self.assertIsNone(after["by_provenance"]["observed"]["first_pass"]["rate"])


class PublicReaderTests(unittest.TestCase):
    def test_only_explicit_public_dataset_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root/"data/retrospective"
            public.mkdir(parents=True)
            path = public/"cases.json"
            path.write_text(json.dumps(sample()))
            with patch.object(cli, "ROOT", root):
                self.assertEqual(4, len(cli.read_public_dataset(path)["cases"]))
                outside = root/"private.json"
                outside.write_text("PRIVATE_SENTINEL")
                with self.assertRaises(RetrospectiveValidationError):
                    cli.read_public_dataset(outside)
                link = public/"linked.json"
                link.symlink_to(outside)
                with self.assertRaises(RetrospectiveValidationError):
                    cli.read_public_dataset(link)
                with self.assertRaises(RetrospectiveValidationError):
                    cli.read_public_dataset(public/".."/"retrospective"/"cases.json")

    def test_cli_output_check_and_mismatch_without_rewriting_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root/"data/retrospective"
            public.mkdir(parents=True)
            path, summary = public/"cases.json", public/"summary.json"
            path.write_text(json.dumps(sample()))
            original = path.read_bytes()
            with patch.object(cli, "ROOT", root):
                with patch("sys.argv", ["report", "--input", str(path), "--output", str(summary)]), redirect_stdout(StringIO()):
                    self.assertEqual(0, cli.main())
                self.assertEqual(original, path.read_bytes())
                with patch("sys.argv", ["report", "--input", str(path), "--check", str(summary)]), redirect_stdout(StringIO()):
                    self.assertEqual(0, cli.main())
                saved = json.loads(summary.read_text())
                saved["case_count"] = 999
                summary.write_text(json.dumps(saved))
                altered = summary.read_bytes()
                with patch("sys.argv", ["report", "--input", str(path), "--check", str(summary)]), redirect_stderr(StringIO()):
                    self.assertEqual(2, cli.main())
                self.assertEqual(altered, summary.read_bytes())
                with patch("sys.argv", ["report", "--input", str(path), "--output", str(path)]), redirect_stderr(StringIO()):
                    self.assertEqual(2, cli.main())
                self.assertEqual(original, path.read_bytes())

    def test_output_cannot_follow_symlink_or_escape_public_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root/"data/retrospective"
            public.mkdir(parents=True)
            path = public/"cases.json"
            path.write_text(json.dumps(sample()))
            outside = root/"private-sentinel.json"
            outside.write_text("UNCHANGED")
            link = public/"summary.json"
            link.symlink_to(outside)
            with patch.object(cli, "ROOT", root):
                for target in [link, outside]:
                    with self.assertRaises(RetrospectiveValidationError):
                        cli.write_public_report(target, summarize_dataset(sample()), path)
            self.assertEqual("UNCHANGED", outside.read_text())

    def test_cli_failure_omits_input_and_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"PRIVATE_SENTINEL.json"
            path.write_text("PRIVATE_SENTINEL")
            result = subprocess.run([sys.executable, "-B", str(ROOT/"scripts/retrospective_report.py"),
                                     "--input", str(path)], capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertNotIn("PRIVATE_SENTINEL", result.stdout+result.stderr)
            self.assertNotIn(str(path), result.stdout+result.stderr)


if __name__ == "__main__":
    unittest.main()
