from pathlib import Path
import io,zipfile,copy,json
import pytest
from lxml import etree as ET
from cumcm_harness.common import IntegrityError,Blocked,file_hash
from cumcm_harness.entry_documents import read_document,validate_edit,apply_edits,check_edits,sha_text,protected_tokens,_docx,W,M


def make_docx(path,text='本文模型的误差为 0.25，保持原有结论。',table=True,math=True):
    # Minimal valid OOXML fixture; ordinary text uses two runs to test preservation.
    root=ET.Element('{'+W+'}document',nsmap={'w':W,'m':M});body=ET.SubElement(root,'{'+W+'}body')
    p=ET.SubElement(body,'{'+W+'}p')
    for t in (text[:4],text[4:]):
        r=ET.SubElement(p,'{'+W+'}r');pr=ET.SubElement(r,'{'+W+'}rPr');ET.SubElement(pr,'{'+W+'}b')
        ET.SubElement(r,'{'+W+'}t').text=t
    if math:
        p=ET.SubElement(body,'{'+W+'}p');o=ET.SubElement(p,'{'+M+'}oMath');ET.SubElement(ET.SubElement(o,'{'+M+'}r'),'{'+M+'}t').text='x=1'
    if table:ET.SubElement(body,'{'+W+'}tbl')
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('word/document.xml',ET.tostring(root))
        z.writestr('word/styles.xml','<styles/>')
        z.writestr('word/media/image1.png',b'fixture-image-not-executed')
    return path


@pytest.mark.parametrize('before,after',[
 ('模型误差为 0.25。','模型的误差为 0.25。'),
 ('采用 MOSAIC。','这里采用 MOSAIC。'),
 ('参见[1]。','有关说明参见[1]。'),
 ('使用 $x=1$。','计算使用 $x=1$。'),
 ('增加 10% 后比较。','增加 10% 之后进行比较。'),
])
def test_polish_preserves_technical(before,after):assert validate_edit(before,after)==after

@pytest.mark.parametrize('before,after',[
 ('误差为 0.25。','误差为 0.20。'),('模型不成立。','模型成立。'),('约束 x < y。','约束 x > y。'),('可能改善。','保证改善。'),('相关关系。','因果关系。'),('成本为 3万元。','成本为 3元。'),
 ('采用 LSTM。','采用 ARIMA。'),('见[1]。','见[2]。'),('约束 $x<1$。','约束 $x>1$。'),
 ('增加三倍。','增加两倍。'),('参考 https://example.org/p。','参考 https://fake.org/p。'),
 ('使用 `x + y`。','使用 `x - y`。'),('代码不执行。','代码 \\input{/etc/passwd}'),
])
def test_polish_rejects_technical_changes(before,after):
    with pytest.raises(IntegrityError):validate_edit(before,after)

@pytest.mark.parametrize('suffix',['md','txt','tex','json'])
def test_read_supported_text(tmp_path,suffix):
    p=tmp_path/('input.'+suffix);p.write_text('{"idea":"Try a reliable baseline"}' if suffix=='json' else '讨论可靠的基准模型，并且验证假设。',encoding='utf8')
    d=read_document(p);assert d['source_sha256']==file_hash(p);assert d['blocks'];assert d['text_sha256']==sha_text(d['text'])

@pytest.mark.parametrize('bad',['','sk-proj-'+'a'*40,'api_key='+('b'*32),'text\x00hidden'])
def test_empty_secret_control_rejected(tmp_path,bad):
    p=tmp_path/'i.md';p.write_text(bad)
    with pytest.raises((Blocked,IntegrityError)):read_document(p)


def test_symlink_rejected(tmp_path):
    p=tmp_path/'a.md';p.write_text('an idea');q=tmp_path/'b.md';q.symlink_to(p)
    with pytest.raises(IntegrityError):read_document(q)


