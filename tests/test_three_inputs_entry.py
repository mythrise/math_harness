from pathlib import Path
import copy,json
import pytest
from cumcm_harness.common import *
from cumcm_harness.entry_inputs import *
from cumcm_harness.controller import DEFAULT_CONFIG,Controller
from cumcm_harness.store import Store
from cumcm_harness.intake import verify_inputs,create_workspace
from cumcm_harness.entry_cli import main

@pytest.fixture
def setup(tmp_path):
    problem=tmp_path/'problem.md';problem.write_text('官方原题：问题一比较已给出数据，问题二选择可行方案。')
    data=tmp_path/'data';data.mkdir();(data/'data.csv').write_text('x,y\n1,2\n2,3\n')
    idea=tmp_path/'idea.md';idea.write_text('我和网页AI的初版建议：先用简单的线性模型，不要跳过验证。')
    cfg={**DEFAULT_CONFIG,'materials_workflow':True}
    return problem,data,idea,cfg

def init(tmp_path,setup,mode='idea',**kwargs):
    p,d,i,c=setup
    args={'input_mode':mode,'problem':p,'data':d,'config':c,'ideas':[i] if mode=='idea' else []}
    args.update(kwargs);root=tmp_path/'run';initialize(root,**args);return root

@pytest.mark.parametrize('mode',['scratch','idea'])
def test_full_mode_keeps_official_problem_separate(tmp_path,setup,mode):
    root=init(tmp_path,setup,mode);p,d,i,c=setup
    assert (root/'problem.md').read_bytes()==p.read_bytes()
    assert set(tree_manifest(root/'inputs/development'))=={'data.csv'}
    entry=load_entry(root);assert entry['full_research_required'];assert entry['input_mode']==mode
    assert verify_inputs(root)
    if mode=='idea':assert (root/entry['ideas'][0]['path']).read_bytes()==i.read_bytes()

@pytest.mark.parametrize('mode',['scratch','idea'])
def test_empty_official_data_directory_is_valid(tmp_path,setup,mode):
    root=init(tmp_path,setup,mode,data=None)
    assert tree_manifest(root/'inputs/development')=={}
    assert verify_inputs(root)

@pytest.mark.parametrize('mode,kwargs',[
 ('idea',{'ideas':[]}),('scratch',{'ideas':'idea'}),('revise',{'paper':None}),
 ('scratch',{'paper':'idea'}),('idea',{'paper':'idea'}),('other',{}),
])
def test_bad_mode_arguments_never_publish(tmp_path,setup,mode,kwargs):
    p,d,i,c=setup;kw={k:i if v=='idea' else v for k,v in kwargs.items()}
    if kw.get('ideas')==i:kw['ideas']=[i]
    with pytest.raises((Blocked,IntegrityError)):init(tmp_path,setup,mode,**kw)
    assert not (tmp_path/'run').exists()


def test_idea_requires_original_problem(tmp_path,setup):
    with pytest.raises(Blocked):init(tmp_path,setup,problem=None)


def test_same_document_cannot_be_both_problem_and_idea(tmp_path,setup):
    with pytest.raises(IntegrityError):init(tmp_path,setup,ideas=[setup[0]])


def test_idea_not_inside_solver_data(tmp_path,setup):
    inside=setup[1]/'idea.md';inside.write_text('初版思路不得混入原始数值数据。')
    with pytest.raises(IntegrityError):init(tmp_path,setup,ideas=[inside])


def test_workspace_not_inside_data(tmp_path,setup):
    p,d,i,c=setup
    with pytest.raises(IntegrityError):initialize(d/'run',input_mode='scratch',problem=p,data=d,config=c)


def test_duplicate_ideas_rejected(tmp_path,setup):
    p,d,i,c=setup;other=tmp_path/'copy.md';other.write_bytes(i.read_bytes())
    with pytest.raises(IntegrityError):init(tmp_path,setup,ideas=[i,other])


def test_unknown_model_not_guessed(tmp_path,setup):
    root=init(tmp_path,setup);records=public_external_records(root)
    assert len(records)==1;assert records[0]['model_reported']=='UNREPORTED'
    assert records[0]['transport']=='USER_REPORTED_EXTERNAL_SOURCE'
    assert records[0]['model_execution_status']=='IMPORTED_NOT_EXECUTED_BY_HARNESS'


