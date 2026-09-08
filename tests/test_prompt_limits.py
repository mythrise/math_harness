"""Request preflight is local infrastructure, never a fabricated model response."""
import pytest
from cumcm_harness.common import read_json
from cumcm_harness.providers import CLIProvider,PromptPacketTooLarge


@pytest.mark.parametrize('text',['x'*1_040_000,'汉'*610_000])
def test_large_prompt_rejected_before_cli_probe_or_launch(tmp_path,monkeypatch,text):
    p=CLIProvider('codex')
    def forbidden(*args,**kwargs):raise AssertionError('No external process may start')
    monkeypatch.setattr(p,'probe',forbidden)
    monkeypatch.setattr('cumcm_harness.providers.run_process',forbidden)
    with pytest.raises(PromptPacketTooLarge):p.invoke('modeler','plan',{'text':text},tmp_path/'call')
    report=read_json(tmp_path/'call/preflight.json')
    assert report['status']=='REJECTED_BEFORE_EXTERNAL_CALL'
    assert report['reason']=='INPUT_TOO_LARGE'
    assert not (tmp_path/'call/receipt.json').exists()


def test_remote_size_failure_is_not_provider_availability(tmp_path,monkeypatch):
    p=CLIProvider('codex');monkeypatch.setattr(p,'probe',lambda:('fake','fixture-cli'))
    def failed(command,*,out,**kwargs):
        (out/'stderr.log').write_text('turn/start failed: input_too_large')
        (out/'stdout.log').write_text('')
        return {'status':'EXITED','returncode':1}
    monkeypatch.setattr('cumcm_harness.providers.run_process',failed)
    with pytest.raises(PromptPacketTooLarge):p.invoke('modeler','plan',{},tmp_path/'call')
    assert read_json(tmp_path/'call/process.json')['returncode']==1
