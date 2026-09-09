"""Source-lane integration boundaries; no live services or untrusted code."""
from pathlib import Path
import inspect
from types import SimpleNamespace
import pytest
from cumcm_harness.common import *
from cumcm_harness.brief_tools import audit_brief,main as audit_main
from cumcm_harness.brief_workflow import BriefWorkflow
from cumcm_harness.materials_workflow import MaterialsWorkflow
from cumcm_harness.brief_contracts import *
from test_brief_rc3 import (FixedController,FixedScript,source_workspace,PROBLEM,
                           sample_brief,legacy_brief,problem_units)


def test_offline_report_keeps_missing_original_refs(tmp_path):
 b=legacy_brief();b['requirements'][0]['statement']='分母见 G37，距离单位见 G39。'
 report=audit_brief(PROBLEM,b)
 assert report['status']=='FAIL' and report['input_modified'] is False
 missing=[f['detail'] for c in report['checks'] if c['status']=='FAIL' for f in c['findings']]
 assert 'G37' in missing and 'G39' in missing


def test_offline_cli_does_not_overwrite_inputs(tmp_path):
 p=tmp_path/'problem.md';p.write_text(PROBLEM);b,_=sample_brief();q=tmp_path/'brief.json';write_json(q,b)
 before={x.name:file_hash(x) for x in (p,q)};out=tmp_path/'diagnostic.json'
 assert audit_main(['--problem',str(p),'--brief',str(q),'--out',str(out)])==0
 assert before=={x.name:file_hash(x) for x in (p,q)}
 with pytest.raises(SystemExit):audit_main(['--problem',str(p),'--brief',str(q),'--out',str(out)])


class PreparationController(FixedController):
 def reviews(self,key,target,*,roles,stage,context,images=()):
  from cumcm_harness.review_stages import SOURCE_REVIEW_STAGES
  assert stage in ('problem_brief','data_policy','model_portfolio',*SOURCE_REVIEW_STAGES)
  return self.review_board.review(key,{'artifact':target,'target_digest':digest(target),'context':context,'review_stage':stage},roles,images=images)
 def call(self,key,role,schema,packet,*,images=()):
  return self.review_board.invoke(key,role,schema,packet,primary='codex',images=images)


def test_native_materials_preparation_reuses_source_and_enters_idea(tmp_path):
 root,text,info=source_workspace(tmp_path);data=root/'inputs/development';data.mkdir(parents=True)
 (data/'original.csv').write_text('id,value\na,1\nb,2\n')
 script=FixedScript();order=[]
 def hook(role,schema,packet,provider):
  if schema=='data_plan':
   order.append('data')
   return {'sampling_unit':'合成固定测试样本','split':'not_applicable','group_key':'NOT_APPLICABLE','time_key':'NOT_APPLICABLE',
    'sources':[{'file':x['file'],'origin':'provided','purpose':'observed_evidence','source_id':'NOT_APPLICABLE'} for x in packet['data_audit']['files']],
    'transforms':[],'required_data':[],'optional_data':[],'leakage_checks':['未读取确认参考'],'quality_checks':['保留原始字节']}
  if schema=='model_portfolio':
   order.append('portfolio')
   return {'questions':[{'question_id':q['id'],'options':[{'id':'baseline_'+q['id'],'kind':'baseline','method_card_id':'test_method',
      'principle':'固定测试方法，不声称已求解','fit_reason':'仅用于验证交接','limitations':'不代表实际算法适配性','validation':'未来独立数值检验',
      'single_change':'无','implementation_status':'AVAILABLE_LOCAL'}],'recommendation':'baseline_'+q['id'],'decision_basis':'固定测试回复'} for q in packet['brief']['questions']],
      'shared_computation':[],'rejected_innovations':[],'stopping_rule':'不在准备阶段运行求解'}
 script.hook=hook;c=PreparationController(root,text,info,script)
 c.config['brief_pipeline']='source-ledger-v1';c.base['methods']=[{'id':'test_method'}]
 class IdeaEntry:
  def prepare(self,preparation):
   order.append('idea')
   assert preparation['brief']['requirements'] and preparation['baseline_contract']
   return {'entry_digest':'1'*64,'items':[]}
 c.ideas=IdeaEntry()
 from cumcm_harness.materials_data import audit_development
 audit=c.store.step('materials:data-audit',{'manifest':tree_manifest(data)},lambda:audit_development(data))
 early=BriefWorkflow(c).run({},audit);count=c.invocations
 result=MaterialsWorkflow(c).prepare({})
 assert result['brief']==early and order==['data','portfolio','idea']
 assert c.invocations-count==8 # data: author+2 review; portfolio: author+4 review
 assert result['external_idea_contract']['full_pipeline_required'] is True
 assert c.base['baseline_binding_contract']
 assert tree_manifest(data)==audit['manifest']


def test_no_exa_or_solver_dependency_in_source_lane():
 source=inspect.getsource(BriefWorkflow)
 for word in ('mosaic_solve(', 'runner.matrix(', 'client.search(', 'httpx.', 'requests.'):
  assert word not in source
 assert 'self.c.review_board.invoke' in source
 assert "except self._stop_types():raise" in source


