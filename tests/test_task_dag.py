import pytest
from cumcm_harness.task_dag import execute
from cumcm_harness.common import IntegrityError,UnknownExternalState

TASKS=[{'id':'prepare','depends_on':[],'shards':2},{'id':'solve','depends_on':['prepare'],'shards':3}]


def test_dag_orders_dependencies_and_replays_completed_shards(tmp_path):
    calls=[]
    def prepare(shard,deps,out):calls.append(('prepare',shard));assert not deps;return {'row':shard}
    def solve(shard,deps,out):
        calls.append(('solve',shard));assert len(deps['prepare'])==2
        return {'row':shard,'input_rows':[r['result']['row'] for r in deps['prepare']]}
    handlers={'prepare':prepare,'solve':solve}
    first=execute(TASKS,handlers,tmp_path,identity={'data':'frozen','code':'v1'})
    assert execute(TASKS,handlers,tmp_path,identity={'data':'frozen','code':'v1'})==first
    assert calls==[('prepare',0),('prepare',1),('solve',0),('solve',1),('solve',2)]
    with pytest.raises(IntegrityError):execute(TASKS,handlers,tmp_path,identity={'data':'changed','code':'v1'})
    (tmp_path/'prepare/0/out/result.json').write_text('{}')
    with pytest.raises(IntegrityError):execute(TASKS,handlers,tmp_path,identity={'data':'frozen','code':'v1'})


def test_interrupted_shard_remains_unknown_and_completed_shards_are_preserved(tmp_path):
    calls=[]
    def run(shard,deps,out):
        calls.append(shard)
        if shard==1:raise KeyboardInterrupt('synthetic interrupt during second shard')
        return {'value':'first completed shard'}
    tasks=[{'id':'task','depends_on':[],'shards':3}]
    with pytest.raises(KeyboardInterrupt):execute(tasks,{'task':run},tmp_path,identity={'code':'v1'})
    with pytest.raises(UnknownExternalState):execute(tasks,{'task':run},tmp_path,identity={'code':'v1'})
    assert calls==[0,1]


def test_sigkill_between_completed_shards_resumes_without_repeating_work(tmp_path):
    import subprocess,sys
    script='''
import os,signal,sys
from pathlib import Path
import cumcm_harness.task_dag as dag
root=Path(sys.argv[1]);kill=sys.argv[2]=='kill'
original=dag.write_json
def write(path,value):
    original(path,value)
    if kill and path.name=='state.json' and value['status']=='DONE':os.kill(os.getpid(),signal.SIGKILL)
dag.write_json=write
def handler(shard,deps,out):
    with (root/'calls.txt').open('a') as f:f.write(str(shard)+'\\n')
    return {'shard':shard}
dag.execute([{'id':'prepare','depends_on':[],'shards':3}],{'prepare':handler},root,identity={'frozen':'same-input-code'})
'''
    first=subprocess.run([sys.executable,'-c',script,str(tmp_path),'kill'],capture_output=True,text=True)
    assert first.returncode<0,first.stderr
    second=subprocess.run([sys.executable,'-c',script,str(tmp_path),'resume'],capture_output=True,text=True)
    assert second.returncode==0,second.stderr
    assert (tmp_path/'calls.txt').read_text().splitlines()==['0','1','2']
