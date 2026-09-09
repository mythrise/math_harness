"""Native PaperKit boundary regressions; PDFs here are explicit test fixtures."""
import json
from pathlib import Path
import pytest
import fitz
from cumcm_harness.common import ROOT, IntegrityError, PaperCompilationFailure, file_hash
from cumcm_harness.paper import compile_tex, preflight
from cumcm_harness.paper_profile import STYLE, STYLE_NAME, prepare_style, profile_digest


def make_paper(path, *, extra='', appendix_extra='', example=False):
    texts=['摘要\n关键词：测试；检查',
           '问题重述\n'+extra+'\nAI工具使用声明\n'+
           ('本工程演示使用测试夹具。' if example else
            '本参赛队在竞赛过程中使用了AI工具，主要用于接口测试，详细使用情况见支撑材料。')+
           '\n参考文献\n本文件只验证排版。',
           '附录：支撑材料与完整源程序\n'+appendix_extra]
    with fitz.open() as doc:
        for i,text in enumerate(texts):
            page=doc.new_page(width=595.276,height=841.89)
            assert page.insert_textbox(fitz.Rect(82,90,512,640),text,fontname='china-s',fontsize=12)>=0
            page.insert_textbox(fitz.Rect(260,748,335,766),str(i+1),fontsize=10,align=1)
        doc.save(path)
    return path


def mutate(source,dest,edit):
    with fitz.open(source) as doc:
        edit(doc)
        doc.save(dest)
    return dest


def codes(pdf, **kwargs):
    return {e['code'] for e in preflight(pdf,trusted_appendix_page=3,**kwargs)['paperkit_checks']['errors']}


def test_native_style_is_the_supplied_style_and_is_fingerprinted():
    original=ROOT/'third_party/paperkit_v1/src/cumcm2026/assets'/STYLE_NAME
    # Docker infrastructure test snapshots also carry these explicit references.
    assert original.read_bytes()==STYLE.encode()==(ROOT/'templates'/STYLE_NAME).read_bytes()
    assert len(profile_digest())==64


def test_reference_tree_is_unmodified():
    root=ROOT/'third_party/paperkit_v1'
    manifest=json.loads((root/'UPSTREAM_MANIFEST.json').read_text())
    for name,sha in manifest['files'].items():
        assert file_hash(root/name)==sha,name


def test_style_drift_is_rejected_before_compilation(tmp_path):
    path=prepare_style(tmp_path);path.write_text(STYLE+'\n% changed')
    with pytest.raises(IntegrityError,match='differs'):compile_tex(tmp_path)


def test_style_symlink_rejected(tmp_path):
    target=tmp_path/'elsewhere';target.write_text(STYLE)
    (tmp_path/STYLE_NAME).symlink_to(target)
    with pytest.raises(IntegrityError,match='symlink'):prepare_style(tmp_path)


@pytest.mark.parametrize('message',[r'Overfull \hbox (1.0pt too wide)',r'Overfull \vbox (1.0pt too high)',
    'Missing character: There is no glyph','LaTeX Warning: There were undefined citations.'])
def test_latex_diagnostics_cannot_pass(tmp_path,monkeypatch,message):
    (tmp_path/'main.tex').write_text('Test fixture')
    def fake_compiler(folder,main):
        (folder/'main.pdf').write_bytes(b'NOT_A_REAL_PDF')
        (folder/'main.log').write_text(message)
        return {'backend':'SYNTHETIC_FIXTURE'}
    monkeypatch.setattr('cumcm_harness.tex_sandbox.compile_isolated',fake_compiler)
    with pytest.raises(PaperCompilationFailure):compile_tex(tmp_path)

def test_missing_compiler_log_cannot_pass(tmp_path,monkeypatch):
    (tmp_path/'main.tex').write_text('Test fixture')
    def fake_compiler(folder,main):
        (folder/'main.pdf').write_bytes(b'NOT_A_REAL_PDF')
        return {'backend':'SYNTHETIC_FIXTURE'}
    monkeypatch.setattr('cumcm_harness.tex_sandbox.compile_isolated',fake_compiler)
    with pytest.raises(PaperCompilationFailure,match='log is missing'):compile_tex(tmp_path)


@pytest.mark.parametrize('kind',['text','vector','rotation','footer','author','xml_identity','toc','duplicate_ai'])
def test_actual_pdf_defects_block(tmp_path,kind):
    original=make_paper(tmp_path/'valid.pdf')
    assert not codes(original)
    def change(doc):
        if kind=='text':doc[1].insert_text((5,20),'outside')
        elif kind=='vector':doc[1].draw_line((5,15),(55,15))
        elif kind=='rotation':doc[1].set_rotation(90)
        elif kind=='footer':
            doc[1].add_redact_annot(fitz.Rect(250,730,345,775));doc[1].apply_redactions()
        elif kind=='author':doc.set_metadata({'author':'TEST_IDENTITY'})
        elif kind=='xml_identity':doc.set_xml_metadata('<x>TEST IDENTITY</x>')
        elif kind=='toc':doc[1].insert_text((90,660),'目录',fontname='china-s',fontsize=12)
        elif kind=='duplicate_ai':doc[0].insert_text((90,660),'AI工具使用声明',fontname='china-s',fontsize=12)
    bad=mutate(original,tmp_path/'bad.pdf',change)
    expected={'text':'content_outside_margins','vector':'content_outside_margins','rotation':'not_a4',
              'footer':'page_number','author':'author_metadata','xml_identity':'identity_denylist_match',
              'toc':'toc_present','duplicate_ai':'ai_order'}[kind]
    assert expected in codes(bad,denylist=['TESTIDENTITY'])


def test_prose_cannot_enable_example_exemption(tmp_path):
    pdf=make_paper(tmp_path/'example-wording.pdf',example=True)
    assert 'ai_declaration' in codes(pdf)
    assert not codes(pdf,demo=True)


def test_literal_source_placeholders_are_not_authored_template_placeholders(tmp_path):
    assert not codes(make_paper(tmp_path/'source.pdf',appendix_extra='TODO variable in source'))
    assert 'placeholder_pdf' in codes(make_paper(tmp_path/'body.pdf',extra='TODO'))
