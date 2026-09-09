"""Native three-input CLI. All other commands delegate to the existing harness CLI."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .common import read_json,IntegrityError


def init_parser():
    p=argparse.ArgumentParser(prog='cumcm init',description='Initialize scratch / idea / existing-paper revision. --mode practice|contest is separate.')
    p.add_argument('workspace',type=Path)
    p.add_argument('--input-mode',choices=['scratch','idea','revise'])
    p.add_argument('--problem',type=Path)
    p.add_argument('--data',type=Path)
    p.add_argument('--prior-idea',action='append',default=[],type=Path)
    p.add_argument('--external-ai-records',type=Path)
    p.add_argument('--paper',type=Path)
    p.add_argument('--config',type=Path)
    p.add_argument('--mode',choices=['practice','contest'])
    p.add_argument('--confirmation',type=Path)
    p.add_argument('--private-dev',type=Path)
    p.add_argument('--private-confirm',type=Path)
    p.add_argument('--sources',type=Path)
    p.add_argument('--exa-policy',type=Path)
    p.add_argument('--research-cutoff')
    return p


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if args and args[0]=='init':
        a=init_parser().parse_args(args[1:])
        try:
            from .entry_inputs import initialize
            from .controller import DEFAULT_CONFIG
            mode=a.input_mode or ('revise' if a.paper else 'idea' if a.prior_idea else 'scratch')
            config={**DEFAULT_CONFIG,'materials_workflow':True,**(read_json(a.config) if a.config else {})}
            if a.mode:config['mode']=a.mode
            result=initialize(a.workspace,input_mode=mode,problem=a.problem,data=a.data,config=config,
                ideas=a.prior_idea,paper=a.paper,metadata=a.external_ai_records,
                confirmation=a.confirmation,private_dev=a.private_dev,private_confirm=a.private_confirm,
                sources=a.sources,exa_policy=read_json(a.exa_policy) if a.exa_policy else None,research_cutoff=a.research_cutoff)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        except Exception as exc:
            print(json.dumps({'status':'BLOCKED','error':type(exc).__name__,'reason':str(exc)},ensure_ascii=False),file=sys.stderr);return 2
    if args and args[0] in ('run','entry-status','audit'):
        p=argparse.ArgumentParser(prog='cumcm '+args[0]);p.add_argument('workspace',type=Path);a=p.parse_args(args[1:])
        try:
            from .entry_inputs import load_entry
            entry=load_entry(a.workspace)
            if args[0]=='entry-status':
                result={'entry':entry,'integrity':'PASS' if entry else 'LEGACY_NO_ENTRY',
                    'mode_changes':'Create a new workspace; never change entry.json in place'}
            elif args[0]=='audit':
                if entry and entry['input_mode']=='revise':
                    from .paper_revision import RevisionController
                    result=RevisionController(a.workspace).audit()
                else:
                    from .cli import main as legacy
                    return legacy(args)
            elif entry and entry['input_mode']=='revise':
                from .paper_revision import RevisionController
                result=RevisionController(a.workspace).run()
            else:
                from .controller import Controller
                result=Controller(a.workspace).run()
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        except Exception as exc:
            print(json.dumps({'status':getattr(exc,'status','BLOCKED'),'error':type(exc).__name__,'reason':str(exc)},ensure_ascii=False),file=sys.stderr);return 2
    if args and args[0]=='schema':
        from . import idea_workflow,paper_revision
    from .cli import main as legacy
    return legacy(args)

if __name__=='__main__':raise SystemExit(main())
