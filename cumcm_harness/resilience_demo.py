"""Fault-injected paper E2E: real numerics/PDF, fixture LLM and Exa transports.

The two brief source excerpts were found using the connected Exa search tool.
Replaying them is NOT a live call to the Exa HTTP API or a live scientific review.
"""
from pathlib import Path
import copy
from .common import ROOT, atomic_write, write_json, read_json
from .controller import Controller, DEFAULT_CONFIG
from .demo import PLAN, responder, verifier_bundle
from .intake import create_workspace
from .providers import FixtureProvider
from .review_board import ProviderFailure
from .literature import ExaClient
from .sandbox import Executor

SOURCES=[
 {'url':'https://pubsonline.informs.org/doi/10.1287/opre.29.1.146',
  'title':'Scheduling Jobs with Linear Delay Penalties and Sequence Dependent Setup Costs',
  'text':'The setup cost for each job is dependent only upon the job that immediately precedes it.'},
 {'url':'https://doi.org/10.1080/0305215X.2021.1876041',
  'title':'Single-machine scheduling problems with job rejection, deterioration effects and past-sequence-dependent setup times',
  'text':'the actual processing time of a job is a function of its position in a sequence'}]

DIAGNOSTICS='''    # Actual analytic checks. They verify the declared synthetic model only,
    # not whether real manufacturing data obey its assumptions.
    small={'values':[10.], 'process':[2.], 'dues':[1.], 'penalty':[3.], 'setup':[[0.],[0.]]}
    assert objective(small,[0])==[-7.,2.]
    small['penalty']=[20.]
    assert objective(small,[0])==[0.,2.]
    cases.append({'name':'hypothesis_H2','passed':True,'detail':'Analytic late-penalty and zero-floor boundary tests; no empirical generalization'})
    order=list(range(len(spec['values'])))
    original=objective(spec,order)
    assert objective(copy.deepcopy(spec),order)==original
    scaled=copy.deepcopy(spec)
    for field in ('process','dues'):scaled[field]=[2*x for x in spec[field]]
    scaled['setup']=[[2*x for x in row] for row in spec['setup']]
    scaled['penalty']=[x/2 for x in spec['penalty']]
    transformed=objective(scaled,order)
    assert abs(transformed[0]-original[0])<1e-9 and transformed[1]==2*original[1]
    cases.append({'name':'hypothesis_H3','passed':True,'detail':'Deterministic repetition and time-unit metamorphic check, not stochastic validity'})
'''


def replay_exa(endpoint, body):
    if endpoint=='search':
        return {'results':copy.deepcopy(SOURCES if 'counterexample' in body['query'] else SOURCES[:1])}
    return {'results':[copy.deepcopy(s) for s in SOURCES if s['url'] in body['urls']]}


