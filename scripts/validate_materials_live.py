"""Bounded real-provider acceptance on public synthetic or explicitly selected inputs.

Defaults to a fixed public integer program; optional problem/data/idea paths create
a new native entry workspace. Uses actual Codex/Claude CLI and frozen Exa R2,
with all generated code and TeX
executed by the existing Docker boundaries. It never signs or submits a paper.
An explicitly selected existing Exa credential is read by the original secure
loader; its value is never copied to configuration, prompts, containers or reports.
"""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cumcm_harness.common import Blocked,write_json,read_json,digest,file_hash

PROBLEM='''Public synthetic integer-programming acceptance test, not a competition problem or real production data.
Question Q1: Minimize 3*x + 5*y subject to 2*x + y >= 6 and x + 2*y >= 6. Variables x and y are integers in [0,6]. Report a feasible minimizing pair and its total cost.
Question Q2: Change only the first requirement to 2*x + y >= 7. Keep every other constraint and cost unchanged. Report a feasible minimizing pair, its total cost and the cost change from Q1.
Data are exact synthetic scenario parameters in coefficients.csv. Quantity is dimensionless; cost uses cost_units. Exhaustive enumeration of the finite domain is an admissible independently checkable baseline. No missing observations may be invented and no generalization to real production is requested.
Both questions require independently recomputed quantitative evidence. Use the Q1 optimal cost as the primary metric, minimized; Q2 has its own measured cost and cost-change evidence. Report all equivalent optimal pairs or state a deterministic tie rule. Retain the baseline when a candidate does not improve it. Variants must preserve the requested questions and answer validity: test an implementation feature and numerical solver tolerance, not a different scientific objective. Each run has at most 192 objective evaluations across both questions; verifier enumeration is separately reported.
Write a concise Chinese validation paper from executed results only. No minimum page count, fabricated empirical assumptions or award claims. This fixed public test validates software and provider integration, not contest-solving quality.
'''
CSV='parameter,value,unit\ncost_x,3,cost_units\ncost_y,5,cost_units\nq1_requirement_1,6,dimensionless\nq2_requirement_1,7,dimensionless\nrequirement_2,6,dimensionless\nupper_x,6,dimensionless\nupper_y,6,dimensionless\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--exa-credential-file',type=Path)
    parser.add_argument('--exa-shared-ledger',type=Path)
    parser.add_argument('--problem',type=Path)
    parser.add_argument('--data',type=Path)
    parser.add_argument('--prior-idea',action='append',type=Path,default=[])
    parser.add_argument('--external-ai-records',type=Path)
    parser.add_argument('--max-model-calls',type=int,default=100)
    parser.add_argument('--max-http-attempts',type=int,default=32)
    args=parser.parse_args();root=args.workspace.resolve()
    if not 1<=args.max_model_calls<=100 or not 1<=args.max_http_attempts<=32:parser.error('Existing authorization permits at most 100 model calls and 32 HTTP attempts')
    if bool(args.problem)!=bool(args.data):parser.error('--problem and --data must be supplied together')
    if args.prior_idea and not args.problem:parser.error('--prior-idea requires an explicit problem and data')
    if root.exists():raise Blocked('Use a new live validation workspace; reconcile prior work before any retry')
    if args.report.exists():raise Blocked('An existing validation report is immutable')
    if args.exa_credential_file:
        from cumcm_harness import credentials
        credentials.EXA_KEY_FILE=args.exa_credential_file.resolve()
    from cumcm_harness.cli import doctor
    from cumcm_harness.controller import Controller,DEFAULT_CONFIG
    from cumcm_harness.intake import create_workspace,verify_inputs
    from cumcm_harness.exa_defaults import DEFAULT_POLICY
    from cumcm_harness.exa_policy import load_frozen
    from cumcm_harness.exa_transport import R2ExaClient
    from cumcm_harness.store import Store
    profile=read_json(ROOT/'configs/exa-modeling-compatible.json')
    policy=read_json(ROOT/'configs/exa-policy-r2.json')
    config={**DEFAULT_CONFIG,**profile,'materials_workflow':True,'literature_enabled':True,
        'network_policy':'EXA_ABSTRACT_QUERIES','max_candidates':1,'repair_attempts':1,
        'fe_budget':192,'max_model_calls':args.max_model_calls,'model_timeout':300,'review_timeout':180,
        'exa_max_requests':args.max_http_attempts,'exa_results_per_query':4,'exa_timeout':45,
        'review_attempts_per_provider':1}
    report={'status':'NOT_RUN','scope':'REAL_SERVICES_AND_DOCKER_ON_FIXED_PUBLIC_SYNTHETIC_INPUT',
        'real_historical_contest_problem':'NOT_RUN','human_approval':'NOT_SIGNED','auto_submission':False,
        'model_call_limit':args.max_model_calls,'exa_http_attempt_limit':args.max_http_attempts,'configuration_profile_sha256':digest(profile),'exa_policy_source_sha256':digest(policy),'problem_digest':digest(PROBLEM)}
    report['doctor']=doctor(True,config);write_json(args.report,report)
    if not report['doctor']['ready_for_live']:
        report.update(status='BLOCKED',reason='Required live infrastructure is unavailable')
        write_json(args.report,report);return 2
    if args.problem:
        from cumcm_harness.entry_inputs import initialize
        problem=args.problem.resolve();inputs=args.data.resolve()
        report.update(scope='REAL_SERVICES_AND_DOCKER_ON_OPERATOR_SELECTED_INPUT',
            real_historical_contest_problem='ATTEMPTED_NOT_YET_COMPLETED',
            problem_digest=file_hash(problem),input_mode='idea' if args.prior_idea else 'scratch',
            genuine_web_draft='NOT_ATTESTED_BY_THIS_VALIDATOR')
        write_json(args.report,report)
        initialize(root,input_mode=report['input_mode'],problem=problem,data=inputs,
            ideas=args.prior_idea,metadata=args.external_ai_records,config=config,exa_policy=policy)
    else:
        inputs=root.parent/(root.name+'-inputs');inputs.mkdir(parents=True,exist_ok=False)
        (inputs/'coefficients.csv').write_text(CSV)
        problem=root.parent/(root.name+'-problem.md')
        with problem.open('x',encoding='utf-8') as handle:handle.write(PROBLEM)
        create_workspace(root,problem,inputs,config,exa_policy=policy)
    store=Store(root)
    client=R2ExaClient(store,load_frozen(root),max_attempts=config['exa_max_requests'],
        shared_path=args.exa_shared_ledger,cross_cache=root/'literature/live-validation-cache')
    controller=Controller(root,exa_client=client)
    try:
        result=controller.run()
        report.update(status=result['status'],result=result)
    except Exception as error:
        report.update(status='BLOCKED',error_type=type(error).__name__,reason=str(error)[:2000])
    finally:
        verify_inputs(root)
        records=controller.all_ai_records()
        report['actual_receipts']=dict(Counter((r.get('provider','UNKNOWN')+':'+r.get('transport','UNKNOWN')) for r in records))
        report['calls_reserved']=store.get('model_calls_reserved',0)
        live=[r for r in records if r.get('transport')=='LIVE_CLI']
        known=[r['cost_usd'] for r in live if type(r.get('cost_usd')) in (int,float)]
        report['model_cost']={'known_cost_usd':sum(known),'calls_with_known_cost':len(known),'reserved_calls_without_known_cost':report['calls_reserved']-len(known),'total_cost_usd':sum(known) if len(known)==report['calls_reserved'] else None}
        report['model_usage']={k:sum(r.get('usage',{}).get(k,0) or 0 for r in live) for k in ('input_tokens','cached_input_tokens','output_tokens')}
        report['coverage_ledger']='ideas/accepted.json' if (root/'ideas/accepted.json').exists() else 'NOT_REACHED'
        report['idea_plan_alignment']='ideas/plan_alignment.json' if (root/'ideas/plan_alignment.json').exists() else 'NOT_REACHED'
        report['receipt_digests']=[digest(r) for r in records]
        report['skill_digests']=sorted({r['skill_digest'] for r in records if 'skill_digest' in r})
        report['exa']=client.ledger.summary()
        with store.connect() as connection:
            report['job_statuses']=dict(Counter(r[0] for r in connection.execute('SELECT status FROM jobs')))
            report['unfinished_steps']=[dict(r) for r in connection.execute("SELECT key,status FROM steps WHERE status!='DONE'")]
        report['state']=store.get('status')
        report['audit']=store.audit()
        write_json(args.report,report)
    print(report['status'], 'calls='+str(report['calls_reserved']), 'http='+str(report['exa']['http_attempts_reserved']))
    return 2 if report['status']=='BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
