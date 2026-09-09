"""Source-grounded preparation and paper coverage; never an award predictor.

Schemas deliberately separate a proposed test from a completed measurement.
No lower page, equation, figure, citation or improvement quota is scientific proof.
"""
from __future__ import annotations
import re
from .common import IntegrityError, digest
from .contracts import SCHEMAS, obj, arr, S, B, I, ID, validate, topo

SPAN = obj(start=I, end=I, quote=S)
REQUIREMENT = obj(id=ID, kind={'enum':['background','given','constraint','deliverable']},
                  statement=S, anchor=SPAN, question_ids=arr(ID,1))
BRIEF_QUESTION = obj(id=ID, title=S, direct_goal=S, inferred_goal=S,
    inputs=arr(S,1), outputs=arr(S,1), constraint_ids=arr(ID),
    depends_on=arr(ID), answer_type={'enum':['quantitative','qualitative']},
    family={'enum':['optimization','prediction','evaluation','graph','dynamics','simulation','statistics','mixed']})
SCHEMAS['problem_brief']=obj(problem_sha256={'type':'string','pattern':'^[0-9a-f]{64}$'},
    questions={**arr(BRIEF_QUESTION,1),'maxItems':24},
    requirements={**arr(REQUIREMENT,1),'maxItems':120},
    ambiguities=arr(obj(id=ID,issue=S,impact=S,resolution=S)),
    unit_risks=arr(S), completion_criteria=arr(S,1))
TRANSFORM = obj(file=S, operation={'enum':['none','impute','flag_outlier','transform','select_features','derive_features']},
    columns=arr(S), reason=S, fit_scope={'enum':['none','training_fold_only']},
    time_causal=B, raw_immutable=B, output_path=S, verification=S)
SCHEMAS['data_plan']=obj(sampling_unit=S,
    split={'enum':['iid','group','time','group_time','not_applicable']},
    group_key=S,time_key=S,
    sources=arr(obj(file=S,origin={'enum':['provided','researched','synthetic_scenario']},
        purpose={'enum':['observed_evidence','diagnostic_only']},source_id=S),0),
    transforms=arr(TRANSFORM),required_data=arr(S),optional_data=arr(S),
    leakage_checks=arr(S,1),quality_checks=arr(S,1))
METHOD = obj(id=ID,kind={'enum':['baseline','challenger']},method_card_id=S,
    principle=S,fit_reason=S,limitations=S,validation=S,
    single_change=S,implementation_status={'enum':['AVAILABLE_LOCAL','RESEARCH_ONLY_NOT_RUN']})
SCHEMAS['model_portfolio']=obj(questions=arr(obj(question_id=ID,
    options={**arr(METHOD,1),'maxItems':3},recommendation=ID,decision_basis=S),1),
    shared_computation=arr(S),rejected_innovations=arr(S),stopping_rule=S)
STEPS=('analysis','assumptions','symbols','derivation','algorithm','execution','results','validation')
BINDING=obj(step={'enum':list(STEPS)},section_indices=arr(I),
    state={'enum':['PRESENT','NOT_APPLICABLE']},reason=S)
SCHEMAS['paper_map']=obj(draft_digest={'type':'string','pattern':'^[0-9a-f]{64}$'},
    questions=arr(obj(question_id=ID,bindings=arr(BINDING,8),claim_ids=arr(ID),
        qualitative_evidence_ids=arr(ID)),1),
    symbols=arr(obj(symbol=S,meaning=S,unit=S)),
    abstract_claim_ids=arr(ID),limitations=arr(S,1))
SCHEMAS['abstract_revision']=obj(abstract=S,keywords={**arr(S,1),'maxItems':10},
    claim_ids=arr(ID),remaining_limitations=arr(S,1))


def _unique(values, label):
    if len(values)!=len(set(values)):raise IntegrityError('Duplicate '+label)
    return set(values)


