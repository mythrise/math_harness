"""Deterministic brief reference checks. These do not prove semantic entailment.

No heliostat formula or answer is built into this module. Reported failure shapes
are regression tests, not privileged domain knowledge.
"""
from __future__ import annotations
from collections import Counter
import re
import unicodedata
from .common import IntegrityError, digest

MAX_REQUIREMENTS = 512
# Explicit in-document cross references, not arbitrary scientific symbols.
REF = r'(?:[A-Z]{1,5}[0-9]{1,4})'
CROSSREF = re.compile(r'(?:参见|详见|见|见于|refer(?:s)?\s+to|see)\s*[:：]?\s*('+REF+r')(?:\s*(?:至|到|[-—–~～])\s*('+REF+r'))?', re.I)
SHORTREF = re.compile(r'(?<![\w])(?:G|R|D|A)[0-9]{1,4}(?![\w])')

class BriefContractError(IntegrityError):
    """Source-bound diagnostics, safe to provide as bounded repair input."""
    def __init__(self, findings):
        self.findings = findings
        first = findings[0] if findings else {'code':'UNKNOWN','location':'brief'}
        super().__init__(f"BRIEF_CONTRACT[{first['code']}] {first['location']}: "
                         f"{first.get('detail','')} ({len(findings)} finding(s))")


def _expanded(a, b):
    if not b:
        return [a]
    x, y = re.fullmatch(r'([A-Za-z]+)(\d+)', a), re.fullmatch(r'([A-Za-z]+)(\d+)', b)
    if not x or not y or x[1].upper() != y[1].upper():
        raise BriefContractError([{'code':'INVALID_REFERENCE_RANGE','location':'statement','detail':a+'..'+b}])
    first, last = int(x[2]), int(y[2])
    if not 0 <= last-first <= MAX_REQUIREMENTS:
        raise BriefContractError([{'code':'UNBOUNDED_REFERENCE_RANGE','location':'statement','detail':a+'..'+b}])
    width = len(x[2]) if x[2].startswith('0') else 0
    return [x[1].upper()+str(i).zfill(width) for i in range(first,last+1)]


def references_in(text, known=(), original=''):
    """Find explicit ranges and requirement-looking IDs absent from source text.

    Case is preserved for exact known IDs; see-references use the author's exact
    spelling. Domain IDs quoted from the official source are not automatically
    treated as references to generated requirements.
    """
    found=[]
    for m in CROSSREF.finditer(text):
        found.extend(_expanded(m[1], m[2]))
    for m in SHORTREF.finditer(text):
        if m[0] in known or not re.search(r'(?<!\w)'+re.escape(m[0])+r'(?!\w)',original):
            found.append(m[0])
    return list(dict.fromkeys(found))


def check_reference_graph(brief, original=''):
    rows=brief['requirements'];known={r['id']:r for r in rows};findings=[];graph={}
    if len(known)!=len(rows):
        raise BriefContractError([{'code':'DUPLICATE_REQUIREMENT_ID','location':'requirements','detail':'IDs must be unique'}])
    for r in rows:
        named=r.get('references',[])
        if len(named)!=len(set(named)):
            findings.append({'code':'DUPLICATE_REFERENCE','location':r['id'],'detail':str(named)})
        textual=references_in(r['statement'],known,original)
        refs=list(dict.fromkeys([*named,*textual]));graph[r['id']]=refs
        for ref in refs:
            if ref not in known:
                findings.append({'code':'DANGLING_REFERENCE','location':r['id'],'detail':ref,'required_fix':'Provide complete source-grounded content or remove the unsupported reference; do not invent the missing item.'})
            elif ref==r['id']:
                findings.append({'code':'SELF_REFERENCE','location':r['id'],'detail':ref})
    if not findings:
        # Iterative topological peeling, bounded at 512 nodes.
        remaining={k:set(v) for k,v in graph.items()}
        while remaining:
            ready={k for k,v in remaining.items() if not v}
            if not ready:
                findings.append({'code':'CYCLIC_REFERENCE','location':'requirements','detail':','.join(sorted(remaining))});break
            remaining={k:v-ready for k,v in remaining.items() if k not in ready}
    if findings:raise BriefContractError(findings)
    return graph


def typed_links(brief):
    """Reject wrong types; NEVER relabel givens to make an invalid ID pass."""
    known={r['id']:r for r in brief['requirements']};findings=[]
    for q in brief['questions']:
        for field,kind in [('constraint_ids','constraint'),('given_ids','given'),('deliverable_ids','deliverable')]:
            ids=q.get(field,[])
            if len(ids)!=len(set(ids)):
                findings.append({'code':'DUPLICATE_TYPED_LINK','location':q['id']+'.'+field,'detail':str(ids)})
            for ref in ids:
                actual=known.get(ref,{}).get('kind','UNKNOWN_ID')
                if actual!=kind or q['id'] not in known.get(ref,{}).get('question_ids',[]):
                    findings.append({'code':'WRONG_REFERENCE_TYPE','location':q['id']+'.'+field,'detail':ref,
                                     'expected_kind':kind,'actual_kind':actual})
    if findings:raise BriefContractError(findings)
    return True