def test_real_terminated_timeout_receipt(tmp_path):
 """Actual local test process, not a Codex/Claude service or solver."""
 import sys
 from cumcm_harness.process import run_process,clean_env
 receipt=run_process([sys.executable,'-c','import time; time.sleep(2)'],cwd=tmp_path,
  out=tmp_path/'logs',env=clean_env(),timeout=.15)
 assert receipt['status']=='TIMEOUT' and receipt['returncode']<0
 assert (tmp_path/'logs/process_receipt.json').is_file()


@pytest.mark.parametrize('target', ['paper','solver','evaluation'])
def test_brief_does_not_publish_downstream_success(tmp_path,target):
 root,text,info=source_workspace(tmp_path);c=FixedController(root,text,info)
 BriefWorkflow(c).run({},{})
 assert not (root/target).exists()
 assert read_json(root/'brief/accepted.json')['scientific_experiments_run_by_brief']==0


def test_unknown_external_call_keeps_running_and_is_not_reissued(tmp_path):
 from cumcm_harness.review_board import ReviewUnavailable
 root,text,info=source_workspace(tmp_path);script=FixedScript()
 def hook(*args):raise UnknownExternalState('Synthetic unknown remote effect')
 script.hook=hook;c=FixedController(root,text,info,script)
 with pytest.raises(UnknownExternalState):BriefWorkflow(c).run({},{})
 count=c.invocations
 with c.store.connect() as db:assert db.execute("SELECT count(*) FROM steps WHERE status='RUNNING'").fetchone()[0]>0
 c.review_cycle+=1
 with pytest.raises(UnknownExternalState):BriefWorkflow(c).run({},{})
 assert c.invocations==count


def isolated_intake_config(monkeypatch):
 """Isolate the config dependency; this is NOT a full Controller/CLI test.

 The controller config/early-stage changes have their own hash-bound transform
 tests. Here we exercise source snapshots and frozen intake integrity only.
 """
 import sys,types
 module=types.ModuleType('cumcm_harness.controller')
 module.DEFAULT_CONFIG={'mode':'practice','brief_pipeline':'legacy',
    'literature_enabled':False,'network_policy':'LOCAL_EVIDENCE_ONLY'}
 def validate_config(config):
  if set(config)!=set(module.DEFAULT_CONFIG):raise IntegrityError('Test config keys')
  if config['brief_pipeline'] not in ('legacy','source-ledger-v1'):raise IntegrityError('Test source lane')
  return config
 module.validate_config=validate_config
 monkeypatch.setitem(sys.modules,'cumcm_harness.controller',module)
 return module


@pytest.mark.parametrize('source_lane',[False,True])
def test_intake_and_immutable_source_tree(tmp_path,monkeypatch,source_lane):
 """Exercise actual patched intake; config registry seeded for component checkout."""
 from copy import deepcopy
 controller=isolated_intake_config(monkeypatch)
 from cumcm_harness.intake import create_workspace,verify_inputs
 cfg=deepcopy(controller.DEFAULT_CONFIG);cfg['brief_pipeline']='source-ledger-v1' if source_lane else 'legacy'
 problem=tmp_path/'p.md';problem.write_text(PROBLEM);data=tmp_path/'data';data.mkdir();(data/'a.csv').write_text('x,y\n1,2\n')
 root=tmp_path/'workspace';info=create_workspace(root,problem,data,cfg)
 again,_=verify_inputs(root);assert again==info
 assert ('problem_source_manifest' in info)==source_lane
 if source_lane:
  before=file_hash(root/'problem.md');(root/'problem_source/original.md').write_text('altered frozen original')
  with pytest.raises(IntegrityError):verify_inputs(root)
  assert file_hash(root/'problem.md')==before


def test_pdf_intake_preserves_frozen_images(tmp_path,monkeypatch):
 from copy import deepcopy
 import fitz
 controller=isolated_intake_config(monkeypatch)
 from cumcm_harness.intake import create_workspace,verify_inputs
 cfg=deepcopy(controller.DEFAULT_CONFIG);cfg['brief_pipeline']='source-ledger-v1'
 p=tmp_path/'p.pdf'
 with fitz.open() as d:page=d.new_page();page.insert_text((72,72),'A complete source expression: eta = A/B.');d.save(p)
 data=tmp_path/'data';data.mkdir();(data/'a.json').write_text('{}')
 root=tmp_path/'workspace';info=create_workspace(root,p,data,cfg);verify_inputs(root)
 assert 'page-0001.png' in info['problem_source_manifest']
 (root/'problem_source/page-0001.png').write_bytes(b'changed')
 with pytest.raises(IntegrityError):verify_inputs(root)


def test_current_upstream_optional_timeout_is_preserved(tmp_path):
 """Actual local process with no deadline; not a live Claude invocation."""
 import sys
 from cumcm_harness.process import run_process,clean_env
 receipt=run_process([sys.executable,'-c','print("completed")'],cwd=tmp_path,
  out=tmp_path/'no-deadline',env=clean_env(),timeout=None)
 assert receipt['status']=='EXITED' and receipt['returncode']==0
 assert receipt['timeout_seconds'] is None
 assert (tmp_path/'no-deadline/stdout.log').read_text().strip()=='completed'
