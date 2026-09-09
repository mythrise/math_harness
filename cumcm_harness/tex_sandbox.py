"""Dedicated TeX container: no host HOME, credentials, repository or network."""
from __future__ import annotations
import os,shutil,subprocess
from pathlib import Path
from .common import (Blocked,IntegrityError,InfrastructureUnavailable,UnknownExternalState,
    PaperCompilationFailure,digest,file_hash,read_json,write_json,tree_manifest,verify_tree)
from .process import clean_env,run_process

TEX_IMAGE='cumcm-egoharness-tex:0.3.1'


def probe(image=TEX_IMAGE):
    if not shutil.which('docker'):raise InfrastructureUnavailable('Docker is required for isolated TeX compilation')
    result=subprocess.run(['docker','image','inspect',image,'--format','{{.Id}}'],capture_output=True,text=True,timeout=20)
    if result.returncode:raise InfrastructureUnavailable('Build the dedicated TeX image first: '+image)
    return {'backend':'DOCKER_TEX','image':image,'image_id':result.stdout.strip()}


def compile_isolated(folder,main,*,image=TEX_IMAGE,timeout=180,output_bytes=30_000_000):
    folder=Path(folder).resolve();runtime=probe(image)
    from .paper import tex_filename
    tex_filename(main)
    if Path(main).name!=main:raise IntegrityError('TeX entry must be a file in the build root')
    candidates=[folder/main]
    from .paper_profile import STYLE_NAME, STYLE
    style=folder/STYLE_NAME
    if style.exists() or style.is_symlink():
        if style.is_symlink() or not style.is_file() or style.read_bytes()!=STYLE.encode('utf-8'):
            raise IntegrityError('Only the fingerprint-bound PaperKit style may enter TeX inputs')
        candidates.append(style)
    for name in ('code','figures'):
        base=folder/name
        if base.is_symlink():raise IntegrityError('TeX input directory cannot be a symlink')
        if base.exists():
            for rel in tree_manifest(base):
                path=base/rel
                allowed={'.pdf','.png','.svg'} if name=='figures' else {'.py','.json','.csv','.txt','.md','.yaml','.yml'}
                if name=='figures' and path.suffix.lower()=='.json':continue  # provenance/data sidecars are not compiler inputs
                if path.suffix.lower() not in allowed:raise IntegrityError('Unexpected TeX build input type')
                candidates.append(path)
    source={}
    for p in candidates:
        rel=p.relative_to(folder).as_posix();tex_filename(rel)
        if p.is_symlink() or not p.is_file():raise IntegrityError('TeX inputs must be ordinary files')
        source[rel]=file_hash(p)
    if len(source)>2000 or sum(p.stat().st_size for p in candidates)>64_000_000:raise IntegrityError('TeX source input limit')
    identity={'source':source,'main':main,'runtime':runtime,'timeout':timeout,'output_bytes':output_bytes,'contract':'isolated-tex/1'}
    base=folder/'_tex_builds'/digest(identity);state_path=base/'state.json';inputs=base/'inputs';out=base/'out'
    if any(',' in str(p) or '\n' in str(p) for p in (inputs,out)):raise IntegrityError('Unsafe TeX mount path')
    if state_path.exists():
        state=read_json(state_path)
        if state['status']=='RUNNING':raise UnknownExternalState('Unknown TeX build; reconcile the recorded container before recovery')
        if state['status']!='DONE':raise PaperCompilationFailure('This TeX source already failed; preserve it and revise the draft')
        verify_tree(inputs,source);verify_tree(out,state['output_manifest']);result=state['result']
    else:
        inputs.mkdir(parents=True,exist_ok=False);out.mkdir()
        for p in candidates:
            dest=inputs/p.relative_to(folder);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
        verify_tree(inputs,source)
        container='cumcm-tex-'+digest(str(base))[:20]
        write_json(state_path,{'status':'RUNNING','identity':identity,'container':container})
        receipts=[]
        for attempt in range(2):
            command=['docker','run','--rm','--name',container,'--network','none','--read-only','--cap-drop','ALL',
                '--security-opt','no-new-privileges','--pids-limit','128','--cpus','1','--memory','1024m','--memory-swap','1024m',
                '--user',f'{os.getuid()}:{os.getgid()}','--tmpfs','/tmp:rw,noexec,nosuid,size=128m',
                '--ulimit',f'fsize={output_bytes}:{output_bytes}',
                '--mount',f'type=bind,src={inputs},dst=/inputs,readonly','--mount',f'type=bind,src={out},dst=/out',
                '-e','HOME=/tmp','-e','TEXMFVAR=/tmp/texmf-var','-e','TEXMFCONFIG=/tmp/texmf-config','-e','TEXMFOUTPUT=/out',
                '--workdir','/inputs',runtime['image_id'],'-output-directory=/out',main]
            if any(',' in str(p) or '\n' in str(p) for p in (inputs,out)):raise IntegrityError('Unsafe TeX mount path')
            try:
                receipt=run_process(command,cwd=inputs,out=base/('pass-'+str(attempt)),env=clean_env(),timeout=timeout,
                                    output_watch=(out,output_bytes,2000))
            finally:
                subprocess.run(['docker','rm','-f',container],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
            receipts.append(receipt);verify_tree(inputs,source)
            if receipt['status']!='EXITED' or receipt['returncode']!=0:
                write_json(state_path,{'status':'FAILED','identity':identity,'receipts':receipts,'failure':'OBSERVED_COMPILER_EXIT'})
                raise PaperCompilationFailure('Isolated LaTeX compile failed; logs: '+str(base))
        pdf=out/Path(main).with_suffix('.pdf')
        if not pdf.is_file():
            write_json(state_path,{'status':'FAILED','identity':identity,'receipts':receipts,'failure':'MISSING_PDF'})
            raise PaperCompilationFailure('Compiler exited without a PDF')
        result={**runtime,'source_manifest':source,'output_manifest':tree_manifest(out),'receipts':receipts,
                'network':'NONE','host_mounts':'STAGED_INPUTS_AND_OUTPUT_ONLY','shell_escape':False}
        write_json(state_path,{'status':'DONE','identity':identity,'output_manifest':result['output_manifest'],'result':result})
    for suffix in ('.pdf','.aux','.log','.out'):
        path=out/Path(main).with_suffix(suffix)
        if path.is_file():shutil.copyfile(path,folder/path.name)
    return result
