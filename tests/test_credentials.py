import json
import stat
import pytest
from cumcm_harness import credentials
from cumcm_harness.common import Blocked, IntegrityError
from cumcm_harness.literature import ExaClient, validate_query
from cumcm_harness.packaging import scan_release
from cumcm_harness.process import clean_env


KEY = 'fixture-local-exa-credential'


def test_local_roundtrip_permissions_environment_precedence(monkeypatch):
    assert credentials.get_exa_api_key() == ''
    path = credentials.save_exa_api_key(KEY)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert credentials.get_exa_api_key() == KEY
    monkeypatch.setenv('EXA_API_KEY', 'fixture-environment-override')
    assert credentials.get_exa_api_key() == 'fixture-environment-override'
    assert 'EXA_API_KEY' not in clean_env(provider=True)
    assert 'EXA_API_KEY' not in clean_env()


def test_broad_permissions_and_symlinks_block(tmp_path):
    path = credentials.save_exa_api_key(KEY)
    path.chmod(0o644)
    with pytest.raises(Blocked, match='owner-only'):
        credentials.get_exa_api_key()
    path.unlink()
    target = tmp_path/'unrelated'
    target.write_text('unrelated contents')
    path.symlink_to(target)
    with pytest.raises(Blocked):
        credentials.get_exa_api_key()
    with pytest.raises(Blocked):
        credentials.save_exa_api_key(KEY)
    assert target.read_text() == 'unrelated contents'


@pytest.mark.parametrize('value', ['', 'x', 'credential\nextra-line', 'x'*1025])
def test_invalid_values_are_not_persisted(value):
    with pytest.raises(Blocked):
        credentials.save_exa_api_key(value)
    assert not credentials.EXA_KEY_FILE.exists()


def test_saved_key_reaches_http_but_not_queries_cache_or_release(tmp_path, monkeypatch):
    credentials.save_exa_api_key(KEY)
    captured = []
    class Response:
        def __enter__(self):return self
        def __exit__(self, *args):pass
        def read(self, n):
            return json.dumps({'results':[{'url':'https://example.org', 'title':'Fixture',
                'text':'Long enough synthetic text for a transport contract test.'}]}).encode()
    class Opener:
        def open(self, request, timeout):
            captured.append(request)
            return Response()
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Opener())
    ExaClient(tmp_path/'cache').search('generic method')
    assert captured[0].get_header('X-api-key') == KEY
    assert all(KEY not in p.read_text() for p in (tmp_path/'cache').glob('*.json'))
    with pytest.raises(IntegrityError):
        validate_query('query '+KEY)
    release = tmp_path/'release'
    release.mkdir()
    (release/'note.txt').write_text(KEY)
    with pytest.raises(Blocked, match='Credential detected'):
        scan_release(release, [])
