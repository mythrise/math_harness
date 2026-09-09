from __future__ import annotations
import hashlib, json, os, re, subprocess, signal, unicodedata
from pathlib import Path, PurePosixPath

class Blocked(RuntimeError):
    """Required evidence/configuration was missing; never silently pass."""

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def load(path: Path):
    try:
        return json.loads(path.read_text('utf-8'),parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    except (OSError,ValueError) as e: raise Blocked(f'Cannot read JSON: {path.name}: {e}') from e

def save(path: Path,obj: object) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    os.replace(tmp,path)

def safe_rel(value: str) -> str:
    if not isinstance(value,str) or not value or '\\' in value or ':' in value:
        raise Blocked('Expected a POSIX relative path')
    p=PurePosixPath(value)
    if p.is_absolute() or any(x in ('','.','..') for x in value.split('/')):
        raise Blocked('Absolute/dot/traversal path rejected')
    if any(ord(c)<32 or c in '{}%#~^$&' or unicodedata.category(c)=='Cf' for c in value):
        raise Blocked('Unsafe path characters')
    return value

def under(root: Path,value: str, *,must_exist=True) -> Path:
    value=safe_rel(value);root=root.resolve();p=root/value
    cur=root
    for part in PurePosixPath(value).parts:
        cur=cur/part
        if cur.is_symlink(): raise Blocked('Symlinks are not accepted as input artifacts')
    if not p.resolve().is_relative_to(root): raise Blocked('Path escaped project')
    if must_exist and not p.exists(): raise Blocked(f'Input missing: {value}')
    return p

def esc(text: str) -> str:
    table={'\\':r'\textbackslash{}','{':r'\{','}':r'\}','%':r'\%','&':r'\&',
           '#':r'\#','_':r'\_','$':r'\$','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    return ''.join(table.get(c,c) for c in str(text))

def compact(text: str) -> str:
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',text))

def run_bounded(argv: list[str],cwd: Path,timeout: int=120) -> tuple[int,str]:
    env={k:v for k,v in os.environ.items() if k in ('PATH','SystemRoot','WINDIR','TMP','TEMP','HOME','USERPROFILE','LANG','LC_ALL')}
    env.update({'openin_any':'p','openout_any':'p','shell_escape':'f','SOURCE_DATE_EPOCH':'1788912000'})
    proc=subprocess.Popen(argv,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,encoding='utf-8',errors='replace',start_new_session=(os.name!='nt'))
    try: text,_=proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name!='nt': os.killpg(proc.pid,signal.SIGKILL)
        else: proc.kill()
        text,_=proc.communicate()
        raise Blocked(f'Timeout after {timeout}s: {Path(argv[0]).name}')
    return proc.returncode,text


def profile_digest() -> str:
    """Pin actual adapter/checker/style bytes, not just a marketing version."""
    root=Path(__file__).parent
    selected=sorted([*root.glob('*.py'),*root.joinpath('assets').glob('*')])
    return digest({p.relative_to(root).as_posix():sha256(p) for p in selected if p.is_file()})
