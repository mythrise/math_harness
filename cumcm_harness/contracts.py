"""Machine-enforced contracts. Model output never supplies its own provenance."""
from __future__ import annotations
import re, sys
from functools import lru_cache
from importlib.metadata import packages_distributions
from typing import Any
from jsonschema import Draft202012Validator
from .common import canonical, IntegrityError, finite, safe_rel

def obj(**fields):
    return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
def arr(item,minimum=0): return {'type':'array','items':item,'minItems':minimum}
S={'type':'string','minLength':1}; TEXT={'type':'string'}
I={'type':'integer','minimum':0}; N={'type':'number'}; B={'type':'boolean'}
ID={'type':'string','pattern':'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$'}
FINDING=obj(severity={'enum':['P0','P1','P2']},location=S,issue=S,required_fix=S)
QUESTION=obj(id=ID,question=S,metric=S,unit=S,acceptance=S)
QUESTION['properties']['answer_type']={'enum':['quantitative','qualitative']}
TASK=obj(id=ID,depends_on=arr(ID),goal=S,algorithm_skill=S,outputs=arr(S,1))
PLAN=obj(summary=S,assumptions=arr(S,1),questions=arr(QUESTION,1),tasks=arr(TASK,1),
         variables=arr(obj(symbol=S,meaning=S,unit=S)),equations=arr(S,1),
         constraints=arr(S,1),baseline=S,ablations=arr(obj(id=ID,change=S)),
         sensitivity=arr(obj(id=ID,change=S)),limitations=arr(S,1),
         primary_metric=S,direction={'enum':['minimize','maximize']},min_effect={'type':'number','minimum':0},
         evaluator_spec=S,resources=obj(cpu_threads={'type':'integer','minimum':1},
             memory_mb={'type':'integer','minimum':64},expected_seconds={'type':'number','minimum':0.001},
             row_sharding=B,checkpointing=B,fold_invariant_precompute=B))
BUNDLE=obj(files=arr(obj(path=S,content=TEXT),1),notes=arr(S),
           algorithm_usage=arr(obj(skill=S,strategy=S,reason=S)))
from .baseline_binding import BINDING,IMPLEMENTATION
PLAN['properties']['baseline_binding']=BINDING
BUNDLE['properties']['baseline_implementation']=IMPLEMENTATION

REVIEW=obj(target_digest={'type':'string','pattern':'^[0-9a-f]{64}$'},
           verdict={'enum':['PASS','FAIL','BLOCKED']},scope=S,
           findings=arr(FINDING),evidence=arr(S,1),unverified=arr(S))
REVIEW['properties']['clarification_responses']=arr(obj(signal_digest={'type':'string','pattern':'^[0-9a-f]{64}$'},reason={'type':'string','minLength':20}))
SUPERVISE=obj(objective=S,priorities=arr(S,1),research_focus=arr(S,1),stop_rules=arr(S,1))
PROPOSAL=obj(hypothesis=S,mechanism=S,expected_effect=S,change_request=S,
             falsification=S,stop=B)
MEASUREMENT=obj(id=ID,value=N,unit=S,question_id=ID,description=S)
EVALUATION=obj(score=N,valid=B,metric=S,checks=arr(obj(name=S,passed=B,detail=S),1),
               question_coverage=arr(ID,1),measurements=arr(MEASUREMENT,1))
EVALUATION['properties']['question_evidence']=arr({'oneOf':[obj(id=ID,question_id=ID,kind={'const':'text'},text=S,sha256={'type':'string','pattern':'^[0-9a-f]{64}$'}),obj(id=ID,question_id=ID,kind={'const':'file'},path=S,description=S,sha256={'type':'string','pattern':'^[0-9a-f]{64}$'})]})
PAPER=obj(title=S,abstract=S,keywords=arr(S,1),sections=arr(obj(heading=S,text=S,equations=arr(S),claim_ids=arr(ID)),1),
          limitations=arr(S,1),figure_caption=S,citation_ids=arr(ID))
SCHEMAS={'plan':PLAN,'bundle':BUNDLE,'review':REVIEW,'supervisor':SUPERVISE,'proposal':PROPOSAL,
         'evaluation':EVALUATION,'paper':PAPER}