def test_all_long_text_is_preserved(tmp_path):
    p=tmp_path/'i.md';p.write_text('甲'*10000)
    d=read_document(p);assert ''.join(b['text'] for b in d['blocks'])==d['text'];assert all(len(b['text'])<=1600 for b in d['blocks'])


def test_code_blocks_remain_protected_across_blank_lines(tmp_path):
    p=tmp_path/'p.md';p.write_text('正文解释。\n\n```python\nx = 1\n\nx += 2\n```\n\n下一段文字。')
    d=read_document(p,purpose='paper');assert all(not b['editable'] for b in d['blocks'] if 'x ' in b['text'])


def test_docx_ideas_reject_unparsed_math(tmp_path):
    p=make_docx(tmp_path/'paper.docx')
    with pytest.raises(Blocked,match='transcription'):read_document(p,purpose='idea')


def test_docx_paper_preserves_math_and_package(tmp_path):
    p=make_docx(tmp_path/'paper.docx');d=read_document(p,purpose='paper');old=p.read_bytes()
    b=next(b for b in d['blocks'] if b['editable']);e={'block_id':b['id'],'before_sha256':b['sha256'],'replacement':b['text'].replace('本文模型','本文所用模型'),'reason':'保留数值与结论，改善语言表达。'}
    target=tmp_path/'revised.docx';apply_edits(p,d,[e],target)
    z1,r1=_docx(old);z2,r2=_docx(target.read_bytes())
    for name in z1.namelist():
        if name!='word/document.xml':assert z1.read(name)==z2.read(name)
    assert ET.tostring(r1.find('.//{'+M+'}oMath'))==ET.tostring(r2.find('.//{'+M+'}oMath'))
    assert p.read_bytes()==old
    assert '本文所用模型' in read_document(target,purpose='paper')['text']


def test_changed_original_rejected(tmp_path):
    p=tmp_path/'p.md';p.write_text('原始结果为 2。');d=read_document(p,purpose='paper');p.write_text('篡改结果为 9。')
    with pytest.raises(IntegrityError):apply_edits(p,d,[],tmp_path/'out.md')


def test_duplicate_and_stale_patch(tmp_path):
    p=tmp_path/'p.md';p.write_text('现有的结果为 2。');d=read_document(p,purpose='paper');b=d['blocks'][0]
    e={'block_id':b['id'],'before_sha256':b['sha256'],'replacement':'现有结果为 2。'}
    with pytest.raises(IntegrityError):check_edits(d,[e,e])
    e['before_sha256']='0'*64
    with pytest.raises(IntegrityError):check_edits(d,[e])


def test_original_never_overwritten(tmp_path):
    p=tmp_path/'p.md';p.write_text('现有结果为 2。');d=read_document(p,purpose='paper')
    with pytest.raises(IntegrityError):apply_edits(p,d,[],p)


@pytest.mark.parametrize('name,payload',[('../escape','x'),('word/vbaProject.bin','x'),('word/document.xml','<!DOCTYPE x [<!ENTITY x "bad">]><x/>')])
def test_docx_archive_hazards(tmp_path,name,payload):
    p=tmp_path/'p.docx'
    with zipfile.ZipFile(p,'w') as z:z.writestr(name,payload)
    with pytest.raises((Blocked,IntegrityError)):read_document(p,purpose='paper')


def test_pdf_is_not_claimed_editable_layout(tmp_path):
    import fitz
    p=tmp_path/'p.pdf'
    with fitz.open() as doc:
        pg=doc.new_page();pg.insert_text((72,72),'This is an existing scientific paper with error 0.25.');doc.save(p)
    d=read_document(p,purpose='paper');assert any('NOT_A_REBUILT' in w for w in d['warnings'])


def test_scanned_pdf_blocks(tmp_path):
    import fitz
    p=tmp_path/'p.pdf'
    with fitz.open() as doc:doc.new_page();doc.save(p)
    with pytest.raises(Blocked):read_document(p,purpose='paper')