def fixture_responder(role, schema, packet):
    if schema=='research_queries':
        opponent=role=='hypothesis_critic'
        return {'queries':[{'query':'counterexample scheduling deterioration position dependent processing times' if opponent else 'single machine scheduling linear delay sequence dependent setup costs',
                            'purpose':'counterexample' if opponent else 'background'}]}
    if schema=='hypotheses':
        return {'hypotheses':[{'id':f'H{i+1}','assumption_index':i,'statement':s,
            'kind':'structural' if i==0 else 'simplification',
            'falsification_test':'Analytic boundary and metamorphic diagnostics on the declared synthetic objective',
            'acceptance_rule':'All declared diagnostics pass; restrict conclusions to the synthetic instance',
            'failure_action':'Revise the model or explicitly exclude unsupported empirical conclusions'} for i,s in enumerate(packet['plan']['assumptions'])]}
    if schema=='hypothesis_audit':
        sources=packet['sources'];support=next(s for s in sources if 'informs.org' in s['url']);counter=next(s for s in sources if 'doi.org' in s['url'])
        checks=[]
        for i,h in enumerate(packet['hypotheses']['hypotheses']):
            s=counter if i==2 else support
            checks.append({'hypothesis_id':h['id'],'judgment':'explicit_simplification',
                'rationale':'Fixture adjudication: assumptions define this synthetic task, not a validated real-world law. Deterioration is a counterexample to generalizing fixed times.',
                'evidence':[{'source_id':s['id'],'quote':s['text'],'relation':'scope_limit'}],
                'requires_execution':i!=0,'required_test':'hypothesis_'+h['id'] if i!=0 else 'not_applicable'})
        return {'decision':'ACCEPT_FOR_TESTING','checks':checks,
                'limitations':['Fixture review only. Exact quotations support literature identity, not empirical truth.'],
                'citation_ids':[support['id'],counter['id']]}
    if role=='verifier_author':
        bundle=verifier_bundle()
        for f in bundle['files']:
            if f['path']=='test_solver.py':
                f['content']=f['content'].replace('    a.out.mkdir(parents=True,exist_ok=True);',DIAGNOSTICS+'    a.out.mkdir(parents=True,exist_ok=True);')
        return bundle
    out=responder(role,schema,packet)
    if role=='writer':
        ids=[s['id'] for s in packet['source_registry'] if s['id'].startswith('exa_')]
        out['sections'].insert(2,{'heading':'文献对抗与假设边界',
            'text':'序列相关准备成本与线性延迟惩罚已有相关建模工作{{cite:'+ids[0]+'}}。但加工时间也可能随加工位置发生劣化{{cite:'+ids[1]+'}}，因此固定加工时间不能不加检验地推广到真实生产。本文将其限定为合成任务的显式简化；独立程序执行线性折损、非负截断、重复确定性和时间单位变换检查。文献存在不等于假设成立。文献片段、规划和审查在本次工程回归中为重放夹具，数值实验与编译实际执行。',
            'equations':[],'claim_ids':[]})
        out['citation_ids']=ids
        out['limitations'].append('Claude 故障为注入测试，GPT 接管使用夹具响应；不能视为真实双模型和当前 Exa 密钥联调完成。')
    return out


class OutageProvider:
    live=False
    model='FAULT_INJECTED_CLAUDE_NOT_LIVE'
    def invoke(self,*args,**kwargs):
        raise ProviderFailure('claude','TIMEOUT')


def run_resilience_demo(root:Path, *, candidates=1, fe_budget=192):
    root=Path(root)
    if not (root/'control.sqlite3').exists():
        src=root.parent/(root.name+'-inputs');src.mkdir(parents=True,exist_ok=True)
        n=6;setup=[[0. if i==j else float(1+(3*i+2*j)%5) for j in range(n)] for i in range(n+1)]
        spec={'id':'synthetic_job6','kind':'job','values':[15.,9.,12.,7.,11.,6.],
              'process':[4.,3.,5.,2.,4.,1.],'dues':[14.,9.,18.,6.,16.,5.],
              'penalty':[1.1,.8,1.2,1.,.9,.5],'setup':setup}
        write_json(src/'problem.json',spec);problem=root.parent/(root.name+'-problem.md')
        atomic_write(problem,'合成双目标工件选择与排序工程测试：非空工件子集的收益与时长折中，不是官方国赛题。')
        cfg={**DEFAULT_CONFIG,'network_policy':'EXA_ABSTRACT_QUERIES','literature_enabled':True,
             'max_candidates':candidates,'fe_budget':fe_budget,'review_backoff_seconds':0,
             'allow_research_algorithms':True,'review_cooldown_seconds':3600}
        create_workspace(root,problem,src,cfg)
    provider=FixtureProvider(fixture_responder)
    c=Controller(root,fixture_provider=provider,executor=Executor('trusted-local'),
                 exa_client=ExaClient(root/'literature/exa-cache',transport=replay_exa))
    c.providers['claude']=OutageProvider()
    result=c.run()
    assert result['literature_status']=='FIXTURE_EXA_TRANSPORT' and result['review_failovers']
    assert (root/'deliverables/paper.pdf').exists() and (root/'deliverables/support.zip').exists()
    result['acceptance_scope']={'llm':'FIXTURE_NOT_LLM','exa':'REPLAYED_SOURCE_FIXTURE_NOT_LIVE_HTTP',
                              'numerics':'ACTUALLY_EXECUTED','pdf':'ACTUALLY_COMPILED',
                              'claude_outage':'INJECTED_NOT_REAL_OUTAGE','user_api_key_validation':'NOT_RUN'}
    write_json(root/'resilience_acceptance.json',result)
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('workspace',type=Path);a=p.parse_args()
    result=run_resilience_demo(a.workspace)
    print(result['status']);print(result['package'])
