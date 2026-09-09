"""Reported failure PATTERNS on synthetic source documents, not private log replay."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json, re, hashlib
import pytest
from jsonschema import Draft202012Validator
from cumcm_harness.common import *
from cumcm_harness.contracts import SCHEMAS, validate
from cumcm_harness.materials_contracts import check_brief
from cumcm_harness.brief_validation import *
from cumcm_harness.brief_sources import *
from cumcm_harness.brief_contracts import *
from cumcm_harness.brief_workflow import BriefWorkflow
from cumcm_harness.review_board import ReviewBoard,ProviderFailure,ReviewUnavailable
from cumcm_harness.store import Store

PROBLEM=('第一问：给出比值及可行方案。\n\n第二问：比较方案并输出结果表。\n\n'
         '约束：分母必须为正，任务不可重复。\n\n'
         'ST 为当地时间。\n\n比值定义为 eta = A/B，其中 A 为接收量，B 为输入量。\n\n'
         '装置采用双轴机构，两个转轴分别控制方位角与俯仰角。\n\n'
         '表格字段：月份、平均输入量、比值。单位为月和瓦，月份为1至12。')

def problem_units(text=PROBLEM):
 return paragraph_units(text,{'start':0,'end':len(text),'quote':text},'T0001',identity=digest(text))

def outline(units):
 qs=[]
 for i in range(2):
  qs.append({'id':'Q'+str(i+1),'title':'原题问题','direct_goal':units[i]['text'],'inferred_goal':'无额外目标',
   'inputs':['原始数据'],'outputs':['问题要求的量与方案'],'depends_on':[],'answer_type':'quantitative',
   'family':'mixed','source_unit_ids':[units[i]['id']]})
 return {'questions':qs,'unit_risks':[],'completion_criteria':['回答原题所有实际小问']}

def source_fact(u):
 text=u['text'];kind='deliverable' if text.startswith(('第一问','第二问')) else 'constraint' if text.startswith('约束') else 'given'
 ds=[{'subject':'ST','quote':'ST 为当地时间'}] if 'ST 为当地时间' in text else []
 category='definition' if ds else 'formula' if 'eta =' in text else 'table' if text.startswith('表格') else 'geometry' if '双轴' in text else 'prose'
 return {'kind':kind,'category':category,'statement':text,'source_unit_ids':[u['id']],
         'question_ids':['Q1'] if text.startswith('第一问') else ['Q2'] if text.startswith('第二问') else ['Q1','Q2'],
         'declarations':ds}

def sample_brief(text=PROBLEM):
 us=problem_units(text);return assemble(outline(us),[source_fact(u) for u in us],us,text),us

def legacy_brief():
 b,u=sample_brief()
 for i,r in enumerate(b['requirements']):
  for field in ('source_unit_ids','anchors','anchor_space','declarations','references','category'):r.pop(field,None)
  r['id']='G'+str(i+1)
 for q in b['questions']:
  for field in ('given_ids','deliverable_ids'):q.pop(field,None)
  q['constraint_ids']=['G3']
 return b

@pytest.mark.parametrize('field,kind',[('constraint_ids','given'),('constraint_ids','deliverable'),('given_ids','constraint'),('deliverable_ids','given')])
def test_wrong_type_rejected(field,kind):
 b,_=sample_brief();r=next(r for r in b['requirements'] if r['kind']==kind)
 b['questions'][0][field]=[r['id']]
 with pytest.raises(BriefContractError):typed_links(b)

def test_51_bad_links_are_reported_not_relabelled():
 rows=[{'id':f'R{i:02}','kind':'given','question_ids':['Q1','Q2','Q3']} for i in range(17)]
 value={'requirements':rows,'questions':[{'id':q,'constraint_ids':[r['id'] for r in rows]} for q in ('Q1','Q2','Q3')]}
 original=deepcopy(value)
 with pytest.raises(BriefContractError) as e:typed_links(value)
 assert len(e.value.findings)==51 and value==original

@pytest.mark.parametrize('statement,missing',[
 ('分母见 G37','G37'),('各因子定义见 G32 至 G38','G38'),('距离单位见 G39','G39'),
 ('see R004-R006','R006'),('详见 R12—R14','R14'),('引用 G999 尚未定义','G999')])
def test_reported_dangling_forms(statement,missing):
 b=legacy_brief();b['requirements'][0]['statement']=statement
 with pytest.raises(BriefContractError) as e:check_reference_graph(b,PROBLEM)
 assert any(f.get('detail')==missing for f in e.value.findings)

@pytest.mark.parametrize('statement',['见 R100至R1','见 R1至R9999','见 R1至G3'])
def test_bad_reference_ranges_bound(statement):
 b=legacy_brief();b['requirements'][0]['statement']=statement
 with pytest.raises(BriefContractError):check_reference_graph(b,PROBLEM)

@pytest.mark.parametrize('refs',[['G2','G2'],['G1']])
def test_duplicate_and_self_reference(refs):
 b=legacy_brief();b['requirements'][0]['references']=refs
 with pytest.raises(BriefContractError):check_reference_graph(b,PROBLEM)

def test_cross_reference_cycle_rejected():
 b=legacy_brief();b['requirements'][0]['references']=['G2'];b['requirements'][1]['references']=['G1']
 with pytest.raises(BriefContractError,match='CYCLIC_REFERENCE'):check_reference_graph(b,PROBLEM)

def test_source_object_identifier_is_not_a_missing_requirement():
 assert references_in('传感器 G37 为原始编号',original='传感器 G37 为原始编号')==[]

def test_given_time_cannot_be_reopened():
 b,_=sample_brief();b['ambiguities']=[{'id':'A01','kind':'missing_information','subject':'ST','issue':'当地时间是否为ST未明确','impact':'改变模型输入','resolution':'等待解释','related_requirement_ids':[]}]
 with pytest.raises(BriefContractError,match='REOPENED'):definition_conflicts(b)

def test_legacy_time_contradiction_detected():
 b=legacy_brief();b['ambiguities']=[{'id':'A01','issue':'当地时间是否直接作为 ST 未完全明确','impact':'输入口径','resolution':'重新解释'}]
 with pytest.raises(BriefContractError,match='LEGACY_CONVENTION'):definition_conflicts(b)

def test_genuine_conflicting_sources_require_two_witnesses():
 b,_=sample_brief();r=next(r for r in b['requirements'] if r['declarations'])
 b['ambiguities']=[{'id':'A01','kind':'source_conflict','subject':'ST','issue':'不同来源冲突','impact':'输入不同','resolution':'保留并请求核对','related_requirement_ids':[r['id']]}]
 with pytest.raises(BriefContractError):definition_conflicts(b)
 second=deepcopy(r);second['id']='G50';second['declarations']=[{'subject':'ST','quote':'ST 为另一个明确写出的口径'}]
 b['requirements'].append(second);b['ambiguities'][0]['related_requirement_ids'].append('G50')
 assert definition_conflicts(b)['ST']

@pytest.mark.parametrize('field,value',[('constraint_ids',['G999']),('given_ids',['G999']),('deliverable_ids',['G999'])])
def test_auto_builder_ignores_model_link_fields(field,value):
 b,_=sample_brief();qs=deepcopy(b['questions']);qs[0][field]=value
 result=assign_typed_links(qs,b['requirements']);typed_links({**b,'questions':result})
 assert 'G999' not in result[0][field]

@pytest.mark.parametrize('n',[119,120,121,145,256,500])
def test_assembled_capacity_above_120(n):
 text='\n\n'.join([*PROBLEM.split('\n\n')[:2],'约束：参数必须非负。']+[f'给定参数 v{i} 为 {i} 米。' for i in range(n-3)])
 b,u=sample_brief(text);check_complete(b,u,text);assert len(b['requirements'])==n

def test_global_cap_never_truncates():
 text='\n\n'.join(PROBLEM.split('\n\n')[:2]+[f'参数 {i} 米' for i in range(512)])
 with pytest.raises(IntegrityError,match='exceeds'):sample_brief(text)

@pytest.mark.parametrize('key',['brief_outline','brief_facts','brief_ambiguities','brief_local_patch','brief_page_text'])
def test_registered_schema_and_transport_projection(key):
 from cumcm_harness.provider_schema import codex_schema
 Draft202012Validator.check_schema(SCHEMAS[key]);Draft202012Validator.check_schema(codex_schema(SCHEMAS[key]))

def test_unknown_outline_source():
 u=problem_units();o=outline(u);o['questions'][0]['source_unit_ids']=['Sbad']
 with pytest.raises(IntegrityError):check_outline(o,u)

def test_outline_must_have_valid_dag():
 u=problem_units();o=outline(u);o['questions'][0]['depends_on']=['Q2'];o['questions'][1]['depends_on']=['Q1']
 with pytest.raises(IntegrityError):check_outline(o,u)

@pytest.mark.parametrize('value',['未知值为99米。','未知值为88.5米。'])
def test_table_title_is_not_numeric_evidence(value):
 u=problem_units('表格名称')[0];f=source_fact(u);f.update(category='table',statement=value)
 with pytest.raises(BriefContractError,match='UNSOURCED_NUMBER'):check_fact(f,[u],['Q1','Q2'])

@pytest.mark.parametrize('symbol',['π','A','B','dHR','omega'])
def test_formula_fragment_cannot_supply_absent_symbol(symbol):
 u=problem_units('公式分母为 cos(x)')[0];f=source_fact(u);f.update(category='formula',statement='完整公式为 '+symbol+'/cos(x)')
 with pytest.raises(BriefContractError,match='UNSOURCED_SYMBOL'):check_fact(f,[u],['Q1','Q2'])

def test_whole_formula_multiline_kept_in_one_unit():
 text='完整公式\neta =\nA / B\n分母 B 为输入量。'
 u=problem_units(text);assert len(u)==1 and u[0]['text']==text
 f=source_fact(u[0]);f.update(category='formula');check_fact(f,u,['Q1','Q2'])

@pytest.mark.parametrize('field',['source_unit_ids','question_ids'])
def test_foreign_fact_identifiers(field):
 u=problem_units();f=source_fact(u[0]);f[field]=['UNKNOWN']
 with pytest.raises(IntegrityError):check_fact(f,u,['Q1','Q2'])

def test_definition_requires_exact_quote():
 u=problem_units();f=source_fact(u[3]);f['declarations'][0]['quote']='ST 为另一种时间'
 with pytest.raises(IntegrityError):check_fact(f,u,['Q1','Q2'])

def test_definition_cannot_hide_from_consistency_register():
 u=problem_units();f=source_fact(u[3]);f['declarations']=[]
 with pytest.raises(IntegrityError):check_fact(f,u,['Q1','Q2'])

def batch_response(units):
 return {'status':'COMPLETE','facts':[source_fact(u) for u in units],'exclusions':[],'unreadable':[],'reason':''}

@pytest.mark.parametrize('kind',['omit','duplicate','overlap','foreign','unreadable'])
def test_batch_completeness_failures(kind):
 us=problem_units()[:2];v=batch_response(us)
 if kind=='omit':v['facts'].pop()
 if kind=='duplicate':v['exclusions']=[{'source_unit_id':us[0]['id'],'reason':'有明确原因但与已有覆盖重叠。'}]*2
 if kind=='overlap':v['exclusions']=[{'source_unit_id':us[0]['id'],'reason':'有明确原因但与已有覆盖重叠。'}]
 if kind=='foreign':v['facts'][0]['source_unit_ids']=['Sbad']
 if kind=='unreadable':v['unreadable']=['缺分母']
 with pytest.raises(IntegrityError):check_facts(v,us,['Q1','Q2'])

def test_split_is_explicit_not_partial_success():
 us=problem_units()[:2];v=batch_response(us);v['status']='NEEDS_SPLIT'
 with pytest.raises(IntegrityError):check_facts(v,us,['Q1','Q2'])
 v['facts']=[];assert check_facts(v,us,['Q1','Q2'])['status']=='NEEDS_SPLIT'

def patch_for(b,u):
 r=b['requirements'][0];f=source_fact(u[0]);f['statement']='按原题要求，'+f['statement']
 return {'base_digest':digest(b),'updates':[{'requirement_id':r['id'],'before_digest':digest(r),'fact':f}],
         'additions':[],'ambiguities':[],'reasons':['仅补充描述，保留原题交付物与全部来源。']}

def test_local_patch_preserves_untouched_items():
 b,u=sample_brief();p=patch_for(b,u);after=apply_local_patch(b,p,u,PROBLEM)
 assert after['requirements'][1:]==b['requirements'][1:]
 assert b['requirements'][0]['statement']==u[0]['text']

@pytest.mark.parametrize('kind',['base','before','unknown','duplicate','weaken','noop','drop_source'])
def test_illegal_global_patches(kind):
 b,u=sample_brief();p=patch_for(b,u)
 if kind=='base':p['base_digest']='0'*64
 if kind=='before':p['updates'][0]['before_digest']='0'*64
 if kind=='unknown':p['updates'][0]['requirement_id']='X'
 if kind=='duplicate':p['updates']*=2
 if kind=='weaken':p['updates'][0]['fact']['kind']='background'
 if kind=='noop':p['updates']=[]
 if kind=='drop_source':p['updates'][0]['fact']['source_unit_ids']=[u[1]['id']];p['updates'][0]['fact']['statement']=u[1]['text']
 with pytest.raises(IntegrityError):apply_local_patch(b,p,u,PROBLEM)

@pytest.mark.parametrize('limit',[1,2,4,12])
def test_source_batches_cover_all_units(limit):
 us=problem_units();b=make_batches(us,max_units=limit,max_chars=150)
 assert [u['id'] for batch in b for u in batch]==[u['id'] for u in us]
 assert all(len(batch)<=limit for batch in b)

def test_oversized_unit_stops_without_truncation():
 with pytest.raises(NeedsSourceInput):problem_units('x'*(MAX_UNIT_CHARS+1))

def source_workspace(tmp_path,text=PROBLEM,pdf=None):
 root=tmp_path/'workspace';root.mkdir();original=tmp_path/'original.md';original.write_text(text)
 if pdf is not None:original=pdf;text=read_source_problem(pdf)
 (root/'problem.md').write_text(text)
 m=snapshot_problem(root,original,text)
 info={'problem_source_manifest':m,'problem_original_sha256':file_hash(original)}
 return root,text,info

def test_frozen_snapshot_original_and_image_tamper(tmp_path):
 root,text,i=source_workspace(tmp_path);load_snapshot(root,i)
 (root/'problem_source/original.md').write_text('changed')
 with pytest.raises(IntegrityError):load_snapshot(root,i)

def test_missing_snapshot_cannot_be_retrofitted(tmp_path):
 with pytest.raises(NeedsSourceInput):load_snapshot(tmp_path,{})

def test_pdf_images_are_retained_without_ocr(tmp_path):
 import fitz
 p=tmp_path/'original.pdf'
 with fitz.open() as d:
  page=d.new_page();page.insert_text((72,72),'Definition: eta = A / B. Complete denominator B.');d.save(p)
 root,text,i=source_workspace(tmp_path,pdf=p);s=load_snapshot(root,i)
 assert s['ocr_used'] is False and len(s['pages'])==1
 assert (root/s['pages'][0]['image']).is_file()
 assert s['pages'][0]['anchor']['quote'] in text

def test_scanned_page_uses_image_not_fabricated_text(tmp_path):
 import fitz
 p=tmp_path/'blank.pdf'
 with fitz.open() as d:d.new_page();d.save(p)
 root,text,i=source_workspace(tmp_path,pdf=p)
 assert 'NO_EXTRACTABLE_TEXT' in text and load_snapshot(root,i)['pages'][0]['image']

# Model/transport responses below are fixed test data. No LLM calls take place.
class FixedScript:
 def __init__(self):self.calls=[];self.hook=None
 def __call__(self,role,schema,packet,provider):
  self.calls.append((role,schema,deepcopy(packet),provider))
  if self.hook:
   value=self.hook(role,schema,packet,provider)
   if value is not None:return value
  if schema=='brief_outline':return outline(packet['source_units'])
  if schema=='brief_facts':return batch_response(packet['source_units'])
  if schema=='brief_ambiguities':
   defs={}
   for f in packet['facts']:
    for d in f['declarations']:defs.setdefault(d['subject'],[]).append(f['id'])
   return {'ambiguities':[],'accepted_definitions':[{'subject':s,'requirement_ids':v} for s,v in defs.items()]}
  if schema=='brief_page_text':return {'status':'COMPLETE','text':PROBLEM,'unreadable':[],'notes':['Synthetic fixed transcription, not live vision.']}
  if schema=='review':
   return {'target_digest':packet['target_digest'],'verdict':'PASS','scope':'FIXED_TEST_RESPONSE',
     'findings':[],'evidence':['Fixture oracle only, not scientific correctness.'],'unverified':[]}
  raise AssertionError(schema)

class FixedController:
 """Test seam: real ReviewBoard + Store + brief code, prewritten model replies."""
 def __init__(self,root,text,intake,script=None):
  self.root=root;self.problem=text;self.intake=intake;self.store=Store(root);self.base={};self.demo=True
  self.config={'repair_attempts':1,'review_attempts_per_provider':1,'review_cooldown_seconds':60,
               'review_backoff_seconds':0,'review_members_per_role':2,'max_model_calls':400}
  self.providers={p:SimpleNamespace(model='FIXTURE_MODEL') for p in ('codex','claude')};self.review_cycle=1
  self.script=script or FixedScript();self.review_board=ReviewBoard(self,sleep=lambda _:None)
  self.invocations=0;self.replay=False
 def _call_one(self,key,role,schema,packet,*,provider_kind,images=(),managed_failure=False):
  inputs={'role':role,'schema':schema,'packet':packet,'provider':provider_kind,'images':[file_hash(p) for p in images]}
  def execute():
   if self.replay:raise AssertionError('Unexpected new model/fixture invocation')
   n=self.store.get('model_calls_reserved',0)
   if n>=self.config['max_model_calls']:raise BudgetExhausted('fixture budget')
   self.store.set('model_calls_reserved',n+1);self.invocations+=1
   try:result=self.script(role,schema,packet,provider_kind)
   except ProviderFailure as e:return {'failure':{'provider':e.provider,'code':e.code,'retryable':e.retryable}}
   validate(schema,result)
   return {'result':result,'receipt':{'packet_digest':digest(packet),'response_digest':digest(result),
      'role':role,'provider':provider_kind,'transport':'FIXTURE_NOT_LLM','invocation_id':digest([key,inputs])}}
  r=self.store.step('fixed-model:'+key,inputs,execute)
  if 'failure' in r:raise ProviderFailure(**r['failure'])
  return r
 def reviews(self,key,target,*,roles,stage,context,images=()):
  from cumcm_harness.review_stages import SOURCE_REVIEW_STAGES
  assert stage in SOURCE_REVIEW_STAGES
  return self.review_board.review(key,{'artifact':target,'target_digest':digest(target),'context':context,'review_stage':stage},roles,images=images)

def test_text_pipeline_and_replay(tmp_path):
 root,text,info=source_workspace(tmp_path);c=FixedController(root,text,info)
 b=BriefWorkflow(c).run({},{});assert len(b['requirements'])==7
 snapshot=file_hash(root/'brief/accepted.json');n=c.store.get('model_calls_reserved')
 c.replay=True;c.review_cycle+=1;again=BriefWorkflow(c).run({},{})
 assert again==b and c.store.get('model_calls_reserved')==n and file_hash(root/'brief/accepted.json')==snapshot
 assert c.store.audit()['integrity']=='PASS'

def test_large_brief_runs_in_small_calls(tmp_path):
 text='\n\n'.join(PROBLEM.split('\n\n')[:2]+['约束：必须可行。']+[f'参数 v{i} 为 {i} 米。' for i in range(142)])
 root,text,info=source_workspace(tmp_path,text);c=FixedController(root,text,info)
 b=BriefWorkflow(c).run({},{});assert len(b['requirements'])==145
 calls=[p for r,s,p,k in c.script.calls if s=='brief_facts']
 assert len(calls)>1 and all(len(p['source_units'])<=4 for p in calls)
 assert b['requirements'][-1]['statement'].endswith('141 米。')

def test_producer_timeout_uses_managed_failover(tmp_path):
 root,text,info=source_workspace(tmp_path);script=FixedScript();failed=[]
 def hook(role,schema,packet,provider):
  if schema=='brief_outline' and provider=='codex' and not failed:
   failed.append(True);raise ProviderFailure('codex','TIMEOUT')
 script.hook=hook;c=FixedController(root,text,info,script)
 result=BriefWorkflow(c).run({},{});assert result
 events=c.store.events();assert any(e['kind']=='PROVIDER_FAILOVER' for e in events)
 assert failed

def test_claude_timeouts_are_not_scientific_reviews(tmp_path):
 root,text,info=source_workspace(tmp_path);script=FixedScript()
 def hook(role,schema,packet,provider):
  if provider=='claude':raise ProviderFailure('claude','TIMEOUT')
 script.hook=hook;c=FixedController(root,text,info,script);BriefWorkflow(c).run({},{})
 for p in (root/'reviews').glob('*.json'):
  report=read_json(p)
  for record in report.get('records',[]):assert record['receipt']['provider']=='codex'

@pytest.mark.parametrize('error',[BudgetExhausted('stop'),UnknownExternalState('unknown'),DeadlineReached('expired')])
def test_control_failures_never_trigger_provider_switch(tmp_path,error):
 root,text,info=source_workspace(tmp_path);script=FixedScript()
 def hook(*a):raise error
 script.hook=hook;c=FixedController(root,text,info,script)
 with pytest.raises(type(error)):BriefWorkflow(c).run({},{})
 assert not any(e['kind']=='PROVIDER_FAILOVER' for e in c.store.events())

def test_both_providers_unavailable_preserve_work(tmp_path):
 root,text,info=source_workspace(tmp_path);script=FixedScript()
 def hook(role,schema,packet,provider):raise ProviderFailure(provider,'TIMEOUT')
 script.hook=hook;c=FixedController(root,text,info,script)
 with pytest.raises(ReviewUnavailable):BriefWorkflow(c).run({},{})
 assert c.store.get('model_calls_reserved')==2 and not (root/'brief/accepted.json').exists()

def test_semantic_fail_is_retained_and_not_bypassed(tmp_path):
 root,text,info=source_workspace(tmp_path);script=FixedScript()
 def hook(role,schema,packet,provider):
  if schema=='review':return {'target_digest':packet['target_digest'],'verdict':'FAIL','scope':'source fidelity',
     'findings':[{'severity':'P1','location':'source','issue':'完整定义缺失','required_fix':'补回来源中已有的完整定义'}],
     'evidence':['Synthetic negative review fixture'],'unverified':[]}
 script.hook=hook;c=FixedController(root,text,info,script)
 with pytest.raises(ScientificRejection):BriefWorkflow(c).run({},{})
 assert not (root/'brief/accepted.json').exists()
 assert any(e['kind']=='BRIEF_CHUNK_REPAIR' for e in c.store.events())

def test_pdf_source_page_is_reviewed_with_images(tmp_path):
 import fitz
 pdf=tmp_path/'original.pdf'
 with fitz.open() as d:p=d.new_page();p.insert_text((72,72),'This synthetic source has an image and a text layer.');d.save(pdf)
 root,text,info=source_workspace(tmp_path,pdf=pdf);c=FixedController(root,text,info)
 b=BriefWorkflow(c).run({},{});assert len(b['requirements'])==7
 ledger=read_json(root/'brief/source-ledger.json');assert len(ledger['visual_pages'])==1
 assert all(u['source_status']=='FIXTURE_TRANSCRIPTION_NOT_LIVE_VISION' for u in ledger['units'])
 assert ledger['model_transport']=='FIXTURE_NOT_LLM'

def test_unreadable_page_does_not_invent_denominator(tmp_path):
 import fitz
 pdf=tmp_path/'original.pdf'
 with fitz.open() as d:d.new_page();d.save(pdf)
 root,text,info=source_workspace(tmp_path,pdf=pdf);script=FixedScript()
 def hook(role,schema,packet,provider):
  if schema=='brief_page_text':return {'status':'NEEDS_SOURCE','text':'','unreadable':['分母无法看清'],'notes':[]}
 script.hook=hook;c=FixedController(root,text,info,script)
 with pytest.raises(NeedsSourceInput):BriefWorkflow(c).run({},{})
 assert c.store.get('model_calls_reserved')==1 and not (root/'brief/accepted.json').exists()

def test_explicit_batch_split_covers_both_halves(tmp_path):
 root,text,info=source_workspace(tmp_path);script=FixedScript();once=[]
 def hook(role,schema,packet,provider):
  if schema=='brief_facts' and len(packet['source_units'])>2:
   once.append(True);return {'status':'NEEDS_SPLIT','facts':[],'exclusions':[],'unreadable':[],'reason':'显式容量不足，需要分批'}
 script.hook=hook;c=FixedController(root,text,info,script)
 result=BriefWorkflow(c).run({},{});assert len(result['requirements'])==7 and once

def test_materials_workflow_hook_does_not_skip_following_stages():
 import inspect
 from cumcm_harness.materials_workflow import MaterialsWorkflow
 code=inspect.getsource(MaterialsWorkflow.prepare)
 assert code.index('BriefWorkflow(c).run')<code.index("'data-plan'")<code.index("'portfolio'")<code.index('c.ideas.prepare')
 assert "'legacy'" in code

def test_visual_anchors_use_explicit_space_not_garbled_page_copies():
 raw='[PAGE 1]\ngarbled '*1500
 units=paragraph_units(PROBLEM,{'start':0,'end':len(raw),'quote':raw},'P0001',identity=digest(raw),visual=True)
 b=assemble(outline(units),[source_fact(u) for u in units],units,raw)
 check_complete(b,units,raw)
 assert all(r['anchor_space']=='reviewed_source_unit' for r in b['requirements'])
 assert len(canonical(b))<len(raw)*2
 with pytest.raises(IntegrityError,match='frozen source ledger'):check_brief(b,raw)


def test_adjacent_source_context_can_supply_whole_definition():
 units=problem_units('公式 eta = A / B。\n\n其中 B 为输入量。')
 f=source_fact(units[0]);f.update(source_unit_ids=[u['id'] for u in units],statement='公式 eta = A / B。其中 B 为输入量。',category='formula')
 v={'status':'COMPLETE','facts':[f],'exclusions':[],'unreadable':[],'reason':''}
 check_facts(v,units[:1],['Q1','Q2'],context_units=units[1:])


def test_context_only_facts_do_not_hide_owned_source_omission():
 units=problem_units('需要覆盖的原文。\n\n不能替代正文的上下文。')
 v=batch_response(units[1:])
 with pytest.raises(IntegrityError,match='owner'):check_facts(v,units[:1],['Q1','Q2'],context_units=units[1:])


def test_source_changed_between_extraction_and_snapshot_rejected(tmp_path):
 p=tmp_path/'original.md';p.write_text('已修改的新原文。')
 with pytest.raises(IntegrityError,match='between extraction'):snapshot_problem(tmp_path/'w',p,'旧原文。')


def test_semantic_local_repair_does_not_regenerate_good_chunks(tmp_path):
 root,text,info=source_workspace(tmp_path);script=FixedScript();bad=[]
 def hook(role,schema,packet,provider):
  if schema=='brief_facts' and not bad:
   bad.append(True);v=batch_response(packet['source_units']);v['facts'][0]['statement']='给出结果。';return v
  if schema=='review' and 'facts' in packet['artifact']:
   if any(x['statement']=='给出结果。' for x in packet['artifact']['facts']):
    return {'target_digest':packet['target_digest'],'verdict':'FAIL','scope':'source meaning only','findings':[
     {'severity':'P1','location':'Q1','issue':'小问交付物缺失','required_fix':'完整保留原题的比值和可行方案要求'}],
     'evidence':['Synthetic local negative review'],'unverified':[]}
 script.hook=hook;c=FixedController(root,text,info,script);b=BriefWorkflow(c).run({},{})
 assert b['requirements'][0]['statement']==problem_units()[0]['text']
 chunks=[p for _,s,p,_ in script.calls if s=='brief_facts']
 assert len(chunks)==3 # one failed first chunk, its repair, one untouched good chunk
 repairs=[p for p in chunks if p.get('prior_rejected_chunk')]
 assert len(repairs)==1 and repairs[0]['substantive_objections'][0]['review_objections']
 assert any(e['kind']=='BRIEF_CHUNK_REPAIR' for e in c.store.events())


def test_full_brief_global_patch_is_bounded_and_replayed(tmp_path):
 root,text,info=source_workspace(tmp_path);script=FixedScript();bad=[]
 def hook(role,schema,packet,provider):
  if schema=='review' and 'question' in packet['artifact']:
   target=packet['artifact'];first=next(r for r in target['requirements'] if r['kind']=='deliverable')
   if first['statement'].startswith('第一问'):
    return {'target_digest':packet['target_digest'],'verdict':'FAIL','scope':'synthetic global repair test',
     'findings':[{'severity':'P1','location':first['id'],'issue':'测试要求补充明确指代','required_fix':'保留原交付内容并补充原题指代'}],
     'evidence':['Synthetic rejection, not a factual defect asserted about this problem'],'unverified':[]}
  if schema=='brief_local_patch':
   return patch_for(packet['current_brief'],packet['source_units'])
 script.hook=hook;c=FixedController(root,text,info,script);b=BriefWorkflow(c).run({},{})
 assert b['requirements'][0]['statement'].startswith('按原题要求，')
 assert any(e['kind']=='BRIEF_PATCH_APPLIED' for e in c.store.events())
 c.replay=True;n=c.invocations;assert BriefWorkflow(c).run({},{})==b;assert c.invocations==n
