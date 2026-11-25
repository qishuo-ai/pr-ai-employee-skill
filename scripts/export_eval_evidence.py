#!/usr/bin/env python3
"""Export reviewed synthetic logs; withhold reviewer packet and decoding material."""
import argparse
import hashlib
import json
from pathlib import Path
import re

TOP = {"manifest.json", "summary.json", "case-snapshot.json", "source-snapshots.json",
       "response-schema.json", "schedule.json", "runner-snapshot.py", "scorer-snapshot.py"}
CALL = {"prompt.txt", "events.jsonl", "stderr.txt", "response.txt", "result.json"}
SECRETS = re.compile(rb"(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
LOCAL_PATH = re.compile(rb"/(?:Users|home)/[^\s\"']+")


def export(source, target):
    if source.is_symlink() or target.exists():
        raise ValueError("Source must not be a symlink; target must be new")
    source = source.resolve()
    def regular(path, directory=False):
        if (path.is_symlink() or not path.resolve().is_relative_to(source) or
                not (path.is_dir() if directory else path.is_file())):
            raise ValueError("Export paths must be nonsymlink files/directories within the run")
    for name in ("case-snapshot.json", "manifest.json", "summary.json"):
        regular(source / name)
    regular(source / "calls", directory=True)
    cases = json.loads((source / "case-snapshot.json").read_text())
    if not cases or any(c.get("provenance") != "synthetic; no customer records used" for c in cases):
        raise ValueError("Only reviewed synthetic case snapshots may be exported")
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest["status"] not in {"completed", "completed_with_errors"}:
        raise ValueError("Run must be finished; never export planned work as evidence")
    paths = [p for p in source.iterdir() if p.name in TOP]
    calls = sorted((source / "calls").iterdir())
    if not calls or len(calls) != manifest.get("planned_calls"):
        raise ValueError("Completed run must retain every planned call")
    for call in calls:
        regular(call, directory=True)
        if call.is_symlink() or not re.fullmatch(r"\d{3}-F\d{2}-(?:baseline|skill)", call.name):
            raise ValueError("Unexpected call directory")
        for name in ("prompt.txt", "events.jsonl", "stderr.txt", "result.json"):
            regular(call / name)
        paths.extend(p for p in call.iterdir() if p.name in CALL)
    prepared, records = [], []
    for path in sorted(paths):
        regular(path)
        original = path.read_bytes()
        if SECRETS.search(original):
            raise ValueError("Credential-like content; export blocked (value withheld)")
        data = original
        redactions = []
        if path.name == "result.json":
            value = json.loads(data)
            if value.get("command"):
                if (not isinstance(value["command"], list) or
                        not isinstance(value["command"][0], str) or
                        Path(value["command"][0]).name not in {"codex", "codex.exe"}):
                    raise ValueError("Unexpected command executable metadata")
                value["command"][0] = "codex"
                redactions.append("command[0]: local executable path replaced with codex")
            data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
        # Fail without exposing any suspicious value; these are heuristic guards,
        # not an anonymization proof. Human source/output inspection is required.
        if SECRETS.search(data) or LOCAL_PATH.search(data):
            raise ValueError("Credential-like content or local home path; export blocked (value withheld)")
        relative = path.relative_to(source).as_posix()
        prepared.append((relative, data))
        records.append({"path": relative, "source_sha256": hashlib.sha256(original).hexdigest(),
                        "export_sha256": hashlib.sha256(data).hexdigest(), "redactions": redactions})
    target.mkdir(parents=True)
    for relative, data in prepared:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    record = {"synthetic_review_attested": True, "files": records,
              "raw_event_logs_modified": False,
              "withheld": ["blind-review/", "holdback/"],
              "limitations": "Heuristic secret/path checks do not prove anonymity. Public arm-tagged outputs can weaken later blinding; reviewers must not view them before rating lock."}
    (target / "export-manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reviewed-synthetic", required=True, action="store_true",
                        help="Attest source and outputs contain no private customer data or credentials")
    args = parser.parse_args()
    try:
        count = export(args.run, args.output)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(f"Exported {count} reviewed files; raw events unchanged; decoding material withheld.")
