"""Independent executable tests for the supplied synthetic demo evaluator."""
from pathlib import Path
import argparse,json,copy
from evaluate import evaluate_payload,decode,objective

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--answer',type=Path,required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--budget',type=int,required=True);p.add_argument('--variant',required=True);a=p.parse_args()
    spec=json.loads((a.input/'public/problem.json').read_text());ans=json.loads((a.answer/'answer.json').read_text());cases=[]
    assert evaluate_payload(spec,ans,a.budget)['valid'];cases.append({'name':'valid_paid_front','passed':True,'detail':'accepted independently recomputed baseline'})
    bad=copy.deepcopy(ans);bad['F'][0][0]-=10000
    try:evaluate_payload(spec,bad,a.budget)
    except ValueError:pass
    else:raise AssertionError('fabricated front accepted')
    cases.append({'name':'fabricated_objective_rejected','passed':True,'detail':'injected false reward triggers failure'})
    bad=copy.deepcopy(ans);bad['budget_spent']-=1
    try:evaluate_payload(spec,bad,a.budget)
    except ValueError:pass
    else:raise AssertionError('false FE count accepted')
    cases.append({'name':'wrong_FE_rejected','passed':True,'detail':'ledger accounting cannot be changed by a reported score'})
    n=len(spec['values']);order=decode([0.]*(2*n),n)
    assert order==[0] and objective(spec,order)[1]>0
    cases.append({'name':'empty_mask_is_one_job','passed':True,'detail':'decoder feasible nonempty subset boundary verified'})
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'tests.json').write_text(json.dumps({'cases':cases,'all_passed':True}))
if __name__=='__main__':main()
