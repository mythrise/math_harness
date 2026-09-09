from pathlib import Path
import copy,json
import pytest
from cumcm_harness.common import *
from cumcm_harness.entry_inputs import initialize,load_entry
from cumcm_harness.entry_documents import sha_text
from cumcm_harness.paper_revision import RevisionController,check_patch
from cumcm_harness.controller import DEFAULT_CONFIG
from cumcm_harness.providers import FixtureProvider
from cumcm_harness.review_board import ProviderFailure
from test_three_inputs_documents import make_docx

class Outage:
    model=None
    def invoke(self,*a,**kw):raise ProviderFailure('claude','INJECTED_OFFLINE',retryable=False)


def responder(role,schema,packet):
    if schema=='review':return {'target_digest':packet['target_digest'],'verdict':'PASS','scope':'Fixture review of declared editorial equivalence only.',
         'findings':[],'evidence':['This is an explicit fixture, not a real scientific review.'],'unverified':[]}
    assert schema=='revision_patch'
    edits=[]
    for b in packet['blocks']:
        if '本文模型' in b['text']:edits.append({'block_id':b['id'],'before_sha256':b['sha256'],
            'replacement':b['text'].replace('本文模型','本文所用模型'),'reason':'增加必要连接成分，保留数值、符号与结论不变。'})
    return {'source_sha256':packet['source_sha256'],'diagnosis':[{'location':'supplied prose blocks','issue':'语言表达可以更连贯。','scope':'LANGUAGE'}],
        'edits':edits,'research_requests':[],'limitations':['本次仅编辑普通正文，未重新验证原论文科学结论。']}


def setup_revision(tmp_path,kind='md'):
    source=tmp_path/('paper.'+kind)
    if kind=='docx':make_docx(source)
    elif kind=='pdf':
        import fitz
        with fitz.open() as pdf:
            p=pdf.new_page();p.insert_text((72,80),'Original model result is 0.25. This is a text-only fixture with enough words.')
            pdf.save(source)
    else:source.write_text('研究说明\n\n本文模型的误差为 0.25，比较结果尚需实际验证。\n\n约束为 $x \\ge 0$。\n\n```python\nx = 1\n```')
    root=tmp_path/'run';cfg={**DEFAULT_CONFIG,'materials_workflow':True,'review_backoff_seconds':0,'review_cooldown_seconds':3600}
    initialize(root,input_mode='revise',paper=source,config=cfg)
    return root,source


@pytest.mark.parametrize('kind',['md','docx','pdf','tex'])
def test_editorial_end_to_end_and_exact_replay(tmp_path,kind):
    root,source=setup_revision(tmp_path,kind);original=source.read_bytes();provider=FixtureProvider(responder)
    c=RevisionController(root,fixture_provider=provider);c.providers['claude']=Outage();result=c.run()
    assert result['status']=='REVISION_FIXTURE_COMPLETE_NOT_LIVE_VALIDATED';assert not result['full_research_run']
    assert source.read_bytes()==original
    manifest=tree_manifest(root/'deliverables');before_calls=c.store.get('model_calls_reserved')
    def never(*a,**kw):raise AssertionError('Replay invoked a new model')
    c2=RevisionController(root,fixture_provider=FixtureProvider(never));c2.providers['claude']=Outage()
    replay=c2.run();assert tree_manifest(root/'deliverables')==manifest
    assert c2.store.get('model_calls_reserved')==before_calls;assert replay['result']==result['result']
    if kind in ('md','docx','tex'):assert result['patches']==1
    if kind=='pdf':assert (root/'deliverables/revised.md').is_file();assert not (root/'deliverables/revised.pdf').exists()


def test_substantive_issue_is_handoff_not_fake_new_results(tmp_path):
    root,source=setup_revision(tmp_path)
    def fn(role,schema,packet):
        v=responder(role,schema,packet)
        if schema=='revision_patch':
            v['diagnosis'].append({'location':'原文未提供实验来源','issue':'需要补充实际基准复现。','scope':'SUBSTANTIVE'})
            v['research_requests']=[{'issue':'实际基准结果未核验。','required_evidence':'原始数据与可运行代码、独立评价器。','suggested_action':'进入新建模工作区重新实验。'}]
        return v
    c=RevisionController(root,fixture_provider=FixtureProvider(fn));result=c.run()
    assert result['research_requests']==1;assert '重新实验' in (root/'deliverables/research_handoff.md').read_text()
    report=read_json(root/'deliverables/revision-report.json');assert report['scientific_revalidation']=='NOT_RUN'
    assert '0.25' in (root/'deliverables/revised.md').read_text()


