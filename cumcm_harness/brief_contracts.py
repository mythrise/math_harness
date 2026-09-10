"""Bounded extraction/assembly schemas; all source IDs and offsets are controller-owned."""
from __future__ import annotations
from copy import deepcopy
import re
from .common import IntegrityError,digest
from .contracts import SCHEMAS,obj,arr,S,I,B,ID,validate,topo
from .materials_contracts import BRIEF_QUESTION,SPAN,check_brief
from .brief_validation import (MAX_REQUIREMENTS,BriefContractError,check_standalone,
    assign_typed_links,definition_conflicts,check_reference_graph,typed_links,declaration_subject_key)

MAX_FACTS_PER_CALL=24
HASH={'type':'string','pattern':'^[0-9a-f]{64}$'}
STRING={'type':'string'}
STATUS={'enum':['COMPLETE','NEEDS_SPLIT','NEEDS_SOURCE']}
DECLARATION=obj(
    subject={**S, 'description':'Exact symbol/name in its definition quote. Prefer the literal source spelling without outer math delimiters. One balanced outer $...$, $$...$$, \\(...\\) or \\[...\\] pair is presentation only; no symbol aliases are inferred.'},
    quote={**S, 'description':'Verbatim continuous source quotation, also present verbatim in this fact statement. Do not normalize whitespace, LaTeX, numbers or units.'})
FACT=obj(kind={'enum':['background','given','constraint','deliverable']},
    category={'enum':['prose','formula','definition','table','geometry','time']},
    statement={'type':'string','minLength':1,'maxLength':2400},
    source_unit_ids={**arr(ID,1),'maxItems':12},question_ids=arr(ID,1),declarations=arr(DECLARATION))
QUESTION=deepcopy(BRIEF_QUESTION)
QUESTION['properties'].pop('constraint_ids');QUESTION['required'].remove('constraint_ids')
QUESTION['properties']['source_unit_ids']={**arr(ID,1),'maxItems':512,
    'description':'Locators for actual question clauses and dependencies. Shared-given locators are optional here; exhaustive fact coverage is checked in later source batches and per-question gates.'};QUESTION['required'].append('source_unit_ids')
AMBIGUITY=obj(id=ID,kind={'enum':['missing_information','source_conflict']},subject=S,
    issue=S,impact=S,resolution=S,related_requirement_ids=arr(ID))
SCHEMAS['brief_page_text']=obj(status={'enum':['COMPLETE','NEEDS_SOURCE']},
    text={'type':'string','maxLength':30000},unreadable=arr(S),notes=arr(S))
SCHEMAS['brief_outline']=obj(questions={**arr(QUESTION,1),'maxItems':24},
    unit_risks=arr(S),completion_criteria=arr(S,1))
SCHEMAS['brief_facts']=obj(status=STATUS,facts={**arr(FACT),'maxItems':MAX_FACTS_PER_CALL},
    exclusions={**arr(obj(source_unit_id=ID,reason={'type':'string','minLength':12})),'maxItems':12},
    unreadable=arr(S),reason=STRING)
SCHEMAS['brief_ambiguities']=obj(ambiguities={**arr(AMBIGUITY),'maxItems':32},
    accepted_definitions=arr(obj(subject=S,requirement_ids=arr(ID,1))))
SCHEMAS['brief_local_patch']=obj(base_digest=HASH,
    updates={**arr(obj(requirement_id=ID,before_digest=HASH,fact=FACT)),'maxItems':12},
    additions={**arr(FACT),'maxItems':12},
    ambiguities={**arr(AMBIGUITY),'maxItems':32},
    reasons=arr(S,1))


def _unique(values,label):
    if len(values)!=len(set(values)):raise IntegrityError('Duplicate '+label)
    return set(values)


def check_outline(value,units):
    validate('brief_outline',value);known={u['id'] for u in units}
    _unique([q['id'] for q in value['questions']],'outlined question')
    topo(value['questions'])
    for q in value['questions']:
        foreign=_unique(q['source_unit_ids'],'question source')-known
        if foreign:
            raise BriefContractError([{'code':'UNKNOWN_OUTLINE_SOURCE','location':q['id']+'.source_unit_ids',
                'detail':','.join(sorted(foreign)),'allowed_source_ids':sorted(known),
                'required_fix':'Select exact supplied IDs. Never append suffixes, invent aliases or silently remap an unknown ID. This outline uses question locators; complete given-fact mapping follows in source batches.'}])
    return value


