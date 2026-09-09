"""Read-only preparation/diagnosis tools. No model execution, upload or approval."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from .common import read_json,write_json,digest,IntegrityError

def diagnose_draft(draft,plan,claims):
    from .contracts import validate
    from .materials_contracts import claim_tokens
    validate('paper',draft);validate('plan',plan)
    findings=[]
    for index,section in enumerate(draft['sections']):
        actual=claim_tokens(section['text']);declared=set(section['claim_ids'])
        if actual!=declared:findings.append({'severity':'P1','location':f'sections[{index}]','issue':'Claim tokens and declared claim IDs differ'})
        if not actual<=set(claims):findings.append({'severity':'P1','location':f'sections[{index}]','issue':'Unknown claim token'})
        if any(w in section['heading'] for w in ('目录','承诺书','编号专用页')):
            findings.append({'severity':'P1','location':f'sections[{index}]','issue':'Paper-only cover or forbidden ToC heading'})
    body=set().union(*(claim_tokens(s['text']) for s in draft['sections']))
    if not claim_tokens(draft['abstract'])<=body:
        findings.append({'severity':'P1','location':'abstract','issue':'Abstract adds a body-absent empirical claim'})
    for q in plan['questions']:
        if q.get('answer_type','quantitative')=='quantitative' and not any(claims[c].get('question_id')==q['id'] for c in body&set(claims)):
            findings.append({'severity':'P1','location':q['id'],'issue':'No question-specific measured claim in body'})
    return {'status':'REPAIR_REQUIRED' if findings else 'STATIC_CHECKS_PASSED_NOT_SEMANTIC_ACCEPTANCE',
       'mode':'EXISTING_STRUCTURED_DRAFT_DIAGNOSIS','draft_digest':digest(draft),
       'findings':findings,'award_prediction':'NOT_SUPPORTED','page_minimum':None,
       'next_gate':'Need coverage map, original evidence, independent semantic review, real compilation and visual checks; no rewriting unverified results.'}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='cmd',required=True)
    s.add_parser('skills')
    q=s.add_parser('schema');q.add_argument('name',nargs='?')
    q=s.add_parser('audit-data');q.add_argument('directory',type=Path)
    q=s.add_parser('reference');q.add_argument('query')
    q=s.add_parser('diagnose-paper');q.add_argument('--draft',type=Path,required=True);q.add_argument('--plan',type=Path,required=True);q.add_argument('--claims',type=Path,required=True)
    q=s.add_parser('verify-submission');q.add_argument('workspace',type=Path)
    a=p.parse_args(argv)
    try:
        if a.cmd=='skills':
            from .role_skills import skill_fingerprint
            result=skill_fingerprint()
        elif a.cmd=='schema':
            from . import materials_contracts
            from .contracts import SCHEMAS
            names=['problem_brief','data_plan','model_portfolio','paper_map','abstract_revision']
            if a.name and a.name not in names:raise IntegrityError('Unknown materials schema')
            result=SCHEMAS[a.name] if a.name else {'available':names}
        elif a.cmd=='audit-data':
            from .materials_data import audit_development
            result=audit_development(a.directory)
        elif a.cmd=='reference':
            from .materials_catalog import retrieve_reference_models
            result=retrieve_reference_models(a.query)
        elif a.cmd=='diagnose-paper':result=diagnose_draft(read_json(a.draft),read_json(a.plan),read_json(a.claims))
        else:
            from .submission_manifest import verify_seal
            result=verify_seal(a.workspace,read_json(a.workspace/'deliverables/submission-manifest.json'))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as exc:
        print(json.dumps({'status':'BLOCKED','error':type(exc).__name__,'reason':str(exc)},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