def validate(name: str, value: Any) -> Any:
    try: canonical(value)
    except (ValueError,TypeError) as e: raise IntegrityError(str(e)) from e
    errors=sorted(Draft202012Validator(SCHEMAS[name]).iter_errors(value),key=lambda e:str(e.path))
    if errors: raise IntegrityError(f'{name}: {errors[0].json_path}: {errors[0].message}')
    if name=='plan': validate_plan(value)
    if name=='bundle': validate_bundle(value)
    if name=='review' and value['verdict']=='PASS':
        if any(x['severity'] in ('P0','P1') for x in value['findings']) or value['unverified']:
            raise IntegrityError('PASS cannot contain blocking findings or unverified required checks')
    if name=='evaluation':
        finite(value['score'])
        for m in value['measurements']: finite(m['value'])
        if len({m['id'] for m in value['measurements']})!=len(value['measurements']):
            raise IntegrityError('Duplicate measurement IDs')
        covered=value['question_coverage']
        if len(set(covered))!=len(covered):raise IntegrityError('Duplicate question coverage IDs')
        if value['valid']:
            if not all(x['passed'] for x in value['checks']):
                raise IntegrityError('Valid evaluation has failing checks')
            measured={m['question_id'] for m in value['measurements']}
            evidence=value.get('question_evidence',[])
            if len({e['id'] for e in evidence})!=len(evidence):raise IntegrityError('Duplicate question evidence IDs')
            for e in evidence:
                if e['kind']=='text':
                    if __import__('hashlib').sha256(e['text'].encode()).hexdigest()!=e['sha256']:raise IntegrityError('Question text evidence hash mismatch')
                else:safe_rel(e['path'])
            measured|={e['question_id'] for e in evidence}
            if measured!=set(covered):
                raise IntegrityError('Valid question coverage must match measurement evidence')
    return value

def topo(tasks: list[dict]) -> list[str]:
    ids=[x['id'] for x in tasks]
    if len(set(ids))!=len(ids):raise IntegrityError('Duplicate task IDs')
    remaining={x['id']:set(x['depends_on']) for x in tasks}
    if any(not deps.issubset(ids) for deps in remaining.values()):raise IntegrityError('Unknown DAG dependency')
    order=[]
    while remaining:
        ready=sorted(k for k,d in remaining.items() if not d)
        if not ready:raise IntegrityError('DAG cycle')
        for k in ready: order.append(k);remaining.pop(k)
        for d in remaining.values():d.difference_update(ready)
    return order

def validate_plan(p: dict) -> None:
    topo(p['tasks'])
    if len({q['id'] for q in p['questions']})!=len(p['questions']):raise IntegrityError('Duplicate questions')
    variants=['baseline','full']+[a['id'] for a in p['ablations']+p['sensitivity']]
    if len(set(variants))!=len(variants):raise IntegrityError('Duplicate or reserved experiment variant')
    if not p['ablations'] or not p['sensitivity']:raise IntegrityError('Require at least one ablation and sensitivity diagnostic')
    if p['primary_metric'] not in [q['metric'] for q in p['questions']]:raise IntegrityError('Primary metric not linked to a question')

@lru_cache(maxsize=1)
def protected_modules():
    legacy_stdlib={'cgi','cgitb','imghdr','mailcap','nntplib','pipes','sndhdr','telnetlib','uu','xdrlib','aifc','audioop','sunau','ossaudiodev','chunk'}
    return {n.casefold() for n in set(sys.stdlib_module_names)|set(packages_distributions())|legacy_stdlib|
            {'cumcm_harness','numpy','scipy','sklearn','numba','matplotlib','pandas','jsonschema','yaml','PIL','fitz','pymupdf','lxml','pypdf'}}

def validate_bundle(b: dict) -> None:
    names=[]; total=0
    for f in b['files']:
        name=safe_rel(f['path']); names.append(name); total+=len(f['content'].encode())
        # /code is the worker's working directory. Never let generated files
        # replace the trusted worker package or its standard/approved dependencies.
        top=name.split('/')[0].split('.')[0]
        if top.casefold() in protected_modules():raise IntegrityError('Generated file shadows a trusted runtime module')
        if not name.endswith(('.py','.json','.md','.txt','.csv')):raise IntegrityError('Unapproved generated file type')
        if name.split('/')[-1] in ('AGENTS.md','CLAUDE.md','sitecustomize.py','usercustomize.py'):
            raise IntegrityError('Generated instruction / Python startup injection forbidden')
        if len(f['content'].encode())>400_000:raise IntegrityError('Generated file exceeds packet budget')
    if len(names)!=len(set(names)):raise IntegrityError('Duplicate generated file path')
    if total>1_500_000:raise IntegrityError('Bundle too large; split into smaller tasks')
