"""Public evidence verifier tests with local synthetic launcher fixtures only."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = script('run_evals')
exporter = script('export_eval_evidence')
verifier = script('verify_eval_evidence')


def fixture(source):
    source.mkdir()
    case = runner.load_cases(ROOT/'evals/finals-scenarios.jsonl')[8]
    cases = [case]
    snapshots = runner.snapshot_sources(ROOT, cases)
    response = {'risk': 'green', 'decision': 'draft', 'approval_required': False,
                'facts': ['本周四15:00，线上会议。'], 'unknowns': [], 'draft': '本周四15:00，线上会议。',
                'next_steps': [], 'tool_requests': [], 'actions_performed': []}
    # Test launcher emits fixed protocol events. It is not a model and is never
    # counted as live benchmark evidence or retained in the repository.
    fake = source.parent/'codex'
    code = '#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\n'
    code += 'response = '+repr(response)+'\n'
    code += "Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text(json.dumps(response,ensure_ascii=False))\n"
    code += "print(json.dumps({'type':'thread.started','thread_id':'synthetic-test'}))\n"
    code += "print(json.dumps({'type':'item.completed','item':{'id':'fixture','type':'agent_message','text':json.dumps(response,ensure_ascii=False)}}))\n"
    code += "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}}))\n"
    fake.write_text(code)
    fake.chmod(0o700)
    runner.write_json(source/'response-schema.json', runner.SCHEMA)
    runner.write_json(source/'case-snapshot.json', cases)
    runner.write_json(source/'source-snapshots.json', snapshots)
    (source/'runner-snapshot.py').write_bytes((ROOT/'scripts/run_evals.py').read_bytes())
    (source/'scorer-snapshot.py').write_bytes((ROOT/'scripts/score_evals.py').read_bytes())
    tasks = [{'scenario_id': case['id'], 'arm': arm, 'call_id': f'{i:03}-{case["id"]}-{arm}'}
             for i,arm in enumerate(['baseline','skill'],1)]
    runner.write_json(source/'schedule.json', tasks)
    results = [runner.run_one(task, case, runner.build_prompt(case, task['arm'], snapshots), source,
                             'synthetic-test-model', 'low', 3, str(fake)) for task in tasks]
    if any(r['status'] != 'ok' for r in results):
        raise AssertionError('Fixture launcher failed')
    runner.write_json(source/'summary.json', runner.summarize(results, len(tasks)))
    manifest = {'format_version':1, 'status':'completed', 'finished_at':'2026-11-25T00:00:00+00:00',
                'config_overrides':runner.CONFIG, 'disabled_features':runner.DISABLED_FEATURES,
                'provider':'codex-cli-chatgpt-login', 'requested_model':'synthetic-test-model',
                'reasoning_effort':'low', 'planned_calls':2, 'scenario_count':1,
                'runner_sha256':runner.digest((source/'runner-snapshot.py').read_bytes()),
                'scorer_sha256':runner.digest((source/'scorer-snapshot.py').read_bytes()),
                'response_schema_sha256':runner.digest(runner.canonical(runner.SCHEMA)),
                'case_snapshot_sha256':runner.digest(runner.canonical(cases)),
                'source_hashes':{k:runner.digest(v) for k,v in snapshots.items()}}
    runner.write_json(source/'manifest.json', manifest)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base/'source'
        self.export = self.base/'export'
        fixture(self.source)
        exporter.export(self.source, self.export)

    def edit_json(self, relative, mutate, refresh=False):
        path = self.export/relative
        value = json.loads(path.read_text())
        mutate(value)
        runner.write_json(path, value)
        if refresh:
            self.refresh_digest(relative)

    def refresh_digest(self, relative):
        path = self.export/'export-manifest.json'
        value = json.loads(path.read_text())
        for record in value['files']:
            if record['path'] == relative:
                record['export_sha256'] = runner.digest((self.export/relative).read_bytes())
                if not record['redactions']:
                    record['source_sha256'] = record['export_sha256']
        runner.write_json(path, value)

    def test_public_and_private_source_verification(self):
        report = verifier.verify(self.export)
        self.assertEqual('verified_local_consistency', report['status'])
        self.assertEqual(2, report['retained_calls'])
        self.assertFalse(report['provider_authenticity_verified'])
        self.assertEqual(2, report['redacted_source_digests_not_recomputed'])
        report = verifier.verify(self.export, self.source)
        self.assertTrue(report['private_source_verified'])
        self.assertEqual(0, report['redacted_source_digests_not_recomputed'])

    def test_original_scorer_hash_absence_is_disclosed(self):
        self.edit_json('manifest.json', lambda value: value.pop('scorer_sha256'), refresh=True)
        report = verifier.verify(self.export)
        self.assertFalse(report['scorer_pinned_in_original_run_manifest'])

    def test_snapshot_python_is_never_executed(self):
        path = self.export/'runner-snapshot.py'
        path.write_text("raise RuntimeError('A verifier must not execute snapshot code')\n")
        self.refresh_digest('runner-snapshot.py')
        self.edit_json('manifest.json', lambda value: value.update(runner_sha256=runner.digest(path.read_bytes())), refresh=True)
        self.assertFalse(verifier.verify(self.export)['snapshot_python_executed'])

    def test_digest_tampering_rejected(self):
        (self.export/'calls/001-F09-baseline/prompt.txt').write_text('tampered')
        with self.assertRaisesRegex(verifier.EvidenceError, 'digest mismatch'):
            verifier.verify(self.export)

    def test_rehashed_summary_cannot_change_computed_result(self):
        self.edit_json('summary.json', lambda value: value['arms']['baseline'].update(deterministic_all_pass=99), refresh=True)
        with self.assertRaisesRegex(verifier.EvidenceError, 'Summary disagrees'):
            verifier.verify(self.export)

    def test_rehashed_response_cannot_disagree_with_raw_events(self):
        relative='calls/001-F09-baseline/response.txt'
        self.edit_json(relative, lambda value: value.update(draft='tampered answer'), refresh=True)
        with self.assertRaisesRegex(verifier.EvidenceError, 'response/result mismatch'):
            verifier.verify(self.export)

    def test_rehashed_call_cannot_change_checks(self):
        relative='calls/001-F09-baseline/result.json'
        self.edit_json(relative, lambda value: value['checks'].update(risk_label=False, all_pass=False), refresh=True)
        with self.assertRaisesRegex(verifier.EvidenceError, 'checks disagree'):
            verifier.verify(self.export)

    def test_source_and_schema_hashes_checked(self):
        for relative, mutation in [
            ('source-snapshots.json', lambda v: v.update({'SKILL.md':'changed source'})),
            ('case-snapshot.json', lambda v: v[0].update(scenario='changed case')),
            ('response-schema.json', lambda v: v['properties']['actions_performed'].pop('description')),
        ]:
            with self.subTest(relative=relative):
                original=(self.export/relative).read_bytes()
                self.edit_json(relative, mutation, refresh=True)
                with self.assertRaises(verifier.EvidenceError):
                    verifier.verify(self.export)
                (self.export/relative).write_bytes(original)
                self.refresh_digest(relative)

    def test_runner_and_scorer_snapshots_are_bound(self):
        for name in ['runner-snapshot.py','scorer-snapshot.py']:
            with self.subTest(name=name):
                original=(self.export/name).read_bytes()
                (self.export/name).write_bytes(original+b'\n# tampered\n')
                self.refresh_digest(name)
                with self.assertRaisesRegex(verifier.EvidenceError, 'snapshot hash mismatch'):
                    verifier.verify(self.export)
                (self.export/name).write_bytes(original)
                self.refresh_digest(name)

    def test_missing_duplicate_and_unlisted_evidence_rejected(self):
        self.edit_json('schedule.json', lambda v: v.__setitem__(1, copy.deepcopy(v[0])), refresh=True)
        with self.assertRaises(verifier.EvidenceError):
            verifier.verify(self.export)
        (self.export/'unexpected.txt').write_text('unlisted')
        with self.assertRaisesRegex(verifier.EvidenceError, 'Unlisted'):
            verifier.verify(self.export)

    def test_private_original_tampering_rejected(self):
        path=self.source/'calls/001-F09-baseline/result.json'
        path.write_text(path.read_text()+' ')
        with self.assertRaisesRegex(verifier.EvidenceError, 'Source digest mismatch'):
            verifier.verify(self.export, self.source)

    def test_symlink_and_traversal_rejected(self):
        path=self.export/'calls/001-F09-baseline/prompt.txt'
        path.unlink()
        path.symlink_to(self.source/'calls/001-F09-baseline/prompt.txt')
        with self.assertRaisesRegex(verifier.EvidenceError, 'Symlink'):
            verifier.verify(self.export)
        with self.assertRaises(verifier.EvidenceError):
            verifier.regular(self.export.resolve(), '../source/manifest.json')

    def test_unfinished_run_rejected(self):
        self.edit_json('manifest.json', lambda value: value.update(status='running'), refresh=True)
        with self.assertRaisesRegex(verifier.EvidenceError, 'incomplete'):
            verifier.verify(self.export)


if __name__ == '__main__':
    unittest.main()
