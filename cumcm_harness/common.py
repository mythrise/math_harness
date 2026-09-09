"""Small trusted core: canonical JSON, safe paths, atomic files and digests."""
from __future__ import annotations
import hashlib, json, math, os, platform, re, tempfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
class HarnessError(RuntimeError): pass
class Blocked(HarnessError): pass
class IntegrityError(HarnessError): pass
class InfrastructureUnavailable(Blocked): pass
class UnknownExternalState(Blocked): pass
class BudgetExhausted(Blocked): pass
class DeadlineReached(Blocked): pass
class PaperReserveReached(DeadlineReached): pass
class ExecutionFailure(Blocked):
    """A subprocess is known to have stopped with an unsuccessful outcome."""
class PaperCompilationFailure(ExecutionFailure): pass
class ScientificRejection(Blocked):
    def __init__(self,message,records=()):
        super().__init__(message);self.records=list(records)

def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()
def file_hash(path: Path) -> str:
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def read_json(path: Path) -> Any:
    def reject(x): raise IntegrityError(f'Nonfinite JSON value: {x}')
    return json.loads(Path(path).read_text('utf-8'), parse_constant=reject)
def atomic_write(path: Path, data: str|bytes) -> None:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    b=data.encode('utf-8') if isinstance(data,str) else data
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(b); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def write_json(path: Path,value: Any) -> None:
    atomic_write(path,json.dumps(value,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n')
def safe_rel(s: str) -> str:
    p=PurePosixPath(s)
    if not s or '\\' in s or '\x00' in s or ':' in s or p.is_absolute() or any(x in ('..','.') or x.startswith('.') for x in p.parts):
        raise IntegrityError(f'Unsafe relative path: {s!r}')
    if str(p)!=s or len(s)>240: raise IntegrityError(f'Noncanonical path: {s!r}')
    return s

def under(root: Path, rel: str) -> Path:
    safe_rel(rel); p=root/rel
    if not p.resolve().is_relative_to(root.resolve()): raise IntegrityError('Path or symlink escapes root')
    return p

def tree_manifest(root: Path) -> dict[str,str]:
    out={}
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink(): raise IntegrityError(f'Symlink forbidden: {p}')
        if p.is_file(): out[p.relative_to(root).as_posix()]=file_hash(p)
    return out

def verify_tree(root: Path, expected: dict[str,str]) -> None:
    if tree_manifest(root)!=expected: raise IntegrityError(f'Changed artifact tree: {root.name}')

def finite(x: Any) -> float:
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x):
        raise IntegrityError('Expected finite numeric value')
    return float(x)

def environment() -> dict:
    import importlib.metadata
    versions={}
    for x in ('numpy','scipy','scikit-learn','pytest','numba','matplotlib','jsonschema','pandas'):
        try: versions[x]=importlib.metadata.version(x)
        except importlib.metadata.PackageNotFoundError: versions[x]='NOT_INSTALLED'
    return {'python':platform.python_version(),'platform':platform.platform(),'machine':platform.machine(),
            'cpu_count':os.cpu_count(),'packages':versions}

def verify_vendor():
    entries=read_json(ROOT/'vendor/MANIFEST.json')
    for entry in entries:
        if file_hash(under(ROOT,entry['path']))!=entry['sha256']:raise IntegrityError('Vendor mismatch: '+entry['path'])
    return {'status':'PASS','files':len(entries),'manifest_sha256':file_hash(ROOT/'vendor/MANIFEST.json')}
