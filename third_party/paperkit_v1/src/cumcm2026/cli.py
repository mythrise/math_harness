from __future__ import annotations
import argparse,json,sys,shutil
from pathlib import Path
from .common import Blocked

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='CUMCM 2026 PaperKit: safe-default local build and explicit review')
    sub=parser.add_subparsers(dest='cmd',required=True)
    sub.add_parser('doctor')
    p=sub.add_parser('init');p.add_argument('destination',type=Path)
    p=sub.add_parser('build');p.add_argument('--project',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    p=sub.add_parser('check');p.add_argument('--out',required=True,type=Path)
    p=sub.add_parser('release');p.add_argument('--out',required=True,type=Path);p.add_argument('--review',required=True,type=Path);p.add_argument('--destination',required=True,type=Path)
    p=sub.add_parser('print');p.add_argument('--paper',required=True,type=Path);p.add_argument('--commitment',required=True,type=Path);p.add_argument('--numbering',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--confirmed-official',action='store_true')
    p=sub.add_parser('install-harness');p.add_argument('--root',required=True,type=Path);p.add_argument('--apply',action='store_true')
    p=sub.add_parser('uninstall-harness');p.add_argument('--root',required=True,type=Path)
    a=parser.parse_args(argv)
    try:
        from .builder import build,verify_bundle,release,make_print
        if a.cmd=='doctor':
            import importlib.metadata
            result={'python':sys.version.split()[0],'xelatex':shutil.which('xelatex'),
                    'PyMuPDF':importlib.metadata.version('PyMuPDF'),'network_used':False,
                    'note':'XeLaTeX with ctex/fandol/fvextra/cleveref is required; no fonts are shipped.'}
            if not result['xelatex']:raise Blocked('XeLaTeX missing')
        elif a.cmd=='init':
            from .project import init_project
            result=init_project(a.destination)
        elif a.cmd=='build':result=build(a.project,a.out)
        elif a.cmd=='check':result=verify_bundle(a.out)
        elif a.cmd=='release':result=release(a.out,a.review,a.destination)
        elif a.cmd=='print':result=make_print(a.paper,a.commitment,a.numbering,a.out,confirmed=a.confirmed_official)
        elif a.cmd=='install-harness':
            from .install import install
            result=install(a.root,apply=a.apply)
        else:
            from .install import uninstall
            result=uninstall(a.root)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as e:
        print(json.dumps({'status':'BLOCKED','message':str(e),'release_ready':False},ensure_ascii=False,indent=2))
        return 2
if __name__=='__main__':raise SystemExit(main())
