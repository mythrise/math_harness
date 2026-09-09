"""Fixed synthetic pipeline validation, NEVER live-model capability evidence.
Default uses existing Docker executors. --local-fixture-components is an explicit
component-test-only mode for this exact prewritten fixture; not an alternative to
production isolation. No arbitrary input, solver or draft can be supplied here.
"""
from __future__ import annotations
import argparse,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cumcm_harness.common import *
from cumcm_harness.controller import Controller,DEFAULT_CONFIG
from cumcm_harness.providers import FixtureProvider
from cumcm_harness.sandbox import Executor
from cumcm_harness.intake import create_workspace
from cumcm_harness.resilience_demo import fixture_responder,replay_exa,OutageProvider
from cumcm_harness.literature import ExaClient
from cumcm_harness.materials_contracts import STEPS
from cumcm_harness.demo import PLAN

PROBLEM=('合成双目标工件选择与排序工程测试，不是官方国赛题。'
 '第一问：求取收益与时长的折中前沿。第二问：根据固定效用尺度给出可行推荐序列。'
 '约束：工件不可重复，必须选择非空子集，采用相同的函数评价预算。'
 '数据由测试程序明确生成，只能用于算法和管线诊断，不能作为真实生产观测。')


def bind_fixture_plan(plan,preparation):
    from cumcm_harness.baseline_binding import independent_baselines,baseline_summary
    old=independent_baselines(preparation['portfolio'])
    binding={**old,'questions':[{'question_id':q['question_id'],'independent_id':q['independent_id'],'independent_digest':q['independent_digest'],
        'disposition':'KEEP','selected_method_card_id':q['method_card_id'],'selected_description':q['description'],
        'applicability_reason':'固定合成测试保留独立提出的同预算基准并遵守原解码约束。',
        'comparison_strength':'固定合成测试使用相同目标评价预算和同一独立重算评测器。'} for q in old['questions']]}
    plan['baseline_binding']=binding;plan['baseline']=baseline_summary(binding)
    return plan

def fixture(role,schema,packet):
    if schema=='problem_brief':
        req=[]
        for n,text in enumerate(['第一问：求取收益与时长的折中前沿。','第二问：根据固定效用尺度给出可行推荐序列。','约束：工件不可重复，必须选择非空子集，采用相同的函数评价预算。']):
            a=PROBLEM.index(text);req.append({'id':f'R{n+1}','kind':'deliverable' if n<2 else 'constraint',
                'statement':text,'anchor':{'start':a,'end':a+len(text),'quote':text},'question_ids':[f'q{n+1}'] if n<2 else ['q1','q2']})
        q=[]
        for i,title in enumerate(['收益与时长折中前沿','固定效用推荐序列']):q.append({'id':f'q{i+1}','title':title,'direct_goal':title,
            'inferred_goal':'核验计算与结论一致','inputs':['problem.json','jobs.csv'],'outputs':['Pareto前沿' if i==0 else '推荐序列'],
            'constraint_ids':['R3'],'depends_on':[] if i==0 else ['q1'],'answer_type':'quantitative','family':'optimization'})
        return {'problem_sha256':digest(PROBLEM),'questions':q,'requirements':req,'ambiguities':[],
            'unit_risks':['时间单位与收益单位分别核验。'],'completion_criteria':['每问都具有独立重算结果；所有测试是合成实例。']}
    if schema=='data_plan':
        return {'sampling_unit':'同一合成实例上的算法随机种子，非独立任务','split':'not_applicable','group_key':'NOT_APPLICABLE','time_key':'NOT_APPLICABLE',
            'sources':[{'file':f['file'],'origin':'synthetic_scenario','purpose':'diagnostic_only','source_id':'FIXTURE_GENERATOR'} for f in packet['data_audit']['files']],
            'transforms':[],'required_data':[],'optional_data':['未来真实场景数据须另开协议验证。'],
            'leakage_checks':['精确枚举仅供独立评价器，搜索器不读取参考解。'],'quality_checks':['CSV完成实际扫描；JSON另由独立求解和评价器解析。']}
    if schema=='model_portfolio':
        return {'questions':[{'question_id':q['id'],'options':[{'id':'base','kind':'baseline','method_card_id':'mosaic-multiobjective',
            'principle':'同预算均匀随机搜索作为基准。','fit_reason':'相同的确定性双目标有序子集输入与解码合同。','limitations':'只支持当前合成实例的比较。',
            'validation':'独立枚举并重算付费目标。','single_change':'基准不使用代理预筛选。','implementation_status':'AVAILABLE_LOCAL'},
            {'id':'candidate','kind':'challenger','method_card_id':'mosaic-multiobjective','principle':'调用原始MOSAIC v14。','fit_reason':'受支持的codec与确定性目标。',
             'limitations':'不声称全局最优和跨任务优势。','validation':'同预算比较与原算法单因素消融。','single_change':'使用已有fast_h0策略。','implementation_status':'AVAILABLE_LOCAL'}],
            'recommendation':'candidate','decision_basis':'先跑基准，开发后选择，确认失败保留基准。'} for q in packet['brief']['questions']],
            'shared_computation':['独立参考域由评价器构造。'],'rejected_innovations':['不把教程新算法名当已安装实现。'],'stopping_rule':'固定预算与候选数。'}
    if schema=='abstract_revision':
        return {'abstract':'针对合成工件选择与排序问题，建立收益与时长的双目标模型，并按固定效用尺度给出推荐序列。基准与候选使用相同评价预算，所有报告目标均由独立程序重新计算；有限域枚举只向评价器开放。代表运行的归一化超体积为{{claim:result_hv}}，推荐序列收益为{{claim:result_reward}}，持续时间为{{claim:result_duration}}。结果只反映当前合成实例，不证明真实生产效果或跨题目优势。',
            'keywords':['双目标优化','独立核验','可复现性'],'claim_ids':['result_hv','result_reward','result_duration'],
            'remaining_limitations':['角色及文献检索响应是预编写夹具，真实模型能力未验证。']}
    if schema=='paper_map':
        d=packet['draft'];plan=packet['plan'];sections=d['sections']
        model=next(i for i,s in enumerate(sections) if '数学模型' in s['heading'])
        execution=next(i for i,s in enumerate(sections) if '控制试验' in s['heading'])
        result=next(i for i,s in enumerate(sections) if s['heading']=='结果与适用范围')
        return {'draft_digest':packet['draft_digest'],'questions':[{'question_id':q['id'],
            'bindings':[{'step':step,'section_indices':[0 if step=='analysis' else model if step in ('assumptions','symbols','derivation') else execution if step in ('algorithm','execution','validation') else result],
              'state':'PRESENT','reason':'固定测试文稿的位置映射；此结构检查不是实际模型语义审查。'} for step in STEPS],
            'claim_ids':['result_hv'] if q['id']=='q1' else ['result_reward','result_duration'],'qualitative_evidence_ids':[]} for q in plan['questions']],
            'symbols':plan['variables'],'abstract_claim_ids':['result_hv','result_reward','result_duration'],'limitations':['仅固定合成测试，不建立获奖结论。']}
    value=fixture_responder(role,schema,packet)
    if role=='modeler' and schema=='plan':
        value['variables'][0]['symbol']=r'\pi'
        if packet.get('materials_preparation'):bind_fixture_plan(value,packet['materials_preparation'])
    if role=='coder' and schema=='bundle' and packet.get('plan',{}).get('baseline_binding'):
        value['baseline_implementation']={'binding_digest':digest(packet['plan']['baseline_binding']),'variant':'baseline','source_paths':['main.py'],'implementation_summary':'合成夹具的 main.py baseline 分支执行同预算均匀随机搜索并独立重算。'}
    if role=='writer' and schema=='paper':
        last=next(s for s in value['sections'] if s['heading']=='结果与适用范围')
        last['text']='代表运行的归一化超体积为{{claim:result_hv}}。'+last['text']
        last['claim_ids'].append('result_hv')
        value['figure_caption']='根据本题逐问目标和依赖合同构建的建模与证据流程；不是软件代理架构图。'
    return value


