#!/usr/bin/env python3
"""Reproduce a frozen solver and evaluator from a support bundle.
Use an isolated environment. This script does not run unless explicitly trusted.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',default='baseline');ap.add_argument('--phase',choices=['development','confirmation'],default='confirmation')
    ap.add_argument('--seed',type=int,default=None);ap.add_argument('--variant',default=None);ap.add_argument('--original-input',type=Path)
    ap.add_argument('--out',type=Path,default=Path('reproduced'));ap.add_argument('--trust-reviewed-code',action='store_true');args=ap.parse_args()
    root=Path(__file__).resolve().parent
    if not args.trust_reviewed_code:ap.error('Review code first; run in an isolated environment and explicitly pass --trust-reviewed-code')
    manifest=json.loads((root/'manifest.json').read_text('utf-8'))
    for rel,expected in manifest['files'].items():
        p=root/rel
        if not p.is_file() or sha(p)!=expected:raise SystemExit('Integrity mismatch: '+rel)
    protocol=json.loads((root/'protocol.json').read_text('utf-8'))
    seed=args.seed if args.seed is not None else protocol[args.phase+'_seeds'][0]
    if seed not in protocol[args.phase+'_seeds']:raise SystemExit('Seed is outside frozen phase protocol')
    code=root/'code'/args.candidate
    if not code.is_dir() or not code.resolve().is_relative_to((root/'code').resolve()):raise SystemExit('Unknown candidate')
    data=root/'inputs'/args.phase
    if not data.is_dir():
        if args.original_input is None:raise SystemExit('Original contest input excluded. Supply --original-input DIR matching input_manifest.json')
        data=args.original_input
    inputs=json.loads((root/'input_manifest.json').read_text('utf-8'))[args.phase]
    for rel,h in inputs.items():
        if not (data/rel).is_file() or sha(data/rel)!=h:raise SystemExit('Original input mismatch: '+rel)
    if args.out.exists() and any(args.out.iterdir()):raise SystemExit('Output must be a new/empty directory')
    args.out.mkdir(parents=True,exist_ok=True);out=args.out.resolve()
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','SYSTEMROOT','TMPDIR')}
    env.update(PYTHONPATH=str(root/'code/dependencies'),PYTHONHASHSEED='0',PYTHONDONTWRITEBYTECODE='1',
        OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',NUMBA_CACHE_DIR=str(out/'numba-cache'))
    variant=args.variant or ('baseline' if args.candidate=='baseline' else 'full')
    common=['--seed',str(seed),'--budget',str(protocol['fe_budget']),'--variant',variant]
    (out/'solver').mkdir();(out/'evaluation').mkdir()
    subprocess.run([sys.executable,'-B','-m','cumcm_harness.worker',str(code/'main.py'),'--input',str(data.resolve()),'--out',str(out/'solver'),*common],env=env,check=True,timeout=600)
    with tempfile.TemporaryDirectory(prefix='cumcm-eval-data-') as td:
        evaluation_data=Path(td);shutil.copytree(data,evaluation_data/'public')
        private=root/'private'/args.phase
        if private.exists():shutil.copytree(private,evaluation_data/'private')
        else:(evaluation_data/'private').mkdir()
        subprocess.run([sys.executable,'-B','-m','cumcm_harness.worker',str(root/'code/verifier/evaluate.py'),
                        '--input',str(evaluation_data),'--out',str(out/'evaluation'),'--answer',str(out/'solver'),*common],env=env,check=True,timeout=600)
    print((out/'evaluation/evaluation.json').read_text('utf-8'))
if __name__=='__main__':main()
