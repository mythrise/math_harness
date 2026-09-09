"""Supplied deterministic R2 fixture; never reports live Exa or live LLM evidence."""
from pathlib import Path
from .resilience_demo import fixture_responder, replay_exa, run_resilience_demo
from .sandbox import Executor


def r2_transport(endpoint, body, headers, timeout):
    value=replay_exa(endpoint,body)
    if endpoint=='contents':
        value['statuses']=[{'id':s['url'],'status':'success'} for s in value['results']]
    value['requestId']='SYNTHETIC_R2_FIXTURE'
    return value


def r2_responder(role, schema, packet):
    if schema=='research_queries_r2':
        opponent=role=='hypothesis_critic'
        query=fixture_responder(role,'research_queries',packet)['queries'][0]
        ids=[h['id'] for h in packet['hypotheses']]
        profiles=['counterexamples'] if opponent else ['foundations'] if ids else ['foundations','unfiltered_scholarly_fallback']
        return {'queries':[{**query,'profile':profile,'hypothesis_ids':ids,'additional_queries':[]} for profile in profiles]}
    if schema=='source_selection_r2':
        ids=[h['id'] for h in packet['hypotheses']['hypotheses']];seen=set();selections=[]
        for source in packet['sources']:
            if source['url'] in seen:continue
            seen.add(source['url'])
            selections.append({'source_id':source['id'],'hypothesis_ids':ids,'critical':True,'expanded':False,
                'reason':'Read the original limited fixture passage for exact scope evidence.'})
        return {'selections':selections,'counter_dispositions':[{'source_id':source['id'],'disposition':'READ' if source['id'] in {s['source_id'] for s in selections} else 'EXCLUDE','reason':'Same work already selected; independently check duplicate evidence.'} for source in packet['sources'] if source.get('purpose') in ('counterexample','limitations')]}
    if schema=='hypothesis_audit_r2':
        result=fixture_responder(role,'hypothesis_audit',packet);known={s['id']:s for s in packet['sources']}
        for check in result['checks']:
            for ref in check['evidence']:
                source=known[ref['source_id']]
                ref.update(snapshot_id=source['snapshot_id'],quote_start=0,quote_end=len(ref['quote']))
        return result
    return fixture_responder(role,schema,packet)


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('workspace',type=Path)
    p.add_argument('--image',default='cumcm-egoharness:0.5.0-rc2');a=p.parse_args()
    result=run_resilience_demo(a.workspace,r2=True,executor=Executor(image=a.image))
    print(json.dumps(result,ensure_ascii=False,indent=2))