def local_fixed_fixture_compiler(folder,main='main.tex'):
    """Only invoked by this explicit fixed-fixture test, never by production run."""
    from cumcm_harness.paper_profile import prepare_style,profile_digest,PROFILE
    from cumcm_harness.process import run_process,clean_env
    prepare_style(folder)
    for i in range(2):
        env=clean_env();env.update({'openin_any':'p','openout_any':'p'})
        r=run_process(['xelatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error',main],
            cwd=folder,out=folder/f'local_fixture_logs/{Path(main).stem}-{i}',env=env,timeout=180)
        if r['status']!='EXITED' or r['returncode']:raise PaperCompilationFailure('Fixed fixture TeX failed; see local_fixture_logs')
    text=(folder/Path(main).with_suffix('.log')).read_text(errors='replace')
    bad=[x for x in ('Missing character:','undefined references','undefined citations',r'Overfull \hbox',r'Overfull \vbox') if x in text]
    if bad:raise PaperCompilationFailure('Fixed fixture TeX quality defects: '+str(bad))
    return {'source_sha256':file_hash(folder/main),'pdf_sha256':file_hash(folder/Path(main).with_suffix('.pdf')),
        'passes':2,'engine':'XeLaTeX','paperkit_profile':PROFILE,'paperkit_profile_digest':profile_digest(),
        'sandbox':{'backend':'TRUSTED_LOCAL_FIXED_FIXTURE_ONLY','production_isolation_tested':False},
        'shell_escape':False,'overfull_boxes':0,'compiler_version':text.splitlines()[0]}


def replay_identity(root):
    """Count durable reservations and hash the three sealed deliverables."""
    from cumcm_harness.store import Store
    store=Store(root)
    with store.connect() as connection:
        jobs=[dict(row) for row in connection.execute('SELECT id,status FROM jobs ORDER BY id')]
    from cumcm_harness.exa_ledger import ExaLedger
    from cumcm_harness.exa_policy import load_frozen
    return {'model_calls_reserved':store.get('model_calls_reserved',0),'jobs':jobs,
            'files':{name:file_hash(root/'deliverables'/name) for name in
                     ('paper.pdf','support.zip','submission-manifest.json')},
            'exa':ExaLedger(store,load_frozen(root)['policy']).summary() if (root/'exa-policy.json').exists() else None}


