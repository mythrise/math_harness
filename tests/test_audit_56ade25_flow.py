"""Synthetic control-plane fault injection; real Docker coverage has separate receipts."""
import copy,hashlib,json
from types import SimpleNamespace
import pytest
from cumcm_harness.common import IntegrityError,digest,read_json
from cumcm_harness.contracts import validate
from cumcm_harness.exa_ledger import SharedHTTPGate,ExaLedger,ExaWait
from cumcm_harness.exa_defaults import DEFAULT_POLICY
from cumcm_harness.exa_evidence import source_packet
from cumcm_harness.store import Store
from cumcm_harness.review_board import NeedsClarification,ScientificRejection
from test_exa_r2_workflow import controller
from test_exa_r2_transport import client,PAYLOAD
from test_review_board import board


@pytest.mark.parametrize('opponent',[False,True])
def test_query_prompt_declares_the_same_stage_purposes_as_runtime_guard(tmp_path,opponent):
    c,_=controller(tmp_path)
    class Captured(Exception):pass
    def capture(key,role,schema,packet,**kwargs):
        assert packet['allowed_purposes']==(['counterexample','limitations'] if opponent else ['background','support','limitations'])
        assert 'allowed_purposes' in packet['requirements']
        raise Captured
    c.call=capture
    with pytest.raises(Captured):c.literature._queries('stage-purpose',opponent=opponent)


