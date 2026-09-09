#!/usr/bin/env python3
"""Run the complete tests and numerical library diagnostics in isolated Docker.

This host-side script only snapshots source and orchestrates the existing executor.
No solver, model credential, Docker socket or writable source tree enters a trial.
"""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path
from cumcm_harness.common import ROOT,Blocked,digest,read_json,tree_manifest,verify_vendor,write_json
from cumcm_harness.sandbox import Executor,Limits


ENTRY = '''import argparse,json,shutil
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--input');p.add_argument('--out',required=True)
p.add_argument('--mode',choices=['tests','lab'],required=True)
p.add_argument('--seeds',type=int,default=12)
p.add_argument('--seed-start',type=int,default=201)
a=p.parse_args()
if a.mode=='tests':
    import subprocess,sys
    scratch=Path('/scratch/pytest')
    command="import sys;sys.path.insert(0,'/code');import pytest;raise SystemExit(pytest.main(sys.argv[1:]))"
    rc=subprocess.call([sys.executable,'-I','-B','-c',command,'/code/tests','-q','-p','no:cacheprovider',
        '--basetemp='+str(scratch),'--junitxml='+str(Path(a.out)/'pytest.xml')])
    (Path(a.out)/'test-result.json').write_text(json.dumps({'exit_code':int(rc),'backend':'DOCKER'}))
    shutil.rmtree(scratch,ignore_errors=True)
    raise SystemExit(rc)
else:
    from cumcm_harness.algorithm_lab import run
    result=run(a.out,seeds=a.seeds,seed_start=a.seed_start)
    print(json.dumps({k:result[k] for k in ['status','rows','seconds','external_candidates_run','global_promotions']}))
    if result['status']!='LOCAL_SMOKE_COMPLETED':raise SystemExit(2)
'''


def numeric_content(value):
    if isinstance(value,dict):return {k:numeric_content(v) for k,v in value.items() if k!='seconds'}
    if isinstance(value,list):return [numeric_content(v) for v in value]
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--image',default='cumcm-egoharness:0.3.0')
    p.add_argument('--test-image',default='cumcm-egoharness:0.3.0-test')
    p.add_argument('--seeds',type=int,default=12)
    p.add_argument('--seed-start',type=int,default=201)
    p.add_argument('--seconds',type=int,default=900)
    args=p.parse_args()
    if not 2<=args.seeds<=30 or args.seed_start<0:p.error('Require 2..30 seeds and a nonnegative seed-start')
    root=args.out.resolve()
    if root.exists() and any(root.iterdir()):raise Blocked('Use a new empty validation directory; prior evidence is preserved')
    root.mkdir(parents=True,exist_ok=True)
    before=verify_vendor();code=root/'code';code.mkdir();data=root/'data';data.mkdir()
    labcode=root/'lab-code';labcode.mkdir()
    for name in ('cumcm_harness','tests','vendor','configs','schemas','examples','templates','third_party'):
        shutil.copytree(ROOT/name,code/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.nbc','*.nbi','.DS_Store'))
    shutil.copy2(ROOT/'pyproject.toml',code/'pyproject.toml')
    (code/'validate.py').write_text(ENTRY)
    # Numerical diagnostics import the installed production image, not the
    # source snapshot used for the complete repository unit tests.
    (labcode/'validate.py').write_text(ENTRY)
    limits=Limits(seconds=args.seconds,cpu_threads=1,memory_mb=2048)
    runtime=Executor(image=args.image);test=Executor(image=args.test_image,test_scratch=True)
    protocol={'scope':'DOCKER_TESTS_AND_BOUNDED_NUMERICAL_DIAGNOSTICS_NOT_LLM_END_TO_END',
        'source_manifest':tree_manifest(code),'vendor':before,'seeds':list(range(args.seed_start,args.seed_start+args.seeds)),
        'runtime':runtime.probe(),'test_runtime':test.probe(),'limits':vars(limits),
        'repeat_policy':'Two identical complete numerical runs; compare every result and diagnostic excluding elapsed seconds'}
    write_json(root/'protocol.json',protocol)
    receipts={}
    for label,executor,mode in [('tests',test,'tests'),('lab-1',runtime,'lab'),('lab-2',runtime,'lab')]:
        print('START '+label,flush=True)
        receipt=executor.execute(code if mode=='tests' else labcode,'validate.py',data,root/label,
            ['--mode',mode,'--seeds',str(args.seeds),'--seed-start',str(args.seed_start)],
            limits,logdir=root/(label+'-logs'))
        write_json(root/(label+'-receipt.json'),receipt);receipts[label]=receipt
        print('PASS '+label,flush=True)
    first=read_json(root/'lab-1/summary.json');second=read_json(root/'lab-2/summary.json')
    repeated={name:numeric_content(read_json(root/'lab-1'/name))==numeric_content(read_json(root/'lab-2'/name))
              for name in ('raw_results.json','diagnostics.json')}
    expected_rows=args.seeds*46+min(args.seeds,4)*3
    if first['rows']!=expected_rows or second['rows']!=expected_rows or not all(repeated.values()):
        write_json(root/'reproducibility.json',repeated)
        raise Blocked('Incomplete or non-reproducible numerical matrix; inspect preserved runs')
    if verify_vendor()!=before:raise Blocked('Vendor verification changed during validation')
    summary={'status':'PASS','protocol_digest':digest(protocol),'rows_per_run':expected_rows,
        'numerical_runs':2,'diagnostics_per_run':len(first['diagnostics']),'reproducibility':repeated,
        'external_candidates_run':0,'global_promotions':0,
        'scope':protocol['scope'],'receipts':{name:digest(value) for name,value in receipts.items()}}
    write_json(root/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