def check_brief(value, problem):
    validate('problem_brief',value)
    if value['problem_sha256']!=digest(problem):raise IntegrityError('Brief is bound to another problem')
    qids=_unique([q['id'] for q in value['questions']], 'brief question')
    topo([{'id':q['id'],'depends_on':q['depends_on']} for q in value['questions']])
    ids=_unique([r['id'] for r in value['requirements']], 'requirement')
    covered=set();deliverables=set()
    for r in value['requirements']:
        a=r['anchor'];start,end=a['start'],a['end']
        if not 0<=start<end<=len(problem) or problem[start:end]!=a['quote']:
            raise IntegrityError('Requirement must quote exact frozen problem offsets')
        linked=_unique(r['question_ids'],'requirement/question mapping')
        if not linked<=qids:raise IntegrityError('Unknown question in requirement')
        covered|=linked
        if r['kind']=='deliverable':deliverables|=linked
    if covered!=qids or deliverables!=qids:raise IntegrityError('Every question needs an anchored deliverable')
    constraints={r['id'] for r in value['requirements'] if r['kind']=='constraint'}
    for q in value['questions']:
        if not set(q['constraint_ids'])<=constraints:raise IntegrityError('Invalid constraint mapping')
    return value


def check_data_plan(value, report):
    validate('data_plan',value)
    known={f['file'] for f in report['files']}
    names=_unique([r['file'] for r in value['sources']], 'data source')
    if names!=known:raise IntegrityError('Data plan must account for every audited development file')
    origins={r['file']:r['origin'] for r in value['sources']}
    for s in value['sources']:
        if s['origin']=='synthetic_scenario' and s['purpose']!='diagnostic_only':
            raise IntegrityError('Synthetic data cannot masquerade as observed evidence')
        if s['origin']=='researched' and s['source_id']=='NOT_APPLICABLE':
            raise IntegrityError('Researched data needs a provenance source ID')
    from .common import safe_rel
    for t in value['transforms']:
        if t['file'] not in known:raise IntegrityError('Transform refers to an unknown input')
        if not t['raw_immutable']:raise IntegrityError('Original input must stay immutable')
        if t['operation'] in ('impute','transform','select_features') and t['fit_scope']!='training_fold_only':
            raise IntegrityError('Learn preprocessing inside the training fold')
        if value['split'] in ('time','group_time') and not t['time_causal']:
            raise IntegrityError('Future-dependent preprocessing is prohibited')
        safe_rel(t['output_path'])
        if t['output_path'] in known:raise IntegrityError('Transform output must not overwrite its input')
    if value['split'] in ('group','group_time') and value['group_key']=='NOT_APPLICABLE':
        raise IntegrityError('Grouped validation needs an explicit independent-unit key')
    if value['split'] in ('time','group_time') and value['time_key']=='NOT_APPLICABLE':
        raise IntegrityError('Temporal validation needs its ordering key')
    return value


def check_portfolio(value,brief,method_cards):
    validate('model_portfolio',value)
    qids={q['id'] for q in brief['questions']}
    if _unique([q['question_id'] for q in value['questions']],'portfolio question')!=qids:
        raise IntegrityError('Portfolio must cover every actual question')
    local={m['id'] for m in method_cards}
    for q in value['questions']:
        ids=_unique([o['id'] for o in q['options']], 'method option')
        if q['recommendation'] not in ids:raise IntegrityError('Unknown recommendation')
        if sum(o['kind']=='baseline' for o in q['options'])!=1:
            raise IntegrityError('One explicit baseline per question is required')
        for o in q['options']:
            if o['implementation_status']=='AVAILABLE_LOCAL' and o['method_card_id'] not in local:
                raise IntegrityError('Reference material does not establish an installed executable algorithm')
            if o['kind']=='baseline' and o['implementation_status']!='AVAILABLE_LOCAL':
                raise IntegrityError('Baseline must be locally available')
    return value


