"""Verify appendix bytes and reproduce one frozen seed per method inside Docker.

Only the extracted support bundle, an empty input directory and a fresh output
directory are mounted. Reproduction consumes the bundled dependency copies.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from cumcm_harness.common import Blocked,IntegrityError,read_json,write_json,file_hash,tree_manifest
from cumcm_harness.intake import extract_zip
from cumcm_harness.sandbox import Executor,Limits
from cumcm_harness.submission_manifest import verify_seal

ENTRY='''import argparse,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--out');p.add_argument('--candidate');p.add_argument('--seed');p.add_argument('--variant');a=p.parse_args()
subprocess.run([sys.executable,'-I','-B',str(Path(__file__).with_name('reproduce.py')),
 '--trust-reviewed-code','--candidate',a.candidate,'--phase','confirmation','--seed',a.seed,
 '--variant',a.variant,'--out',a.out],check=True)
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();root=args.workspace.resolve();out=args.out.resolve()
    if out.exists():raise Blocked('Use a new reproduction directory')
    seal=read_json(root/'deliverables/submission-manifest.json');verify_seal(root,seal)
    out.mkdir(parents=True);code=out/'support';code.mkdir()
    extract_zip(root/'deliverables/support.zip',code)
    expected=read_json(code/'manifest.json')['files']
    for name,sha in expected.items():
        if file_hash(code/name)!=sha:raise IntegrityError('Support manifest mismatch: '+name)
    inventory=read_json(root/'paper/source_inventory.json')
    for name in inventory:
        if (root/'paper'/name).read_bytes()!=(code/name).read_bytes():
            raise IntegrityError('Appendix source differs from support: '+name)
    wrapper=code/'validate_reproduce.py'
    if wrapper.exists():raise IntegrityError('Reproduction driver name conflicts with bundle')
    wrapper.write_text(ENTRY)
    source_before=tree_manifest(code);data=out/'empty-input';data.mkdir()
    rows=read_json(code/'results/confirmation.json')['rows'];selected={}
    for row in rows:selected.setdefault(row['candidate'],row)
    executor=Executor();checks=[]
    for candidate,row in sorted(selected.items()):
        result=out/candidate
        receipt=executor.execute(code,wrapper.name,data,result,
            ['--candidate',candidate,'--seed',str(row['seed']),'--variant',row['variant']],
            Limits(seconds=180),logdir=out/(candidate+'-logs'))
        matched={}
        for relative in ('solver/answer.json','evaluation/evaluation.json'):
            original=code/'jobs'/row['job_id']/relative
            matched[relative]=original.read_bytes()==(result/relative).read_bytes()
        if not all(matched.values()):raise IntegrityError('Independent bundle reproduction changed answer/evaluation')
        checks.append({'candidate':candidate,'seed':row['seed'],'job_id':row['job_id'],
                       'matches':matched,'execution':receipt})
    if tree_manifest(code)!=source_before:raise IntegrityError('Read-only support source changed')
    verify_seal(root,seal)
    report={'status':'PASS','scope':'ONE_FROZEN_CONFIRMATION_SEED_PER_METHOD_REAL_DOCKER',
            'source_inventory_count':len(inventory),'all_appendix_source_bytes_match':True,
            'checks':checks,'runtime':executor.probe(),'model_calls':0,'network_access':False}
    write_json(out/'summary.json',report)
    print('PASS:',len(checks),'methods; appendix source files:',len(inventory))


if __name__=='__main__':main()
