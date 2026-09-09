from pathlib import Path
import json, sys, shutil, hashlib
import pytest
from cumcm2026.common import Blocked, safe_rel, under, esc, digest, save, load, run_bounded
from cumcm2026.validation import (validate_ai,check_fragment,check_citations,identity_scan,enumerate_sources,validate_project)
from cumcm2026.install import make_patch,git_blob,install,OLD_STATEMENT,NEW_STATEMENT
from cumcm2026.project import init_project

@pytest.mark.parametrize('bad',['../x','/tmp/x','a/../b','./a','a//b','C:/x','a\\b','a\nx','a#b','a/\u202ex'])
def test_path_rejects(bad):
    with pytest.raises(Blocked):safe_rel(bad)

@pytest.mark.parametrize('good',['code/main.py','data/数据.csv','AI工具使用详情.pdf'])
def test_path_accepts(good):assert safe_rel(good)==good

def test_symlink_rejected(tmp_path):
    (tmp_path/'real').write_text('x');(tmp_path/'link').symlink_to(tmp_path/'real')
    with pytest.raises(Blocked):under(tmp_path,'link')

def test_escape():assert esc('a_b&c%')==r'a\_b\&c\%'
def test_hash_stable():assert digest({'b':1,'a':2})==digest({'a':2,'b':1})

def ai_record():return {'id':'one','tool':'Local tool','version_or_model':'v1','stage':'debugging','purpose':'test',
    'prompting':'analyze input','process':'one interaction','adoption':'part','human_modification':'changed parsing',
    'human_verification':'compared expected answer','language_polishing_only':False}

@pytest.mark.parametrize('field',['tool','version_or_model','purpose','stage','prompting','process','adoption','human_modification','human_verification'])
def test_ai_missing_field(field):
    r=ai_record();del r[field]
    with pytest.raises(Blocked):validate_ai({'status':'used','brief_purpose':'test','records':[r]},'used')

def test_ai_polish_exception():
    r=ai_record();r['language_polishing_only']=True
    for k in ('adoption','human_modification','human_verification'):del r[k]
    assert validate_ai({'status':'used','brief_purpose':'polish','records':[r]},'used')

def test_ai_unused_contradiction():
    with pytest.raises(Blocked):validate_ai({'status':'unused','records':[ai_record()]},'unused')

def test_ai_unconfirmed_blocks():
    with pytest.raises(Blocked):validate_ai({'status':'unconfirmed','records':[]},'unconfirmed')

def test_ai_duplicates():
    with pytest.raises(Blocked):validate_ai({'status':'used','brief_purpose':'test','records':[ai_record(),ai_record()]},'used')

def test_ai_empty_used():
    with pytest.raises(Blocked):validate_ai({'status':'used','brief_purpose':'test','records':[]},'used')

@pytest.mark.parametrize('command',[r'\tableofcontents',r'\input{secret}',r'\geometry{margin=1cm}',r'\enlargethispage{2cm}',r'\write18{curl example}',r'\catcode1=2',r'\newcommand{\stealth}{x}',r'\end{document}','^^5cinput'])
def test_reserved_tex(command):
    with pytest.raises(Blocked):check_fragment(command,'test')

def test_commented_tex_is_ignored():check_fragment('% \\tableofcontents\n正常正文','test')
def test_latex_equations_allowed():check_fragment(r'\begin{equation}a=\frac{1}{2}\end{equation}','test')
def test_placeholder_blocks():
    with pytest.raises(Blocked):check_fragment('[[FILL:content]]','test')

def test_citations_match():check_citations(r'\cite{a}',r'\begin{thebibliography}{1}\bibitem{a} A\end{thebibliography}')
@pytest.mark.parametrize('refs',[r'\bibitem{b} B',r'\bibitem{a} A\bibitem{a} A',r'\bibitem{a} A\bibitem{b} B'])
def test_citations_mismatch(refs):
    with pytest.raises(Blocked):check_citations(r'\cite{a}',refs)

def test_identity_denylist():assert identity_scan('某某大学', ['某某大学'])
def test_identity_whitespace():assert identity_scan('某 某 大 学', ['某某大学'])
def test_secret():assert 'possible_secret' in identity_scan('api_key="0123456789abcdef012345"',[])
def test_personal_path():assert 'personal_absolute_path' in identity_scan('/home/alice/results.csv',[])

def test_sources_unclassified(tmp_path):
    (tmp_path/'hidden.py').write_text('print(1)')
    with pytest.raises(Blocked):enumerate_sources(tmp_path,{'code_roots':[],'support_files':[],'program_used':False})

def test_sources_exclusion(tmp_path):
    (tmp_path/'unused.py').write_text('print(1)')
    assert not enumerate_sources(tmp_path,{'code_roots':[],'support_files':[],'program_used':False,'excluded_code_files':{'unused.py':'Not used in modeling'}})

