"""Sandbox entry wrapper; records imported code AND runtime-read custom assets.

The Python audit hook is dependency observation, not a security boundary. Native
extensions may read files without emitting a Python open event; isolated support
bundle reproduction remains a required acceptance check.
"""
from __future__ import annotations
import os, runpy, sys
from pathlib import Path
from .common import ROOT, Blocked, file_hash, write_json

class DependencyReads:
    def __init__(self, root: Path):
        self.root=root.resolve();self.paths=set();self.active=True
    def __call__(self,event,args):
        if not self.active or event!='open' or not args or not isinstance(args[0],(str,bytes,os.PathLike)):return
        # Do not treat generated outputs or cache writes as input dependencies.
        mode=args[1] if len(args)>1 else None
        flags=args[2] if len(args)>2 else 0
        if isinstance(mode,str) and any(c in mode for c in 'wax+'):return
        if isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):return
        try:
            p=Path(os.fsdecode(args[0])).resolve()
            if not p.is_relative_to(self.root):return
            rel=p.relative_to(self.root).as_posix()
            if not rel.startswith(('vendor/mosaic_v14/','cumcm_harness/')):return
            if '__pycache__' in p.parts or p.suffix in ('.pyc','.pyo','.nbc','.nbi'):return
            if p.suffix.lower() in ('.ttf','.otf','.ttc','.woff','.woff2','.eot'):
                raise Blocked('Runtime font dependency cannot be distributed; install fonts externally')
            self.paths.add(p)
        except (OSError,ValueError):return

def main():
    entry=Path(sys.argv[1]).resolve();args=sys.argv[2:]
    if '--out' not in args:raise SystemExit('missing output path')
    out=Path(args[args.index('--out')+1]);sys.argv=[str(entry),*args]
    sys.path.insert(0,str(entry.parent))
    reads=DependencyReads(ROOT);sys.addaudithook(reads)
    try:
        try:runpy.run_path(str(entry),run_name='__main__')
        except SystemExit as e:
            if e.code not in (None,0):raise
    finally:reads.active=False
    paths=set(reads.paths)
    for module in list(sys.modules.values()):
        value=getattr(module,'__file__',None)
        if not value:continue
        path=Path(value).resolve()
        if path.suffix=='.py' and path.is_relative_to(ROOT) and path.is_file():
            rel=path.relative_to(ROOT).as_posix()
            if rel.startswith(('vendor/mosaic_v14/','cumcm_harness/')):paths.add(path)
    refs={p.relative_to(ROOT).as_posix():file_hash(p) for p in sorted(paths) if p.is_file()}
    write_json(out/'custom_dependencies.json',refs)
if __name__=='__main__':main()
