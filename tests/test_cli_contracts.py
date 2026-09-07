"""Fake executable protocol tests, NOT calls to actual Codex/Claude models."""
import json,os,sys
from pathlib import Path
import pytest
from cumcm_harness.common import *
from cumcm_harness.providers import CLIProvider,FixtureProvider,review_quorum

REVIEW={'target_digest':'a'*64,'verdict':'PASS','scope':'unit protocol test','findings':[],'evidence':['synthetic evidence for contract testing only'],'unverified':[]}

@pytest.fixture
def fake_cli(tmp_path,monkeypatch):
    def make(kind,mode='ok'):
        p=tmp_path/kind
        source='''#!SHEBANG
import sys,json,pathlib
args=sys.argv[1:]
if '--version' in args: print('FAKE_CLI_TEST_ONLY 0');sys.exit(0)
if '--help' in args:
 print('--output-schema --output-last-message --sandbox --ephemeral --ignore-user-config --json-schema --tools --no-session-persistence --bare --safe-mode --setting-sources --strict-mcp-config --image');sys.exit(0)
prompt=sys.stdin.read()
result=REVIEW
MODE
'''.replace('SHEBANG',sys.executable).replace('result=REVIEW','result='+repr(REVIEW))
        if mode=='malformed':body='print("this is not JSON")'
        elif mode=='error':body='print(json.dumps({"is_error":True,"structured_output":result}))'
        elif mode=='missing':body='print(json.dumps({"result":"PASS"}))'
        elif kind=='claude':body='print(json.dumps({"structured_output":result,"is_error":False,"usage":{},"total_cost_usd":0}))'
        else:body="pathlib.Path(args[args.index('--output-last-message')+1]).write_text(json.dumps(result));print(json.dumps({'type':'turn.completed','usage':{}}))"
        p.write_text(source.replace('MODE',body));p.chmod(0o755);monkeypatch.setenv('PATH',str(tmp_path)+os.pathsep+os.environ['PATH']);return p
    return make

def test_codex_real_adapter_fake_process(fake_cli,tmp_path):
    fake_cli('codex');r=CLIProvider('codex').invoke('paper_reviewer','review',{'target_digest':'a'*64},tmp_path/'logs')
    assert r['result']==REVIEW;assert r['receipt']['cli_version'].startswith('FAKE_CLI_TEST_ONLY')
def test_claude_real_adapter_fake_process(fake_cli,tmp_path):
    fake_cli('claude');r=CLIProvider('claude').invoke('math_reviewer','review',{'target_digest':'a'*64},tmp_path/'logs')
    assert r['result']==REVIEW;assert r['receipt']['model_reported']=='UNREPORTED'
    assert '--max-budget-usd' not in r['receipt']['argv']

def test_claude_null_budget_omits_flag_for_all_shipped_configs(tmp_path):
    from cumcm_harness.controller import DEFAULT_CONFIG,validate_config
    assert DEFAULT_CONFIG['claude_call_budget_usd'] is None
    for path in (Path(__file__).resolve().parents[1]/'configs').glob('*.json'):
        config={**DEFAULT_CONFIG,**json.loads(path.read_text())}
        validate_config(config)
        assert config['claude_call_budget_usd'] is None,path
        command=CLIProvider('claude',max_budget_usd=config['claude_call_budget_usd']).command('claude',tmp_path,'bundle')
        assert '--max-budget-usd' not in command

def test_explicit_historical_budget_still_reproduces_command(tmp_path):
    command=CLIProvider('claude',max_budget_usd=3.0).command('claude',tmp_path,'review')
    assert command[command.index('--max-budget-usd')+1]=='3.0'

def test_fable_does_not_silently_switch_models(tmp_path):
    command=CLIProvider('claude',model='claude-fable-5').command('claude',tmp_path,'bundle')
    assert json.loads(command[command.index('--settings')+1])=={
        'availableModels':['claude-fable-5'],'switchModelsOnFlag':False}
    assert command[command.index('--model')+1]=='claude-fable-5'
    assert '--max-budget-usd' not in command
@pytest.mark.parametrize('mode',['malformed','error','missing'])
def test_claude_bad_envelope(fake_cli,tmp_path,mode):
    fake_cli('claude',mode)
    with pytest.raises((ValueError,IntegrityError,Blocked)):CLIProvider('claude').invoke('math_reviewer','review',{},tmp_path/'logs')
def test_no_dangerous_flags(tmp_path):
    for kind in ('codex','claude'):
        command=CLIProvider(kind).command(kind,tmp_path,'review')
        assert '--yolo' not in command;assert '--dangerously-skip-permissions' not in command
    c=CLIProvider('claude').command('claude',tmp_path,'review');assert c[c.index('--tools')+1]=='';assert 'mcp__*' in c

def test_claude_reuses_user_auth_without_customizations(tmp_path):
    c=CLIProvider('claude').command('claude',tmp_path,'review')
    assert '--bare' not in c
    assert '--safe-mode' in c
    assert c[c.index('--setting-sources')+1]=='user'
    assert c[c.index('--tools')+1]==''
    assert json.loads(c[c.index('--mcp-config')+1])=={'mcpServers':{}}
    assert '--strict-mcp-config' in c and '--no-session-persistence' in c

def test_oauth_env_only_reaches_model_provider(monkeypatch):
    from cumcm_harness.process import clean_env
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN','test-token-not-a-real-secret')
    monkeypatch.setenv('CUMCM_OPERATOR_KEY','test-operator-key')
    assert clean_env(provider=True)['CLAUDE_CODE_OAUTH_TOKEN']=='test-token-not-a-real-secret'
    assert 'CLAUDE_CODE_OAUTH_TOKEN' not in clean_env()
    assert 'CUMCM_OPERATOR_KEY' not in clean_env(provider=True)

def reviews(tmp_path):
    p=FixtureProvider(lambda *a:dict(REVIEW))
    return [p.invoke(role,'review',{},tmp_path/role) for role in ('math_reviewer','experiment_reviewer')]
def test_fixture_cannot_pass_live_gate(tmp_path):
    with pytest.raises(Blocked):review_quorum(reviews(tmp_path),'a'*64)
def test_demo_explicit_label(tmp_path):assert review_quorum(reviews(tmp_path),'a'*64,allow_fixture=True)['status']=='DEMO_QUORUM'
def test_stale_review(tmp_path):
    with pytest.raises(IntegrityError):review_quorum(reviews(tmp_path),'b'*64,allow_fixture=True)
def test_duplicate_review(tmp_path):
    r=reviews(tmp_path)
    with pytest.raises(IntegrityError):review_quorum([r[0],r[0]],'a'*64,allow_fixture=True)
