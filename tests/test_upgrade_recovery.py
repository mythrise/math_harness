"""Real store/controller recovery with injected transports; no live model calls."""
import json
from pathlib import Path
import pytest

from cumcm_harness.common import Blocked, IntegrityError, ROOT, digest
from cumcm_harness.controller import Controller, DEFAULT_CONFIG, validate_config
from cumcm_harness.demo import responder
from cumcm_harness.providers import FixtureProvider
from cumcm_harness.review_board import ReviewBoard, ProviderFailure
from cumcm_harness.store import Store


def test_new_workspace_runtime_tracks_the_installed_release(tmp_path):
    from cumcm_harness import __version__
    from cumcm_harness.intake import create_workspace
    from cumcm_harness.sandbox import Executor
    expected='cumcm-egoharness:'+__version__
    problem=tmp_path/'problem.md';problem.write_text('Synthetic runtime configuration test')
    data=tmp_path/'data';data.mkdir();(data/'input.txt').write_text('fixture')
    workspace=tmp_path/'workspace'
    create_workspace(workspace,problem,data,dict(DEFAULT_CONFIG))
    assert json.loads((workspace/'config.json').read_text())['docker_image']==expected
    assert Executor().image==expected
    for path in (ROOT/'configs').glob('*.json'):
        assert {**DEFAULT_CONFIG,**json.loads(path.read_text())}['docker_image']==expected,path
    assert Executor(image='custom-harness:frozen').image=='custom-harness:frozen'


def controller(tmp_path, provider):
    c = Controller.__new__(Controller)
    c.root = tmp_path
    c.store = Store(tmp_path)
    c.config = {**DEFAULT_CONFIG, 'review_backoff_seconds': 0}
    c.providers = {'claude': provider, 'codex': provider}
    c.review_cycle = 1
    c.check_deadline = lambda: None
    c.demo = True
    c.review_board = ReviewBoard(c, sleep=lambda _: None)
    return c


@pytest.mark.parametrize('error', [KeyboardInterrupt, IntegrityError])
def test_interrupted_or_rejected_call_cannot_be_restarted_by_cycle_or_parent(tmp_path, error):
    class FailingProvider:
        count = 0
        def invoke(self, *args, **kwargs):
            self.count += 1
            raise error('injected interruption or integrity violation')
    provider = FailingProvider()
    c = controller(tmp_path, provider)
    packet = {'target_digest': digest('fixture')}
    with pytest.raises(error):
        c.review_board.invoke('old-parent', 'math_reviewer', 'review', packet)
    c.review_cycle += 1
    with pytest.raises(Blocked, match='recover-step'):
        c.review_board.invoke('new-parent', 'math_reviewer', 'review', packet)
    assert provider.count == 1
    assert c.store.get('model_calls_reserved') == 1


def test_completed_call_replays_after_crash_before_board_cache(tmp_path, monkeypatch):
    provider = FixtureProvider(responder)
    c = controller(tmp_path, provider)
    packet = {'target_digest': digest('fixture')}
    original = c.store.set
    interrupted = False
    def crash(key, value):
        nonlocal interrupted
        if key.startswith('provider-result:') and not key.endswith(':pending') and not interrupted:
            interrupted = True
            raise KeyboardInterrupt('crash after successful model step')
        return original(key, value)
    monkeypatch.setattr(c.store, 'set', crash)
    with pytest.raises(KeyboardInterrupt):
        c.review_board.invoke('old-parent', 'math_reviewer', 'review', packet)
    c.review_cycle += 1
    record = c.review_board.invoke('new-parent', 'math_reviewer', 'review', packet)
    assert record['result']['verdict'] == 'PASS'
    assert provider.count == c.store.get('model_calls_reserved') == 1
    assert c.store.audit()['integrity'] == 'PASS'


def test_direct_author_failure_retains_explicit_recovery_path(tmp_path):
    class Unavailable:
        def invoke(self, *args, **kwargs):
            raise ProviderFailure('codex', 'REMOTE_ERROR')
    c = controller(tmp_path, Unavailable())
    with pytest.raises(ProviderFailure):
        c.call('initial', 'supervisor', 'supervisor', {})
    with c.store.connect() as db:
        assert db.execute('SELECT status FROM steps WHERE key=?', ('model:initial',)).fetchone()['status'] == 'FAILED'


def test_unknown_running_work_blocks_before_new_cycle_or_external_calls(tmp_path):
    c = controller(tmp_path, FixtureProvider(responder))
    def interrupt():
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        c.store.step('model:prior-run', {}, interrupt)
    with pytest.raises(Blocked, match='Unknown RUNNING'):
        c._run()
    assert c.review_cycle == 1
    assert c.store.get('model_calls_reserved', 0) == 0


def test_legacy_profiles_stay_offline_and_online_profile_is_explicit():
    assert DEFAULT_CONFIG['network_policy'] == 'LOCAL_EVIDENCE_ONLY'
    assert DEFAULT_CONFIG['literature_enabled'] is False
    for name in ('practice', 'contest-2026', 'exa-resilient'):
        config = validate_config({**DEFAULT_CONFIG, **json.loads((ROOT/'configs'/f'{name}.json').read_text())})
        assert config['literature_enabled'] is (name == 'exa-resilient')
    with pytest.raises(IntegrityError, match='Online literature'):
        validate_config({**DEFAULT_CONFIG, 'literature_enabled': True})


def test_doctor_requires_exa_key_only_for_online_profile(monkeypatch):
    from cumcm_harness.cli import doctor, parser
    monkeypatch.setattr('cumcm_harness.tex_sandbox.probe',lambda:{'backend':'DOCKER_TEX','image_id':'fixture'})
    monkeypatch.delenv('EXA_API_KEY', raising=False)
    monkeypatch.setattr('cumcm_harness.cli.shutil.which', lambda name: '/fixture/'+name)
    assert doctor()['ready_for_live'] is True
    online = json.loads((ROOT/'configs/exa-resilient.json').read_text())
    assert doctor(config=online)['ready_for_live'] is False
    monkeypatch.setenv('EXA_API_KEY', 'fixture-only-not-a-secret')
    assert doctor(config=online)['ready_for_live'] is True
    assert parser().parse_args(['doctor', '--live', '--config', 'configs/exa-resilient.json']).config == Path('configs/exa-resilient.json')


def test_doctor_probes_the_selected_image(monkeypatch):
    from cumcm_harness.cli import doctor
    monkeypatch.setattr('cumcm_harness.tex_sandbox.probe',lambda:{'backend':'DOCKER_TEX','image_id':'fixture'})
    from cumcm_harness.sandbox import Executor
    seen = []
    monkeypatch.setattr('cumcm_harness.cli.shutil.which', lambda name: '/fixture/'+name)
    monkeypatch.setattr('cumcm_harness.providers.CLIProvider.probe', lambda self: ('fixture', 'fake-cli'))
    monkeypatch.setattr(Executor, 'probe', lambda self: seen.append(self.image) or {'backend':'DOCKER','image_id':'fixture'})
    assert doctor(live=True, config={'docker_image':'custom-harness:test'})['ready_for_live']
    assert seen == ['custom-harness:test']