def check_fact(fact,units,question_ids,*,location='fact'):
    # Use the registered parent validator for shape, below for referential integrity.
    sources={u['id']:u for u in units}
    ids=_unique(fact['source_unit_ids'],'fact source')
    if not ids<=set(sources):raise IntegrityError('Fact cites a source outside its assigned source packet')
    if not _unique(fact['question_ids'],'fact question')<=set(question_ids):raise IntegrityError('Fact refers to an unknown actual question')
    text='\n\n'.join(sources[i]['text'] for i in fact['source_unit_ids'])
    check_standalone(fact['statement'],text)
    # A source unit is the WHOLE paragraph/table or reviewed visual transcription,
    # not an arbitrary one-line title or formula tail selected by the author.
    # Numeric lexemes in a brief are source facts, not new calculations.
    nums=lambda s:set(re.findall(r'(?<![A-Za-z_])\d+(?:\.\d+)?',s))
    unsupported=nums(fact['statement'])-nums(text)
    if unsupported:
        raise BriefContractError([{'code':'UNSOURCED_NUMBER','location':'statement','detail':','.join(sorted(unsupported))}])
    if fact['category'] in ('formula','definition','table','geometry','time'):
        def math_tokens(s):
            s=s.replace(r'\pi','π')
            s=re.sub(r'\\(?:frac|mathrm|mathbf|operatorname|left|right|cdot|times|quad|text)\b','',s)
            return set(re.findall(r'[A-Za-z][A-Za-z0-9_]*|[α-ωΑ-Ω]',s))
        missing=math_tokens(fact['statement'])-math_tokens(text)
        if missing:
            raise BriefContractError([{'code':'UNSOURCED_SYMBOL','location':'statement','detail':','.join(sorted(missing))}])
    declarations=fact['declarations']
    if fact['category']=='definition' and not declarations:
        raise IntegrityError('A definition fact needs an explicit source-grounded subject/meaning declaration')
    keys=[declaration_subject_key(d['subject']) for d in declarations]
    findings=[]
    if len(keys)!=len(set(keys)):
        findings.append({'code':'DUPLICATE_DECLARATION_SUBJECT','location':location+'.declarations',
            'detail':'The same source subject appears more than once, including presentation-wrapper variants.',
            'required_fix':'Keep one complete source-grounded declaration for each subject in this fact.'})
    for i,(d,subject) in enumerate(zip(declarations,keys)):
        checks=[('DECLARATION_SUBJECT_NOT_IN_SOURCE','subject',bool(subject) and subject in text,
                 'Use the literal symbol/name in the cited source. Outer math delimiters are optional; do not invent aliases or alter subscripts.'),
                ('DECLARATION_SUBJECT_NOT_IN_QUOTE','subject',bool(subject) and subject in d['quote'],
                 'Bind this subject to its own exact definition quote; a different definition elsewhere in the paragraph is insufficient.'),
                ('DECLARATION_QUOTE_NOT_IN_SOURCE','quote',d['quote'] in text,
                 'Copy a continuous quotation exactly from the cited source, preserving all characters, notation, numbers and units.'),
                ('DECLARATION_QUOTE_NOT_IN_STATEMENT','quote',d['quote'] in fact['statement'],
                 'Include the exact definition quotation in this self-contained statement; do not replace it with a cross-reference.')]
        for code,field,ok,fix in checks:
            if not ok:
                findings.append({'code':code,'location':f'{location}.declarations[{i}].{field}',
                    'detail':d[field][:240],'source_unit_ids':list(fact['source_unit_ids']),
                    'required_fix':fix})
    if findings:raise BriefContractError(findings)
    return fact


def check_facts(value,units,questions,*,context_units=()):
    validate('brief_facts',value)
    if value['status']!='COMPLETE':
        if value['facts'] or value['exclusions']:raise IntegrityError('Noncomplete batch cannot publish partial accepted facts')
        return value
    if value['unreadable']:raise IntegrityError('COMPLETE may not contain unreadable source parts')
    known={u['id'] for u in units};covered=set()
    available=list({u['id']:u for u in [*units,*context_units]}.values())
    findings=[]
    for i,f in enumerate(value['facts']):
        try:check_fact(f,available,questions,location=f'facts[{i}]')
        except BriefContractError as exc:findings.extend(exc.findings)
        if f['source_unit_ids'][0] not in known:raise IntegrityError('Fact owner must be in the assigned batch, not only its context')
        covered.update(set(f['source_unit_ids']) & known)
    if findings:raise BriefContractError(findings)
    excluded=_unique([e['source_unit_id'] for e in value['exclusions']],'excluded unit')
    if not excluded<=known or covered&excluded or covered|excluded!=known:
        raise IntegrityError('Every source unit needs facts OR a reviewed exclusion; missing/overlapping/foreign source coverage')
    return value