def test_qualitative_question_has_real_text_not_placeholder_measurement():
    text='The boundary case is infeasible because the capacity is zero.'
    ev={'score':1.,'valid':True,'metric':'score','checks':[{'name':'constraints','passed':True,'detail':'Checked'}],
        'question_coverage':['Q1','Q2'],'measurements':[{'id':'m','value':1.,'unit':'score','question_id':'Q1','description':'Measured'}],
        'question_evidence':[{'id':'argument','question_id':'Q2','kind':'text','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]}
    assert validate('evaluation',ev)==ev
    bad=copy.deepcopy(ev);bad['question_evidence'][0]['text']='Changed argument'
    with pytest.raises(IntegrityError):validate('evaluation',bad)
    bad=copy.deepcopy(ev);bad['question_evidence']=[]
    with pytest.raises(IntegrityError):validate('evaluation',bad)


def test_hypothesis_coverage_accumulates_across_distinct_rounds(tmp_path):
    c,_=controller(tmp_path);wf=c.literature
    queries=iter([{'queries':[{'query':f'generic method {round} {h}','profile':'foundations','purpose':'support',
        'hypothesis_ids':[h],'additional_queries':[]} for h in ['H1','H2']]} for round in [1,2]])
    c.call=lambda *a,**k:{'result':next(queries)}
    original=wf.client.search
    def search(query,**kwargs):
        if query.endswith('1 H2') or query.endswith('2 H1'):return []
        return original(query,**kwargs)
    wf.client.search=search
    sources,links=wf._queries('alternating',hypotheses=[{'id':'H1'},{'id':'H2'}])
    assert len(links)==4 and {h for s in sources for h in s['hypothesis_ids']}=={'H1','H2'}
    assert wf.client.ledger.summary()['http_attempts_reserved']==2


@pytest.mark.parametrize('phase',['ACQUIRED_UNSENT','RESERVING_UNSENT','BOUND_UNSENT','SENT_OR_UNKNOWN'])
def test_orphan_lease_has_explicit_owner_and_recovery_by_id(tmp_path,phase):
    store=Store(tmp_path/'run');ledger=ExaLedger(store,DEFAULT_POLICY);gate=SharedHTTPGate(tmp_path/'gate.sqlite3')
    key=digest('request');ledger.prepare(key,{'synthetic':True})
    lease=gate.acquire('test-credential-source','run',DEFAULT_POLICY,request=key)
    if phase!='ACQUIRED_UNSENT':gate.phase(lease,'RESERVING_UNSENT')
    if phase in ('BOUND_UNSENT','SENT_OR_UNKNOWN'):
        attempt=ledger.reserve(key,'scouting');gate.bind(lease,attempt)
    if phase=='SENT_OR_UNKNOWN':gate.phase(lease,phase)
    row=gate.inspect('run')[0]
    assert row['phase']==phase and row['owner'] and row['request']==key
    # An old timestamp alone does not expire a lease or authorize another HTTP.
    with gate.connect() as db:db.execute('UPDATE leases SET started=0 WHERE id=?',(lease,))
    assert len(gate.inspect('run'))==1
    with pytest.raises(IntegrityError):gate.recover_lease('wrong-run',lease,ledger,'Synthetic stopped-owner verification')
    gate.recover_lease('run',lease,ledger,'Synthetic stopped-owner verification, remote state checked')
    assert gate.inspect('run')==[]
    assert ledger.get(key)['status']=='READY'


def test_reserve_before_bind_is_recoverable_by_request_identity(tmp_path):
    c=client(tmp_path);key=digest('reserve gap');c.ledger.prepare(key,{'test':True})
    lease=c.gate.acquire(c.credential_source,c.snapshot['run_id'],c.policy,request=key)
    c.gate.phase(lease,'RESERVING_UNSENT');attempt=c.ledger.reserve(key,'scouting')
    assert c.gate.inspect(c.snapshot['run_id'])[0]['attempt'] is None
    c.gate.recover_lease(c.snapshot['run_id'],lease,c.ledger,'Test-only owner stopped before transport invocation')
    with c.store.connect() as db:assert db.execute('SELECT status FROM exa_attempts WHERE id=?',(attempt,)).fetchone()[0]=='RECONCILED_UNKNOWN'


def test_read_window_preserves_original_offsets_and_rejects_unknown_section(tmp_path):
    c=client(tmp_path);source=c.search('generic mathematical method')[0]
    source['text']='INTRODUCTION\n'+('x'*1000)+'\nMETHODS\nThe material theorem.'
    row=source_packet([source],60,windows={source['id']:{'section':'METHODS'}})[0]
    assert row['text'].startswith('METHODS')
    assert source['text'][row['packet_coverage']['offset_start']:row['packet_coverage']['offset_end']]==row['text']
    with pytest.raises(IntegrityError):source_packet([source],60,windows={source['id']:{'section':'ABSENT'}})


def test_immutable_text_object_is_separate_from_request_identity(tmp_path):
    c=client(tmp_path);a=c.search('generic first mathematical method')[0];b=c.search('generic second mathematical method')[0]
    assert a['snapshot_id']!=b['snapshot_id'] and a['original_text_object']==b['original_text_object']
    assert c.ledger.summary()['http_attempts_reserved']==2
    objects=list((tmp_path/'literature/source-text-objects').glob('*.json'));assert len(objects)==1
    value=read_json(objects[0]);value['text']='tampered';objects[0].write_text(json.dumps(value))
    with pytest.raises(IntegrityError):c.search('generic first mathematical method')


def test_clarification_must_address_signal_and_keeps_actual_packet_receipt(tmp_path):
    c,b,calls,p=board(tmp_path);original=c._call_one;signal={'raw_excerpt':'REVISE: contradicted','signal_digest':digest('negative')}
    def invoke(key,role,schema,packet,**kw):
        if not packet.get('clarification_signals'):raise NeedsClarification(signal,{'test':'receipt'})
        result=original(key,role,schema,packet,**kw)
        result['result']['clarification_responses']=[{'signal_digest':signal['signal_digest'],'reason':'The cited counterexample is retained and requires the specified scope restriction.'}]
        result['receipt']['response_digest']=digest(result['result'])
        return result
    c._call_one=invoke
    result=b.invoke('clarify','math_reviewer','review',p)
    assert result['receipt']['packet_digest']==digest(calls[0][2]) and result['receipt']['packet_digest']!=digest(p)
    assert b.invoke('different-parent','math_reviewer','review',p)==result and len(calls)==1


def test_clarification_cannot_be_silently_dropped(tmp_path):
    c,b,calls,p=board(tmp_path);original=c._call_one;signal={'raw_excerpt':'FAIL','signal_digest':digest('negative')}
    def invoke(key,role,schema,packet,**kw):
        if not packet.get('clarification_signals'):raise NeedsClarification(signal,{})
        return original(key,role,schema,packet,**kw)
    c._call_one=invoke
    with pytest.raises(IntegrityError,match='ignored'):b.invoke('clarify','math_reviewer','review',p)
    assert len(calls)==1


def test_opposing_candidate_cannot_disappear_from_selection(tmp_path):
    c,_=controller(tmp_path);wf=c.literature
    source=wf.client.search('generic counterexample method',profile='counterexamples')[0]
    source['purpose']='counterexample';source['hypothesis_ids']=['H1']
    c.call=lambda *a,**k:{'result':{'selections':[{'source_id':source['id'],'hypothesis_ids':['H1'],'critical':True,'expanded':False,'reason':'Material source to read independently.'}]}}
    with pytest.raises(IntegrityError,match='opposing candidate'):wf._read_selected('test',{'hypotheses':[{'id':'H1'}]},[source])

@pytest.mark.parametrize('window',['acquired','reserved','bound','http_returned','before_receipt'])
def test_sigkill_windows_preserve_lease_without_automatic_retry(tmp_path,window):
    import subprocess,sys
    root=tmp_path/'killed'
    script='''
import os,signal,sys
from pathlib import Path
from cumcm_harness.store import Store
from cumcm_harness.exa_defaults import DEFAULT_POLICY
from cumcm_harness.exa_ledger import ExaLedger,SharedHTTPGate
root=Path(sys.argv[1]);window=sys.argv[2]
store=Store(root);ledger=ExaLedger(store,DEFAULT_POLICY);gate=SharedHTTPGate(root/'gate.sqlite3')
ledger.prepare('request',{'synthetic':True})
lease=gate.acquire('synthetic-source','run',DEFAULT_POLICY,request='request')
def kill():os.kill(os.getpid(),signal.SIGKILL)
if window=='acquired':kill()
gate.phase(lease,'RESERVING_UNSENT');attempt=ledger.reserve('request','scouting')
if window=='reserved':kill()
gate.bind(lease,attempt)
if window=='bound':kill()
gate.phase(lease,'SENT_OR_UNKNOWN')
# A deterministic fake transport returned a body. No network was used.
if window=='http_returned':kill()
store.put({'synthetic_response':True})
if window=='before_receipt':kill()
'''
    process=subprocess.run([sys.executable,'-c',script,str(root),window],capture_output=True,text=True)
    assert process.returncode<0,process.stderr
    ledger=ExaLedger(Store(root),DEFAULT_POLICY);gate=SharedHTTPGate(root/'gate.sqlite3')
    rows=gate.inspect('run');assert len(rows)==1
    if window!='acquired':
        with pytest.raises(ExaWait,match='UNKNOWN'):ledger.prepare('request',{'synthetic':True})
    gate.recover_lease('run',rows[0]['id'],ledger,'Synthetic SIGKILL owner observed stopped; fake transport had no remote billing')
    assert not gate.inspect('run') and ledger.get('request')['status']=='READY'


def test_timeout_does_not_guess_request_was_unsent_or_release_lease(tmp_path):
    calls=[]
    def transport(*args):calls.append(args);raise TimeoutError('synthetic timeout')
    c=client(tmp_path,transport)
    with pytest.raises(ExaWait,match='UNKNOWN_TRANSPORT'):c.search('generic timeout method')
    with pytest.raises(ExaWait,match='UNKNOWN_INFLIGHT'):c.search('generic timeout method')
    assert len(calls)==1 and len(c.gate.inspect(c.snapshot['run_id']))==1
    assert c.ledger.summary()['http_attempts_reserved']==1


from test_cli_contracts import fake_cli
from cumcm_harness.providers import CLIProvider

@pytest.mark.parametrize('schema,raw',[('review','REVISE: contradicted {invalid json'),('hypothesis_audit_r2','REVISE: contradicted {invalid json')])
def test_real_adapter_preserves_negative_malformed_raw_reply(fake_cli,tmp_path,schema,raw):
    binary=fake_cli('claude','malformed')
    binary.write_text(binary.read_text().replace('this is not JSON',raw))
    with pytest.raises(NeedsClarification) as error:CLIProvider('claude').invoke('hypothesis_critic',schema,{'target_digest':'a'*64},tmp_path/'logs')
    assert error.value.signal['raw_excerpt'].strip()==raw
    assert (tmp_path/'logs/invalid_response.txt').read_text().strip()==raw
    assert read_json(tmp_path/'logs/clarification.json')['status']=='NEEDS_CLARIFICATION'


def test_every_bundle_variant_has_independent_tests_and_negative_replay(tmp_path):
    from cumcm_harness.controller import Controller,DEFAULT_CONFIG
    from cumcm_harness.common import write_json
    store=Store(tmp_path);calls=[]
    class Executor:
        def execute(self,code,entry,data,out,args,limits,**kwargs):
            variant=args[args.index('--variant')+1];calls.append(variant)
            write_json(out/'tests.json',{'all_passed':variant!='broken','cases':[{'name':str(i),'passed':variant!='broken','detail':'Known boundary case.'} for i in range(3)]})
    c=SimpleNamespace(root=tmp_path,store=store,config=DEFAULT_CONFIG,executor=Executor(),literature=None)
    verifier={'files':[{'path':'test_solver.py','content':'# supplied test fixture'}],'notes':[],'algorithm_usage':[]}
    runner=SimpleNamespace(negative_controls=lambda _:[])
    row={'job_id':'baseline-code','seed':101,'variant':'baseline'}
    assert Controller.selftests(c,runner,verifier,row)['passed']
    assert Controller.selftests(c,runner,verifier,row)['passed']
    row={'job_id':'changed-code','seed':101,'variant':'full'}
    assert Controller.selftests(c,runner,verifier,row)['passed']
    row={'job_id':'changed-code-broken-variant','seed':101,'variant':'broken'}
    for _ in range(2):
        with pytest.raises(ScientificRejection):Controller.selftests(c,runner,verifier,row)
    assert calls==['baseline','full','broken']


def test_doctor_does_not_count_host_tex_as_container_readiness(monkeypatch):
    from cumcm_harness.cli import doctor
    from cumcm_harness.common import InfrastructureUnavailable
    monkeypatch.setattr('cumcm_harness.cli.shutil.which',lambda name:'/fixture/'+name)
    def unavailable():raise InfrastructureUnavailable('Synthetic missing dedicated TeX image')
    monkeypatch.setattr('cumcm_harness.tex_sandbox.probe',unavailable)
    result=doctor()
    assert not result['ready_for_live'] and result['tex_container_probe']['status']=='BLOCKED'
