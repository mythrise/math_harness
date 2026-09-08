"""Unit tests must never read the operator's real local credential."""
import pytest


@pytest.fixture(autouse=True)
def isolated_exa_credential(tmp_path, monkeypatch):
    monkeypatch.setattr('cumcm_harness.credentials.EXA_KEY_FILE',
                        tmp_path/'.runtime/credentials/exa-api-key')
    monkeypatch.delenv('EXA_API_KEY', raising=False)
