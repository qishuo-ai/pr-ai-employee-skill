#!/usr/bin/env python3
"""Record private text-free Shadow events or report measured metrics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.shadow import ShadowValidationError, decode_json, read_events, record_event, summarize_events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record", help="consume a private JSON input; append text-free event")
    record.add_argument("--input", required=True, type=Path)
    record.add_argument("--log", required=True, type=Path)
    report = commands.add_parser("report", help="report synthetic and observed metrics separately")
    report.add_argument("--log", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "record":
            event = decode_json(args.input.read_text(encoding="utf-8"))
            stored = record_event(args.log, event)
            print(json.dumps({"status": "recorded", "event_id": stored["event_id"],
                              "provenance": stored["provenance"], "text_persisted": False}))
        else:
            print(json.dumps(summarize_events(read_events(args.log)), ensure_ascii=False, indent=2, allow_nan=False))
    except (ShadowValidationError, OSError, ValueError):
        # Input paths and parser exception details can contain private data.
        print("Shadow operation failed: invalid event/log or inaccessible local file. No input text emitted.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
