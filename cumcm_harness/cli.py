"""Command-line control surface. Human approval never synthesizes a review."""
from __future__ import annotations
import argparse,getpass,json,os,shutil,sys
from pathlib import Path
from .common import ROOT,Blocked,IntegrityError,read_json,write_json,environment,file_hash

def parser():
    p=argparse.ArgumentParser(prog='cumcm',description='Evidence-gated Codex + Claude modeling harness')
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('doctor');a.add_argument('--live',action='store_true');a.add_argument('--config',type=Path);a.add_argument('--exa-policy',type=Path)
    a=sub.add_parser('init');a.add_argument('workspace',type=Path);a.add_argument('--problem',required=True,type=Path);a.add_argument('--data',required=True,type=Path)
    a.add_argument('--config',type=Path);a.add_argument('--mode',choices=['practice','contest']);a.add_argument('--confirmation',type=Path)
    a.add_argument('--private-dev',type=Path);a.add_argument('--private-confirm',type=Path);a.add_argument('--sources',type=Path)
    a.add_argument('--exa-policy',type=Path);a.add_argument('--research-cutoff',help='Explicit UTC cutoff; defaults to initialization time')
    a=sub.add_parser('run');a.add_argument('workspace',type=Path)
    a=sub.add_parser('demo');a.add_argument('workspace',type=Path);a.add_argument('--candidates',type=int,default=2);a.add_argument('--fe-budget',type=int,default=192)
    for name in ('status','audit'):
        a=sub.add_parser(name);a.add_argument('workspace',type=Path)
    a=sub.add_parser('approve');a.add_argument('workspace',type=Path);a.add_argument('--stage',choices=['plan','release','research'],required=True);a.add_argument('--review',type=Path,required=True)
    for name in ('recover-step','recover-job','recover-exa','recover-exa-lease'):
        a=sub.add_parser(name);a.add_argument('workspace',type=Path);a.add_argument('key');a.add_argument('--reason',required=True);a.add_argument('--external-process-stopped',action='store_true')
    a=sub.add_parser('methods');a.add_argument('query')
    a=sub.add_parser('schema');a.add_argument('name',nargs='?')
    a=sub.add_parser('verify-vendor')
    a=sub.add_parser('exa-status');a.add_argument('workspace',type=Path)
    a=sub.add_parser('exa-probe');a.add_argument('workspace',type=Path);a.add_argument('--query',required=True);a.add_argument('--dynamic',action='store_true',required=True)
    a=sub.add_parser('exa-rules');a.add_argument('workspace',type=Path);a.add_argument('--query',required=True);a.add_argument('--year',type=int,required=True)
    sub.add_parser('set-exa-key',help='Save a local-only Exa credential using hidden input')
    return p

def doctor(live=False, config=None):
    from .providers import CLIProvider
    from .controller import DEFAULT_CONFIG, validate_config
    config = validate_config({**DEFAULT_CONFIG, **(config or {})})
    report={'environment':environment(),'commands':{},'live_model_calls':'NOT_RUN','docker_execution':'NOT_RUN'}
    for name in ('codex','claude','docker','xelatex','inkscape'):
        report['commands'][name]=shutil.which(name) or 'NOT_INSTALLED'
    if live:
        for name in ('codex','claude'):
            try:report[name+'_probe']=CLIProvider(name).probe()[1]
            except Exception as e:report[name+'_probe']={'status':'BLOCKED','reason':str(e)}
        from .sandbox import Executor
        try:report['docker_probe']=Executor(image=config['docker_image']).probe()
        except Exception as e:report['docker_probe']={'status':'BLOCKED','reason':str(e)}
    from .credentials import get_exa_api_key
    report['exa_key_configured']=bool(get_exa_api_key())
    report['claude_optional']='DEGRADED_TO_INDEPENDENT_CODEX_SEATS' if report['commands']['claude']=='NOT_INSTALLED' or isinstance(report.get('claude_probe'),dict) else 'AVAILABLE_NOT_AUTH_VERIFIED'
    from .tex_sandbox import probe as tex_probe
    try:report['tex_container_probe']=tex_probe()
    except Exception as e:report['tex_container_probe']={'status':'BLOCKED','reason':str(e)}
    required=('codex','docker','inkscape')
    report['literature_enabled']=config['literature_enabled']
    report['network_policy']=config['network_policy']
    report['ready_for_live']=report['tex_container_probe'].get('status')!='BLOCKED' and all(report['commands'][x]!='NOT_INSTALLED' for x in required) and not any(isinstance(report.get(x+'_probe'),dict) and report[x+'_probe'].get('status')=='BLOCKED' for x in ('codex','docker')) and (not config['literature_enabled'] or report['exa_key_configured'])
    report['auth_and_end_to_end_verified']=False
    return report

