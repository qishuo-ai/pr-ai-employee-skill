#!/usr/bin/env python3
"""Report anonymized historical case counts without reading private evidence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.retrospective import RetrospectiveValidationError, decode_json, summarize_dataset


def public_path(path: Path, *, existing: bool) -> Path:
    """Confine explicit inputs/outputs to this repo's public dataset directory."""
    public_directory = ROOT / "data" / "retrospective"
    if public_directory.is_symlink() or not public_directory.is_dir():
        raise RetrospectiveValidationError("public retrospective directory is unavailable")
    base = public_directory.resolve()
    if not base.is_relative_to(ROOT.resolve()):
        raise RetrospectiveValidationError("public directory cannot escape repository")
    absolute = path.absolute()
    if not absolute.is_relative_to(public_directory.absolute()):
        raise RetrospectiveValidationError("path must be inside the public retrospective directory")
    relative = absolute.relative_to(public_directory.absolute())
    if not relative.parts or ".." in relative.parts:
        raise RetrospectiveValidationError("parent traversal or directory target is not allowed")
    cursor = public_directory
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise RetrospectiveValidationError("path cannot contain symlinks")
    resolved = absolute.resolve()
    if not resolved.is_relative_to(base) or not resolved.parent.is_dir():
        raise RetrospectiveValidationError("path must remain in the public dataset directory")
    if existing and not resolved.is_file():
        raise RetrospectiveValidationError("input must be a regular public dataset file")
    if resolved.exists() and not resolved.is_file():
        raise RetrospectiveValidationError("target must be a regular file")
    return resolved


def read_public_dataset(path: Path):
    resolved = public_path(path, existing=True)
    if resolved.stat().st_size > 2_000_000:
        raise RetrospectiveValidationError("public retrospective input exceeds size limit")
    return decode_json(resolved.read_text(encoding="utf-8"))


def write_public_report(path: Path, report, source: Path) -> None:
    target = public_path(path, existing=False)
    if target == public_path(source, existing=True):
        raise RetrospectiveValidationError("report must not overwrite its input")
    content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                dir=target.parent, prefix=".retrospective-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck the explicit destination immediately before an atomic replace.
        public_path(path, existing=False)
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/retrospective/cases.json",
                        help="Public JSON dataset within this repository's data/retrospective directory")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--output", type=Path, help="Write a reproducible summary within data/retrospective")
    modes.add_argument("--check", type=Path, help="Compare a saved public summary without writing")
    args = parser.parse_args()
    try:
        report = summarize_dataset(read_public_dataset(args.input))
        if args.check is not None:
            expected = read_public_dataset(args.check)
            if expected != report:
                raise RetrospectiveValidationError("saved summary differs from recomputation")
            print("PASS: retrospective summary matches recomputation; quality metrics remain null.")
        elif args.output is not None:
            write_public_report(args.output, report, args.input)
            print("Wrote retrospective summary; no observed Shadow metrics changed.")
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (RetrospectiveValidationError, OSError, ValueError, TypeError, OverflowError):
        # Inputs may contain mistakenly supplied private values; do not echo.
        print("Retrospective report failed: invalid public dataset, mismatched summary or inaccessible file. No input values emitted.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
