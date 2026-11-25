"""Exporter tests use ephemeral synthetic_test_fixture data, never model evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "export_eval_evidence", Path(__file__).resolve().parents[1] / "scripts" / "export_eval_evidence.py")
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "synthetic_test_fixture"
        self.target = self.root / "synthetic_test_fixture_export"
        self.source.mkdir()
        self.call = self.source / "calls" / "001-F01-baseline"
        self.call.mkdir(parents=True)
        self.write_json("manifest.json", {"status": "completed", "planned_calls": 1, "synthetic_test_fixture": True})
        self.write_json("case-snapshot.json", [{"id": "F01", "synthetic_test_fixture": True,
                                                "provenance": "synthetic; no customer records used"}])
        self.write_json("summary.json", {"synthetic_test_fixture": True})
        self.events = b'{"type":"synthetic_test_fixture","message":"not a model run"}\r\n'
        (self.call / "events.jsonl").write_bytes(self.events)
        (self.call / "prompt.txt").write_text("synthetic_test_fixture input only\n")
        (self.call / "response.txt").write_text("synthetic_test_fixture response only\n")
        (self.call / "stderr.txt").write_bytes(b"synthetic_test_fixture diagnostics\n")
        self.command = ["/Users/synthetic-test-user/bin/codex", "exec", "--json", "-"]
        self.result = {"command": self.command, "synthetic_test_fixture": True,
                       "status": "fixture", "elapsed_ms": 1, "note": "preserve all other values"}
        (self.call / "result.json").write_text(json.dumps(self.result) + "\n")

    def write_json(self, relative, value):
        (self.source / relative).write_text(json.dumps(value) + "\n")

    def test_export_preserves_raw_bytes_hashes_and_source(self):
        source_bytes = {p.relative_to(self.source).as_posix(): p.read_bytes()
                        for p in self.source.rglob("*") if p.is_file()}
        count = EXPORTER.export(self.source, self.target)
        manifest = json.loads((self.target / "export-manifest.json").read_text())
        records = {r["path"]: r for r in manifest["files"]}
        self.assertEqual(count, len(source_bytes))
        self.assertFalse(manifest["raw_event_logs_modified"])
        for relative, before in source_bytes.items():
            after = (self.target / relative).read_bytes()
            self.assertEqual((self.source / relative).read_bytes(), before)
            self.assertEqual(records[relative]["source_sha256"], sha(before))
            self.assertEqual(records[relative]["export_sha256"], sha(after))
            if not relative.endswith("result.json"):
                self.assertEqual(after, before)
                self.assertEqual(records[relative]["redactions"], [])
        self.assertEqual((self.target / "calls/001-F01-baseline/events.jsonl").read_bytes(), self.events)

    def test_only_executable_command_value_is_sanitized(self):
        EXPORTER.export(self.source, self.target)
        result = json.loads((self.target / "calls/001-F01-baseline/result.json").read_text())
        expected = dict(self.result, command=["codex", *self.command[1:]])
        self.assertEqual(result, expected)
        manifest = json.loads((self.target / "export-manifest.json").read_text())
        redactions = [(r["path"], r["redactions"]) for r in manifest["files"] if r["redactions"]]
        self.assertEqual(redactions, [("calls/001-F01-baseline/result.json",
                                      ["command[0]: local executable path replaced with codex"])])

    def test_holdback_blind_review_and_unknown_files_are_withheld(self):
        for folder in ("holdback", "blind-review"):
            (self.source / folder).mkdir()
            (self.source / folder / "mapping.json").write_text('"synthetic_test_fixture withheld"')
        (self.source / "private-notes.txt").write_text("synthetic_test_fixture withheld")
        (self.call / "private-notes.txt").write_text("synthetic_test_fixture withheld")
        EXPORTER.export(self.source, self.target)
        exported = {p.relative_to(self.target).as_posix() for p in self.target.rglob("*") if p.is_file()}
        self.assertFalse(any("holdback" in p or "blind-review" in p or "private-notes" in p for p in exported))
        manifest = json.loads((self.target / "export-manifest.json").read_text())
        self.assertEqual(manifest["withheld"], ["blind-review/", "holdback/"])

    def test_nonsynthetic_and_empty_case_sets_rejected(self):
        for cases in ([], [{"provenance": "observed"}], [{"id": "F01"}],
                      [{"provenance": "synthetic; no customer records used"}, {"provenance": "observed"}]):
            with self.subTest(cases=cases):
                self.write_json("case-snapshot.json", cases)
                with self.assertRaises(ValueError):
                    EXPORTER.export(self.source, self.target)
                self.assertFalse(self.target.exists())

    def test_unfinished_run_is_not_exported_as_evidence(self):
        for status in ("planned", "running", "dry_run", "interrupted"):
            with self.subTest(status=status):
                self.write_json("manifest.json", {"status": status, "synthetic_test_fixture": True})
                with self.assertRaises(ValueError):
                    EXPORTER.export(self.source, self.target)
                self.assertFalse(self.target.exists())

    def test_existing_target_is_never_overwritten(self):
        self.target.mkdir()
        sentinel = self.target / "existing.txt"
        sentinel.write_bytes(b"synthetic_test_fixture existing bytes")
        with self.assertRaises(ValueError):
            EXPORTER.export(self.source, self.target)
        self.assertEqual(list(self.target.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"synthetic_test_fixture existing bytes")

    def test_credential_and_home_path_guards_do_not_echo_values_or_write_target(self):
        suspicious = ["sk-proj-" + "X" * 32, "/Users/synthetic-test-user/private.txt",
                      "/home/synthetic-test-user/private.txt", "-----BEGIN " + "PRIVATE KEY-----"]
        for value in suspicious:
            with self.subTest(kind=value.split("-")[0]):
                (self.call / "events.jsonl").write_text(json.dumps({"synthetic_test_fixture": value}) + "\n")
                with self.assertRaises(ValueError) as failure:
                    EXPORTER.export(self.source, self.target)
                self.assertNotIn(value, str(failure.exception))
                self.assertIn("value withheld", str(failure.exception))
                self.assertFalse(self.target.exists())

    def test_home_paths_in_other_command_arguments_are_blocked_not_redacted(self):
        value = "/Users/synthetic-test-user/private-result.json"
        changed = dict(self.result, command=[*self.command, "--output-last-message", value])
        (self.call / "result.json").write_text(json.dumps(changed) + "\n")
        with self.assertRaises(ValueError) as failure:
            EXPORTER.export(self.source, self.target)
        self.assertNotIn(value, str(failure.exception))
        self.assertFalse(self.target.exists())


    def test_symlink_calls_parent_cannot_export_outside_source(self):
        outside = self.root / "outside-synthetic-test-fixture"
        (self.source / "calls").rename(outside)
        (self.source / "calls").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            EXPORTER.export(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_required_metadata_symlinks_rejected_before_read(self):
        for name in ("case-snapshot.json", "manifest.json", "summary.json"):
            original = self.source / name
            backing = self.root / ("outside-" + name)
            original.rename(backing)
            original.symlink_to(backing)
            with self.subTest(name=name), patch.object(Path, "read_text", side_effect=AssertionError("must not read")):
                with self.assertRaises(ValueError):
                    EXPORTER.export(self.source, self.target)
            self.assertFalse(self.target.exists())
            original.unlink()
            backing.rename(original)

    def test_missing_raw_evidence_is_rejected(self):
        for name in ("prompt.txt", "events.jsonl", "stderr.txt", "result.json"):
            original = self.call / name
            before = original.read_bytes()
            original.unlink()
            with self.subTest(name=name), self.assertRaises(ValueError):
                EXPORTER.export(self.source, self.target)
            self.assertFalse(self.target.exists())
            original.write_bytes(before)

    def test_missing_planned_call_is_rejected(self):
        self.write_json("manifest.json", {"status": "completed", "planned_calls": 2,
                                           "synthetic_test_fixture": True})
        with self.assertRaises(ValueError):
            EXPORTER.export(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_empty_call_set_never_counts_as_completed_evidence(self):
        for item in self.call.iterdir():
            item.unlink()
        self.call.rmdir()
        self.write_json("manifest.json", {"status": "completed", "planned_calls": 0,
                                           "synthetic_test_fixture": True})
        with self.assertRaises(ValueError):
            EXPORTER.export(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_credential_like_executable_cannot_be_erased_by_sanitization(self):
        marker = "sk-proj-" + "X" * 32
        executable = "/Users/synthetic-test-user/" + marker + "/codex"
        changed = dict(self.result, command=[executable, *self.command[1:]])
        (self.call / "result.json").write_text(json.dumps(changed) + "\n")
        with self.assertRaises(ValueError) as failure:
            EXPORTER.export(self.source, self.target)
        self.assertNotIn(marker, str(failure.exception))
        self.assertIn("value withheld", str(failure.exception))
        self.assertFalse(self.target.exists())

    def test_unexpected_executable_metadata_is_rejected(self):
        for command in (["not-codex", "exec"], [123, "exec"], "codex"):
            (self.call / "result.json").write_text(json.dumps(dict(self.result, command=command)) + "\n")
            with self.subTest(command=command), self.assertRaises(ValueError):
                EXPORTER.export(self.source, self.target)
            self.assertFalse(self.target.exists())

    def test_failed_call_without_response_still_preserves_raw_failure_evidence(self):
        self.write_json("manifest.json", {"status": "completed_with_errors", "planned_calls": 1,
                                           "synthetic_test_fixture": True})
        (self.call / "response.txt").unlink()
        EXPORTER.export(self.source, self.target)
        self.assertFalse((self.target / "calls/001-F01-baseline/response.txt").exists())
        self.assertEqual((self.target / "calls/001-F01-baseline/events.jsonl").read_bytes(), self.events)

    def test_symlink_source_and_export_files_are_rejected(self):
        alias = self.root / "source-alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            EXPORTER.export(alias, self.target)
        events = self.call / "events.jsonl"
        events.unlink()
        backing = self.root / "fixture-events.jsonl"
        backing.write_bytes(self.events)
        events.symlink_to(backing)
        with self.assertRaises(ValueError):
            EXPORTER.export(self.source, self.target)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
