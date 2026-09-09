"""Finite inputs can still overflow accumulated route costs."""
import pytest
from cumcm_harness.alggraph import shortest_path

def test_reachable_overflow_is_not_unreachable():
    with pytest.raises(ValueError,match='overflow'):
        shortest_path(3,[(0,1,1e308),(1,2,1e308)],0,2)

def test_large_finite_path_and_actual_unreachable_are_distinct():
    r=shortest_path(3,[(0,1,1e307),(1,2,1e307)],0,2)
    assert r['status']=='PATH_FOUND' and r['distance']==2e307
    assert shortest_path(3,[(0,1,1e307)],0,2)['status']=='UNREACHABLE'

def test_unreachable_negative_edge_does_not_trigger_overflow():
    r=shortest_path(4,[(0,1,1.),(2,3,-1.)],0,1)
    assert r['status']=='PATH_FOUND' and r['distance']==1