def main(argv=None):
    args=parser().parse_args(argv)
    try:
        from .store import Store,controller_lock
        if args.command=='set-exa-key':
            from .credentials import save_exa_api_key
            path=save_exa_api_key(getpass.getpass('Exa API key (hidden): '))
            result={'status':'LOCAL_CREDENTIAL_SAVED','path':str(path),'git_tracked':False}
        elif args.command=='doctor':
            result=doctor(args.live,read_json(args.config) if args.config else None)
            if args.exa_policy:
                from .exa_policy import validate_policy
                policy=validate_policy(read_json(args.exa_policy))
                from .controller import DEFAULT_CONFIG
                config={**DEFAULT_CONFIG,**(read_json(args.config) if args.config else {})}
                result['exa_policy']={'status':'VALIDATED_NOT_HTTP_TESTED','effective_policy':policy,'capability_probe':'NOT_RUN',
                    'effective_http_attempt_cap':min(config['exa_max_requests'],policy['budget']['max_total_http_attempts']),
                    'effective_default_timeout_seconds':min(config['exa_timeout'],policy['http']['default_timeout_seconds'])}
        elif args.command=='init':
            from .controller import DEFAULT_CONFIG,validate_config
            from .intake import create_workspace
            config={**DEFAULT_CONFIG,**(read_json(args.config) if args.config else {})}
            if args.mode:config['mode']=args.mode
            validate_config(config)
            info=create_workspace(args.workspace,args.problem,args.data,config,confirmation=args.confirmation,private_dev=args.private_dev,private_confirm=args.private_confirm,
                                  exa_policy=read_json(args.exa_policy) if args.exa_policy else None,research_cutoff=args.research_cutoff)
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
        elif args.command in ('recover-step','recover-job','recover-exa','recover-exa-lease'):
            if not args.external_process_stopped:raise Blocked('First reconcile external CLI/container billing/process state, then pass --external-process-stopped')
            with controller_lock(args.workspace):
                store=Store(args.workspace)
                if args.command=='recover-step':store.recover_step(args.key,args.reason)
                elif args.command=='recover-job':store.recover_job(args.key,args.reason)
                else:
                    from .intake import verify_inputs
                    from .exa_policy import load_frozen
                    from .exa_ledger import ExaLedger,SharedHTTPGate
                    verify_inputs(args.workspace);snapshot=load_frozen(args.workspace)
                    if snapshot is None:raise IntegrityError('recover-exa requires a frozen R2 workspace')
                    ledger=ExaLedger(store,snapshot['policy']);gate=SharedHTTPGate(ROOT/'.runtime/exa/shared.sqlite3')
                    if args.command=='recover-exa-lease':gate.recover_lease(snapshot['run_id'],args.key,ledger,args.reason)
                    else:
                        attempts=ledger.reconcile(args.key,args.reason)
                        gate.reconcile(snapshot['run_id'],attempts)
            result={'status':'EXPLICIT_RETRY_AUTHORIZED','key':args.key,'prior_attempt_preserved':True}
        elif args.command in ('exa-status','exa-probe','exa-rules'):
            from .controller import Controller
            with controller_lock(args.workspace):
                controller=Controller(args.workspace)
                from .literature_r2 import R2LiteratureWorkflow
                if not isinstance(controller.literature,R2LiteratureWorkflow):raise IntegrityError('This command requires a frozen R2 workspace')
                result=controller.literature.collect_rules(args.query,args.year) if args.command=='exa-rules' else controller.literature.client.ledger.summary() if args.command=='exa-status' else controller.literature.client.probe_dynamic(args.query)
                if args.command=='exa-status':result['leases']=controller.literature.client.gate.inspect(controller.literature.snapshot['run_id'])
        elif args.command=='methods':
            from .algorithms import route_methods
            result=route_methods(args.query,top_k=10)
        elif args.command=='schema':
            from . import literature,literature_r2  # registers evidence/policy schemas
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
