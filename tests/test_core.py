import copy,json,sys,zipfile
from pathlib import Path
import numpy as np
import pytest
from cumcm_harness.common import *
from cumcm_harness.contracts import validate,topo
from cumcm_harness.store import Store,controller_lock
from cumcm_harness.demo import PLAN,code_bundle,verifier_bundle
from cumcm_harness.controller import DEFAULT_CONFIG,validate_config
from cumcm_harness.research import freeze_protocol,paired_effect,choose_development
from cumcm_harness.intake import create_workspace,verify_inputs,extract_zip,profile
from cumcm_harness.sandbox import Executor,Limits,resource_gate
from cumcm_harness.process import run_process,clean_env
from cumcm_harness import approval
from cumcm_harness.algorithms import linear_fit,linear_forecast,topsis,hv2,route_methods
from cumcm_harness.paper import bind_prose,equation

def test_canonical_order():assert digest({'b':2,'a':1})==digest({'a':1,'b':2})
@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite(value):
    with pytest.raises((ValueError,IntegrityError)):canonical({'x':value})
@pytest.mark.parametrize('value',['../evil','a/../evil','/tmp/evil','a\\evil','.env','a//b','C:evil'])
def test_path_escape(value):
    with pytest.raises(IntegrityError):safe_rel(value)
def test_symlink(tmp_path):
    (tmp_path/'x').symlink_to('/etc/passwd')
    with pytest.raises(IntegrityError):tree_manifest(tmp_path)
def test_atomic_and_mutation(tmp_path):
    write_json(tmp_path/'x.json',{'value':3});m=tree_manifest(tmp_path);write_json(tmp_path/'x.json',{'value':4})
    with pytest.raises(IntegrityError):verify_tree(tmp_path,m)
def test_dag_order():assert topo([{'id':'b','depends_on':['a']},{'id':'a','depends_on':[]}])==['a','b']
@pytest.mark.parametrize('tasks',[[{'id':'a','depends_on':['b']},{'id':'b','depends_on':['a']}],[{'id':'a','depends_on':['z']}],[{'id':'a','depends_on':[]},{'id':'a','depends_on':[]}]])
def test_dag_bad(tasks):
    with pytest.raises(IntegrityError):topo(tasks)
def test_plan():assert validate('plan',copy.deepcopy(PLAN))==PLAN
def test_missing_schema_field():
    p=copy.deepcopy(PLAN);p.pop('baseline')
    with pytest.raises(IntegrityError):validate('plan',p)
def test_bundle_injection():
    b=code_bundle();b['files'][0]['path']='sitecustomize.py'
    with pytest.raises(IntegrityError):validate('bundle',b)
def test_review_cannot_pass_unknown():
    r={'target_digest':'a'*64,'verdict':'PASS','scope':'test','findings':[],'evidence':['x'],'unverified':['not executed']}
    with pytest.raises(IntegrityError):validate('review',r)
def test_store_step_cache_and_stale(tmp_path):
    s=Store(tmp_path);n=[]
    def once():n.append(1);return {'x':2}
    assert s.step('a',{'in':1},once)==s.step('a',{'in':1},once);assert len(n)==1
    with pytest.raises(IntegrityError):s.step('a',{'in':2},once)
def test_store_fail_closed_recovery(tmp_path):
    s=Store(tmp_path)
    with pytest.raises(ValueError):s.step('x',{},lambda:(_ for _ in ()).throw(ValueError('fault')))
    with pytest.raises(Blocked):s.step('x',{},lambda:1)
    s.recover_step('x','Operator checked no external side effects');assert s.step('x',{},lambda:1)==1
    assert s.audit()['integrity']=='PASS'
def test_ledger_tamper(tmp_path):
    s=Store(tmp_path);s.event('TEST',{'a':1})
    with s.connect() as c:c.execute('UPDATE events SET payload=? WHERE seq=1',('{"a":2}',))
    with pytest.raises(IntegrityError):s.audit()
def test_cas_tamper(tmp_path):
    s=Store(tmp_path);h=s.put({'a':1});write_json(tmp_path/'objects'/f'{h}.json',{'a':2})
    with pytest.raises(IntegrityError):s.load(h)
def test_grant_scope_and_reuse(tmp_path):
    s=Store(tmp_path);g=s.grant('job',{'x':1})
    with pytest.raises(IntegrityError):s.consume(g,'other')
    s.consume(g,'job')
    with pytest.raises(IntegrityError):s.consume(g,'job')
def test_job_recovery_preserves_attempt(tmp_path):
    s=Store(tmp_path);job=digest('job');g=s.grant(job,{});s.consume(g,job);atomic_write(tmp_path/'jobs'/job/'partial.txt','partial')
    s.recover_job(job,'Killed local process and inspected incomplete outputs')
    assert s.job(job) is None;assert list((tmp_path/'recovery').rglob('partial.txt'))
