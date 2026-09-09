from pathlib import Path
import shutil, json, zipfile, hashlib, sys
import pytest
import fitz
from cumcm2026.common import Blocked,load,save,sha256
from cumcm2026.builder import build,verify_bundle,release,make_print,compile_tex,REVIEW_KEYS
from cumcm2026.pdfcheck import inspect_pdf
from cumcm2026.validation import NO_AI,USED_PREFIX

ROOT=Path(__file__).parents[1]
pytestmark=pytest.mark.skipif(not shutil.which('xelatex'),reason='XeLaTeX required for real compilation')

@pytest.fixture(scope='module')
def built(tmp_path_factory):
    root=tmp_path_factory.mktemp('compiled')
    for kind,example in [('used','used_ai'),('unused','unused_ai_no_program')]:
        build(ROOT/'examples'/example,root/kind)
    return root

def text(pdf):
    with fitz.open(pdf) as d:return '\n'.join(p.get_text() for p in d).replace(' ','').replace('\n','')

def test_real_used_pdf(built):
    r=verify_bundle(built/'used');assert r['preflight']['status']=='PASS';assert r['release_ready'] is False
    assert 'AI工具使用详情.pdf' in r['support_inventory']
    assert text(built/'used/paper.pdf').find('AI工具使用声明')<text(built/'used/paper.pdf').find('参考文献')

def test_exact_code_archive_bytes(built):
    r=load(built/'used/build_report.json')
    with zipfile.ZipFile(built/'used/support.zip') as z:
        for p,h in r['source_inventory'].items():
            assert hashlib.sha256(z.read(p)).hexdigest()==h
            assert z.read(p)==(ROOT/'examples/used_ai'/p).read_bytes()

def test_source_in_appendix(built):
    t=text(built/'used/paper.pdf')
    for k in ('def fit','Zero variance','test_nonfinite'):
        assert k.replace(' ','') in t

def test_unused_branches(built):
    t=text(built/'unused/paper.pdf')
    assert NO_AI in t and USED_PREFIX not in t
    assert '本论文没有用到程序' in t and '本论文没有支撑材料' in t
    assert not (built/'unused/support.zip').exists()

def test_examples_cannot_release(built,tmp_path):
    with pytest.raises(Blocked):release(built/'used',tmp_path/'any.json',tmp_path/'release')

def test_stale_output_rejected(built):
    with pytest.raises(Blocked):build(ROOT/'examples/used_ai',built/'used')

def test_tamper_fails(built,tmp_path):
    shutil.copytree(built/'used',tmp_path/'output');p=tmp_path/'output/paper.pdf';p.write_bytes(p.read_bytes()+b'changed')
    with pytest.raises(Blocked):verify_bundle(tmp_path/'output')

def test_author_metadata_detected(built,tmp_path):
    with fitz.open(built/'used/paper.pdf') as d:
        m=d.metadata;m['author']='someone';d.set_metadata(m);d.save(tmp_path/'bad.pdf')
    r=inspect_pdf(tmp_path/'bad.pdf',example=True)
    assert any(e['code']=='author_metadata' for e in r['errors'])

def test_non_a4_detected(built,tmp_path):
    with fitz.open(built/'used/paper.pdf') as d:
        d[0].set_mediabox(fitz.Rect(0,0,612,792));d.save(tmp_path/'letter.pdf')
    assert any(e['code']=='not_a4' for e in inspect_pdf(tmp_path/'letter.pdf',example=True)['errors'])

def test_pdf_margin_injection(built,tmp_path):
    with fitz.open(built/'used/paper.pdf') as d:
        d[1].insert_text((5,20),'outside margin');d.save(tmp_path/'margin.pdf')
    assert any(e['code']=='content_outside_margins' for e in inspect_pdf(tmp_path/'margin.pdf',example=True)['errors'])

def test_pdf_ai_order_detected(built,tmp_path):
    with fitz.open(built/'used/paper.pdf') as d:
        # Add a second declaration heading using the built-in CJK font.
        d[0].insert_text((100,650),'AI工具使用声明',fontname='china-s',fontsize=12);d.save(tmp_path/'duplicate.pdf')
    assert any(e['code']=='ai_order' for e in inspect_pdf(tmp_path/'duplicate.pdf',example=True)['errors'])

def test_print_no_fabricated_forms(built,tmp_path):
    with pytest.raises(Blocked):make_print(built/'used/paper.pdf',tmp_path/'c.pdf',tmp_path/'n.pdf',tmp_path/'p.pdf',confirmed=False)

def test_print_body_identical(built,tmp_path):
    for name in ('c','n'):
        with fitz.open() as d:
            p=d.new_page(width=595.276,height=841.89);p.insert_text((90,110),'SYNTHETIC TEST FRONT PAGE - NOT OFFICIAL');d.save(tmp_path/f'{name}.pdf')
    r=make_print(built/'used/paper.pdf',tmp_path/'c.pdf',tmp_path/'n.pdf',tmp_path/'print.pdf',confirmed=True)
    assert r['body_pixel_identical']
    with fitz.open(tmp_path/'print.pdf') as d,fitz.open(built/'used/paper.pdf') as orig:assert len(d)==len(orig)+2

