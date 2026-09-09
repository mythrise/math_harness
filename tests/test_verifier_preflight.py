"""Synthetic transport tests for the pre-freeze gate, not optical validation."""
from pathlib import Path
import pytest
from cumcm_harness.common import Blocked, ExecutionFailure, write_json
from cumcm_harness.controller import DEFAULT_CONFIG
from cumcm_harness.store import Store
from cumcm_harness.verifier_preflight import run_preflight, validate_tests

BUNDLE={'files':[{'path':p,'content':'# synthetic test source\n'} for p in
                 ('evaluate.py','test_evaluator.py')],'notes':[],'algorithm_usage':[]}

class FakeExecutor:
    def __init__(self,mode):self.mode=mode;self.calls=[]
    def execute(self,code,entry,data,out,args,limits,*,answer=None,logdir=None):
        self.calls.append(entry);out.mkdir(parents=True);logdir.mkdir(parents=True)
        if self.mode=='infra':raise Blocked('Docker image missing or daemon unavailable')
        if self.mode=='crash':
            write_json(logdir/'process_receipt.json',{'status':'EXITED','returncode':1})
            (logdir/'stderr.log').write_text('IndexError: index 4 is out of bounds for axis 0 with size 4')
            raise ExecutionFailure('Execution failed: EXITED, rc=1; synthetic log')
        if entry=='test_evaluator.py':
            write_json(out/'tests.json',{'all_passed':True,'cases':[
                {'name':n,'passed':True,'detail':'synthetic fixture'} for n in ('positive','negative','boundary')]})
        else:
            write_json(out/'evaluation.json',{'valid':self.mode=='accept','score':0,'metric':'fixture',
                'question_coverage':['Q1'],'checks':[{'name':'malformed','passed':self.mode=='accept','detail':'synthetic'}],
                'measurements':[{'id':'validity','value':0,'unit':'bool','question_id':'Q1','description':'invalid placeholder'}]})
        return {'status':'EXITED','returncode':0,'backend':'SYNTHETIC_TEST_FIXTURE'}

def preflight(tmp_path,mode):
    executor=FakeExecutor(mode)
    report=run_preflight(tmp_path,Store(tmp_path),executor,DEFAULT_CONFIG,BUNDLE)
    return report,executor

def test_array_crash_is_preserved_and_blocks_before_reviews(tmp_path):
    report,executor=preflight(tmp_path,'crash')
    assert report['passed'] is False
    assert 'IndexError' in report['reports'][0]['stderr']
    assert executor.calls==['test_evaluator.py']
    assert (tmp_path/report['output_path']/'summary.json').exists()

def test_success_tests_all_three_controller_negative_controls(tmp_path):
    report,executor=preflight(tmp_path,'pass')
    assert report['passed'] is True
    assert executor.calls==['test_evaluator.py','evaluate.py','evaluate.py','evaluate.py']
    assert report['certifies_full_scientific_execution'] is False

def test_evaluator_that_accepts_empty_answer_cannot_freeze(tmp_path):
    report,_=preflight(tmp_path,'accept')
    assert report['passed'] is False
    assert 'accepted invalid answer' in report['reports'][-1]['error']

def test_missing_docker_propagates_without_code_repair(tmp_path):
    with pytest.raises(Blocked,match='Docker image missing'):
        preflight(tmp_path,'infra')

@pytest.mark.parametrize('report',[
    [],
    {'all_passed':True,'cases':[]},
    {'all_passed':True,'cases':[{'name':'same','passed':True,'detail':'fixture'}]*3},
    {'all_passed':True,'cases':[{'name':str(i),'passed':i!=1,'detail':'fixture'} for i in range(3)]},
])
def test_fake_green_or_incomplete_reports_fail(report):
    with pytest.raises(Blocked):validate_tests(report)
