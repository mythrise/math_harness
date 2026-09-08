#!/usr/bin/env python3
"""Bounded public Exa REST smoke; at most eight HTTP attempts, no LLM calls."""
import argparse
import copy
from pathlib import Path
from cumcm_harness.common import ROOT,Blocked,read_json,write_json,digest
from cumcm_harness.credentials import get_exa_api_key
from cumcm_harness.controller import DEFAULT_CONFIG
from cumcm_harness.intake import create_workspace,verify_inputs
from cumcm_harness.store import Store
from cumcm_harness.exa_policy import load_frozen
from cumcm_harness.exa_defaults import DEFAULT_POLICY
from cumcm_harness.exa_transport import R2ExaClient


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);a=p.parse_args();root=a.workspace.resolve()
    if root.exists():raise Blocked('Use a new live smoke workspace; inspect prior attempts before retry')
    report={'status':'NOT_RUN','authentication_configured':bool(get_exa_api_key()),'max_http_attempts':8,
        'scope':'PUBLIC_METHOD_QUERIES_AND_PRIMARY_READS_ONLY','live_llm':'NOT_RUN','dynamic':'NOT_RUN_DISABLED',
        'deep':'NOT_RUN_DISABLED','calls':[]}
    if not report['authentication_configured']:
        report['reason']='Exa credential absent';write_json(a.report,report);return
    inputs=root.parent/(root.name+'-inputs');inputs.mkdir(parents=True,exist_ok=False)
    (inputs/'public-smoke.txt').write_text('Public API smoke only. No competition problem or user data.')
    problem=root.parent/(root.name+'-problem.md');problem.write_text('Public mathematical method API smoke. No current competition problem.')
    config={**DEFAULT_CONFIG,**read_json(ROOT/'configs/exa-modeling-compatible.json'),'exa_max_requests':8}
    create_workspace(root,problem,inputs,config,exa_policy=DEFAULT_POLICY)
    c=R2ExaClient(Store(root),load_frozen(root),max_attempts=8,cross_cache=root/'literature/live-smoke-cache')
    selected=[]
    def run(label,fn):
        try:
            sources=fn();report['calls'].append({'label':label,'status':'OK' if sources else 'EMPTY',
                'sources':[{'id':s['id'],'snapshot_id':s['snapshot_id'],'url':s['url'],'title':s['title'],
                    'request_id':s['request_id'],'evidence_kind':s['evidence_kind'],'coverage':s['coverage'],
                    'temporal_status':s['temporal_status'],'highlight_characters':len(s['highlight_text']),
                    'generated_output_present':s.get('provider_output') is not None} for s in sources]})
            write_json(a.report,report);return sources
        except Exception as exc:
            report['calls'].append({'label':label,'status':'BLOCKED','error_type':type(exc).__name__,
                                   'reason':str(exc)[:250]});write_json(a.report,report);return []
    selected+=run('foundation_publication',lambda:c.search('single machine scheduling sequence dependent setup linear delay penalties'))
    run('counterexample_publication',lambda:c.search('counterexample scheduling deterioration position dependent processing times',profile='counterexamples',stage='adversary'))
    if selected:
        origin=selected[0]['origin_request'];urls=[s['url'] for s in selected[:4]]
        run('primary_text_up_to_four_urls',lambda:c.contents(urls,origin=origin)[0])
    request=c.compiler.search('multiobjective optimization methodological limitations')
    request['body']['outputSchema']=copy.deepcopy(DEFAULT_POLICY['profiles']['deep_escalation']['request_template']['outputSchema'])
    try:
        result=c.execute(request)
        report['calls'].append({'label':'auto_output_schema_capability','status':result['status'],
            'provider_output_present':result['response'].get('output') is not None,
            'generated_output_is_not_quote_evidence':True})
    except Exception as exc:report['calls'].append({'label':'auto_output_schema_capability','status':'BLOCKED','error_type':type(exc).__name__,'reason':str(exc)[:250]})
    before=c.ledger.summary()['http_attempts_reserved']
    if selected:
        replay=c.search('single machine scheduling sequence dependent setup linear delay penalties')
        report['same_run_replay']={'same_snapshots':[s['snapshot_id'] for s in replay]==[s['snapshot_id'] for s in selected],
                                 'extra_http_attempts':c.ledger.summary()['http_attempts_reserved']-before}
    report['ledger']=c.ledger.summary();report['policy_digest']=c.snapshot['policy_digest'];report['research_cutoff']=c.snapshot['research_cutoff']
    report['status']='LIVE_HTTP_SMOKE_COMPLETED' if all(x['status'] in ('OK','EMPTY') for x in report['calls']) else 'LIVE_HTTP_SMOKE_PARTIAL'
    verify_inputs(root);write_json(a.report,report)
    print(report['status']);print('http_attempts='+str(report['ledger']['http_attempts_reserved']))


if __name__=='__main__':main()
