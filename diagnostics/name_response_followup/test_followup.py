"""Offline checks for matched interventions, sequential history, and accounting."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import design
import analyze


class DesignTests(unittest.TestCase):
    def test_fixed_budget_and_unique_deterministic_cases(self):
        for experiment, n in [('replication', 1600), ('rules', 1800), ('retention', 5920)]:
            rows = design.make_cases(experiment)
            self.assertEqual(len(rows), n)
            self.assertEqual(len({r['id'] for r in rows}), n)
            self.assertEqual(rows, design.make_cases(experiment))
            self.assertTrue(all(r['seed'] >= 20261008 for r in rows))
        for invalid in [0, 201, True]:
            with self.assertRaises(ValueError):
                design.make_cases('replication', invalid)

    def test_replication_orders_are_independent_and_payoffs_correct(self):
        rows = design.make_cases('replication', 1)
        combinations = {(r['prompt_first'], r['enum_first']) for r in rows}
        self.assertEqual(combinations, {('I', 'I'), ('I', 'C'), ('C', 'I'), ('C', 'C')})
        by_context = defaultdict(dict)
        for r in rows:
            p = r['player']
            self.assertEqual(p['outcome'], [100 if a==b else -50 for a,b in zip(p['my_history'],p['partner_history'])])
            by_context[(r['challenger'], r['prompt_first'], r['enum_first'])][r['history']] = p
        for context in by_context.values():
            old, new = context['mismatch_oldest'], context['mismatch_latest']
            self.assertEqual(Counter(zip(old['my_history'],old['partner_history'])), Counter(zip(new['my_history'],new['partner_history'])))
            self.assertEqual(sum(old['outcome']), sum(new['outcome']))
            self.assertNotEqual(old['partner_history'][-1], new['partner_history'][-1])

    def test_rules_matched_counts_payoffs_options_and_predictions(self):
        matched = defaultdict(dict)
        for row in design.make_cases('rules', 1):
            matched[(row['family'], tuple(sorted(row['labels'].items())), row['reverse'])][row['variant']] = row
        self.assertEqual(len(matched), 36)
        for variants in matched.values():
            a,b = variants['last_A'], variants['last_B']
            self.assertEqual(a['prompt_options'], b['prompt_options'])
            self.assertEqual(a['enum_options'], b['enum_options'])
            self.assertEqual(set(a['enum_options']), set(design.OPTIONS))
            for field in ['my_history', 'partner_history', 'outcome']:
                self.assertEqual(Counter(a['player'][field]), Counter(b['player'][field]))
            column = 'own_last' if a['family']=='own_recency' else 'partner_last'
            self.assertEqual(a['predictions'][column], a['labels']['A'])
            self.assertEqual(b['predictions'][column], b['labels']['B'])
            self.assertEqual(a['predictions']['combined_mode'], b['predictions']['combined_mode'])
            if a['family']=='frequency_recency':
                self.assertEqual(a['predictions']['partner_mode'], a['labels']['A'])
                self.assertNotEqual(b['predictions']['partner_mode'], b['predictions']['partner_last'])

    def test_retention_parents_precede_and_shared_initials(self):
        rows = design.make_cases('retention', 1)
        seen = set()
        self.assertEqual(sum(r['phase']=='initial' for r in rows), 8)
        self.assertEqual(len(rows), 296)
        for r in rows:
            if r['parent_id']:
                self.assertIn(r['parent_id'], seen)
            seen.add(r['id'])
        roots = Counter(r['parent_id'] for r in rows if r['step']==1)
        self.assertEqual(sorted(roots.values()), [3]*8)

    def test_retention_history_uses_observed_choice_and_actual_partner(self):
        row = next(r for r in design.make_cases('retention', 1) if r['phase']=='initial')
        result = dict(case=row, status='valid', value=row['incumbent'])
        player = design.advance_player(result)
        self.assertEqual(len(player['my_history']), 13)
        self.assertEqual(player['my_history'][-1], row['incumbent'])
        self.assertEqual(player['partner_history'][-1], row['challenger'])
        self.assertEqual(player['outcome'][-1], -50)
        with self.assertRaises(ValueError):
            design.advance_player(dict(case=row, status='invalid', value=None))


class AnalysisTests(unittest.TestCase):
    def test_block_sign_support_and_holm(self):
        self.assertEqual(analyze.exact_sign([0]*50), 1.)
        self.assertAlmostEqual(analyze.exact_sign([1]*3), .25)
        self.assertAlmostEqual(analyze.exact_sign([1]*50), 2/2**50)
        result = analyze.block_effect([(seed,1) for seed in range(50) for _ in range(8)])
        self.assertEqual(result['seed_blocks'], 50)
        self.assertEqual(result['effect_pp'], 100)
        self.assertEqual(result['ci_low_pp'], '')
        self.assertEqual(result['interval_status'], 'degenerate_bootstrap')

    def test_mock_enum_effect_is_identified(self):
        rows = [dict(case=c, status='valid', value=c['enum_options'][0]) for c in design.make_cases('replication', 3)]
        effects = {r['factor']: r for r in analyze.replication(rows)}
        self.assertEqual({k:v['effect_pp'] for k,v in effects.items()}, dict(challenger=0,prompt_first=0,enum_first=100,history=0,recency=0))
        self.assertEqual(effects['enum_first']['seed_blocks'], 3)
        self.assertEqual(effects['enum_first']['seed_sign_p'], .25)

    def test_missing_invalid_and_duplicate_records_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            command=[sys.executable,str(HERE/'run.py'),'--model','olmo31_32b','--experiment','replication','--repeats','1','--output',tmp,'--mock']
            subprocess.run(command,check=True,capture_output=True)
            responses=next(Path(tmp).rglob('responses.jsonl'))
            rows=responses.read_text().splitlines()
            responses.write_text('\n'.join(rows[:-1])+'\n')
            result=analyze.analyze(responses.parent)
            self.assertFalse(result['complete'])
            self.assertEqual(result['missing'],1)
            responses.write_text('\n'.join(rows+[rows[0]])+'\n')
            with self.assertRaises(ValueError):
                analyze.analyze(responses.parent)

    def test_retention_initial_denominator_not_tripled_and_invalid_censored(self):
        plan=design.make_cases('retention',1)
        by_id={}
        for c in plan:
            c=dict(c)
            if c['parent_id']:
                c['player']=design.advance_player(by_id[c['parent_id']])
            by_id[c['id']]=dict(case=c,status='valid',value=c['challenger'])
        rows=list(by_id.values())
        summary=analyze.retention(rows)
        self.assertEqual(summary[0]['initial_adopters'],8)
        self.assertTrue(all(r.get('complete_trajectories',8)==8 for r in summary))
        row=next(r for r in rows if r['case']['branch']=='reverted' and r['case']['step']==2)
        row['status']='invalid'
        summary=analyze.retention(rows)
        step3=next(r for r in summary if r['branch']=='reverted' and r['step']==3)
        self.assertEqual(step3['complete_trajectories'],7)
        self.assertEqual(step3['censored_or_missing'],1)
        missing_initial=[r for r in rows if r['case']['id']!=plan[0]['id']]
        result=analyze.retention(missing_initial,plan)
        self.assertEqual(result[0]['initial_contexts'],8)
        self.assertEqual(result[0]['recorded_initials'],7)


class RunnerTests(unittest.TestCase):
    def command(self,experiment,output,*args):
        return [sys.executable,str(HERE/'run.py'),'--model','olmo31_32b','--experiment',experiment,'--repeats','1','--output',str(output),*args]

    def test_dry_run_has_no_response_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run(self.command('replication',tmp,'--dry-run'),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(list(Path(tmp).rglob('responses.jsonl')))
            self.assertFalse(list(Path(tmp).rglob('attempts.jsonl')))

    def test_mock_each_experiment_and_resume_byte_identical(self):
        for experiment,n in [('replication',32),('rules',72),('retention',296)]:
            with self.subTest(experiment=experiment),tempfile.TemporaryDirectory() as tmp:
                command=self.command(experiment,tmp,'--mock')
                result=subprocess.run(command,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                responses=next(Path(tmp).rglob('responses.jsonl'))
                before=responses.read_bytes()
                self.assertEqual(len(before.splitlines()),n)
                result=subprocess.run(command,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(responses.read_bytes(),before)
                verification=analyze.analyze(responses.parent)
                self.assertTrue(verification['all_valid'])

    def test_reserved_unknown_outcome_not_resent_and_children_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            command=self.command('retention',tmp,'--mock')
            subprocess.run(command,check=True,capture_output=True)
            responses=next(Path(tmp).rglob('responses.jsonl'))
            journal=responses.with_name('attempts.jsonl')
            first_reservation=journal.read_text().splitlines()[0]
            responses.write_text('')
            journal.write_text(first_reservation+'\n')
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            records=[json.loads(line) for line in responses.read_text().splitlines()]
            self.assertEqual(len(records),296)
            self.assertEqual(records[0]['status'],'invalid')
            self.assertEqual(sum(r['status']=='blocked' for r in records),36)
            attempts=[json.loads(line) for line in journal.read_text().splitlines()]
            self.assertEqual(len(attempts),260)
            self.assertEqual(sum(r['id']==json.loads(first_reservation)['id'] for r in attempts),1)
            before=journal.read_bytes()
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(journal.read_bytes(),before)
            verification=analyze.analyze(responses.parent)
            self.assertTrue(verification['complete'])
            self.assertFalse(verification['all_valid'])
            self.assertEqual(verification['blocked'],36)

    def test_duplicate_resume_refuses_before_any_new_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            command=self.command('replication',tmp,'--mock')
            subprocess.run(command,check=True,capture_output=True)
            responses=next(Path(tmp).rglob('responses.jsonl'))
            journal=responses.with_name('attempts.jsonl')
            before=journal.read_bytes()
            text=responses.read_text()
            responses.write_text(text+text.splitlines()[0]+'\n')
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(journal.read_bytes(),before)

    def test_materialized_retention_prompt_advances_true_round(self):
        import run as runner
        rows=design.make_cases('retention',1)
        by_id={}
        for row in rows[:37]:
            case=runner.materialize_case(row,by_id)
            self.assertIsNotNone(case)
            if row['phase']=='followup':
                self.assertEqual(len(case['player']['my_history']),12+row['step'])
                self.assertIn('round '+str(13+row['step']),case['prompt'].lower())
            by_id[row['id']]=dict(case=case,status='valid',value=case['incumbent'])

    def test_recursive_analysis_keeps_model_batteries_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            for model in ('olmo31_32b','glm4_32b'):
                command=[sys.executable,str(HERE/'run.py'),'--model',model,'--experiment','replication','--repeats','1','--output',tmp,'--mock']
                subprocess.run(command,check=True,capture_output=True)
            result=subprocess.run([sys.executable,str(HERE/'analyze.py'),'--results-root',tmp],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads((Path(tmp)/'aggregate-verification.json').read_text())
            self.assertEqual(len(report['batteries']),2)
            self.assertTrue(report['all_valid'])
            self.assertEqual({r['model'] for r in report['batteries']},{'olmo31_32b','glm4_32b'})

    def test_http_failure_stops_after_three_without_retry_and_partial_analysis_fails(self):
        import run as runner
        spec=runner.resolve_model(runner.load_config(runner.ROOT/'config.yaml'),'olmo31_32b')
        calls=[]
        def fail(**kwargs):
            calls.append(kwargs)
            raise RuntimeError('simulated unavailable inference server')
        fake=SimpleNamespace(models=SimpleNamespace(list=lambda:SimpleNamespace(model_dump=lambda:{'data':[{'id':spec.model_id}]})),
                             chat=SimpleNamespace(completions=SimpleNamespace(create=fail)),close=lambda:None)
        with tempfile.TemporaryDirectory() as tmp:
            argv=self.command('replication',tmp)
            with patch.object(sys,'argv',argv[1:]),patch.dict(sys.modules,{'openai':SimpleNamespace(OpenAI=lambda **kwargs:fake)}):
                with self.assertRaises(SystemExit):
                    runner.main()
            self.assertEqual(len(calls),3)
            responses=next(Path(tmp).rglob('responses.jsonl'))
            records=[json.loads(line) for line in responses.read_text().splitlines()]
            self.assertEqual(len(records),3)
            self.assertTrue(all(r['status']=='invalid' for r in records))
            self.assertEqual(len(responses.with_name('attempts.jsonl').read_text().splitlines()),3)
            result=subprocess.run([sys.executable,str(HERE/'analyze.py'),'--input',str(responses.parent)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stderr)

    def test_metadata_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(self.command('replication',tmp,'--mock'),check=True,capture_output=True)
            metadata=next(Path(tmp).rglob('design.json'))
            data=json.loads(metadata.read_text())
            data['model']='glm4_32b'
            metadata.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                analyze.analyze(metadata.parent)

    def test_response_validation_rejects_malformed_unknown_and_truncated(self):
        spec=importlib.util.spec_from_file_location('followup_run',HERE/'run.py')
        runner=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        for text,finish in [('not json','stop'),('{"value":"unknown","reason":"ok"}','stop'),
                            ('{"value":"dicfv","reason":"ok"}','length')]:
            with self.assertRaises(Exception):
                runner.validate(text,finish,['dicfv','lwlsi'])


if __name__=='__main__':
    unittest.main()
