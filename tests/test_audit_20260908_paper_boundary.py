import pytest
from cumcm_harness.paper import preflight

def make_pdf(path, pages=37,spoof=True):
    import fitz
    d=fitz.open()
    for i in range(pages):
        p=d.new_page(width=595.276,height=841.89)
        text='摘要' if i==0 else '问题重述' if i==1 else '正文测试页'
        if i==1 and spoof:text+='\n附录：支撑材料与完整源程序'
        if i==pages-2:text+='\nAI工具使用声明\n参考文献'
        if i==pages-1:text='附录：支撑材料与完整源程序'
        p.insert_text((72,100),text,fontname='china-s',fontsize=12)
    d.save(path);d.close()

def test_spoofed_body_heading_cannot_establish_boundary(tmp_path):
    p=tmp_path/'x.pdf';make_pdf(p)
    assert preflight(p)['status']=='FAIL'

def test_trusted_boundary_still_enforces_page_limit(tmp_path):
    p=tmp_path/'x.pdf';make_pdf(p)
    r=preflight(p,trusted_appendix_page=37)
    assert r['status']=='FAIL' and r['body_pages']==35

def test_small_valid_document_retains_pass(tmp_path):
    p=tmp_path/'x.pdf';make_pdf(p,pages=4)
    assert preflight(p,trusted_appendix_page=4)['status']=='PASS'

@pytest.mark.parametrize('value',[0,-1,999,True,'4'])
def test_bad_boundary_cannot_pass(tmp_path,value):
    p=tmp_path/'x.pdf';make_pdf(p,pages=4)
    assert preflight(p,trusted_appendix_page=value)['status']=='FAIL'
