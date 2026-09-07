"""Independent evaluator: no imports from MOSAIC or its simulator/metrics.
The exact reference enumerates this six-job finite domain only.
"""
from pathlib import Path
from itertools import permutations
import argparse,json
import numpy as np

def decode(x,n):
    active=[i for i in range(n) if x[i]>=.5]
    if not active:active=[max(range(n),key=lambda i:x[i])]
    return [i for i in sorted(range(n),key=lambda i:(x[n+i],i)) if i in active]
def objective(spec,order):
    n=len(spec['values']);previous=n;t=0.;reward=0.
    for j in order:
        t+=spec['setup'][previous][j]+spec['process'][j]
        reward+=max(0.,spec['values'][j]-spec['penalty'][j]*max(t-spec['dues'][j],0.));previous=j
    return [-reward,t]
def hv(F,r):
    y=r[1];area=0.
    for x,v in sorted(set(tuple(map(float,f)) for f in F)):
        if x>r[0] or v>r[1]:raise ValueError('reference does not dominate point')
        if v<y:area+=(r[0]-x)*(y-v);y=v
    return area

def evaluate_payload(spec,a,budget):
    n=len(spec['values']);X=np.asarray(a['X'],float);F=np.asarray(a['F'],float)
    LX=np.asarray(a['ledger_X'],float);LF=np.asarray(a['ledger_F'],float)
    if X.ndim!=2 or X.shape[1]!=2*n or F.shape!=(len(X),2) or not len(X):raise ValueError('bad front shapes')
    if LX.shape!=(budget,2*n) or LF.shape!=(budget,2) or a['budget_spent']!=budget:raise ValueError('paid ledger mismatch')
    if any(not np.isfinite(v).all() for v in (X,F,LX,LF)) or np.any(X<0) or np.any(X>1) or np.any(LX<0) or np.any(LX>1):raise ValueError('invalid values/bounds')
    expected=np.array([objective(spec,decode(x,n)) for x in LX])
    if not np.allclose(expected,LF,rtol=0,atol=1e-9):raise ValueError('paid objectives not independently reproducible')
    checks=[{'name':'independent_objective_recompute','passed':True,'detail':'all paid objective vectors recomputed in independent Python implementation'}]
    for x,f in zip(X,F):
        if not np.allclose(objective(spec,decode(x,n)),f,rtol=0,atol=1e-9):raise ValueError('fabricated front objective')
        if not np.any(np.all(LX==x,axis=1)&np.all(np.isclose(LF,f,rtol=0,atol=1e-9),axis=1)):raise ValueError('front includes unpaid point')
        if np.any(np.all(LF<=f,axis=1)&np.any(LF<f-1e-9,axis=1)):raise ValueError('front contains dominated paid observation')
    checks.append({'name':'budget_and_archive','passed':True,'detail':'FE count and paid-observation archive validated'})
    T=sum(spec['process'])+n*max(max(row) for row in spec['setup'])+1;r=[1.,float(T)]
    exact=[objective(spec,p) for k in range(1,n+1) for p in permutations(range(n),k)]
    score=hv(F,r)/hv(exact,r)
    if not 0<=score<=1+1e-10:raise ValueError('impossible normalized hypervolume')
    index=a['selected_index']
    if type(index)!=int or not 0<=index<len(F):raise ValueError('invalid selection')
    utility=-F[:,0]/sum(spec['values'])-F[:,1]/T
    if index!=int(np.argmax(utility)):raise ValueError('recommendation violates frozen utility rule')
    reward=-float(F[index,0]);duration=float(F[index,1])
    checks.append({'name':'exact_finite_domain','passed':True,'detail':f'enumerated {len(exact)} feasible nonempty ordered subsets; not a global domain claim'})
    return {'score':float(score),'valid':True,'metric':'normalized_hv','checks':checks,'question_coverage':['q1','q2'],
            'measurements':[{'id':'hv','value':float(score),'unit':'ratio','question_id':'q1','description':'normalized dominated hypervolume'},
              {'id':'reward','value':reward,'unit':'reward_units','question_id':'q2','description':'reward of representative selected schedule'},
              {'id':'duration','value':duration,'unit':'minutes','question_id':'q2','description':'duration of representative selected schedule'}]}

def invalid(message):
    return {'score':0.,'valid':False,'metric':'normalized_hv','checks':[{'name':'input_validation','passed':False,'detail':message}],
            'question_coverage':['q1','q2'],'measurements':[{'id':'invalid','value':0.,'unit':'none','question_id':'q1','description':'invalid answer, never accepted as a measured result'}]}

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--answer',type=Path,required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--budget',type=int,required=True);p.add_argument('--variant',required=True);a=p.parse_args()
    try:
        spec=json.loads((a.input/'public/problem.json').read_text());ans=json.loads((a.answer/'answer.json').read_text());result=evaluate_payload(spec,ans,a.budget)
    except (KeyError,ValueError,TypeError,IndexError,FileNotFoundError) as e:result=invalid(type(e).__name__+': '+str(e))
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'evaluation.json').write_text(json.dumps(result,allow_nan=False))
if __name__=='__main__':main()