def fact_to_requirement(fact,units,*,requirement_id=None):
    known={u['id']:u for u in units}
    selected=[known[i] for i in fact['source_unit_ids']]
    # Keep complete source paragraphs, not repeated copies of an entire PDF
    # page for each fact. The reviewed coordinate space is explicit and requires
    # the frozen page-backed ledger when validated. No reconstructed text is
    # silently substituted into original problem.md.
    def compact_anchor(unit):
        return {'start':0,'end':len(unit['text']),'quote':unit['text']} if unit['visual'] else deepcopy(unit['anchor'])
    anchor=compact_anchor(selected[0])
    rid=requirement_id or 'R'+digest([fact,sorted(fact['source_unit_ids'])])[:22]
    return {'id':rid,'kind':fact['kind'],'statement':fact['statement'],'anchor':deepcopy(anchor),
        'question_ids':list(fact['question_ids']),'source_unit_ids':list(fact['source_unit_ids']),
        'anchors':[compact_anchor(u) for u in selected],
        'anchor_space':'reviewed_source_unit' if selected[0]['visual'] else 'original_problem',
        'category':fact['category'],'declarations':deepcopy(fact['declarations']),'references':[]}


def assemble(outline,facts,units,problem,*,ambiguities=()):
    if len(facts)>MAX_REQUIREMENTS:raise IntegrityError('Assembled brief exceeds explicit global requirement bound; never truncate to fit')
    requirements=[fact_to_requirement(f,units) for f in facts]
    if len({r['id'] for r in requirements})!=len(requirements):raise IntegrityError('Duplicate extracted fact; consolidate with explicit source coverage')
    questions=[]
    for q in outline['questions']:
        q=deepcopy(q);q.pop('source_unit_ids');questions.append(q)
    value={'problem_sha256':digest(problem),'questions':assign_typed_links(questions,requirements),
        'requirements':requirements,'ambiguities':list(ambiguities),'unit_risks':outline['unit_risks'],
        'completion_criteria':outline['completion_criteria']}
    return value


def check_complete(value,units,problem):
    check_brief(value,problem,source_units=units);typed_links(value);check_reference_graph(value,problem);definition_conflicts(value)
    qids={q['id'] for q in value['questions']};seen=set()
    for r in value['requirements']:
        f={k:r[k] for k in ('kind','category','statement','source_unit_ids','question_ids','declarations')}
        check_fact(f,units,qids,location=f'requirements[{r["id"]}]')
        expected=fact_to_requirement(f,units,requirement_id=r['id'])
        if r!=expected:raise IntegrityError('Source anchors or typed requirement projection modified')
        seen.update(r['source_unit_ids'])
    return value


def check_ambiguities(value,brief):
    validate('brief_ambiguities',value)
    declared={}
    for r in brief['requirements']:
        for d in r['declarations']:declared.setdefault(declaration_subject_key(d['subject']),[]).append(r['id'])
    found={declaration_subject_key(x['subject']):x['requirement_ids'] for x in value['accepted_definitions']}
    if len(found)!=len(value['accepted_definitions']) or set(found)!=set(declared):
        raise IntegrityError('Consistency pass must explicitly acknowledge every source declaration')
    for key,ids in declared.items():
        if _unique(found[key],'definition link')!=set(ids):raise IntegrityError('Declaration recognition mismatch')
    test={**brief,'ambiguities':value['ambiguities']};definition_conflicts(test)
    return value


def apply_local_patch(brief,patch,units,problem):
    validate('brief_local_patch',patch)
    if patch['base_digest']!=digest(brief):raise IntegrityError('Stale global brief patch')
    updated=deepcopy(brief);by_id={r['id']:i for i,r in enumerate(updated['requirements'])};touched=set()
    qids={q['id'] for q in brief['questions']}
    for i,op in enumerate(patch['updates']):
        rid=op['requirement_id']
        if rid not in by_id or rid in touched:raise IntegrityError('Unknown/duplicate patch target')
        touched.add(rid);old=updated['requirements'][by_id[rid]]
        if op['before_digest']!=digest(old):raise IntegrityError('Patch does not bind the original requirement')
        check_fact(op['fact'],units,qids,location=f'updates[{i}].fact')
        new=fact_to_requirement(op['fact'],units,requirement_id=rid)
        # Repairing wording cannot silently delete a hard constraint/deliverable.
        if old['kind'] in ('constraint','deliverable') and new['kind']!=old['kind']:
            raise IntegrityError('Patch may not weaken a hard constraint/deliverable; re-extract in a new source version')
        updated['requirements'][by_id[rid]]=new
    for i,fact in enumerate(patch['additions']):
        check_fact(fact,units,qids,location=f'additions[{i}]');r=fact_to_requirement(fact,units)
        if r['id'] in by_id:raise IntegrityError('Duplicate addition')
        by_id[r['id']]=len(updated['requirements']);updated['requirements'].append(r)
    updated['questions']=assign_typed_links(updated['questions'],updated['requirements'])
    updated['ambiguities']=deepcopy(patch['ambiguities'])
    if digest(updated)==digest(brief):raise IntegrityError('No-op patch cannot clear a rejection')
    old_covered={s for r in brief['requirements'] for s in r['source_unit_ids']}
    new_covered={s for r in updated['requirements'] for s in r['source_unit_ids']}
    if not old_covered<=new_covered:raise IntegrityError('Patch silently dropped previously covered source evidence')
    check_complete(updated,units,problem)
    return updated
