"""Bounded subprocess execution. No shell strings and no quiet timeout fallback."""
from __future__ import annotations
import os, signal, stat, subprocess, time
from pathlib import Path
from .common import *

def terminate(p):
    if p.poll() is not None:return
    try: os.killpg(p.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    p.wait(timeout=10)

def output_usage(root,byte_limit,file_limit):
    """Bound traversal itself, and never follow an output symlink or special file."""
    size=0;count=0;pending=[Path(root)]
    while pending:
        folder=pending.pop()
        for path in folder.iterdir():
            info=path.lstat();count+=1
            if count>file_limit:return False,size,count
            if stat.S_ISDIR(info.st_mode):pending.append(path)
            elif stat.S_ISREG(info.st_mode):size+=info.st_size
            else:return False,size,count
            if size>byte_limit:return False,size,count
    return True,size,count

def run_process(argv:list[str], *, cwd:Path, out:Path, env:dict[str,str], timeout:float,
                stdin:str|None=None, max_log_bytes=8_000_000, output_watch=None) -> dict:
    if not argv or not all(isinstance(x,str) for x in argv):raise IntegrityError('Command must be an argument vector')
    if timeout<=0:raise IntegrityError('Positive timeout required')
    out.mkdir(parents=True,exist_ok=True)
    stdout=out/'stdout.log';stderr=out/'stderr.log';start=time.monotonic()
    input_path=out/'stdin.txt'
    if stdin is not None:atomic_write(input_path,stdin)
    with stdout.open('wb') as so, stderr.open('wb') as se, (input_path.open('rb') if stdin is not None else open(os.devnull,'rb')) as si:
        p=subprocess.Popen(argv,cwd=cwd,env=env,stdin=si,stdout=so,stderr=se,start_new_session=True)
        state='EXITED'
        try:
            while p.poll() is None:
                if time.monotonic()-start>timeout:state='TIMEOUT';terminate(p);break
                if stdout.stat().st_size+stderr.stat().st_size>max_log_bytes:state='LOG_LIMIT';terminate(p);break
                if output_watch is not None:
                    try:within,_,_=output_usage(*output_watch)
                    except FileNotFoundError:within=True # transient file rename; final scan still mandatory
                    if not within:state='OUTPUT_LIMIT';terminate(p);break
                time.sleep(.05)
        except BaseException:
            terminate(p);raise
    if state=='EXITED' and stdout.stat().st_size+stderr.stat().st_size>max_log_bytes:state='LOG_LIMIT'
    if output_watch is not None and not output_usage(*output_watch)[0]:state='OUTPUT_LIMIT'
    result={'argv':argv,'returncode':p.returncode,'status':state,'seconds':time.monotonic()-start,
            'stdout_sha256':file_hash(stdout),'stderr_sha256':file_hash(stderr)}
    write_json(out/'process_receipt.json',result)
    return result

BASE_ENV=('PATH','HOME','USER','LANG','LC_ALL','TMPDIR','SYSTEMROOT','SSL_CERT_FILE','SSL_CERT_DIR',
          'REQUESTS_CA_BUNDLE','http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','no_proxy')
def clean_env(*,provider=False,threads=1):
    env={k:v for k,v in os.environ.items() if k in BASE_ENV}
    env.update({'PYTHONHASHSEED':'0','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':str(threads),
                'MKL_NUM_THREADS':str(threads),'OPENBLAS_NUM_THREADS':str(threads),
                'NUMEXPR_NUM_THREADS':str(threads),'MPLBACKEND':'Agg'})
    if provider:
        keys=('CODEX_HOME','CODEX_API_KEY','OPENAI_API_KEY','OPENAI_BASE_URL',
              'ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL','CLAUDE_CONFIG_DIR','CLAUDE_CODE_OAUTH_TOKEN')
        env.update({k:v for k,v in os.environ.items() if k in keys})
    return env
