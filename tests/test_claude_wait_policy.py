"""No live models: verify waiting, explicit failure and unchanged finite deadlines."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cumcm_harness.common import IntegrityError
from cumcm_harness.controller import Controller, DEFAULT_CONFIG, validate_config
from cumcm_harness.entry_inputs import initialize
from cumcm_harness.intake import create_workspace
from cumcm_harness.paper_revision import RevisionController
from cumcm_harness.process import clean_env, run_process
from cumcm_harness.providers import CLIProvider
from cumcm_harness.review_board import ProviderFailure
from cumcm_harness.store import Store


@pytest.mark.parametrize('value', [True, False, 0, -1, float('nan'), float('inf'), '180'])
def test_invalid_claude_deadline_rejected(value):
    with pytest.raises(IntegrityError, match='Claude timeout'):
        validate_config({**DEFAULT_CONFIG, 'claude_timeout': value})


def test_shipped_profiles_wait_without_a_claude_deadline():
    for path in (Path(__file__).resolve().parents[1] / 'configs').glob('*.json'):
        if path.name == 'exa-policy-r2.json':
            continue
        config = validate_config({**DEFAULT_CONFIG, **json.loads(path.read_text())})
        assert config['claude_timeout'] is None, path
    assert CLIProvider('claude').timeout is None
    assert CLIProvider('codex').timeout == 600
    assert validate_config({**DEFAULT_CONFIG, 'claude_timeout': 900})['claude_timeout'] == 900


@pytest.mark.parametrize('mode', ['research', 'revise'])
def test_actual_controllers_use_independent_claude_timeout(tmp_path, mode):
    if mode == 'research':
        problem = tmp_path / 'problem.md'
        problem.write_text('Public fixture: minimize cost with the supplied observations. ' * 3)
        data = tmp_path / 'data'
        data.mkdir()
        (data / 'values.csv').write_text('x,y\n1,2\n2,4\n')
        root = tmp_path / 'run'
        create_workspace(root, problem, data, DEFAULT_CONFIG)
        controller = Controller(root)
    else:
        paper = tmp_path / 'paper.md'
        paper.write_text('This is a language-editing fixture with no empirical claims. ' * 3)
        root = tmp_path / 'run'
        initialize(root, input_mode='revise', paper=paper, config=DEFAULT_CONFIG)
        controller = RevisionController(root)
    assert controller.providers['claude'].timeout is None
    assert controller.providers['codex'].timeout == DEFAULT_CONFIG['model_timeout']


@pytest.mark.parametrize('kind,role,schema,expected', [
    ('claude', 'math_reviewer', 'review', None),
    ('claude', 'hypothesis_critic', 'hypothesis_audit', None),
    ('claude', 'verifier_author', 'bundle', None),
    ('codex', 'math_reviewer', 'review', 180),
])
def test_dispatch_does_not_reapply_review_cap(tmp_path, monkeypatch, kind, role, schema, expected):
    controller = Controller.__new__(Controller)
    controller.root = tmp_path
    controller.store = Store(tmp_path)
    controller.config = dict(DEFAULT_CONFIG)
    controller.providers = {kind: CLIProvider(kind)}
    observed = []

    def explicit_failure(self, *args, **kwargs):
        observed.append(self.timeout)
        raise ProviderFailure(kind, 'EXPLICIT_TEST_FAILURE', retryable=False)

    monkeypatch.setattr(CLIProvider, 'invoke', explicit_failure)
    with pytest.raises(ProviderFailure, match='EXPLICIT_TEST_FAILURE'):
        controller._call_one('test', role, schema, {}, provider_kind=kind)
    assert observed == [expected]
    assert controller.store.get('model_calls_reserved') == 1


def test_no_deadline_survives_clock_advancing_beyond_old_caps(tmp_path, monkeypatch):
    from cumcm_harness import process
    ticks = iter([0.0, 3601.0, 7202.0, 10803.0])
    monkeypatch.setattr(process, 'time', SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda _: None))
    polls = iter([None, None, 0])
    child = SimpleNamespace(poll=lambda: next(polls), returncode=0)
    monkeypatch.setattr(process.subprocess, 'Popen', lambda *args, **kwargs: child)
    monkeypatch.setattr(process, 'terminate', lambda _: pytest.fail('Elapsed time terminated an unlimited call'))
    receipt = run_process(['fake-test-only'], cwd=tmp_path, out=tmp_path/'logs', env={}, timeout=None)
    assert receipt['status'] == 'EXITED'
    assert receipt['timeout_seconds'] is None
    assert receipt['seconds'] > 600


@pytest.mark.parametrize('exit_code', [0, 7])
def test_unlimited_real_subprocess_records_normal_or_explicit_failed_exit(tmp_path, exit_code):
    receipt = run_process([sys.executable, '-c', f'import time;time.sleep(.1);raise SystemExit({exit_code})'],
                          cwd=tmp_path, out=tmp_path/'logs', env=clean_env(), timeout=None)
    assert receipt['status'] == 'EXITED'
    assert receipt['returncode'] == exit_code
    assert receipt['timeout_seconds'] is None


def test_finite_worker_deadline_still_terminates(tmp_path):
    receipt = run_process([sys.executable, '-c', 'import time;time.sleep(5)'],
                          cwd=tmp_path, out=tmp_path/'logs', env=clean_env(), timeout=.1)
    assert receipt['status'] == 'TIMEOUT'


def test_unlimited_call_can_be_interrupted_and_reaps_child(tmp_path, monkeypatch):
    from cumcm_harness import process
    killed = []
    child = SimpleNamespace(poll=lambda: None, returncode=None)
    monkeypatch.setattr(process.subprocess, 'Popen', lambda *args, **kwargs: child)
    monkeypatch.setattr(process.time, 'sleep', lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(process, 'terminate', lambda p: killed.append(p))
    with pytest.raises(KeyboardInterrupt):
        run_process(['fake-test-only'], cwd=tmp_path, out=tmp_path/'logs', env={}, timeout=None)
    assert killed == [child]
