"""Bind blind portfolio comparators to final plans and actual baseline jobs."""
from .common import IntegrityError,digest
def obj(**fields):return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
def arr(item,minimum=0):return {'type':'array','items':item,'minItems':minimum}
ID={'type':'string','pattern':'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$'}
S={'type':'string','minLength':1}
HASH={'type':'string','pattern':'^[0-9a-f]{64}$'}
BINDING=obj(portfolio_digest=HASH,variant={'const':'baseline'},questions=arr(obj(
    question_id=ID,independent_id=ID,independent_digest=HASH,
    disposition={'enum':['KEEP','REPLACE']},selected_method_card_id=S,selected_description=S,
    applicability_reason={'type':'string','minLength':20},comparison_strength={'type':'string','minLength':20}),1))
IMPLEMENTATION=obj(binding_digest=HASH,variant={'const':'baseline'},source_paths=arr(S,1),
    implementation_summary={'type':'string','minLength':20})


def independent_baselines(portfolio):
    rows=[]
    for q in portfolio['questions']:
        baseline=next(x for x in q['options'] if x['kind']=='baseline')
        rows.append({'question_id':q['question_id'],'independent_id':'baseline_'+digest([q['question_id'],baseline['id']])[:24],
            'independent_digest':digest(baseline),'method_card_id':baseline['method_card_id'],'description':baseline['principle']})
    return {'portfolio_digest':digest(portfolio),'variant':'baseline','questions':rows}


def baseline_summary(binding):
    return '\n'.join(f"{q['question_id']}: {q['selected_method_card_id']} — {q['selected_description']}" for q in sorted(binding['questions'],key=lambda q:q['question_id']))


def check_binding(plan,portfolio):
    expected=independent_baselines(portfolio);binding=plan.get('baseline_binding')
    if not binding:raise IntegrityError('Plan needs the independent portfolio baseline binding')
    from jsonschema import Draft202012Validator
    if list(Draft202012Validator(BINDING).iter_errors(binding)):raise IntegrityError('Invalid baseline binding schema')
    if binding['portfolio_digest']!=expected['portfolio_digest']:raise IntegrityError('Stale baseline portfolio digest')
    known={x['question_id']:x for x in expected['questions']};ids=[x['question_id'] for x in binding['questions']]
    if len(set(ids))!=len(ids) or set(ids)!=set(known):raise IntegrityError('Baseline must cover each official question exactly once')
    for row in binding['questions']:
        old=known[row['question_id']]
        if any(row[k]!=old[k] for k in ('independent_id','independent_digest')):raise IntegrityError('Independent baseline identity changed')
        if row['disposition']=='KEEP' and (row['selected_method_card_id']!=old['method_card_id'] or row['selected_description']!=old['description']):raise IntegrityError('KEEP cannot silently replace or weaken the baseline')
        if row['disposition']=='REPLACE' and row['selected_method_card_id']==old['method_card_id'] and row['selected_description']==old['description']:raise IntegrityError('Replacement must identify the actual comparator change')
    if plan['baseline']!=baseline_summary(binding):raise IntegrityError('Free-text baseline differs from the canonical bound comparator')
    return binding


def check_implementation(bundle,binding):
    if binding is None:return None
    data=bundle.get('baseline_implementation')
    from jsonschema import Draft202012Validator
    if not data or list(Draft202012Validator(IMPLEMENTATION).iter_errors(data)):raise IntegrityError('Solver must locate its baseline implementation')
    if data['binding_digest']!=digest(binding):raise IntegrityError('Solver baseline binding differs from frozen plan/protocol')
    paths=data['source_paths'];known={f['path'] for f in bundle['files']}
    if len(paths)!=len(set(paths)) or not set(paths)<=known:raise IntegrityError('Baseline implementation refers to absent source')
    # Metadata is an identity guard; the existing independent source review must
    # still inspect this branch and tests for substantive algorithm fidelity.
    return data
