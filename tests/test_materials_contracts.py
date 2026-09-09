import copy
import pytest
from cumcm_harness.common import IntegrityError,digest
from cumcm_harness.contracts import validate
from cumcm_harness.materials_contracts import *
from materials_samples import samples,PROBLEM

def test_all_sample_contracts():
    b,d,a,p,m,plan,draft,claims,e,pm=samples()
    assert check_brief(b,PROBLEM)==b
    assert check_data_plan(d,a)==d
    assert check_portfolio(p,b,m)==p
    assert check_plan_alignment(plan,{'brief':b,'portfolio':p})
    assert check_paper_map(pm,draft,plan,claims,e)['status']=='STRUCTURAL_PASS_SEMANTIC_REVIEW_REQUIRED'
    validate('plan',plan);validate('paper',draft)

@pytest.mark.parametrize('mutation',[
    lambda b:b.update(problem_sha256='0'*64),
    lambda b:b['requirements'][0]['anchor'].update(start=1),
    lambda b:b['requirements'][0]['anchor'].update(quote='编造片段'),
    lambda b:b['requirements'][0].update(question_ids=['Q9']),
    lambda b:b['requirements'][0].update(kind='background'),
    lambda b:b['questions'][0].update(depends_on=['Q2']),
    lambda b:b['questions'][0].update(constraint_ids=['R1']),
    lambda b:b['questions'].append(copy.deepcopy(b['questions'][0])),
    lambda b:b.update(unknown=True),
])
def test_brief_rejects_bad_grounding(mutation):
    b,*_=samples();mutation(b)
    with pytest.raises(IntegrityError):check_brief(b,PROBLEM)

@pytest.mark.parametrize('mutation',[
    lambda d:d['sources'][0].update(origin='synthetic_scenario'),
    lambda d:d['sources'][0].update(file='imaginary.csv'),
    lambda d:d['sources'][0].update(origin='researched'),
    lambda d:d['transforms'][0].update(raw_immutable=False),
    lambda d:d['transforms'][0].update(time_causal=False),
    lambda d:d['transforms'][0].update(operation='impute'),
    lambda d:d['transforms'][0].update(operation='select_features'),
    lambda d:d['transforms'][0].update(output_path='../escape.csv'),
    lambda d:d['transforms'][0].update(output_path='history.csv'),
    lambda d:d.update(time_key='NOT_APPLICABLE'),
    lambda d:d.update(split='group_time'),
])
def test_data_contract_rejects_leaks(mutation):
    _,d,a,*_=samples();mutation(d)
    with pytest.raises(IntegrityError):check_data_plan(d,a)

@pytest.mark.parametrize('mutation',[
    lambda p:p['questions'][0]['options'][0].update(method_card_id='brand_new_not_installed'),
    lambda p:p['questions'][0]['options'][0].update(implementation_status='RESEARCH_ONLY_NOT_RUN'),
    lambda p:p['questions'][0].update(recommendation='nonexistent'),
    lambda p:p['questions'].pop(),
    lambda p:p['questions'][0]['options'].append(copy.deepcopy(p['questions'][0]['options'][0])),
])
def test_portfolio_rejects_unverified_executability(mutation):
    b,_,_,p,m,*_=samples();mutation(p)
    with pytest.raises(IntegrityError):check_portfolio(p,b,m)

@pytest.mark.parametrize('mutation',[
    lambda p:p['questions'].pop(),
    lambda p:p['questions'][1].pop('answer_type'),
    lambda p:p['variables'].append(copy.deepcopy(p['variables'][0])),
    lambda p:p['variables'][0].update(unit='待补充'),
])
def test_plan_handoff_integrity(mutation):
    b,_,_,portfolio,_,p,*_=samples();mutation(p)
    with pytest.raises(IntegrityError):check_plan_alignment(p,{'brief':b,'portfolio':portfolio})

@pytest.mark.parametrize('mutation',[
    lambda m:m.update(draft_digest='0'*64),
    lambda m:m['questions'].pop(),
    lambda m:m['questions'][0]['bindings'].pop(),
    lambda m:m['questions'][0].update(claim_ids=['invented']),
    lambda m:m['questions'][1].update(qualitative_evidence_ids=[]),
    lambda m:m['questions'][1].update(qualitative_evidence_ids=['imaginary']),
    lambda m:m['questions'][0]['bindings'][0].update(section_indices=[99]),
    lambda m:m['questions'][0]['bindings'][0].update(section_indices=[]),
    lambda m:m['questions'][0]['bindings'][0].update(state='NOT_APPLICABLE',section_indices=[]),
    lambda m:m.update(abstract_claim_ids=[]),
    lambda m:m['symbols'][0].update(unit='kg'),
    lambda m:m['symbols'].pop(),
])
def test_paper_map_rejects_false_coverage(mutation):
    _,_,_,_,_,plan,draft,claims,e,m=samples();mutation(m)
    with pytest.raises(IntegrityError):check_paper_map(m,draft,plan,claims,e)

def test_qualitative_evidence_is_question_bound():
    _,_,_,_,_,plan,draft,claims,e,m=samples();e[0]['question_id']='Q1'
    with pytest.raises(IntegrityError):check_paper_map(m,draft,plan,claims,e)

def test_optional_theory_steps_can_be_na_with_reason():
    _,_,_,_,_,plan,draft,claims,e,m=samples()
    m['questions'][1]['bindings'][3].update(state='NOT_APPLICABLE',section_indices=[],reason='本问只解释已验证的适用边界，不另立数学方程；结果与核验仍不能省略。')
    assert check_paper_map(m,draft,plan,claims,e)
