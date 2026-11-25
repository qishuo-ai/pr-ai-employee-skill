#!/usr/bin/env python3
"""Verify finals export integrity and recompute contract checks without model calls.

Only trusted local verifier/runner code is imported. Snapshot Python is data and
is never executed. Local hashes establish consistency, not provider authenticity.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import re

_spec = importlib.util.spec_from_file_location('evidence_protocol', Path(__file__).with_name('run_evals.py'))
protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(protocol)

TOP = {'manifest.json', 'summary.json', 'case-snapshot.json', 'source-snapshots.json',
       'response-schema.json', 'schedule.json', 'runner-snapshot.py', 'scorer-snapshot.py'}
CALL_REQUIRED = {'prompt.txt', 'events.jsonl', 'stderr.txt', 'result.json'}
CALL_OPTIONAL = {'response.txt'}
REDACTION = 'command[0]: local executable path replaced with codex'
SHA = re.compile(r'[0-9a-f]{64}')
CALL_ID = re.compile(r'\d{3}-F\d{2}-(baseline|skill)')


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def regular(root, relative):
    require(isinstance(relative, str), 'Non-string evidence path')
    parsed = PurePosixPath(relative)
    require(relative == parsed.as_posix() and not parsed.is_absolute()
            and '..' not in parsed.parts and '.' not in parsed.parts and '\\' not in relative,
            'Unsafe evidence path')
    path = root.joinpath(*parsed.parts)
    for depth in range(1, len(parsed.parts)+1):
        require(not root.joinpath(*parsed.parts[:depth]).is_symlink(), 'Symlink in evidence')
    require(path.is_file() and path.resolve().is_relative_to(root), 'Missing or escaping evidence file: ' + relative)
    return path


def read_json(root, relative):
    try:
        return json.loads(regular(root, relative).read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise EvidenceError('Invalid JSON: ' + relative) from exc


def verify(export_root, source_root=None):
    require(not export_root.is_symlink() and export_root.is_dir(), 'Export directory must be a nonsymlink directory')
    root = export_root.resolve()
    source = None
    if source_root is not None:
        require(not source_root.is_symlink() and source_root.is_dir(), 'Private source must be a nonsymlink directory')
        source = source_root.resolve()
    export = read_json(root, 'export-manifest.json')
    require(isinstance(export, dict) and export.get('synthetic_review_attested') is True,
            'Missing synthetic export attestation')
    require(export.get('raw_event_logs_modified') is False, 'Modified raw events unsupported')
    require(set(export.get('withheld', [])) == {'blind-review/', 'holdback/'}, 'Unexpected blinding disclosure policy')
    files = export.get('files')
    require(isinstance(files, list) and files, 'Missing export file inventory')
    inventory = {}
    redacted_originals_unverified = []
    for record in files:
        require(isinstance(record, dict) and set(record) == {'path', 'source_sha256', 'export_sha256', 'redactions'}, 'Invalid export file record')
        relative = record['path']
        require(isinstance(relative, str) and relative not in inventory, 'Duplicate export path')
        require(all(isinstance(record[k], str) and SHA.fullmatch(record[k]) for k in ['source_sha256', 'export_sha256']), 'Invalid file digest')
        data = regular(root, relative).read_bytes()
        require(protocol.digest(data) == record['export_sha256'], 'Export digest mismatch: ' + relative)
        redactions = record['redactions']
        require(redactions == [] or redactions == [REDACTION], 'Unsupported redaction')
        if redactions:
            require(relative.startswith('calls/') and relative.endswith('/result.json'), 'Only command executable metadata may be redacted')
            result = read_json(root, relative)
            require(isinstance(result.get('command'), list) and result['command'] and result['command'][0] == 'codex', 'Invalid executable redaction')
            if source is None:
                redacted_originals_unverified.append(relative)
        else:
            require(record['source_sha256'] == record['export_sha256'], 'Unreported transformation: ' + relative)
        if source is not None:
            original = regular(source, relative).read_bytes()
            require(protocol.digest(original) == record['source_sha256'], 'Source digest mismatch: ' + relative)
            expected = original
            if redactions:
                original_result = json.loads(original)
                require(isinstance(original_result.get('command'), list) and original_result['command']
                        and isinstance(original_result['command'][0], str)
                        and Path(original_result['command'][0]).name in {'codex', 'codex.exe'}, 'Invalid original command')
                original_result['command'][0] = 'codex'
                expected = (json.dumps(original_result, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
            require(expected == data, 'Export differs beyond declared redaction: ' + relative)
        inventory[relative] = record
    disk_files = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'Symlink in export')
        if path.is_file():
            disk_files.add(path.relative_to(root).as_posix())
    require(disk_files == set(inventory) | {'export-manifest.json'}, 'Unlisted or missing exported files')
    require(TOP <= set(inventory), 'Unsupported/incomplete protocol: frozen finals snapshots required')
    require(all(p in TOP or re.fullmatch(r'calls/\d{3}-F\d{2}-(?:baseline|skill)/(?:prompt.txt|events.jsonl|stderr.txt|result.json|response.txt)', p) for p in inventory), 'Unexpected public evidence file')

    manifest = read_json(root, 'manifest.json')
    require(manifest.get('format_version') == 1 and manifest.get('status') in {'completed', 'completed_with_errors'}, 'Run is incomplete or protocol unsupported')
    require(bool(manifest.get('finished_at')), 'Run lacks completion timestamp')
    require(manifest.get('config_overrides') == protocol.CONFIG and manifest.get('disabled_features') == protocol.DISABLED_FEATURES, 'Unsupported tool/context configuration')
    require(manifest.get('provider') == 'codex-cli-chatgpt-login', 'Unsupported provider protocol')
    require(manifest.get('reasoning_effort') in {'low', 'medium', 'high'} and isinstance(manifest.get('requested_model'), str), 'Missing model configuration')
    require(protocol.digest(regular(root, 'runner-snapshot.py').read_bytes()) == manifest.get('runner_sha256'), 'Runner snapshot hash mismatch')
    scorer_hash = protocol.digest(regular(root, 'scorer-snapshot.py').read_bytes())
    if 'scorer_sha256' in manifest:
        require(scorer_hash == manifest['scorer_sha256'], 'Scorer snapshot hash mismatch')
    # Legacy finals manifest binds scorer only through the export inventory.
    # Do not pretend it contained a pre-run scorer hash that was never recorded.
    require(scorer_hash == inventory['scorer-snapshot.py']['source_sha256'], 'Scorer export/source mismatch')
    schema = read_json(root, 'response-schema.json')
    require(schema == protocol.SCHEMA, 'Unsupported protocol: response schema differs; legacy smoke runs are not rerated')
    require(protocol.digest(protocol.canonical(schema)) == manifest.get('response_schema_sha256'), 'Schema snapshot hash mismatch')
    cases = read_json(root, 'case-snapshot.json')
    require(isinstance(cases, list) and cases, 'No scenario snapshot')
    require(protocol.digest(protocol.canonical(cases)) == manifest.get('case_snapshot_sha256'), 'Case snapshot hash mismatch')
    require(all(isinstance(c, dict) and isinstance(c.get('id'), str) and re.fullmatch(r'F\d{2}', c['id'])
                and c.get('provenance') == 'synthetic; no customer records used' for c in cases), 'Invalid/sensitive scenario snapshot')
    case_index = {c['id']: c for c in cases}
    require(len(case_index) == len(cases) == manifest.get('scenario_count'), 'Duplicate/missing scenarios')
    snapshots = read_json(root, 'source-snapshots.json')
    require(isinstance(snapshots, dict) and all(isinstance(v, str) for v in snapshots.values()), 'Invalid source snapshots')
    expected_sources = {name for c in cases for name in protocol.context_files(c)}
    require(set(snapshots) == expected_sources, 'Source snapshot coverage mismatch')
    require({k: protocol.digest(v) for k, v in snapshots.items()} == manifest.get('source_hashes'), 'Source snapshot hash mismatch')
    schedule = read_json(root, 'schedule.json')
    require(isinstance(schedule, list) and len(schedule) == 2*len(cases) == manifest.get('planned_calls'), 'Schedule count mismatch')
    planned_pairs, planned_calls = set(), set()
    for sequence, task in enumerate(schedule, 1):
        require(isinstance(task, dict) and set(task) == {'scenario_id', 'arm', 'call_id'}, 'Invalid schedule item')
        case_id, arm, call_id = task['scenario_id'], task['arm'], task['call_id']
        require(case_id in case_index and arm in {'baseline', 'skill'} and isinstance(call_id, str), 'Unknown case/arm')
        require(call_id == f'{sequence:03}-{case_id}-{arm}', 'Call ID/order mismatch')
        require(call_id not in planned_calls and (case_id, arm) not in planned_pairs, 'Duplicate call or case/arm')
        planned_calls.add(call_id)
        planned_pairs.add((case_id, arm))
    observed_calls = {p.split('/')[1] for p in inventory if p.startswith('calls/')}
    require(planned_calls == observed_calls, 'Planned calls do not match retained calls')
    results = []
    for task in schedule:
        prefix = 'calls/' + task['call_id'] + '/'
        require({prefix + name for name in CALL_REQUIRED} <= set(inventory), 'Incomplete call evidence: ' + task['call_id'])
        result = read_json(root, prefix+'result.json')
        require(isinstance(result, dict) and all(result.get(k) == v for k, v in task.items()), 'Result/schedule mismatch')
        latency = result.get('latency_seconds')
        require(type(latency) in {int, float} and math.isfinite(latency) and latency >= 0, 'Invalid latency')
        command = protocol.build_command('codex', manifest['requested_model'], manifest['reasoning_effort'],
                    Path('<isolated-temp>'), Path('<isolated-temp>/response.json'), Path('<run-dir>/response-schema.json'))
        require(result.get('command') == command, 'Per-call model/config command mismatch')
        prompt = regular(root, prefix+'prompt.txt').read_text(encoding='utf-8')
        require(protocol.digest(prompt) == result.get('prompt_sha256'), 'Prompt digest mismatch')
        expected_prompt = protocol.build_prompt(case_index[task['scenario_id']], task['arm'], snapshots)
        require(prompt == expected_prompt, 'Prompt not reconstructible from frozen inputs')
        raw = regular(root, prefix+'events.jsonl').read_text(encoding='utf-8')
        stderr = regular(root, prefix+'stderr.txt').read_text(encoding='utf-8')
        require(result.get('raw_sha256') == {'events.jsonl': protocol.digest(raw), 'stderr.txt': protocol.digest(stderr)}, 'Raw event/stderr digest mismatch')
        response = result.get('response')
        if prefix+'response.txt' in inventory:
            try:
                decoded = json.loads(regular(root, prefix+'response.txt').read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                decoded = None
            require(decoded == response, 'Raw final response/result mismatch')
        else:
            require(response is None, 'Parsed response has no retained raw final response')
        events, errors, tools, completed = protocol.classify_events(raw)
        require(result.get('event_errors') == errors and result.get('observed_tool_events') == tools, 'Event classification mismatch')
        require(result.get('usage') == [e.get('usage') for e in events if e.get('type') == 'turn.completed'], 'Usage/event mismatch')
        success_shape = result.get('returncode') == 0 and completed and not errors and not tools and response is not None
        status = result.get('status')
        if status == 'timeout':
            require(result.get('returncode') != 0, 'Timeout lacks terminated process status')
        else:
            expected_status = ('ok' if not protocol.validate_response(response) else 'invalid_schema') if success_shape else ('tool_boundary_violation' if tools else 'error')
            require(status == expected_status, 'Status does not match process/events/response')
        if status == 'ok':
            final_messages = [e['item']['text'] for e in events if e.get('type') == 'item.completed'
                              and e.get('item', {}).get('type') == 'agent_message' and isinstance(e['item'].get('text'), str)]
            require(bool(final_messages), 'Completed call has no raw final message')
            try:
                final_json = json.loads(final_messages[-1])
            except json.JSONDecodeError as exc:
                raise EvidenceError('Final event message is not response JSON') from exc
            require(final_json == response, 'Final event and final response disagree')
        checks = protocol.deterministic_checks(case_index[task['scenario_id']], response) if response is not None else {'all_pass': False, 'schema': False}
        require(checks == result.get('checks'), 'Deterministic checks disagree with recomputation')
        results.append(result)
    results.sort(key=lambda r: r['call_id'])
    summary = read_json(root, 'summary.json')
    require(summary == protocol.summarize(results, len(schedule)), 'Summary disagrees with recomputation')
    expected_status = 'completed' if all(r['status'] == 'ok' for r in results) else 'completed_with_errors'
    require(manifest['status'] == expected_status, 'Run completion status contradicts calls')
    return {'status': 'verified_local_consistency', 'scenario_count': len(cases), 'planned_calls': len(schedule),
            'retained_calls': len(results), 'verified_export_files': len(inventory),
            'private_source_verified': source is not None,
            'redacted_source_digests_not_recomputed': len(redacted_originals_unverified),
            'scorer_pinned_in_original_run_manifest': 'scorer_sha256' in manifest,
            'snapshot_python_executed': False, 'provider_authenticity_verified': False,
            'limitations': ['Local hashes and recomputation do not prove provider authenticity, human independence or resistance to coordinated rewriting of data and all digests.',
                           'Without --source, original digests of redacted result metadata cannot be recomputed.',
                           'No model calls or human-quality reassessment; historical smoke protocols are intentionally unsupported.'],
            'summary': summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True, help='Published directory with export-manifest.json')
    parser.add_argument('--source', type=Path, help='Optional original private run to verify pre-redaction digests')
    args = parser.parse_args()
    try:
        report = verify(args.run, args.source)
    except (EvidenceError, OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
