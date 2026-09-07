"""Lifecycle regression tests. Fixtures here are not live scientific reviews."""
import pytest

from cumcm_harness.common import Blocked, IntegrityError
from cumcm_harness.controller import Controller, DEFAULT_CONFIG
from cumcm_harness.demo import responder
from cumcm_harness.providers import FixtureProvider
from cumcm_harness.store import Store


def controller(tmp_path, response=responder):
    c = Controller.__new__(Controller)
    c.root = tmp_path
    c.problem = 'Synthetic controller scope test only'
    c.base = {'experiment_contract': {'development_seeds': [101, 202, 303]},
              'source_registry': [{'id': 'synthetic-test-source'}]}
    c.config = {**DEFAULT_CONFIG, 'repair_attempts': 0}
    c.store = Store(tmp_path)
    c.demo = True
    provider = FixtureProvider(response)
    packets = []

    def call(key, role, schema, packet, **kwargs):
        packets.append((role, packet))
        return provider.invoke(role, schema, packet, tmp_path / 'calls' / str(len(packets)))

    c.call = call
    return c, packets


@pytest.mark.parametrize('role,schema,key', [
    ('modeler', 'plan', 'plan'), ('coder', 'bundle', 'candidate:c0')])
def test_pre_execution_reviews_get_explicit_scope(tmp_path, role, schema, key):
    c, packets = controller(tmp_path)
    c.produce_reviewed(key, role, schema, {})
    review_packets = [p for r, p in packets if r.endswith('_reviewer')]
    expected = 'plan_design' if role == 'modeler' else 'source_code'
    assert len(review_packets) == 2
    assert all(p['review_stage'] == expected for p in review_packets)
    assert all(p['stage_requirements']['certifies_execution'] is False for p in review_packets)
    assert all(p['context']['experiment_contract']['development_seeds'] == [101, 202, 303]
               for p in review_packets)
    assert all(p['context']['source_registry'] == c.base['source_registry'] for p in review_packets)


def test_runtime_review_still_requires_execution_evidence(tmp_path):
    c, packets = controller(tmp_path)
    c.reviews('smoke', {'smoke': 'synthetic test'})
    assert all(p['review_stage'] == 'execution' for _, p in packets)
    assert all(p['stage_requirements']['certifies_execution'] is True for _, p in packets)


def test_plan_findings_are_not_downgraded_or_waived(tmp_path):
    def fail(role, schema, packet):
        if schema != 'review':
            return responder(role, schema, packet)
        r = responder(role, schema, packet)
        r.update(verdict='FAIL', findings=[{
            'severity': 'P1', 'location': 'equation', 'issue': 'Wrong dimensions',
            'required_fix': 'Correct the equation before implementation'}])
        return r
    c, _ = controller(tmp_path, fail)
    with pytest.raises(Blocked, match='Wrong dimensions'):
        c.produce_reviewed('plan', 'modeler', 'plan', {})
    assert c.store.get('plan') is None


def test_inconsistent_review_retries_same_reviewer_and_artifact(tmp_path):
    c, _ = controller(tmp_path)
    c.config['repair_attempts'] = 1
    original_call = c.call
    seen = []

    def call(key, role, schema, packet, **kwargs):
        seen.append((key, role, packet))
        if len(seen) == 1:
            raise IntegrityError('PASS cannot contain blocking findings or unverified required checks')
        return original_call(key, role, schema, packet, **kwargs)

    c.call = call
    target = {'equation': 'synthetic test'}
    c.reviews('plan-review', target, stage='plan_design')
    assert [r for _, r, _ in seen] == ['math_reviewer', 'math_reviewer', 'experiment_reviewer']
    assert len({k for k, _, _ in seen}) == 3
    assert all(p['artifact'] == target for _, _, p in seen)
    assert 'response_contract_feedback' in seen[1][2]


def test_consistent_negative_review_is_not_retried(tmp_path):
    def fail(role, schema, packet):
        r = responder(role, schema, packet)
        r.update(verdict='BLOCKED', unverified=['Required in-scope proof missing'])
        return r
    c, packets = controller(tmp_path, fail)
    c.config['repair_attempts'] = 2
    with pytest.raises(Blocked):
        c.reviews('plan-review', {'equation': 'synthetic'}, stage='plan_design')
    assert len(packets) == 2


def test_review_transport_failure_does_not_trigger_schema_retry(tmp_path):
    c, _ = controller(tmp_path)
    c.config['repair_attempts'] = 2
    seen = []
    def timeout(*args, **kwargs):
        seen.append(args)
        raise Blocked('claude failed (TIMEOUT, -9)')
    c.call = timeout
    with pytest.raises(Blocked, match='TIMEOUT'):
        c.reviews('review', {'result': 'test'})
    assert len(seen) == 1


def test_failed_prefreeze_execution_reaches_author_before_any_review(tmp_path):
    c, packets = controller(tmp_path)
    c.demo=False
    c.config['repair_attempts']=1
    attempts=[];review_contexts=[]
    def preflight(bundle):
        attempts.append(bundle)
        return {'passed':len(attempts)>1,'stderr':'IndexError: weight array has 4 entries for 64 nodes'}
    c.verifier_preflight=preflight
    c.reviews=lambda *a,**k:review_contexts.append(k['context']) or []
    plan={'contract':'fixed plan fixture'}
    c.produce_reviewed('verifier','verifier_author','bundle',{'plan':plan})
    assert len(attempts)==2 and len(review_contexts)==1
    author_packets=[p for role,p in packets if role=='verifier_author']
    repair=author_packets[1]['repair_feedback'][0]
    assert repair['prior_artifact']==attempts[0]
    assert 'IndexError' in repair['runtime_diagnostic']['stderr']
    assert review_contexts[0]['bounded_preflight']['passed'] is True
    assert review_contexts[0]['plan']==plan