def assign_typed_links(questions,requirements):
    """Controller derives reference lists AFTER all fact types are finalized."""
    import copy
    result=copy.deepcopy(questions)
    for q in result:
        for field,kind in [('constraint_ids','constraint'),('given_ids','given'),('deliverable_ids','deliverable')]:
            q[field]=[r['id'] for r in requirements if r['kind']==kind and q['id'] in r['question_ids']]
    return result


def check_standalone(statement, source_text):
    refs=references_in(statement,(),source_text)
    if refs:
        raise BriefContractError([{'code':'NON_STANDALONE_FACT','location':'statement','detail':','.join(refs),
                                  'required_fix':'Write a self-contained statement with its complete definition and units, not see Gxx.'}])


def definition_conflicts(brief):
    """Machine check only explicitly declared subjects, not unrestricted NLI."""
    declarations={}
    for r in brief['requirements']:
        declared=list(r.get('declarations',[]))
        # A narrow, source-exact legacy compatibility guard. No subject value is
        # invented; this recognizes only an explicit Latin-symbol definition
        # repeated in both the statement and its existing original anchor.
        anchor=r.get('anchor',{}).get('quote','')
        # PDF math italic Latin letters and plain Latin are comparison aliases
        # only. Original quotations and frozen offsets are never rewritten.
        comparable=lambda text:re.sub(r'\s+','',unicodedata.normalize('NFKC',text))
        for m in re.finditer(r'(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]{0,20})\s*(?:定义为|表示|为|是)\s*([^，。；;\n]+)',r['statement']):
            if comparable(m[0]) in comparable(anchor) and not any(d['subject']==m[1] for d in declared):
                declared.append({'subject':m[1],'quote':m[0]})
        for d in declared:
            declarations.setdefault(d['subject'].strip(),[]).append((r['id'],d['quote'].strip()))
    findings=[]
    for a in brief.get('ambiguities',[]):
        subject=a.get('subject','').strip()
        linked=a.get('related_requirement_ids',[])
        known={r['id'] for r in brief['requirements']}
        if any(ref not in known for ref in linked):
            findings.append({'code':'UNKNOWN_AMBIGUITY_REFERENCE','location':a['id'],'detail':str(linked)})
        if a.get('kind')=='missing_information' and subject in declarations:
            findings.append({'code':'REOPENED_EXPLICIT_DEFINITION','location':a['id'],'detail':subject,
                'given_requirements':[x[0] for x in declarations[subject]],
                'required_fix':'Respect the supplied definition. A real source conflict needs two contradictory source-grounded declarations, not a guessed alternative interpretation.'})
        if not a.get('kind') and re.search(r'是否|不明确|未.*明确|待定|不清楚',a.get('issue','')):
            for term,rows in declarations.items():
                if re.search(r'(?<![A-Za-z0-9_])'+re.escape(term)+r'(?![A-Za-z0-9_])',a['issue']):
                    findings.append({'code':'LEGACY_CONVENTION_REOPENED','location':a['id'],'detail':term,
                        'given_requirements':[r[0] for r in rows],
                        'required_fix':'Explicitly distinguish a real source conflict from a convention the problem has already supplied.'})
        if a.get('kind')=='source_conflict':
            witnesses={rid:value for rid,value in declarations.get(subject,[]) if rid in linked}
            if len(witnesses)<2 or len(set(witnesses.values()))<2:
                findings.append({'code':'UNSUPPORTED_SOURCE_CONFLICT','location':a['id'],'detail':subject})
    if findings:raise BriefContractError(findings)
    return declarations


def diagnostics(brief,problem):
    """Offline check for previously generated briefs; never modifies originals."""
    checks=[]
    for name,fn in [('typed_links',lambda:typed_links(brief)),
                    ('reference_closure',lambda:check_reference_graph(brief,problem)),
                    ('explicit_definitions',lambda:definition_conflicts(brief))]:
        try:fn();checks.append({'check':name,'status':'PASS'})
        except BriefContractError as e:checks.append({'check':name,'status':'FAIL','findings':e.findings})
    return {'status':'FAIL' if any(c['status']=='FAIL' for c in checks) else 'STRUCTURAL_PASS_REVIEW_REQUIRED',
            'checks':checks,'artifact_digest':digest(brief),'semantic_entailment':'NOT_CERTIFIED'}
