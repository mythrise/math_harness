"""Command-line control surface. Human approval never synthesizes a review."""
from __future__ import annotations
import argparse,getpass,json,os,shutil,sys
from pathlib import Path
from .common import ROOT,Blocked,IntegrityError,read_json,write_json,environment,file_hash

def parser():
    p=argparse.ArgumentParser(prog='cumcm',description='Evidence-gated Codex + Claude modeling harness')
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('doctor');a.add_argument('--live',action='store_true')
    a=sub.add_parser('init');a.add_argument('workspace',type=Path);a.add_argument('--problem',required=True,type=Path);a.add_argument('--data',required=True,type=Path)
    a.add_argument('--config',type=Path);a.add_argument('--mode',choices=['practice','contest']);a.add_argument('--confirmation',type=Path)
    a.add_argument('--private-dev',type=Path);a.add_argument('--private-confirm',type=Path);a.add_argument('--sources',type=Path)
    a=sub.add_parser('run');a.add_argument('workspace',type=Path)
    a=sub.add_parser('demo');a.add_argument('workspace',type=Path);a.add_argument('--candidates',type=int,default=2);a.add_argument('--fe-budget',type=int,default=192)
    for name in ('status','audit'):
        a=sub.add_parser(name);a.add_argument('workspace',type=Path)
    a=sub.add_parser('approve');a.add_argument('workspace',type=Path);a.add_argument('--stage',choices=['plan','release'],required=True);a.add_argument('--review',type=Path,required=True)
    for name in ('recover-step','recover-job'):
        a=sub.add_parser(name);a.add_argument('workspace',type=Path);a.add_argument('key');a.add_argument('--reason',required=True);a.add_argument('--external-process-stopped',action='store_true')
    a=sub.add_parser('methods');a.add_argument('query')
    a=sub.add_parser('schema');a.add_argument('name',nargs='?')
    a=sub.add_parser('verify-vendor')
    return p

def doctor(live=False):
    from .providers import CLIProvider
    report={'environment':environment(),'commands':{},'live_model_calls':'NOT_RUN','docker_execution':'NOT_RUN'}
    for name in ('codex','claude','docker','xelatex','inkscape'):
        report['commands'][name]=shutil.which(name) or 'NOT_INSTALLED'
    if live:
        for name in ('codex','claude'):
            try:report[name+'_probe']=CLIProvider(name).probe()[1]
            except Exception as e:report[name+'_probe']={'status':'BLOCKED','reason':str(e)}
        from .sandbox import Executor
        try:report['docker_probe']=Executor().probe()
        except Exception as e:report['docker_probe']={'status':'BLOCKED','reason':str(e)}
    report['ready_for_live']=all(report['commands'][x]!='NOT_INSTALLED' for x in report['commands']) and not any(isinstance(v,dict) and v.get('status')=='BLOCKED' for v in report.values())
    return report

def main(argv=None):
    args=parser().parse_args(argv)
    try:
        from .store import Store,controller_lock
        if args.command=='doctor':result=doctor(args.live)
        elif args.command=='init':
            from .controller import DEFAULT_CONFIG,validate_config
            from .intake import create_workspace
            config={**DEFAULT_CONFIG,**(read_json(args.config) if args.config else {})}
            if args.mode:config['mode']=args.mode
            validate_config(config)
            info=create_workspace(args.workspace,args.problem,args.data,config,confirmation=args.confirmation,private_dev=args.private_dev,private_confirm=args.private_confirm)
            if args.sources:write_json(args.workspace/'sources.json',read_json(args.sources))
            result={'status':'INITIALIZED','workspace':str(args.workspace.resolve()),'confirmation_scope':info['confirmation_scope']}
        elif args.command=='run':
            from .controller import Controller
            result=Controller(args.workspace).run()
        elif args.command=='demo':
            from .demo import run_demo
            result=run_demo(args.workspace,candidates=args.candidates,fe_budget=args.fe_budget)
        elif args.command=='status':
            store=Store(args.workspace)
            with store.connect() as c:
                jobs=[dict(x) for x in c.execute('SELECT id,status FROM jobs ORDER BY id')]
                steps=[dict(x) for x in c.execute('SELECT key,status,error FROM steps WHERE status != ?',( 'DONE',))]
            result={'status':store.get('status'),'jobs':jobs,'unfinished_steps':steps,'model_calls_reserved':store.get('model_calls_reserved',0)}
        elif args.command=='audit':
            from .intake import verify_inputs
            verify_inputs(args.workspace);result=Store(args.workspace).audit()
        elif args.command=='approve':
            from .approval import sign
            if not sys.stdin.isatty():raise Blocked('Human approval requires an interactive operator terminal')
            print('核对目标摘要与每项人工审核记录；此操作不代表模型或程序替你完成审核。',file=sys.stderr)
            if input('确认本人/团队已完成上述审核，输入 HUMAN-REVIEWED: ').strip()!='HUMAN-REVIEWED':raise Blocked('Human approval cancelled')
            key=os.getenv('CUMCM_OPERATOR_KEY') or getpass.getpass('Operator key (at least 32 characters): ')
            with controller_lock(args.workspace):r=sign(args.workspace,args.stage,read_json(args.review),key)
            result={'status':'LOCAL_HUMAN_ATTESTATION_SAVED','target':r['payload']['review']['target_digest']}
        elif args.command in ('recover-step','recover-job'):
            if not args.external_process_stopped:raise Blocked('First reconcile external CLI/container billing/process state, then pass --external-process-stopped')
            with controller_lock(args.workspace):
                store=Store(args.workspace)
                if args.command=='recover-step':store.recover_step(args.key,args.reason)
                else:store.recover_job(args.key,args.reason)
            result={'status':'EXPLICIT_RETRY_AUTHORIZED','key':args.key,'prior_attempt_preserved':True}
        elif args.command=='methods':
            from .algorithms import route_methods
            result=route_methods(args.query,top_k=10)
        elif args.command=='schema':
            from .contracts import SCHEMAS
            if args.name and args.name not in SCHEMAS:raise IntegrityError('Unknown schema')
            result=SCHEMAS[args.name] if args.name else {'available':list(SCHEMAS)}
        else:
            from .common import verify_vendor
            result=verify_vendor()
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as e:
        print(json.dumps({'status':'BLOCKED','error':type(e).__name__,'reason':str(e)},ensure_ascii=False,indent=2),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
