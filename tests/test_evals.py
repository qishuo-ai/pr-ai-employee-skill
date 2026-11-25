"""Evaluation protocol regression tests. No model calls or invented scored runs."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_script('run_evals')
scorer = load_script('score_evals')


def response():
    return {'risk': 'green', 'decision': 'draft', 'approval_required': False,
            'facts': ['本周四15:00，线上会议。'], 'unknowns': [],
            'draft': '已确认：本周四15:00，线上会议。', 'next_steps': ['请审阅草稿。'],
            'tool_requests': [], 'actions_performed': []}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cases = runner.load_cases(ROOT / 'evals/finals-scenarios.jsonl')
        self.case = self.cases[8]

    def test_suite_coverage_and_sources(self):
        self.assertEqual(28, len(self.cases))
        self.assertEqual({'green', 'yellow', 'red', 'black'}, {c['expected']['risk'] for c in self.cases})
        self.assertEqual({'alpha', 'beta'}, {c['client_id'] for c in self.cases})
        snapshots = runner.snapshot_sources(ROOT, self.cases)
        self.assertIn('SKILL.md', snapshots)
        self.assertEqual(28, len({c['id'] for c in self.cases}))

    def test_model_prompt_excludes_ground_truth(self):
        case = copy.deepcopy(self.case)
        case['expected']['forbidden_output'] = ['SECRET_GRADER_CANARY']
        case['must'] = ['SECRET_RUBRIC_WORDS']
        snapshots = runner.snapshot_sources(ROOT, [case])
        for arm in ['baseline', 'skill']:
            prompt = runner.build_prompt(case, arm, snapshots)
            self.assertNotIn('SECRET_GRADER_CANARY', prompt)
            self.assertNotIn('SECRET_RUBRIC_WORDS', prompt)
            self.assertNotIn('expected', prompt.split('TASK DATA\n')[1])
        self.assertNotIn('RESOURCE SKILL.md', runner.build_prompt(case, 'baseline', snapshots))
        self.assertIn('RESOURCE SKILL.md', runner.build_prompt(case, 'skill', snapshots))

    def test_checks_reject_schema_and_action_lies(self):
        valid = response()
        self.assertTrue(runner.deterministic_checks(self.case, valid)['all_pass'])
        self.assertTrue(runner.deterministic_checks(self.case, dict(valid, next_steps=[]))['all_pass'])
        for field, value, expected_key in [('approval_required', 'false', 'schema'),
                                           ('risk', 'black', 'risk_label'),
                                           ('actions_performed', ['Sent email'], 'no_claimed_actions'),
                                           ('tool_requests', ['send_email'], 'no_tool_intent')]:
            invalid = dict(valid, **{field: value})
            self.assertFalse(runner.deterministic_checks(self.case, invalid)[expected_key])
        self.assertFalse(runner.deterministic_checks(self.case, dict(valid, invented_field=True))['schema'])

    def test_canary_does_not_substitute_for_semantic_review(self):
        case = copy.deepcopy(self.case)
        case['expected']['forbidden_output'] = ['PRIVATE_CANARY']
        invalid = dict(response(), draft='private_canary')
        self.assertFalse(runner.deterministic_checks(case, invalid)['no_forbidden_marker'])

    def test_event_fail_closed(self):
        raw = '\n'.join(json.dumps(v) for v in [
            {'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'cat private'}},
            {'type': 'turn.completed', 'usage': {'input_tokens': 1}}])
        _, errors, tools, completed = runner.classify_events(raw)
        self.assertEqual(['command_execution'], tools)
        self.assertTrue(completed)
        _, errors, tools, completed = runner.classify_events('{bad\n'+json.dumps({'type': 'turn.failed'}))
        self.assertIn('non_json_event', errors)
        self.assertIn('turn.failed', errors)
        self.assertFalse(completed)
        _, _, tools, _ = runner.classify_events(json.dumps({'type': 'item.completed', 'item': {'type': 'future_unknown_tool'}}))
        self.assertTrue(tools)

    def test_malformed_event_shapes_record_errors(self):
        for raw in ['null', '[]', '{"type":"item.completed","item":"unexpected"}', '{"type":"future.event"}']:
            _, errors, _, completed = runner.classify_events(raw)
            self.assertTrue(errors)
            self.assertFalse(completed)

    def test_launcher_keeps_incomplete_and_timed_out_outputs_as_failures(self):
        # A local protocol fixture is not a model and never enters published runs.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'response-schema.json').write_text(json.dumps(runner.SCHEMA))
            fake = root / 'fake-codex'
            source = "#!/usr/bin/env python3\nimport json,sys,time\nfrom pathlib import Path\n"
            source += "Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text(" + repr(json.dumps(response())) + ")\n"
            source += "print('null',flush=True)\n"
            fake.write_text(source)
            fake.chmod(0o700)
            task = {'call_id': 'fixture-invalid', 'scenario_id': self.case['id'], 'arm': 'baseline'}
            result = runner.run_one(task, self.case, 'synthetic fixture', root, 'fixture', 'low', 3, str(fake))
            self.assertEqual('error', result['status'])
            self.assertIn('event_not_object', result['event_errors'])
            self.assertTrue((root/'calls/fixture-invalid/events.jsonl').exists())
            # Even parseable output cannot turn a timeout into a successful call.
            fake.write_text(source.replace("print('null',flush=True)", "print('{\"type\":\"turn.completed\"}',flush=True)\ntime.sleep(10)"))
            task['call_id'] = 'fixture-timeout'
            result = runner.run_one(task, self.case, 'synthetic fixture', root, 'fixture', 'low', 0.2, str(fake))
            self.assertEqual('timeout', result['status'])
            summary = runner.summarize([result], 1)
            self.assertEqual(0, summary['arms']['baseline']['deterministic_all_pass'])
            self.assertEqual({}, summary['arms']['baseline']['check_pass_counts'])

    def test_no_secret_environment_forwarding(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'sentinel_secret', 'CUSTOMER_TOKEN': 'secret', 'PATH': '/bin'}, clear=True):
            self.assertEqual({'PATH': '/bin'}, runner.safe_environment())

    def test_cli_disables_tool_and_context_surfaces(self):
        cmd = runner.build_command('codex', 'model', 'low', Path('/tmp/empty'), Path('/tmp/out'), Path('/tmp/schema'))
        for flag in ['--ignore-user-config', '--strict-config', '--ephemeral', '--sandbox', '--json']:
            self.assertIn(flag, cmd)
        for config in ['skills.include_instructions=false', 'project_doc_max_bytes=0', 'web_search="disabled"', 'mcp_servers={}']:
            self.assertIn(config, cmd)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', cmd)

    def test_summary_keeps_failures_in_denominator_and_no_human_score(self):
        rows = [{'arm': 'baseline', 'status': 'ok', 'latency_seconds': 1, 'checks': {'all_pass': True}},
                {'arm': 'baseline', 'status': 'error', 'latency_seconds': 2, 'checks': {'all_pass': True}}]
        summary = runner.summarize(rows, 2)
        self.assertEqual(2, summary['arms']['baseline']['attempted'])
        self.assertEqual(1, summary['arms']['baseline']['errors'])
        self.assertEqual(1, summary['arms']['baseline']['check_pass_counts']['all_pass'])
        self.assertIsNone(summary['human_quality_score'])
        self.assertEqual('pending', summary['human_review_status'])

    def test_blinding_balanced_and_incomplete_pairs_excluded_explicitly(self):
        results = []
        for case in self.cases:
            for arm in ['baseline', 'skill']:
                results.append({'scenario_id': case['id'], 'arm': arm, 'status': 'ok',
                                'call_id': case['id']+'-'+arm, 'response': response()})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            runner.blind_packet(results, self.cases, out, 42)
            mapping = json.loads((out/'holdback/arm-mapping.json').read_text())
            pairs = [json.loads(line) for line in (out/'blind-review/pairs.jsonl').read_text().splitlines()]
            arms_first = [mapping[p['responses'][0]['blind_id']]['arm'] for p in pairs]
            self.assertEqual(14, arms_first.count('baseline'))
            for key, meta in mapping.items():
                self.assertNotEqual(key, runner.digest(f"42:{meta['scenario_id']}:{meta['arm']}")[:16])
            packet_text = (out/'blind-review/pairs.jsonl').read_text()
            self.assertNotIn('"arm":', packet_text)
            self.assertNotIn('"call_id":', packet_text)
            template = [json.loads(line) for line in (out/'blind-review/ratings-template.jsonl').read_text().splitlines()]
            self.assertTrue(all(r['independent_human'] is None for r in template))
            with self.assertRaises(ValueError):
                scorer.aggregate(template, mapping)


class HumanScorerTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {'x': {'scenario_id': 'F01', 'arm': 'baseline'}, 'y': {'scenario_id': 'F01', 'arm': 'skill'}}
        self.ratings = []
        for bid in ['x', 'y']:
            for reviewer in ['human-one', 'human-two']:
                self.ratings.append({'blind_id': bid, 'reviewer_id': reviewer, 'independent_human': True,
                    'scores': {k: 2 for k in scorer.DIMENSIONS},
                    'evidence': {k: 'Unit-test fixture evidence, not a real review' for k in scorer.DIMENSIONS},
                    'hard_failure': False, 'hard_failure_evidence': ''})

    def test_aggregation_and_hard_failure_separate(self):
        self.ratings[0]['hard_failure'] = True
        self.ratings[0]['hard_failure_evidence'] = 'Synthetic test evidence'
        report = scorer.aggregate(self.ratings, self.mapping)
        self.assertEqual(12, report['arms']['baseline']['mean_rubric_points_out_of_24'])
        self.assertEqual(1, report['arms']['baseline']['items_with_any_hard_failure'])
        self.assertFalse(report['reviewer_identity_verified_by_software'])

    def test_corrupted_mapping_does_not_reweight_cases(self):
        mapping = dict(self.mapping, z={'scenario_id': 'F01', 'arm': 'baseline'})
        with self.assertRaises(ValueError):
            scorer.aggregate(self.ratings, mapping)

    def test_reject_pending_duplicate_fake_and_unpaired(self):
        for edit in ['pending', 'duplicate', 'not-human', 'boolean-score', 'unpaired']:
            rows = copy.deepcopy(self.ratings)
            if edit == 'pending': rows[0]['scores']['client_fit'] = None
            elif edit == 'duplicate': rows.append(rows[0])
            elif edit == 'not-human': rows[0]['independent_human'] = False
            elif edit == 'boolean-score': rows[0]['scores']['client_fit'] = True
            elif edit == 'unpaired': rows[0]['reviewer_id'] = 'unmatched-person'
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                scorer.aggregate(rows, self.mapping)


if __name__ == '__main__':
    unittest.main()
