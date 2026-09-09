#!/usr/bin/env python3
"""Synthetic model/Exa fault injection with real Docker numerics and TeX.

Use a NEW workspace. A valid first-PDF rejection must produce a new PDF; the
second complete run must reuse calls, numerical jobs and frozen deliverables.
"""
import argparse
from pathlib import Path
from cumcm_harness import exa_r2_demo
from cumcm_harness.resilience_demo import run_resilience_demo
from cumcm_harness.sandbox import Executor
from cumcm_harness.common import Blocked, file_hash, write_json
from cumcm_harness.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    if root.exists() and any(root.iterdir()):
        raise Blocked('Use a new empty workspace; prior evidence is preserved')
    original = exa_r2_demo.r2_responder
    rejected = []

    def responder(role, schema, packet):
        result = original(role, schema, packet)
        if schema == 'paper' and packet.get('repair_feedback'):
            result['limitations'].append('修订稿明确补充视觉审查所要求的图示适用范围说明。')
        if schema == 'review' and role == 'paper_reviewer':
            pdf = packet['artifact']['pdf_sha256']
            if not rejected:
                rejected.append(pdf)
            if pdf == rejected[0]:
                result.update(verdict='FAIL', findings=[{
                    'severity':'P1', 'location':'figure scope',
                    'issue':'Synthetic visual repair injection: clarify figure applicability.',
                    'required_fix':'Add an explicit figure scope limitation and submit a new PDF.'}])
        return result

    def snapshot():
        store = Store(root)
        with store.connect() as connection:
            jobs = [dict(row) for row in connection.execute('SELECT id,status FROM jobs ORDER BY id')]
        return {'model_calls':store.get('model_calls_reserved'),
                'exa_calls':store.get('exa_requests_reserved'), 'jobs':jobs,
                'pdf':file_hash(root/'deliverables/paper.pdf'),
                'zip':file_hash(root/'deliverables/support.zip')}

    exa_r2_demo.r2_responder = responder
    try:
        result = run_resilience_demo(root, r2=True, executor=Executor())
        before = snapshot()
        run_resilience_demo(root, r2=True, executor=Executor())
        after = snapshot()
    finally:
        exa_r2_demo.r2_responder = original
    versions = sorted((root/'paper_versions').glob('*/main.pdf'))
    assert before == after, 'Replay changed reservations, jobs or frozen artifacts'
    assert len(versions) == 2 and len({file_hash(p) for p in versions}) == 2
    assert len(list((root/'selftests').glob('*/out/tests.json'))) == 4
    write_json(args.report, {'status':'PASS',
        'scope':'SYNTHETIC_MODEL_EXA_WITH_REAL_DOCKER_NUMERICS_AND_TEX',
        'acceptance_scope':result['acceptance_scope'],
        'versions':[{'draft':p.parent.name,'pdf_sha256':file_hash(p)} for p in versions],
        'before':before,'after':after,'numerical_jobs':len(before['jobs']),
        'variant_selftests':4,'valid_negative_preserved':True})
    print('PASS: actual Docker/TeX, rejected PDF -> new PDF, unchanged complete replay')


if __name__ == '__main__':
    main()
