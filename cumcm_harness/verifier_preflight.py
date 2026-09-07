"""Bounded, replayable evaluator diagnostics before the evaluator is frozen."""
from pathlib import Path
from .common import Blocked, IntegrityError, digest, read_json, tree_manifest, write_json
from .contracts import validate
from .sandbox import Limits


def validate_tests(report):
    if not isinstance(report,dict):raise Blocked('Evaluator primitive tests report must be an object')
    cases=report.get('cases',[])
    if (not isinstance(cases,list) or len(cases)<3
        or any(not isinstance(c,dict) or not isinstance(c.get('name'),str) or not c['name']
               or c.get('passed') is not True or not isinstance(c.get('detail'),str) or not c['detail'] for c in cases)
        or len({c['name'] for c in cases})!=len(cases) or report.get('all_passed') is not True):
        raise Blocked('Evaluator primitive tests failed or are incomplete')
    return report


def run_preflight(root,store,executor,config,bundle):
    code=store.publish_bundle(bundle)
    base=root/'verifier_preflight'/digest(bundle)
    base.mkdir(parents=True,exist_ok=True)
    lim=Limits(min(config['trial_timeout'],120),config['cpu_threads'],config['memory_mb'])
    args=['--seed','0','--budget',str(config['fe_budget']),'--variant','full']
    data=root/'evaluation_inputs/development'
    reports=[]
    def run(name,entry,answer=None):
        target=base/name
        try:
            receipt=executor.execute(code,entry,data,target/'out',args,lim,answer=answer,logdir=target/'logs')
        except Blocked as exc:
            # Only an observed, terminated program failure is repairable here.
            if not str(exc).startswith('Execution failed:'):raise
            process=target/'logs/process_receipt.json'
            reports.append({'name':name,'passed':False,'error':str(exc),
                            'process':read_json(process) if process.exists() else None,
                            'stderr':(target/'logs/stderr.log').read_text(errors='replace')[-8000:]})
            return False
        reports.append({'name':name,'passed':True,'receipt':receipt})
        return True
    passed=False
    try:
        if not (code/'test_evaluator.py').is_file():
            raise Blocked('Verifier must supply standalone test_evaluator.py for pre-freeze primitive tests')
        if not run('primitives','test_evaluator.py'):raise Blocked('Primitive test process failed')
        report=read_json(base/'primitives/out/tests.json')
        reports[-1]['tests']=report
        validate_tests(report)
        for name,content in [('missing',None),('malformed','{ definitely not JSON'),
                             ('fabricated','{"score": 1e100, "valid": true, "fabricated": true}')]:
            answer=base/name/'answer';answer.mkdir(parents=True,exist_ok=True)
            if content is not None:(answer/'answer.json').write_text(content)
            if not run(name,'evaluate.py',answer):raise Blocked('Malformed-answer process failed: '+name)
            evaluation=validate('evaluation',read_json(base/name/'out/evaluation.json'))
            reports[-1]['evaluation']=evaluation
            if evaluation['valid'] is not False:raise Blocked('Evaluator accepted invalid answer: '+name)
            if not any(c['passed'] is False for c in evaluation['checks']):
                raise Blocked('Rejected answer lacks a failing check: '+name)
        passed=True
    except (Blocked,IntegrityError,FileNotFoundError,ValueError,TypeError,KeyError) as exc:
        # Infrastructure and unknown-state failures must not become author retries.
        if isinstance(exc,Blocked) and not any(str(exc).startswith(x) for x in
                ('Verifier must supply','Primitive test','Evaluator primitive','Malformed-answer process',
                 'Evaluator accepted invalid','Rejected answer lacks')):raise
        reports.append({'name':'preflight_contract','passed':False,'error':type(exc).__name__+': '+str(exc)})
    summary={'passed':passed,'verifier_digest':digest(bundle),'scope':'BOUNDED_PRIMITIVES_AND_INVALID_ANSWERS_ONLY',
             'certifies_full_scientific_execution':False,'reports':reports}
    write_json(base/'summary.json',summary)
    return {**summary,'output_path':str(base.relative_to(root)),'output_manifest':tree_manifest(base)}
