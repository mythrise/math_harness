from pathlib import Path
import copy,json
import pytest
from cumcm_harness.common import IntegrityError,digest
from cumcm_harness.materials_figures import question_framework,confirmation_plot
from materials_samples import samples

@pytest.mark.parametrize('n',[1,2,6,24])
def test_framework_records_all_actual_questions(tmp_path,n):
    qs=[{'id':f'Q{i+1}','title':'当前问题的结果与边界','family':'prediction','depends_on':[] if i==0 else [f'Q{i}']} for i in range(n)]
    p=question_framework(tmp_path/'view.svg',qs);r=json.loads(p.with_suffix('.provenance.json').read_text())
    assert r['questions']==qs and len(r['dependency_edges'])==n-1
    assert not r['numerical_execution_certified_by_this_figure']
    assert p.with_suffix('.pdf').is_file() and p.with_suffix('.png').is_file()


def test_chart_rejects_incompatible_units(tmp_path):
    _,_,_,_,_,plan,*_=samples()
    rows=[{'candidate':'baseline','evaluation':{'metric':'wrong','score':1.}}]
    with pytest.raises(IntegrityError):confirmation_plot(rows,tmp_path/'bad',plan)


@pytest.mark.parametrize('rows',[
    [],
    [{'candidate':'baseline','evaluation':{'metric':'wrong','score':1.}}],
])
def test_bad_measurements_fail_before_font_discovery(tmp_path,monkeypatch,rows):
    from cumcm_harness import materials_figures
    def unexpected(*args):raise AssertionError('No rendering should start for invalid measurements')
    monkeypatch.setattr(materials_figures,'chinese_font',unexpected)
    _,_,_,_,_,plan,*_=samples()
    with pytest.raises(IntegrityError):confirmation_plot(rows,tmp_path/'invalid',plan)