def check_plan_alignment(plan,preparation):
    brief=preparation['brief'];qids={q['id'] for q in brief['questions']}
    if {q['id'] for q in plan['questions']}!=qids:raise IntegrityError('Plan omits or invents a question')
    expected={q['id']:q['answer_type'] for q in brief['questions']}
    if any(q.get('answer_type','quantitative')!=expected[q['id']] for q in plan['questions']):
        raise IntegrityError('Plan changed the requested answer type')
    _unique([v['symbol'] for v in plan['variables']], 'global symbol')
    if any(v['unit'].strip().lower() in ('','unknown','tbd','待补充') for v in plan['variables']):
        raise IntegrityError('Global symbols need units or an explicit dimensionless convention')
    return True


def claim_tokens(text):
    return set(re.findall(r'\{\{claim:([a-zA-Z][a-zA-Z0-9_-]*)\}\}',text))


def check_paper_map(mapping,draft,plan,claims,qualitative_evidence=()):
    validate('paper_map',mapping)
    if mapping['draft_digest']!=digest(draft):raise IntegrityError('Stale paper coverage map')
    qids={q['id'] for q in plan['questions']};known_e={e['id']:e for e in qualitative_evidence}
    if _unique([q['question_id'] for q in mapping['questions']], 'paper question')!=qids:
        raise IntegrityError('Paper map must cover all actual questions')
    sections=draft['sections'];types={q['id']:q.get('answer_type','quantitative') for q in plan['questions']}
    for q in mapping['questions']:
        if _unique([b['step'] for b in q['bindings']], 'coverage step')!=set(STEPS):
            raise IntegrityError('Every question requires the eight coverage decisions, not eight page quotas')
        linked=set(q['claim_ids'])
        if not linked<=set(claims):raise IntegrityError('Paper map contains unmeasured claim')
        if not set(q['qualitative_evidence_ids'])<=set(known_e):raise IntegrityError('Unknown qualitative evidence')
        if any(known_e[k]['question_id']!=q['question_id'] for k in q['qualitative_evidence_ids']):
            raise IntegrityError('Qualitative evidence belongs to another question')
        if types[q['question_id']]=='quantitative':
            if not any(claims[c].get('question_id')==q['question_id'] for c in linked):
                raise IntegrityError('Quantitative conclusion needs a measured claim for this question')
        elif not q['qualitative_evidence_ids']:
            raise IntegrityError('Qualitative conclusion needs its verified evidence, not a placeholder number')
        question_text=[]
        for b in q['bindings']:
            if b['state']=='PRESENT':
                if not b['section_indices']:raise IntegrityError('Present content needs a real section')
                for i in b['section_indices']:
                    if i>=len(sections):raise IntegrityError('Paper mapping points outside draft')
                    if not sections[i]['text'].strip():raise IntegrityError('Empty section cannot satisfy coverage')
                    question_text.append(sections[i]['text'])
            elif b['section_indices'] or len(b['reason'].strip())<20:
                raise IntegrityError('Not-applicable coverage needs a substantive auditable reason')
            elif b['step'] in ('analysis','execution','results','validation'):
                raise IntegrityError('Core question evidence cannot be waived')
        used=set().union(*(claim_tokens(t) for t in question_text))
        if not linked<=used:raise IntegrityError('Declared question claims are not actually used in its text')
    body_claims=set().union(*(claim_tokens(s['text']) for s in sections))
    abstract=claim_tokens(draft['abstract'])
    if abstract!=set(mapping['abstract_claim_ids']) or not abstract<=body_claims:
        raise IntegrityError('Abstract claims must already appear in the body')
    symbols={v['symbol']:v for v in plan['variables']}
    if len(mapping['symbols'])!=len({v['symbol'] for v in mapping['symbols']}):raise IntegrityError('Duplicate paper symbol')
    for v in mapping['symbols']:
        if v['symbol'] not in symbols or v!=symbols[v['symbol']]:raise IntegrityError('Paper symbol meaning/unit differs from plan')
    if set(symbols)!={v['symbol'] for v in mapping['symbols']}:raise IntegrityError('Missing global symbol definitions')
    return {'status':'STRUCTURAL_PASS_SEMANTIC_REVIEW_REQUIRED','draft_digest':digest(draft),
            'question_ids':sorted(qids),'map_digest':digest(mapping),
            'award_prediction':'NOT_SUPPORTED','page_minimum':None}
