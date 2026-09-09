"""Bounded artifact DAG for solver-side shards, intended to run inside Docker.

Completed shards are verified and reused. A crashed RUNNING shard needs explicit
reconciliation; this helper never guesses that side effects did not occur.
"""
from pathlib import Path
from .common import (IntegrityError,UnknownExternalState,ExecutionFailure,digest,
                     read_json,write_json,tree_manifest,verify_tree,safe_rel)
from .contracts import topo


def execute(tasks,handlers,root,*,identity):
    if not tasks or len(tasks)>64:raise IntegrityError('DAG requires 1..64 tasks')
    root=Path(root);order=topo(tasks);known={t['id']:t for t in tasks}
    if set(handlers)!=set(order):raise IntegrityError('DAG handlers must match task IDs exactly')
    if any(type(t.get('shards',1)) is not int or not 1<=t.get('shards',1)<=128 for t in tasks):raise IntegrityError('DAG shard limit')
    frozen={'tasks':tasks,'identity':identity};path=root/'identity.json'
    if path.exists():
        if read_json(path)!=frozen:raise IntegrityError('DAG input/code identity changed')
    else:write_json(path,frozen)
    completed={}
    for name in order:
        safe_rel(name);task=known[name];dependencies={d:completed[d] for d in task['depends_on']};rows=[]
        for shard in range(task.get('shards',1)):
            intent={'task':name,'shard':shard,'identity':digest(frozen),'dependencies':digest(dependencies)}
            base=root/name/str(shard);state=base/'state.json';out=base/'out'
            if state.exists():
                record=read_json(state)
                if record['intent']!=intent:raise IntegrityError('DAG shard intent changed')
                if record['status']=='RUNNING':raise UnknownExternalState('DAG shard RUNNING; reconcile before explicit recovery')
                if record['status']!='DONE':raise ExecutionFailure('DAG shard failed; create a revised solver run')
                verify_tree(out,record['manifest'])
            else:
                out.mkdir(parents=True,exist_ok=False)
                write_json(state,{'status':'RUNNING','intent':intent})
                try:
                    value=handlers[name](shard,dependencies,out)
                    write_json(out/'result.json',value)
                    record={'status':'DONE','intent':intent,'manifest':tree_manifest(out),'result':value}
                    write_json(state,record)
                except Exception as exc:
                    write_json(state,{'status':'FAILED','intent':intent,'error_type':type(exc).__name__,'error':str(exc)})
                    raise
            rows.append({'task':name,'shard':shard,'path':str(out),'manifest':record['manifest'],'result':record['result']})
        completed[name]=rows
    result={'status':'DONE','identity_digest':digest(frozen),'tasks':completed,'order':order,
            'scope':'BOUNDED_DAG_SHARD_CHECKPOINTS_NOT_A_PROOF_OF_MODEL_CORRECTNESS'}
    write_json(root/'dag_receipt.json',result)
    return result
