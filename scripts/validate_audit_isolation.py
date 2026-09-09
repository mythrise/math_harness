#!/usr/bin/env python3
"""Real Docker worker/TeX boundary checks using artificial files only."""
import argparse
from pathlib import Path
from cumcm_harness.common import (IntegrityError,ExecutionFailure,PaperCompilationFailure,
    digest,file_hash,read_json,write_json)
from cumcm_harness.contracts import validate
from cumcm_harness.sandbox import Executor,Limits
from cumcm_harness.tex_sandbox import compile_isolated,TEX_IMAGE


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--image',default='cumcm-egoharness:0.5.0-rc2')
    parser.add_argument('--tex-image',default=TEX_IMAGE)
    args=parser.parse_args();root=args.out.resolve()
    if root.exists() and any(root.iterdir()):raise IntegrityError('Use a new empty validation directory')
    root.mkdir(parents=True,exist_ok=True);data=root/'data';data.mkdir()
    executor=Executor(image=args.image);results=[]
    for name in ('cumcm_harness','json','numpy','sitecustomize'):
        bundle={'files':[{'path':name+'.py','content':'raise RuntimeError("ARTIFICIAL_SHADOW")'}],'notes':[],'algorithm_usage':[]}
        try:validate('bundle',bundle)
        except IntegrityError:results.append({'case':'bundle-shadow-'+name,'status':'PASS'})
        else:raise AssertionError('Shadow bundle was accepted')
    code=root/'startup-code';code.mkdir();(code/'cumcm_harness').mkdir()
    (code/'cumcm_harness/__init__.py').write_text('raise RuntimeError("ARTIFICIAL_WORKER_HIJACK")')
    (code/'json.py').write_text('raise RuntimeError("ARTIFICIAL_JSON_HIJACK")')
    (code/'main.py').write_text('''import sys,json,cumcm_harness
from pathlib import Path
out=Path(sys.argv[sys.argv.index('--out')+1])
assert str(cumcm_harness.__file__).startswith('/opt/cumcm/')
(out/'startup.json').write_text(json.dumps({'package':str(cumcm_harness.__file__),'json':str(json.__file__)}))
''')
    receipt=executor.execute(code,'main.py',data,root/'startup-out',[],Limits(seconds=15),logdir=root/'startup-logs')
    assert 'cumcm_harness/worker.py' in read_json(root/'startup-out/custom_dependencies.json')
    results.append({'case':'installed-worker-isolated-startup','status':'PASS','receipt_digest':digest(receipt)})
    for name,source,limit in [
        ('missing-receipt','import os;os._exit(0)',Limits(seconds=10)),
        ('invalid-receipt',"import os,sys\nfrom pathlib import Path\nout=Path(sys.argv[sys.argv.index('--out')+1])\n(out/'custom_dependencies.json').write_text('{invalid json')\nos._exit(0)",Limits(seconds=10)),
        ('output-bomb',"import sys\nfrom pathlib import Path\nout=Path(sys.argv[sys.argv.index('--out')+1])\nfor i in range(100): (out/(str(i)+'.txt')).write_text('x'*4096)",Limits(seconds=10,output_bytes=8192)),
        ('timeout','while True: pass',Limits(seconds=1))]:
        folder=root/name;folder.mkdir();(folder/'main.py').write_text(source)
        try:executor.execute(folder,'main.py',data,root/(name+'-out'),[],limit,logdir=root/(name+'-logs'))
        except (ExecutionFailure,IntegrityError) as exc:
            process=read_json(root/(name+'-logs/process_receipt.json'))
            if name=='timeout':assert process['status']=='TIMEOUT'
            if name=='output-bomb':assert process['status']=='OUTPUT_LIMIT'
            if name=='missing-receipt':assert 'mandatory custom_dependencies' in str(exc)
            if name=='invalid-receipt':assert 'Unreadable custom dependency receipt' in str(exc)
            results.append({'case':name,'status':'PASS','observed_process_status':process['status']})
        else:raise AssertionError(name+' was not blocked')
    # The sole host-read target is this newly created artificial marker.
    canary=root/'artificial-canary.txt';canary.write_text('ARTIFICIAL_HOST_CANARY_FOR_ISOLATION_TEST')
    safe=root/'safe-tex';safe.mkdir();(safe/'figures').mkdir()
    write_json(safe/'figures/figure.provenance.json',{'artificial':True})
    (safe/'main.tex').write_text(r'\documentclass{article}\usepackage{amsmath}\begin{document}$\begin{matrix}a&b\\c&d\end{matrix}$\end{document}')
    receipt=compile_isolated(safe,'main.tex',image=args.tex_image)
    assert not any(p.endswith('.json') for p in receipt['source_manifest'])
    first=file_hash(safe/'main.pdf')
    assert compile_isolated(safe,'main.tex',image=args.tex_image)==receipt and file_hash(safe/'main.pdf')==first
    results.append({'case':'tex-legal-matrix-and-immutable-replay','status':'PASS','receipt_digest':digest(receipt)})
    unsafe=root/'host-read-tex';unsafe.mkdir()
    (unsafe/'main.tex').write_text(r'\documentclass{article}\begin{document}\input{'+str(canary)+r'}\end{document}')
    try:compile_isolated(unsafe,'main.tex',image=args.tex_image)
    except PaperCompilationFailure:results.append({'case':'artificial-host-canary-not-mounted','status':'PASS'})
    else:raise AssertionError('Host canary was accessible to TeX')
    result={'status':'PASS','checks':results,'runtime':executor.probe(),'scope':'REAL_DOCKER_AND_TEX_NO_MODEL_OR_NETWORK_CALLS'}
    write_json(root/'summary.json',result);print('PASS',len(results),'real Docker/TeX boundary checks')


if __name__=='__main__':main()