def meta(tmp_path,source_type='mixed_human_ai'):
    row={'source_type':source_type,'tool':'Web AI','model':'UNREPORTED','used_at':'USER_REPORTED_DATE',
        'purpose':'初步建模讨论','prompt_summary':'我要求比较方法并识别风险。','output_summary':'候选线性模型。',
        'adoption':'PENDING_REVIEW','human_modification':'NOT_REPORTED','human_verification':'NOT_ATTESTED'}
    path=tmp_path/'meta.json';write_json(path,[row]);return path


def test_human_notes_not_invented_as_model_call(tmp_path,setup):
    root=init(tmp_path,setup,metadata=meta(tmp_path,'human_notes'));assert public_external_records(root)==[]


def test_multiple_external_ideas_keep_separate_provenance(tmp_path,setup):
    p,d,i,c=setup;j=tmp_path/'second.md';j.write_text('第二份思路：先独立检验时间平稳性。')
    root=init(tmp_path,setup,ideas=[i,j]);assert len(load_entry(root)['ideas'])==2
    assert len({r['response_digest'] for r in public_external_records(root)})==2


@pytest.mark.parametrize('target',['entry.json','entry/ideas/idea_01.md','entry/ideas/idea_01.normalized.json','input_provenance.json'])
def test_frozen_inputs_detect_every_kind_of_tampering(tmp_path,setup,target):
    root=init(tmp_path,setup);p=root/target;p.write_bytes(p.read_bytes()+b' ')
    # JSON semantic identity allows harmless whitespace, so alter a value as well.
    if p.suffix=='.json':
        value=read_json(p);value['tampered']=True;write_json(p,value)
    with pytest.raises(IntegrityError):load_entry(root)


def test_legacy_workspace_cannot_silently_add_entry(tmp_path,setup):
    p,d,i,c=setup;root=tmp_path/'run';create_workspace(root,p,d,c)
    assert load_entry(root) is None
    write_json(root/'entry.json',{'input_mode':'idea'})
    with pytest.raises(IntegrityError):load_entry(root)


def test_reinitialize_existing_run_is_blocked(tmp_path,setup):
    root=init(tmp_path,setup)
    with pytest.raises(Blocked):init(tmp_path,setup)
    assert load_entry(root)


def test_failed_data_read_is_atomic(tmp_path,setup):
    (setup[1]/'data.csv').write_text('x,y\n1,2,3\n')
    with pytest.raises(Blocked):init(tmp_path,setup)
    assert not (tmp_path/'run').exists();assert not list(tmp_path.glob('.entry-staging-*'))


def test_contest_requires_external_records(tmp_path,setup):
    cfg={**setup[-1],'mode':'contest'}
    with pytest.raises(Blocked):init(tmp_path,setup,config=cfg)
    root=init(tmp_path,setup,config=cfg,metadata=meta(tmp_path))
    assert load_entry(root)['input_mode']=='idea'


def test_idea_requires_full_preparation(tmp_path,setup):
    with pytest.raises(Blocked):init(tmp_path,setup,config={**setup[-1],'materials_workflow':False})


def test_native_cli_autodetect_and_status(tmp_path,setup,capsys):
    p,d,i,c=setup;root=tmp_path/'run'
    assert main(['init',str(root),'--problem',str(p),'--data',str(d),'--prior-idea',str(i)])==0
    assert load_entry(root)['input_mode']=='idea'
    assert main(['entry-status',str(root)])==0
    assert 'PROPOSAL_ONLY' in capsys.readouterr().out


def test_paper_revision_is_not_full_research(tmp_path,setup):
    p,d,i,c=setup;root=tmp_path/'rev'
    initialize(root,input_mode='revise',paper=i,config=c)
    e=load_entry(root);assert not e['full_research_required'];assert e['ideas']==[]
    assert not (root/'inputs').exists();assert Store(root).get('revision_frozen')


@pytest.mark.parametrize('argument',['data','private_dev','private_confirm','confirmation','exa_policy','sources'])
def test_revision_does_not_silently_execute_research(tmp_path,setup,argument):
    p,d,i,c=setup
    with pytest.raises((Blocked,IntegrityError)):
        initialize(tmp_path/'run',input_mode='revise',paper=i,config=c,**{argument:d})


def test_live_idea_cannot_silently_skip_literature(tmp_path,setup):
    root=init(tmp_path,setup)
    with pytest.raises(Blocked,match='literature'):Controller(root)
