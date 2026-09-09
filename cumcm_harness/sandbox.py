"""Solver/evaluator isolation. Docker is mandatory for live model-generated code.
Trusted local mode has a content allowlist and is reserved for supplied demos/tests.
"""
from __future__ import annotations
import os, shutil, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
from .common import *
from .process import run_process, clean_env

@dataclass(frozen=True)
class Limits:
    seconds: float=120
    cpu_threads: int=1
    memory_mb: int=2048
    output_bytes: int=30_000_000
    pids: int=128
    def check(self):
        if self.seconds<=0 or self.cpu_threads<1 or self.memory_mb<128 or self.output_bytes<1024:raise IntegrityError('Invalid resource limits')

class Executor:
    def __init__(self,kind='docker',image='cumcm-egoharness:0.3.0',trusted_hashes=None,*,test_scratch=False):
        if kind not in ('docker','trusted-local'):raise ValueError(kind)
        self.kind=kind;self.image=image;self.trusted_hashes=set(trusted_hashes or []);self.test_scratch=test_scratch
    def probe(self):
        if self.kind=='trusted-local':return {'backend':'TRUSTED_LOCAL_NOT_SANDBOX'}
        if hasattr(self,'_resolved_backend'):return dict(self._resolved_backend)
        if not shutil.which('docker'):raise InfrastructureUnavailable('Docker is required for untrusted generated code; no local fallback')
        r=subprocess.run(['docker','image','inspect',self.image,'--format','{{.Id}}'],capture_output=True,text=True,timeout=20)
        if r.returncode:raise InfrastructureUnavailable(f'Docker image missing or daemon unavailable: {self.image}')
        self._resolved_backend={'backend':'DOCKER','image_id':r.stdout.strip()}
        return dict(self._resolved_backend)
    def execute(self,code:Path,entry:str,data:Path,out:Path,args:list[str],limits:Limits,*,answer:Path|None=None,logdir:Path|None=None):
        limits.check();safe_rel(entry)
        if not (code/entry).is_file():raise IntegrityError(f'Missing entrypoint {entry}')
        cm=tree_manifest(code);dm=tree_manifest(data);am=tree_manifest(answer) if answer else None
        tree_id=digest(cm);logdir=logdir or out.parent/'logs';out.mkdir(parents=True,exist_ok=True)
        if any(out.iterdir()):raise UnknownExternalState('Output directory is not empty; no overwrite/reuse without verified receipt')
        backend=self.probe();env=clean_env(threads=limits.cpu_threads);container_name='cumcm-'+digest(str(out.resolve()))[:20]
        if self.kind=='trusted-local':
            if tree_id not in self.trusted_hashes:raise Blocked('Local execution refused: code is not allowlisted supplied demo/test code')
            # Local mode is not a security sandbox. Never use on model-generated code.
            env['PYTHONPATH']=str(ROOT);env['NUMBA_CACHE_DIR']=str(Path(os.getenv('TMPDIR','/tmp'))/'cumcm-numba-cache')
            cmd=[sys.executable,'-s','-m','cumcm_harness.worker',str(code/entry),'--input',str(data.resolve()),'--out',str(out.resolve()),*args]
            if answer:cmd+=['--answer',str(answer.resolve())]
        else:
            for p in (code,data,out,*([answer] if answer else [])):
                if any(x in str(p.resolve()) for x in (',','\n')):raise IntegrityError('Unsupported mount path')
            cmd=['docker','run','--rm','--name',container_name,'--network','none','--read-only','--cap-drop','ALL',
                 '--security-opt','no-new-privileges','--pids-limit',str(limits.pids),'--cpus',str(limits.cpu_threads),
                 '--memory',f'{limits.memory_mb}m','--memory-swap',f'{limits.memory_mb}m','--user',f'{os.getuid()}:{os.getgid()}',
                 '--tmpfs','/tmp:rw,noexec,nosuid,size=256m','--ulimit',f'fsize={limits.output_bytes}:{limits.output_bytes}',
                 '--mount',f'type=bind,src={code.resolve()},dst=/code,readonly',
                 '--mount',f'type=bind,src={data.resolve()},dst=/data,readonly',
                 '--mount',f'type=bind,src={out.resolve()},dst=/out',
                 '-e','HOME=/tmp','-e','PYTHONHASHSEED=0','-e','NUMBA_CACHE_DIR=/tmp/numba',
                 '-e',f'OMP_NUM_THREADS={limits.cpu_threads}','-e',f'OPENBLAS_NUM_THREADS={limits.cpu_threads}',
                 '-e',f'MKL_NUM_THREADS={limits.cpu_threads}','-e','MPLBACKEND=Agg','--workdir','/code']
            if self.test_scratch:cmd+=['--tmpfs','/scratch:rw,exec,nosuid,nodev,size=256m']
            if answer:cmd+=['--mount',f'type=bind,src={answer.resolve()},dst=/answer,readonly']
            # Isolated startup resolves the trusted installed package before the
            # worker deliberately exposes the validated solver's own imports.
            cmd += [backend['image_id'],'python','-I','-B','-m','cumcm_harness.worker',f'/code/{entry}','--input','/data','--out','/out',*args]
            if answer:cmd+=['--answer','/answer']
        try:r=run_process(cmd,cwd=code,out=logdir,env=env,timeout=limits.seconds,output_watch=(out,limits.output_bytes,2000))
        finally:
            if self.kind=='docker':subprocess.run(['docker','rm','-f',container_name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
        verify_tree(code,cm);verify_tree(data,dm)
        if answer:verify_tree(answer,am)
        if r['status']!='EXITED' or r['returncode']!=0:raise ExecutionFailure(f'Execution failed: {r["status"]}, rc={r["returncode"]}; {logdir}')
        m=tree_manifest(out)
        if len(m)>1000 or sum((out/k).stat().st_size for k in m)>limits.output_bytes:raise ExecutionFailure('Output limit exceeded')
        if 'custom_dependencies.json' not in m:raise ExecutionFailure('Missing mandatory custom_dependencies.json worker receipt')
        try:dependencies=read_json(out/'custom_dependencies.json')
        except (ValueError,OSError) as exc:
            raise IntegrityError('Unreadable custom dependency receipt after observed process exit') from exc
        if not isinstance(dependencies,dict) or any(not isinstance(k,str) or not isinstance(v,str) or len(v)!=64 for k,v in dependencies.items()):
            raise IntegrityError('Invalid custom dependency receipt')
        return {**r,**backend,'code_digest':tree_id,'input_digest':digest(dm),'output_manifest':m,'trusted_test_scratch':self.test_scratch}

def resource_gate(plan:dict,config:dict):
    r=plan['resources'];fail=[]
    if r['cpu_threads']>config['cpu_threads']:fail.append('requested CPU threads exceed frozen per-job cap')
    if r['memory_mb']>config['memory_mb']:fail.append('requested memory exceeds per-job cap')
    if r['expected_seconds']>config['trial_timeout']:fail.append('trial estimate exceeds timeout; split job')
    if r['expected_seconds']>300 and not (r['row_sharding'] and r['checkpointing']):fail.append('long jobs require row shards and checkpoints')
    if not r['fold_invariant_precompute']:fail.append('declare/precompute fold-invariant work once')
    if config['workers']*config['cpu_threads']>config['total_cpu_threads']:fail.append('CPU oversubscription')
    if config['workers']*config['memory_mb']>config['total_memory_mb']:fail.append('memory oversubscription')
    if fail:raise ScientificRejection('RESOURCE_GATE: '+'; '.join(fail))
    return {'status':'PASS','human_can_override':False,'workers':config['workers'],'threads_per_worker':config['cpu_threads'],
            'long_job_checkpoint_contract':'DECLARED_NOT_DYNAMICALLY_PROVEN'}