def test_bundle_content_immutable(tmp_path):
    s=Store(tmp_path);b={'files':[{'path':'main.py','content':'print(1)'}],'notes':[],'algorithm_usage':[]};p=s.publish_bundle(b);atomic_write(p/'main.py','print(2)')
    with pytest.raises(IntegrityError):s.publish_bundle(b)
def test_lock(tmp_path):
    with controller_lock(tmp_path):
        with pytest.raises(Blocked):
            with controller_lock(tmp_path):pass

def test_resource_overcommit():
    c={**DEFAULT_CONFIG,'workers':3}
    with pytest.raises(Blocked):resource_gate(PLAN,c)
def test_holdout_seeds_overlap():
    c={**DEFAULT_CONFIG,'confirmation_seeds':[101]}
    with pytest.raises(IntegrityError):freeze_protocol(PLAN,c,{'confirmation_scope':'seed'},'a'*64)
def test_bootstrap_reproducible():
    a=paired_effect([1,1,1,1,1],[2,2,2,2,2],seed=4)
    assert a==paired_effect([1]*5,[2]*5,seed=4);assert a['decision']=='KEEP_CANDIDATE'
def test_bootstrap_inconclusive():assert paired_effect([1,2],[3,4])['decision']=='INCONCLUSIVE'
def test_bootstrap_negative():assert paired_effect([2]*5,[1]*5)['decision']=='RETAIN_BASELINE'
def test_selection_missing_cell():
    rows=[{'candidate':'baseline','variant':'baseline','seed':1,'evaluation':{'valid':True,'score':1}}]
    with pytest.raises(IntegrityError):choose_development(rows,{'development_seeds':[1,2]})
def test_selection_tie_baseline():
    rows=[{'candidate':name,'variant':'baseline' if name=='baseline' else 'full','seed':s,'evaluation':{'valid':True,'score':1}} for name in ('baseline','c0') for s in (1,2)]
    assert choose_development(rows,{'development_seeds':[1,2],'direction':'maximize','min_effect':0})['winner']=='baseline'

def test_intake_frozen_and_no_private_preview(tmp_path):
    data=tmp_path/'data';data.mkdir();write_json(data/'x.json',{'x':[1,2]})
    private=tmp_path/'private';private.mkdir();write_json(private/'labels.json',{'secret':[989897]})
    problem=tmp_path/'q.md';problem.write_text('Some explicit problem');root=tmp_path/'run'
    i=create_workspace(root,problem,data,DEFAULT_CONFIG,private_dev=private)
    assert '989897' not in json.dumps(i['private_schema']);verify_inputs(root)
    (root/'inputs/development/x.json').write_text('{}')
    with pytest.raises(IntegrityError):verify_inputs(root)
def test_empty_data_supported(tmp_path):
    data=tmp_path/'data';data.mkdir();p=tmp_path/'q.md';p.write_text('Analytical problem with no supplied dataset')
    create_workspace(tmp_path/'run',p,data,DEFAULT_CONFIG);verify_inputs(tmp_path/'run')
def test_zip_traversal(tmp_path):
    z=tmp_path/'bad.zip'
    with zipfile.ZipFile(z,'w') as f:f.writestr('../escape.txt','bad')
    with pytest.raises((IntegrityError,Blocked)):extract_zip(z,tmp_path/'unpack')
def test_local_execution_refuses_untrusted(tmp_path):
    code=tmp_path/'code';data=tmp_path/'data';code.mkdir();data.mkdir();(code/'main.py').write_text('print(1)')
    with pytest.raises(Blocked):Executor('trusted-local').execute(code,'main.py',data,tmp_path/'out',[],Limits())
def test_process_timeout(tmp_path):
    r=run_process([sys.executable,'-c','import time;time.sleep(5)'],cwd=tmp_path,out=tmp_path/'logs',env=clean_env(),timeout=.12)
    assert r['status']=='TIMEOUT';assert (tmp_path/'logs/process_receipt.json').exists()
def test_process_log_limit(tmp_path):
    r=run_process([sys.executable,'-c','print("x"*30000)'],cwd=tmp_path,out=tmp_path/'logs',env=clean_env(),timeout=5,max_log_bytes=1000)
    assert r['status']=='LOG_LIMIT'
def test_clean_env_excludes_operator(monkeypatch):
    monkeypatch.setenv('CUMCM_OPERATOR_KEY','never-pass-to-agent');assert 'CUMCM_OPERATOR_KEY' not in clean_env(provider=True)

def test_human_sign_scope(tmp_path):
    pending=approval.request(tmp_path,'plan','a'*64,['x'],'Review modeling')
    review={'target_digest':'a'*64,'team_led_core_modeling':True,'visual_review_done':False,'items':[{'id':'x','adopted':True,'modification':'No changes','verification':'Manually checked every equation and unit'}],'statement':'Human team completed model verification'}
    approval.sign(tmp_path,'plan',review,'k'*32);assert approval.require(tmp_path,'plan',pending,'k'*32)
    with pytest.raises(IntegrityError):approval.require(tmp_path,'plan',pending,'x'*32)
