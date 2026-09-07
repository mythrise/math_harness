#!/usr/bin/env python3
"""Aggregate externally judged, file-bound matched task results.
This script is NOT itself an expert judge. It rejects mismatched comparison cells;
conclusions still require independent mathematical review of the evaluator.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np

def compare(records,root,reference,challenger):
    groups={reference:{},challenger:{}}
    for row in records:
        if row['agent'] not in groups:continue
        key=(row['task_id'],row['replicate'])
        if key in groups[row['agent']]:raise ValueError('duplicate comparison cell')
        for kind in ('artifact','judge'):
            p=(root/row[kind+'_file']).resolve()
            if not p.is_relative_to(root.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=row[kind+'_sha256']:raise ValueError('unbound/mutated evidence')
        judge=json.loads((root/row['judge_file']).read_text())
        if judge.get('valid') is not True or judge.get('independent') is not True:raise ValueError('invalid/unverified task result')
        if not np.isfinite(judge['score']):raise ValueError('nonfinite score')
        groups[row['agent']][key]=(row,judge)
    if not groups[reference] or set(groups[reference])!=set(groups[challenger]):raise ValueError('missing matched cells; not comparable')
    differences={}
    for key,(a,ja) in groups[reference].items():
        b,jb=groups[challenger][key]
        for field in ('problem_sha256','data_sha256','budget_profile','backbone_profile','evaluator_digest','metric','direction'):
            if a[field]!=b[field]:raise ValueError('unmatched comparison '+field)
        if ja.get('evaluator_digest')!=a['evaluator_digest'] or jb.get('evaluator_digest')!=b['evaluator_digest']:raise ValueError('judge identity mismatch')
        sign=1 if a['direction']=='maximize' else -1
        differences.setdefault(key[0],[]).append(sign*(jb['score']-ja['score']))
    # Task, not run, is the unit. Do not count seeds as different problems.
    x=np.array([np.mean(differences[t]) for t in sorted(differences)])
    report={'reference':reference,'challenger':challenger,'task_count':len(x),'paired_cells':len(groups[reference]),'mean_task_difference':float(x.mean()),'scope':'supplied frozen tasks only','superiority':'NOT_ESTABLISHED','multiple_comparisons':'Requires pre-registered correction across baseline comparisons'}
    if len(x)>=10:
        boot=x[np.random.default_rng(20260905).integers(0,len(x),(10000,len(x)))].mean(1)
        report['ci95']=np.quantile(boot,[.025,.975]).tolist()
    else:report['ci95']=None
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('--reference',required=True);p.add_argument('--challenger',default='CUMCM-EgoHarness');a=p.parse_args()
    print(json.dumps(compare(json.loads(a.manifest.read_text()),a.manifest.parent,a.reference,a.challenger),ensure_ascii=False,indent=2))