def test_invalid_numeric_edit_is_repaired_not_accepted(tmp_path):
    root,source=setup_revision(tmp_path);attempts=[]
    def fn(role,schema,packet):
        v=responder(role,schema,packet)
        if schema=='revision_patch':
            attempts.append(packet)
            if not packet['repair_feedback']:v['edits'][0]['replacement']=v['edits'][0]['replacement'].replace('0.25','0.20')
        return v
    c=RevisionController(root,fixture_provider=FixtureProvider(fn));result=c.run()
    assert len(attempts)==2;assert '0.25' in (root/'deliverables/revised.md').read_text()
    assert any(e['kind']=='REVISION_REPAIR' for e in c.store.events())


def test_valid_negative_review_stays_negative(tmp_path):
    root,source=setup_revision(tmp_path)
    def fn(role,schema,packet):
        v=responder(role,schema,packet)
        if schema=='review':v.update(verdict='FAIL',findings=[{'severity':'P1','location':'改写语义','issue':'改变了不确定性表述。','required_fix':'恢复原文不确定性。'}])
        return v
    c=RevisionController(root,fixture_provider=FixtureProvider(fn))
    with pytest.raises(ScientificRejection):c.run()
    assert not (root/'deliverables/revised.md').exists()


def test_revision_source_tamper_detected_before_resume(tmp_path):
    root,source=setup_revision(tmp_path);c=RevisionController(root,fixture_provider=FixtureProvider(responder));c.run()
    (root/'entry/paper/original.md').write_text('修改原始数据。')
    with pytest.raises(IntegrityError):RevisionController(root,fixture_provider=FixtureProvider(responder))


def test_revision_output_tamper_blocks_replay(tmp_path):
    root,source=setup_revision(tmp_path);c=RevisionController(root,fixture_provider=FixtureProvider(responder));c.run()
    (root/'deliverables/revised.md').write_text('修改输出。')
    with pytest.raises(IntegrityError):RevisionController(root,fixture_provider=FixtureProvider(responder)).run()


def test_config_tamper_is_rejected(tmp_path):
    root,source=setup_revision(tmp_path);cfg=read_json(root/'config.json');cfg['max_model_calls']+=1;write_json(root/'config.json',cfg)
    with pytest.raises(IntegrityError):RevisionController(root,fixture_provider=FixtureProvider(responder))


def test_unknown_external_call_is_not_retried(tmp_path):
    root,source=setup_revision(tmp_path);c=RevisionController(root,fixture_provider=FixtureProvider(responder))
    with c.store.connect() as db:db.execute('INSERT INTO steps VALUES(?,?,?,NULL,NULL)',('pending',digest({}),'RUNNING'))
    with pytest.raises(UnknownExternalState):c.run()


def test_patch_checker_rejects_unmapped_substantive_change(tmp_path):
    root,source=setup_revision(tmp_path);doc=read_json(root/'entry/paper/document.json')
    v={'source_sha256':doc['source_sha256'],'diagnosis':[{'location':'正文','issue':'数学错误','scope':'SUBSTANTIVE'}],
      'edits':[],'research_requests':[],'limitations':['需要真实核验。']}
    with pytest.raises(IntegrityError):check_patch(v,doc,[])


def test_patch_checker_rejects_out_of_window(tmp_path):
    root,source=setup_revision(tmp_path);doc=read_json(root/'entry/paper/document.json');b=next(b for b in doc['blocks'] if '本文模型' in b['text'])
    v=responder('paper_editor','revision_patch',{'source_sha256':doc['source_sha256'],'blocks':[b]})
    with pytest.raises(IntegrityError):check_patch(v,doc,[])


def test_optional_clarification_preserves_schema_contract(tmp_path):
    from cumcm_harness.contracts import validate
    root,source=setup_revision(tmp_path);doc=read_json(root/'entry/paper/document.json')
    value=responder('paper_editor','revision_patch',{'source_sha256':doc['source_sha256'],'blocks':doc['blocks']})
    value['clarification_responses']=[{'signal_digest':'1'*64,'reason':'这是针对原始否定信号的明确回应，不能通过更换模型忽略问题。'}]
    assert validate('revision_patch',value)


def test_native_audit_checks_revision_exports_without_new_calls(tmp_path,capsys):
    from cumcm_harness.entry_cli import main
    root,source=setup_revision(tmp_path);c=RevisionController(root,fixture_provider=FixtureProvider(responder));c.run()
    count=c.store.get('model_calls_reserved');assert main(['audit',str(root)])==0
    assert 'verified_export_count' in capsys.readouterr().out
    # Editing both an output and its non-authoritative summary cannot bypass CAS.
    (root/'deliverables/revised.md').write_text('篡改输出。')
    summary=read_json(root/'revision_summary.json');summary['result']['output_manifest']=tree_manifest(root/'deliverables')
    write_json(root/'revision_summary.json',summary)
    assert main(['audit',str(root)])==2
    assert c.store.get('model_calls_reserved')==count
