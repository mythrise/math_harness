"""Local integration checks beyond the preserved upstream algorithm tests."""
import pytest
from cumcm_harness.algorithms import METHODS,route_methods
from cumcm_harness.algorithm_library import select_algorithms
from cumcm_harness.algorithm_lab import run
from cumcm_harness.algpromotion import promotion_decision
from test_algorithm_upgrade import protocol_fixture


def test_mosaic_router_keeps_the_original_representation_and_budget_guards():
    original=next(c for c in METHODS if c['id']=='mosaic-multiobjective')
    enriched=next(c for c in route_methods('多目标',10) if c['id']==original['id'])
    assert set(original['assumptions'])<=set(enriched['assumptions'])
    assert set(original['checks'])<=set(enriched['checks'])
    assert 'algorithm_upgrade' not in original
    assert select_algorithms({'family':'graph-path'})['admission_scope']=='PARTIAL_STRUCTURAL_SCREEN_NOT_EXECUTION_APPROVAL'


@pytest.mark.parametrize('alias',['new','strong'])
def test_promotion_cannot_relabel_candidate_or_baseline_as_ablation(alias):
    protocol,rows=protocol_fixture()
    protocol['required_ablations']=[alias]
    protocol['code_hashes'].pop('no_residual')
    rows=[r for r in rows if r['method']!='no_residual']
    with pytest.raises(ValueError,match='Ablation IDs'):promotion_decision(rows,protocol)


@pytest.mark.parametrize('seeds',[0,1,31,True])
def test_benchmark_api_rejects_empty_or_invalid_seed_matrix(tmp_path,seeds):
    with pytest.raises(ValueError):run(tmp_path/'run',seeds=seeds)
    assert not (tmp_path/'run').exists()
