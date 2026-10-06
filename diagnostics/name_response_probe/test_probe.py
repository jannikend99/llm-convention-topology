"""Offline checks for counterfactual controls and accounting."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('probe', Path(__file__).with_name('run.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def test_budget_and_unique_cases(self):
        rows = probe.cases()
        self.assertEqual(len(rows), 96)
        self.assertEqual(len({r['id'] for r in rows}), 96)
        self.assertEqual(rows, probe.cases())

    def test_independent_order_controls(self):
        model = probe.resolve_model(probe.load_config(probe.ROOT / 'config.yaml'), 'olmo31_32b')
        for row in probe.cases(1):
            req = probe.request(model, row)
            enum = req['response_format']['json_schema']['schema']['properties']['value']['enum']
            self.assertEqual(enum, row['enum_options'])
            self.assertIn(f"these values: {row['prompt_options']}", req['messages'][0]['content'])
        self.assertTrue(any(r['enum_options'] != r['prompt_options'] for r in probe.cases(1)))

    def test_recency_pair_holds_counts_and_score(self):
        old = probe.HISTORIES['mismatch_oldest']
        new = probe.HISTORIES['mismatch_latest']
        self.assertEqual(sorted(old), sorted(new))
        self.assertNotEqual(old[-1], new[-1])
        for r in probe.cases(1):
            if r['history'] in ('mismatch_oldest', 'mismatch_latest'):
                self.assertEqual(sum(r['player']['outcome']), 1050)

    def test_reject_truncated_invalid_and_unknown_choices(self):
        for text, finish in [('{"value":"dicfv","reason":"ok"}', 'length'),
                             ('garbage', 'stop'), ('{"value":"other","reason":"ok"}', 'stop')]:
            with self.assertRaises(Exception):
                probe.validate(text, finish, ['dicfv', 'lwlsi'])

    def test_mock_contrast_detects_enum_only(self):
        records = [dict(case=r, status='valid', value=r['enum_options'][0]) for r in probe.cases()]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            probe.summarize(path, records)
            import csv
            with (path / 'paired_contrasts.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            values = {r['factor']: float(r['challenger_share_difference_pp']) for r in rows}
            self.assertEqual(values, dict(challenger=0, prompt_first=0, enum_first=100, history=0))

    def test_resume_and_interrupted_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            command = [sys.executable, str(Path(__file__).with_name('run.py')), '--model',
                       'olmo31_32b', '--repeats', '1', '--mock', '--output', temp]
            subprocess.run(command, check=True, capture_output=True)
            responses = next(Path(temp).rglob('responses.jsonl'))
            before = responses.read_text()
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(responses.read_text(), before)
            journal = responses.with_name('attempts.jsonl')
            reservations = journal.read_text()
            # Simulate one reserved call interrupted before its response was saved.
            responses.write_text('\n'.join(before.splitlines()[:-1]) + '\n')
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(journal.read_text(), reservations)
            rows = [json.loads(line) for line in responses.read_text().splitlines()]
            self.assertEqual(len(rows), 32)
            self.assertEqual(sum(r['status'] == 'invalid' for r in rows), 1)

    def test_reject_remote_endpoint_and_oversized_budget(self):
        for extra in [('--base-url', 'https://example.com/v1'), ('--repeats', '11')]:
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('run.py')),
                                     '--model', 'olmo31_32b', '--dry-run', *extra], capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