def test_binary_source_blocks(tmp_path):
    (tmp_path/'bad.py').write_bytes(b'\xff\xfe')
    with pytest.raises(Blocked):enumerate_sources(tmp_path,{'code_roots':['bad.py'],'support_files':[],'program_used':True})

def test_hidden_executable_support(tmp_path):
    (tmp_path/'bad.py').write_text('print(1)')
    with pytest.raises(Blocked):enumerate_sources(tmp_path,{'code_roots':[],'support_files':['bad.py'],'program_used':False})

def test_new_project_unconfirmed(tmp_path):
    p=tmp_path/'project';init_project(p)
    assert load(p/'project.json')['ai_status']=='unconfirmed'
    with pytest.raises(Blocked):validate_project(load(p/'project.json'))

def test_filename_alias_requires_reason():
    c=load(Path(__file__).parents[1]/'examples/used_ai/project.json')
    c['ai_details_filename']='AI 工具使用详情.pdf'
    with pytest.raises(Blocked):validate_project(c)
    c['ai_filename_override_reason']='Locally confirmed attachment typography convention'
    assert validate_project(c)

def test_timeout(tmp_path):
    with pytest.raises(Blocked):run_bounded([sys.executable,'-c','import time;time.sleep(5)'],tmp_path,0.1)

def test_installer_hash_guard(tmp_path):
    d=tmp_path/'cumcm_harness';d.mkdir();f=d/'paper.py';f.write_text('custom source')
    before=f.read_bytes()
    with pytest.raises(Blocked):install(tmp_path,apply=True)
    assert f.read_bytes()==before
    assert not (tmp_path/'.paperkit-backups').exists()

def test_patch_keeps_functions_and_replaces_only_declaration():
    source=('def build_paper():pass\ndef build_ai_details():pass\ndef preflight():pass\ndef compile_tex():pass\ns='+repr(OLD_STATEMENT)+'\n').encode()
    patched=make_patch(source).decode()
    assert NEW_STATEMENT in patched and OLD_STATEMENT not in patched
    assert 'def build_paper():pass' in patched
    assert '_paperkit_attach(globals(), expected_profile_digest=' in patched
    with pytest.raises(Blocked):make_patch(patched.encode())

def test_git_blob():assert git_blob(b'hello\n')=='ce013625030ba8dba906f756967f9e9ca394464a'


def test_adapter_profile_hash_guard():
    from cumcm2026.harness_adapter import attach
    with pytest.raises(RuntimeError,match='profile changed'):
        attach({},expected_profile_digest='wrong')


def test_official_caps_are_conservative_decimal():
    from cumcm2026.validation import MAX_BYTES
    assert MAX_BYTES==20_000_000

def test_project_unknown_keys_rejected():
    c=load(Path(__file__).parents[1]/'examples/used_ai/project.json');c['silently_disable_checks']=True
    with pytest.raises(Blocked,match='Schema'):validate_project(c)

def test_wrong_json_type():
    with pytest.raises(Blocked):validate_project([])


def test_install_restore_reinstall_is_reversible(tmp_path,monkeypatch):
    import cumcm2026.install as mod
    source=('def build_paper():pass\ndef build_ai_details():pass\ndef preflight():pass\ndef compile_tex():pass\ns='+repr(OLD_STATEMENT)+'\n').encode()
    (tmp_path/'cumcm_harness').mkdir();paper=tmp_path/'cumcm_harness/paper.py';paper.write_bytes(source)
    sentinel=tmp_path/'config.json';sentinel.write_text('KEEP_UNCHANGED')
    monkeypatch.setattr(mod,'INSPECTED_BLOB',git_blob(source))
    assert mod.install(tmp_path)['status']=='DRY_RUN' and paper.read_bytes()==source
    assert mod.install(tmp_path,apply=True)['status']=='INSTALLED'
    assert mod.uninstall(tmp_path)['status']=='RESTORED' and paper.read_bytes()==source
    assert mod.install(tmp_path,apply=True)['status']=='INSTALLED'
    assert sentinel.read_text()=='KEEP_UNCHANGED'

def test_uninstall_refuses_later_user_edits(tmp_path,monkeypatch):
    import cumcm2026.install as mod
    source=('def build_paper():pass\ndef build_ai_details():pass\ndef preflight():pass\ndef compile_tex():pass\ns='+repr(OLD_STATEMENT)+'\n').encode()
    (tmp_path/'cumcm_harness').mkdir();paper=tmp_path/'cumcm_harness/paper.py';paper.write_bytes(source)
    monkeypatch.setattr(mod,'INSPECTED_BLOB',git_blob(source));mod.install(tmp_path,apply=True)
    paper.write_bytes(paper.read_bytes()+b'\n# USER EDIT\n');edited=paper.read_bytes()
    with pytest.raises(Blocked):mod.uninstall(tmp_path)
    assert paper.read_bytes()==edited
