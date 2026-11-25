#!/usr/bin/env python3
"""Check release versions and accidental secret/artifact tracking, not data anonymity."""
import json
import re
import subprocess
from pathlib import Path


def check(root):
    errors = []
    version = (root / "VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("VERSION must be semver")
    skill = (root / "SKILL.md").read_text()
    match = re.search(r'^  version: "([^\"]+)"$', skill, re.M)
    if not match or match.group(1) != version:
        errors.append("SKILL metadata version mismatch")
    if json.loads((root / "roles/registry.json").read_text())["version"] != version:
        errors.append("Role registry release version mismatch")
    if f'POLICY_VERSION = "{version}"' not in (root / "runtime/gateway.py").read_text():
        errors.append("Runtime policy release version mismatch")
    for path in sorted((root / "policies").glob("*.yaml")):
        if not path.read_text().startswith(f"version: {version}\nschema_version: 1\n"):
            errors.append(f"Policy release/schema version mismatch: {path.name}")
    if f"## v{version}" not in (root / "CHANGELOG.md").read_text():
        errors.append("Current release absent from CHANGELOG")
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    credential = re.compile(rb"(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
    for name in filter(None, paths):
        path = root / name
        if path.is_symlink():
            errors.append(f"Tracked symlink requires separate review: {name}")
            continue
        if (path.name == ".env" or path.name.startswith(".env.") or
                path.suffix in {".sqlite", ".sqlite3", ".db"} or
                "artifacts" in path.parts):
            errors.append(f"Private runtime artifact is tracked: {name}")
        if path.is_file() and credential.search(path.read_bytes()):
            errors.append(f"Credential-like content found (value withheld): {name}")
    return errors


if __name__ == "__main__":
    errors = check(Path(__file__).resolve().parents[1])
    for error in errors:
        print("FAIL:", error)
    if not errors:
        print("PASS: release versions and tracked-file hygiene; anonymity requires content review.")
    raise SystemExit(bool(errors))