def test_no_automatic_human_approval(tmp_path):
    pending=approval.request(tmp_path,'release','a'*64,['x'],'Review release')
    with pytest.raises(Blocked):approval.require(tmp_path,'release',pending,'k'*32)
    with pytest.raises(IntegrityError):approval.sign(tmp_path,'release',read_json(tmp_path/'approvals/release.review-template.json'),'k'*32)

def test_regression():assert np.allclose(linear_fit([0,1,2],[3,5,7]),[3,2])
def test_regression_rank_deficient():
    with pytest.raises(ValueError):linear_fit([1,1,1],[2,3,4])
def test_forecast():assert np.allclose(linear_forecast([2,4,6],2),[8,10])
def test_topsis():assert topsis([[1,3],[2,2],[3,1]],[.5,.5],[True,False])[-1]==1
@pytest.mark.parametrize('X',[[[1,2],[1,3]],[[0,1],[0,2]]])
def test_topsis_constant(X):
    with pytest.raises(ValueError):topsis(X,[1,1],[True,True])
def test_hv_exact():assert hv2([[1,3],[2,2],[3,1]],[4,4])==6

def test_hv_reference_invalid():
    with pytest.raises(ValueError):hv2([[1,5]],[4,4])
def test_method_router():assert route_methods('多目标 multiobjective')[0]['id']=='mosaic-multiobjective'
def test_claim_binding():assert bind_prose('Result {{claim:gain}}',{'gain':{'value':2.5}})=='Result 2.5'
def test_unbound_numbers():
    with pytest.raises(IntegrityError):bind_prose('Measured gain 99.9',{})
@pytest.mark.parametrize('text',[r'\input{secret}',r'\write18{curl}',r'\def\a{bad}',r'\begin{document}bad\end{document}'])
def test_math_io_blocked(text):
    with pytest.raises(IntegrityError):equation(text)
def test_math_allowed():assert equation(r'\min_x \sum_i x_i^2')

def test_citation_binding():
    s={'ref1':{'verified':True}}
    assert bind_prose('Evidence {{cite:ref1}}',{},sources=s)==r'Evidence \cite{ref1}'
def test_citation_injection():
    from cumcm_harness.paper import validate_sources
    with pytest.raises(IntegrityError):validate_sources([{'id':'a','title':'bad','url':r'https://example.com/\input{x}','verified':True,'verification_note':'known'}])
def test_failed_job_not_silently_complete(tmp_path):
    s=Store(tmp_path);g=s.grant('job',{});s.consume(g,'job');s.fail_job('job','confirmed process failure')
    assert s.job('job')['status']=='FAILED'
    with pytest.raises(IntegrityError):s.finish_job('job',{})

def test_ego_requires_scope_and_network_optin():
    from cumcm_harness.ego_bridge import phase_payload,commit
    with pytest.raises(IntegrityError):phase_payload(team_id='',agent_id='a',user_id='u',session_id='s',task_id='t',stage_id='p',messages=['x'],evidence=['e'])
    p=phase_payload(team_id='t',agent_id='a',user_id='u',session_id='s',task_id='t',stage_id='p',messages=['x'],evidence=['e'])
    with pytest.raises(Blocked):commit('http://localhost:8000',p)

def test_parallel_bundle_first_publication(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    s=Store(tmp_path);b={'files':[{'path':'main.py','content':'print(1)\n'*5000}],'notes':[],'algorithm_usage':[]}
    with ThreadPoolExecutor(max_workers=8) as pool:paths=list(pool.map(lambda _:s.publish_bundle(b),range(24)))
    assert len(set(paths))==1;assert (paths[0]/'main.py').read_text()==b['files'][0]['content']

@pytest.mark.parametrize('mode,flags,expected',[('r',0,True),('rb',0,True),('w',1,False),('r+',2,False),(None,0,True)])
def test_runtime_resource_dependency_reads(tmp_path,mode,flags,expected):
    from cumcm_harness.worker import DependencyReads
    p=tmp_path/'vendor/mosaic_v14/data/parameters.json';p.parent.mkdir(parents=True);p.write_text('{}')
    reads=DependencyReads(tmp_path);reads('open',(str(p),mode,flags))
    assert (p in reads.paths)==expected
    reads.active=False;reads('open',(str(p.parent/'later.json'),'r',0));assert p.parent/'later.json' not in reads.paths

def test_runtime_resources_exclude_external_and_cache(tmp_path):
    from cumcm_harness.worker import DependencyReads
    reads=DependencyReads(tmp_path)
    for name in ('vendor/mosaic_v14/__pycache__/x.pyc','outside/config.json'):
        reads('open',(str(tmp_path/name),'r',0))
    assert not reads.paths

def test_runtime_resources_refuse_font(tmp_path):
    from cumcm_harness.worker import DependencyReads
    reads=DependencyReads(tmp_path)
    with pytest.raises(Blocked):reads('open',(str(tmp_path/'vendor/mosaic_v14/secret.ttf'),'r',0))