def run(out,local=False,replay=False,*,r2=False,image=DEFAULT_CONFIG['docker_image']):
    out=Path(out).resolve()
    if replay and not (out/'control.sqlite3').is_file():
        raise Blocked('Replay requires an existing completed validation workspace')
    if not (out/'control.sqlite3').exists():
        if out.exists() and any(out.iterdir()):raise Blocked('Use a new validation workspace')
        source=out.parent/(out.name+'-fixture-inputs');source.mkdir(parents=True,exist_ok=False)
        n=6;spec={'id':'synthetic_job6','kind':'job','values':[15.,9.,12.,7.,11.,6.],
            'process':[4.,3.,5.,2.,4.,1.],'dues':[14.,9.,18.,6.,16.,5.],'penalty':[1.1,.8,1.2,1.,.9,.5],
            'setup':[[0. if i==j else float(1+(3*i+2*j)%5) for j in range(n)] for i in range(n+1)]}
        write_json(source/'problem.json',spec)
        atomic_write(source/'jobs.csv','job,value,process,due,penalty\n'+'\n'.join(','.join(map(str,[i,*[spec[k][i] for k in ('values','process','dues','penalty')]])) for i in range(n))+'\n')
        problem=out.parent/(out.name+'-problem.md')
        if problem.exists():raise Blocked('Existing fixture problem is preserved; choose a new workspace name')
        atomic_write(problem,PROBLEM)
        config={**DEFAULT_CONFIG,'materials_workflow':True,'network_policy':'EXA_ABSTRACT_QUERIES','literature_enabled':True,
            'max_candidates':1,'fe_budget':192,'review_backoff_seconds':0,'review_cooldown_seconds':3600,
            'allow_research_algorithms':True,'docker_image':image}
        from cumcm_harness.exa_defaults import DEFAULT_POLICY
        if r2:config.update(exa_max_requests=80,exa_results_per_query=6,exa_timeout=45)
        create_workspace(out,problem,source,config,exa_policy=DEFAULT_POLICY if r2 else None)
    config=read_json(out/'config.json')
    if not config['materials_workflow'] or (out/'exa-policy.json').exists()!=r2:
        raise IntegrityError('Requested materials/R2 mode differs from the frozen workspace')
    before=replay_identity(out) if replay else None
    def no_calls(*a,**k):raise AssertionError('Replay attempted new external/fixture work')
    def responder(role,schema,packet):
        if r2 and schema.endswith('_r2'):
            from cumcm_harness.exa_r2_demo import r2_responder
            return r2_responder(role,schema,packet)
        return fixture(role,schema,packet)
    provider=FixtureProvider(no_calls if replay else responder)
    executor=Executor('trusted-local' if local else 'docker',image=image)
    if replay:executor.execute=no_calls
    if r2:
        from cumcm_harness.exa_transport import R2ExaClient
        from cumcm_harness.exa_r2_demo import r2_transport
        from cumcm_harness.exa_policy import load_frozen
        from cumcm_harness.store import Store
        client=R2ExaClient(Store(out),load_frozen(out),transport=no_calls if replay else r2_transport)
    else:client=ExaClient(out/'literature/exa-cache',transport=no_calls if replay else replay_exa)
    c=Controller(out,fixture_provider=provider,executor=executor,exa_client=client)
    c.providers['claude']=OutageProvider()
    if replay:c.providers['claude'].invoke=no_calls
    import cumcm_harness.paper as paper
    original=paper.compile_tex
    if local:paper.compile_tex=local_fixed_fixture_compiler
    if replay:paper.compile_tex=no_calls
    try:result=c.run()
    finally:paper.compile_tex=original
    after=replay_identity(out)
    if replay and (after!=before or provider.count):raise IntegrityError('Replay changed reservations, jobs or sealed deliverables')
    result['validation_scope']={'model_responses':'FIXTURE_NOT_LLM','exa':'REPLAYED_NOT_LIVE_HTTP',
        'frozen_r2_sidecar':r2,'replay_identity':after,'replay_unchanged':before==after if replay else None,
        'numeric_execution':'TRUSTED_LOCAL_FIXED_FIXTURE' if local else 'DOCKER',
        'tex_execution':'TRUSTED_LOCAL_FIXED_FIXTURE' if local else 'DOCKER',
        'new_model_fixture_calls':provider.count,'replay':replay,'live_semantic_skill_quality':'NOT_RUN'}
    write_json(out/('materials-replay.json' if replay else 'materials-validation.json'),result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--local-fixture-components',action='store_true');p.add_argument('--replay',action='store_true')
    p.add_argument('--r2',action='store_true',help='Use the actual frozen R2 sidecar and injected HTTP transport')
    p.add_argument('--image',default=DEFAULT_CONFIG['docker_image'])
    a=p.parse_args();r=run(a.out,a.local_fixture_components,a.replay,r2=a.r2,image=a.image);print(json.dumps(r,ensure_ascii=False,indent=2))
