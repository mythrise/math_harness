"""CLI transport mocks exercise prompt wiring, not real model capability."""
import json,copy,shutil
from types import SimpleNamespace
from pathlib import Path
import pytest
from cumcm_harness import providers
from cumcm_harness.common import ROOT,IntegrityError,digest,write_json
from cumcm_harness.materials_contracts import *
from materials_samples import samples,PROBLEM

@pytest.mark.parametrize('role,schema',[
 ('problem_analyst','problem_brief'),('data_steward','data_plan'),('abstract_editor','abstract_revision')])
def test_actual_cli_adapter_sends_skill_prompt_and_receipts(tmp_path,monkeypatch,role,schema):
    b,d,*_=samples();result={'problem_brief':b,'data_plan':d,'abstract_revision':{'abstract':'测试摘要','keywords':['测试'],'claim_ids':[],'remaining_limitations':['没有真实模型调用。']}}[schema]
    captured={}
    def mock_process(argv,*,cwd,out,env,timeout,stdin):
        captured['prompt']=stdin;captured['argv']=argv
        assert 'EXA_API_KEY' not in env and 'CUMCM_OPERATOR_KEY' not in env
        write_json(Path(argv[argv.index('--output-last-message')+1]),result)
        (out/'stdout.log').write_text(json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}})+'\n')
        (out/'stderr.log').write_text('')
        return {'status':'EXITED','returncode':0,'seconds':0.0,'stdout_sha256':'MOCK_ONLY','stderr_sha256':'MOCK_ONLY'}
    monkeypatch.setattr(providers,'run_process',mock_process)
    p=providers.CLIProvider('codex');monkeypatch.setattr(p,'probe',lambda:('/mock/codex','MOCK_VERSION'))
    record=p.invoke(role,schema,{'sample':True},tmp_path/'call')
    assert record['result']==result
    assert '## TRUSTED SKILL materials-principles' in captured['prompt']
    assert record['receipt']['skill_digest']
    assert record['receipt']['usage_disclosure']['response_contract']==schema
    assert (tmp_path/'call/prompt.txt').stat().st_mode&0o777==0o600
    assert (tmp_path/'call').stat().st_mode&0o777==0o700


def test_controller_durable_call_binds_skills_and_reuses(tmp_path):
    from cumcm_harness.controller import Controller,DEFAULT_CONFIG
    from cumcm_harness.store import Store
    b,*_=samples();provider=providers.FixtureProvider(lambda *a:b)
    c=Controller.__new__(Controller);c.root=tmp_path;c.store=Store(tmp_path);c.config=copy.deepcopy(DEFAULT_CONFIG)
    c.providers={'codex':provider};c.check_deadline=lambda:None
    r=c._call_one('brief','problem_analyst','problem_brief',{'problem':PROBLEM},provider_kind='codex')
    assert c._call_one('brief','problem_analyst','problem_brief',{'problem':PROBLEM},provider_kind='codex')==r
    assert provider.count==1 and r['receipt']['skill_digest']


def test_changed_skill_invalidates_even_cached_call(tmp_path,monkeypatch):
    from cumcm_harness.controller import Controller,DEFAULT_CONFIG
    from cumcm_harness.store import Store
    from cumcm_harness import role_skills
    shutil.copytree(ROOT/'.agents',tmp_path/'.agents');monkeypatch.setattr(role_skills,'ROOT',tmp_path)
    b,*_=samples();provider=providers.FixtureProvider(lambda *a:b)
    c=Controller.__new__(Controller);c.root=tmp_path/'workspace';c.store=Store(c.root);c.config=copy.deepcopy(DEFAULT_CONFIG)
    c.providers={'codex':provider};c.check_deadline=lambda:None
    c._call_one('brief','problem_analyst','problem_brief',{},provider_kind='codex')
    p=tmp_path/'.agents/skills/problem-intake/SKILL.md';p.write_text(p.read_text()+'\nChanged trusted instruction.\n')
    with pytest.raises(IntegrityError):c._call_one('brief','problem_analyst','problem_brief',{},provider_kind='codex')
    assert provider.count==1