def test_known_environment_credential_never_enters_model_packet(tmp_path,monkeypatch):
    value='synthetic-private-value-for-test-only'
    monkeypatch.setenv('EXA_API_KEY',value)
    p=tmp_path/'idea.md';p.write_text('错误复制的配置：'+value)
    with pytest.raises(Blocked):read_document(p)


def test_pdf_prose_remains_editable_without_changing_original_layout_claim(tmp_path):
    import fitz
    p=tmp_path/'input.pdf'
    with fitz.open() as d:
        page=d.new_page();page.insert_text((72,80),'A long ordinary paragraph for editing with result 0.25 and clear source scope.');d.save(p)
    doc=read_document(p,purpose='paper')
    assert any(b['editable'] for b in doc['blocks'])
    assert any(not b['editable'] and '[PAGE' in b['text'] for b in doc['blocks'])


def test_utf16_doctype_cannot_bypass_document_guard(tmp_path):
    xml='<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE doc [<!ENTITY external SYSTEM "file:///not-read-by-test">]><doc>&external;</doc>'
    p=tmp_path/'bad.docx'
    with zipfile.ZipFile(p,'w') as z:z.writestr('word/document.xml',xml.encode('utf-16'))
    with pytest.raises(IntegrityError):read_document(p,purpose='paper')


@pytest.mark.parametrize('formula',[
    '$'+'x+'*1000+'1$', '$$x +\n\ny$$', r'\['+'x+'*1000+r'1\]',
    r'\(x +'+'\n\ny'+r'\)', '$x +\n\ny',
])
def test_math_windows_cannot_be_polished_as_partial_prose(tmp_path,formula):
    p=tmp_path/'long.md';p.write_text('可编辑的前文。\n\n'+formula+'\n\n后续说明。')
    d=read_document(p,purpose='paper')
    assert d['blocks'][0]['editable']
    for b in d['blocks']:
        if 'x' not in b['text'] and 'y' not in b['text']:continue
        assert not b['editable']
        with pytest.raises(IntegrityError,match='Protected'):
            check_edits(d,[{'block_id':b['id'],'before_sha256':b['sha256'],
                           'replacement':b['text'].replace('+','*')}])


@pytest.mark.parametrize('markup',['commentRangeStart','ins','moveFrom','rPrChange'])
def test_docx_review_ranges_protect_all_prose(tmp_path,markup):
    p=make_docx(tmp_path/'review.docx',math=False,table=False)
    z,root=_docx(p.read_bytes());members={i.filename:z.read(i) for i in z.infolist()};z.close()
    pnode=root.find('.//{'+W+'}p');ET.SubElement(pnode,'{'+W+'}'+markup)
    second=ET.SubElement(root.find('{'+W+'}body'),'{'+W+'}p')
    ET.SubElement(ET.SubElement(second,'{'+W+'}r'),'{'+W+'}t').text='批注范围可能跨过此段。'
    members['word/document.xml']=ET.tostring(root)
    with zipfile.ZipFile(p,'w') as z:
        for name,data in members.items():z.writestr(name,data)
    original=p.read_bytes();d=read_document(p,purpose='paper')
    assert not any(b['editable'] for b in d['blocks'])
    assert 'DOCX_REVIEW_MARKUP_PRESENT_ALL_PROSE_PROTECTED' in d['warnings']
    assert p.read_bytes()==original
    with pytest.raises(Blocked,match='transcription'):read_document(p,purpose='idea')


def test_utf16_doctype_in_preserved_member_is_rejected(tmp_path):
    p=make_docx(tmp_path/'ancillary.docx',math=False,table=False)
    with zipfile.ZipFile(p,'a') as z:
        z.writestr('word/footnotes.xml','<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY ext SYSTEM "file:///never-read">]><x>&ext;</x>'.encode('utf-16'))
    with pytest.raises(IntegrityError):read_document(p,purpose='paper')
