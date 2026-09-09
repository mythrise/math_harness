"""Safe offline regressions. No real model, Exa, Docker, or secret access."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest
from cumcm_harness.common import Blocked, IntegrityError, tree_manifest, write_json
from cumcm_harness.contracts import validate
from cumcm_harness.paper import equation
from cumcm_harness.research import ResearchRunner
from cumcm_harness.store import Store


def evaluation():
    return {'score':1.0,'valid':True,'metric':'score','checks':[{'name':'value','passed':True,'detail':'controlled arithmetic fixture'}],
            'question_coverage':['Q1'], 'measurements':[{'id':'m1','value':1.0,'unit':'unitless','question_id':'Q1','description':'controlled value'}]}


@pytest.mark.parametrize('text', [
    r'\text{^^5cinput{marker.txt}}',
    r'\begin {filecontents}{marker.txt}x\end {filecontents}',
    '\\begin\n{filecontents}{marker.txt}x\\end\n{filecontents}',
    '\\begin\t{filecontents}{marker.txt}x\\end\t{filecontents}',
])
def test_equation_rejects_non_math_syntax(text):
    with pytest.raises(IntegrityError): equation(text)

@pytest.mark.parametrize('text', [r'x^2+\frac{1}{n}', r'\begin{aligned}x&=y\\y&=z\end{aligned}', r'\begin {pmatrix}a&b\\c&d\end {pmatrix}'])
def test_equation_keeps_allowed_math(text):
    assert equation(text)==text

@pytest.mark.parametrize('problem', ['unmeasured','foreign','duplicate'])
def test_valid_evaluation_requires_linked_question_evidence(problem):
    ev=evaluation()
    if problem=='unmeasured':ev['question_coverage']+=['Q2']
    if problem=='foreign':ev['measurements'][0]['question_id']='Q99'
    if problem=='duplicate':ev['question_coverage']+=['Q1']
    with pytest.raises(IntegrityError):validate('evaluation',ev)

def test_invalid_evaluation_can_describe_missing_answers():
    ev=evaluation();ev['valid']=False;ev['checks'][0]['passed']=False
    ev['question_coverage'].append('Q2')
    assert validate('evaluation',ev)['valid'] is False

class ControlledExecutor:
    """Writes known data, never executes the supplied source bundle."""
    def __init__(self, mode='ok'):self.mode=mode;self.calls=[]
    def probe(self):return 'CONTROLLED_FAKE_EXECUTOR_NOT_DOCKER'
    def execute(self,code,entry,data,out,args,limits,*,answer=None,logdir=None):
        self.calls.append(entry);out.mkdir(parents=True,exist_ok=False)
        if self.mode=='interrupted':raise KeyboardInterrupt('intentional unknown process simulation')
        if entry=='main.py':write_json(out/'answer.json',{'answer':1})
        else:
            ev=evaluation()
            if self.mode=='missing':pass
            elif self.mode=='malformed':(out/'evaluation.json').write_text('{broken')
            elif self.mode=='invalid_utf8':(out/'evaluation.json').write_bytes(b'\xff')
            else:
                if self.mode=='wrong_metric':ev['metric']='other'
                if self.mode=='wrong_coverage':ev['question_coverage']=['Q2'];ev['measurements'][0]['question_id']='Q2'
                if self.mode=='contradiction':ev['checks'][0]['passed']=False
                if self.mode=='reject':ev['valid']=False;ev['checks'][0]['passed']=False
                write_json(out/'evaluation.json',ev)
            if self.mode=='mutate':(data/'private/reference.txt').write_text('changed during evaluation')
        return {'status':'EXITED','returncode':0,'output_manifest':tree_manifest(out)}

def make_runner(tmp_path,mode='ok'):
    store=Store(tmp_path);exe=ControlledExecutor(mode)
    for phase in ('development','confirmation'):
        (tmp_path/'inputs'/phase).mkdir(parents=True)
        write_json(tmp_path/'inputs'/phase/'data.json',{'known':1})
        (tmp_path/'evaluation_inputs'/phase/'private').mkdir(parents=True)
        (tmp_path/'evaluation_inputs'/phase/'private/reference.txt').write_text('original')
    config={'trial_timeout':2,'cpu_threads':1,'memory_mb':128,'workers':1}
    protocol={'metric':'score','fe_budget':32,'scope':'CONTROLLED_AUDIT_FIXTURE'}
    runner=ResearchRunner(store,exe,config,protocol,{'questions':[{'id':'Q1'}]})
    bundle={'files':[{'path':'main.py','content':'# Never executed\n'}],'notes':[],'algorithm_usage':[]}
    verifier={'files':[{'path':'evaluate.py','content':'# Never executed\n'}],'notes':[],'algorithm_usage':[]}
    return runner,exe,bundle,verifier

def rows(runner):
    with runner.store.connect() as conn:return [dict(x) for x in conn.execute('SELECT * FROM jobs')]

@pytest.mark.parametrize('mode',['missing','malformed','invalid_utf8','wrong_metric','wrong_coverage','contradiction'])
def test_observed_invalid_evaluation_is_failed_not_running(tmp_path,mode):
    r,e,b,v=make_runner(tmp_path,mode)
    with pytest.raises((IntegrityError,ValueError,OSError)):
        r.cell('baseline',b,v,'development',101,'baseline')
    assert e.calls==['main.py','evaluate.py']
    assert rows(r)[0]['status']=='FAILED'


def test_real_interruption_remains_unknown(tmp_path):
    r,e,b,v=make_runner(tmp_path,'interrupted')
    with pytest.raises(KeyboardInterrupt):r.cell('baseline',b,v,'development',101,'baseline')
    assert rows(r)[0]['status']=='RUNNING'


def test_same_inputs_reuse_result_without_reexecution(tmp_path):
    r,e,b,v=make_runner(tmp_path)
    first=r.cell('baseline',b,v,'development',101,'baseline')
    assert r.cell('baseline',b,v,'development',101,'baseline')==first
    assert len(e.calls)==2


def test_private_evaluation_drift_never_reuses_cached_score(tmp_path):
    r,e,b,v=make_runner(tmp_path)
    r.cell('baseline',b,v,'development',101,'baseline')
    (tmp_path/'evaluation_inputs/development/private/reference.txt').write_text('different ground truth')
    with pytest.raises(IntegrityError):r.cell('baseline',b,v,'development',101,'baseline')
    assert len(e.calls)==2


def test_mid_execution_input_drift_is_failed(tmp_path):
    r,e,b,v=make_runner(tmp_path,'mutate')
    with pytest.raises(IntegrityError):r.cell('baseline',b,v,'development',101,'baseline')
    assert rows(r)[0]['status']=='FAILED'


def test_negative_verdict_is_durable_and_never_silently_retried(tmp_path):
    r,e,b,v=make_runner(tmp_path,'reject')
    with pytest.raises(Blocked):r.cell('baseline',b,v,'development',101,'baseline')
    assert rows(r)[0]['status']=='DONE'
    with pytest.raises(Blocked):r.cell('baseline',b,v,'development',101,'baseline')
    assert len(e.calls)==2

@pytest.mark.parametrize('path', ['cumcm_harness/worker.py','cumcm_harness.py','json.py','numpy/__init__.py'])
def test_generated_bundle_cannot_shadow_trusted_entry_modules(path):
    bundle={'files':[{'path':path,'content':'# Not executed\n'}],'notes':[],'algorithm_usage':[]}
    with pytest.raises(IntegrityError):validate('bundle',bundle)


@pytest.mark.parametrize('path',['code/a}.py','inputs/x^^5c.csv','inputs/line\nname.csv','code/safe%name.py'])
def test_tex_filename_rejects_expansion_or_structure(path):
    from cumcm_harness.paper import tex_filename
    with pytest.raises(IntegrityError):tex_filename(path)

@pytest.mark.parametrize('path',['code/c0/main.py','inputs/观测 数据.csv'])
def test_tex_filename_retains_normal_paths(path):
    from cumcm_harness.paper import tex_filename
    assert tex_filename(path)==path
