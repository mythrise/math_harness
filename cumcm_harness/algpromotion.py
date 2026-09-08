"""Promotion is a separate decision from compilation, execution and inner selection.
This gate consumes controller-owned evidence. It is not authentication: do not let
candidate agents author or edit the protocol, evaluator or run receipts.
"""
from __future__ import annotations
import hashlib,json
import numpy as np
from .algscience import paired_summary,adjust_pvalues


def logical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def promotion_decision(records,protocol):
    required=('candidate','baselines','independent_units','unit_families','development_families',
              'metric','direction','budget','evaluator_hash','candidate_hash','min_effect',
              'alpha','required_ablations','code_hashes','multiplicity_total','min_units','max_regression_fraction')
    if any(k not in protocol for k in required):raise ValueError('Incomplete frozen promotion protocol')
    if protocol['direction'] not in ('min','max') or not 0<protocol['alpha']<1:raise ValueError('Protocol directions/alpha')
    units=protocol['independent_units'];names=protocol['baselines']
    if len(units)!=len(set(units)) or len(names)!=len(set(names)) or protocol['candidate'] in names:raise ValueError('Duplicate protocol IDs')
    ablations=protocol['required_ablations']
    if len(ablations)!=len(set(ablations)) or set(ablations)&{protocol['candidate'],*names}:
        raise ValueError('Ablation IDs must be distinct from each other, the candidate and baselines')
    if len(units)<protocol['min_units'] or protocol['min_units']<2:raise ValueError('Too few preregistered independent units')
    if set(protocol['unit_families'])!=set(units):raise ValueError('Unit-family mapping incomplete')
    if set(protocol['unit_families'].values()) & set(protocol['development_families']):
        return {'decision':'HOLD','reasons':['CONFIRMATION_FAMILY_LEAKAGE']}
    if not names or protocol['multiplicity_total']<len(names):raise ValueError('Missing baselines or multiplicity budget')
    if not np.isfinite(protocol['min_effect']) or not 0<=protocol['max_regression_fraction']<=1:raise ValueError('Invalid effect threshold')
    # Actual evaluation JSON & its immutable digest are both included; no boolean-only certification.
    table={};reasons=[]
    allowed={protocol['candidate'],*names,*protocol['required_ablations']}
    if not protocol['required_ablations'] or set(protocol['code_hashes'])!=allowed:raise ValueError('Ablations and every method code hash must be preregistered')
    for r in records:
        if r.get('method') not in allowed or r.get('unit') not in units:raise ValueError('Unregistered experiment row')
        key=(r['method'],r['unit'])
        if key in table:raise ValueError('Duplicate experiment row')
        for field,expect in [('phase','confirmation'),('metric',protocol['metric']),('budget',protocol['budget']),('evaluator_hash',protocol['evaluator_hash'])]:
            if r.get(field)!=expect:raise ValueError(f'Mismatched {field}')
        ev=r.get('evaluation')
        if not isinstance(ev,dict) or r.get('evaluation_hash')!=logical_hash(ev):raise ValueError('Evaluation digest mismatch')
        if ev.get('valid') is not True:reasons.append('INVALID:'+str(key))
        if isinstance(ev.get('score'),bool) or not isinstance(ev.get('score'),(int,float)) or not np.isfinite(ev['score']):raise ValueError('Nonfinite score')
        if r.get('code_hash')!=protocol['code_hashes'][r['method']]:raise ValueError('Method code changed after preregistration')
        if protocol['code_hashes'][protocol['candidate']]!=protocol['candidate_hash']:raise ValueError('Candidate hash inconsistency')
        table[key]=r
    for method in allowed:
        if any((method,u) not in table for u in units):reasons.append('MISSING_ROWS:'+method)
    if reasons:return dict(decision='HOLD',reasons=sorted(reasons),scope='PREREGISTERED_FAMILIES_ONLY')
    comparisons=[]
    for b in names:
        x=[table[b,u]['evaluation']['score'] for u in units]
        y=[table[protocol['candidate'],u]['evaluation']['score'] for u in units]
        eff=paired_summary(x,y,direction=protocol['direction'],seed=0,
                           alpha=protocol['alpha']/protocol['multiplicity_total'])
        comparisons.append({'baseline':b,**eff})
    pvals=[r['one_sided_sign_pvalue'] for r in comparisons]
    # Conservatively include unobserved preregistered comparisons as p=1.
    adj=adjust_pvalues(pvals+[1.]*(protocol['multiplicity_total']-len(pvals)))[:len(pvals)]
    for r,p in zip(comparisons,adj):
        r['holm_adjusted_sign_pvalue']=float(p)
        if r['ci'][0]<=protocol['min_effect'] or p>protocol['alpha']:reasons.append('NO_CONFIRMED_GAIN:'+r['baseline'])
        if r['losses']/r['n_units']>protocol['max_regression_fraction']:reasons.append('TOO_MANY_REGRESSIONS:'+r['baseline'])
    return dict(decision='PROMOTE_WITHIN_SCOPE' if not reasons else 'HOLD',reasons=reasons,
                comparisons=comparisons,scope='PREREGISTERED_FAMILIES_ONLY_NOT_GLOBAL_SOTA',
                protocol_hash=logical_hash(protocol),
                caveat='Bootstrap CI is approximate; ablation coverage required but mechanistic interpretation still needs reviewers')