def copy_project(tmp_path):
    p=tmp_path/'project';shutil.copytree(ROOT/'examples/unused_ai_no_program',p);return p

def test_long_title_wraps(tmp_path):
    p=copy_project(tmp_path);c=load(p/'project.json');c['title']='针对复杂任务的数学建模、误差检验与结果可复核分析：'+('具有较长标题的排版稳定性验证'*4);save(p/'project.json',c)
    assert build(p,tmp_path/'out')['preflight']['status']=='PASS'

def test_abstract_overflow_rejected(tmp_path):
    p=copy_project(tmp_path);(p/'sections/abstract.tex').write_text('摘要长度边界验证。'*800,'utf-8')
    with pytest.raises(Blocked,match='Abstract'):build(p,tmp_path/'out')

def test_body_page_limit_rejected(tmp_path):
    p=copy_project(tmp_path);(p/'sections/analysis.tex').write_text(('边界页测试。\\newpage\n')*31,'utf-8')
    with pytest.raises(Blocked,match='body_overflow'):build(p,tmp_path/'out')

def test_true_nonexample_requires_bound_review(tmp_path):
    # Synthetic integration fixture intentionally uses the non-example code path.
    # It is not shipped as a competition deliverable or signed by a real person.
    p=copy_project(tmp_path);c=load(p/'project.json');c['example']=False;save(p/'project.json',c)
    r=build(p,tmp_path/'out')
    review=load(tmp_path/'out/review.required.json')
    save(tmp_path/'review.json',review)
    with pytest.raises(Blocked):release(tmp_path/'out',tmp_path/'review.json',tmp_path/'r')
    review.update(reviewer_alias='TEST_FIXTURE',checked_at='2026-09-09',bundle_digest='not-matching')
    review['checks']={k:True for k in REVIEW_KEYS};save(tmp_path/'review.json',review)
    with pytest.raises(Blocked):release(tmp_path/'out',tmp_path/'review.json',tmp_path/'r')
    review['bundle_digest']=r['bundle_digest'];save(tmp_path/'review.json',review)
    released=release(tmp_path/'out',tmp_path/'review.json',tmp_path/'r')
    assert released['auto_submission'] is False
    assert released['human_identity_authenticated'] is False
    assert list((tmp_path/'r').iterdir())==[tmp_path/'r/paper.pdf']

def test_native_adapter_contract(tmp_path):
    from cumcm2026.harness_adapter import attach
    calls=[]
    def original_compile(folder,main='main.tex'):
        calls.append(('compile',main));return compile_tex(folder,main)
    def original_preflight(pdf, *,denylist=(),require_ai=True):
        calls.append(('preflight',require_ai));return {'status':'PASS','failures':[],'warnings':[],
                  'pages':3,'body_pages':1,'legacy_preserved':'yes','pdf_sha256':sha256(pdf)}
    namespace={'build_paper':lambda:None,'build_ai_details':lambda:None,'compile_tex':original_compile,
               'preflight':original_preflight,'Blocked':Blocked,'PREAMBLE':''}
    attach(namespace);attach(namespace)
    (tmp_path/'main.tex').write_text(namespace['PREAMBLE']+r'''
\PaperKitTitle{接口契约测试}
\section*{摘要}本文件是隔离接口测试。\keywords{契约；测试}\label{abstract-end}\clearpage
\section{问题重述}这不是实际竞赛论文。
\section*{AI工具使用声明}
本参赛队在竞赛过程中使用了AI工具，主要用于接口测试，详细使用情况见支撑材料。
\section*{参考文献}本测试不引用外部文献。
\clearpage\section*{附录：支撑材料与完整源程序}仅验证接口。
\end{document}
''','utf-8')
    result=namespace['compile_tex'](tmp_path)
    qa=namespace['preflight'](tmp_path/'main.pdf')
    assert result['paperkit_profile'].endswith('1.0.0')
    assert qa['legacy_preserved']=='yes' and qa['status']=='PASS'
    assert calls==[('compile','main.tex'),('preflight',True)]


def test_size_gate_boundary_logic(built,monkeypatch):
    import cumcm2026.pdfcheck as checker
    p=built/'used/paper.pdf'
    monkeypatch.setattr(checker,'MAX_BYTES',p.stat().st_size)
    assert not any(e['code']=='file_too_large' for e in checker.inspect_pdf(p,example=True)['errors'])
    monkeypatch.setattr(checker,'MAX_BYTES',p.stat().st_size-1)
    assert any(e['code']=='file_too_large' for e in checker.inspect_pdf(p,example=True)['errors'])

def test_implementation_drift_blocks(built,monkeypatch):
    import cumcm2026.builder as builder
    monkeypatch.setattr(builder,'profile_digest',lambda:'changed-profile')
    with pytest.raises(Blocked,match='different implementation'):builder.verify_bundle(built/'used')
