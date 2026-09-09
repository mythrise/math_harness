"""Rendered PDF checks adapted from the supplied PaperKit v1 pdfcheck.py.

Native differences: appendix boundary must be controller/compiler supplied;
example mode is an explicit argument, never inferred from authored prose;
placeholder wording is checked in the authored paper, not verbatim source code.
See third_party/paperkit_v1/UPSTREAM_MANIFEST.json for original bytes.
Machine PASS never certifies scientific truth/anonymity.
"""
from __future__ import annotations
import re
from pathlib import Path
import fitz
from .common import file_hash as sha256, PaperCompilationFailure as Blocked
import unicodedata
MAX_BYTES=20_000_000
NO_AI='本参赛队在竞赛过程中未使用任何AI工具。'
USED_PREFIX='本参赛队在竞赛过程中使用了AI工具，主要用于'
USED_SUFFIX='，详细使用情况见支撑材料。'
APPENDIX_TITLE='附录：支撑材料与完整源程序'
PLACEHOLDER_RE=re.compile(r'\[\[FILL[^\]]*\]\]|【(?:填写|待填|待补)[^】]*】|在此输入|关键词一|\bTODO\b|\bTBD\b',re.I)
SECRET_RE=re.compile(r'(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:api[_-]?key|access[_-]?token)\s*[=:]\s*["\']?[A-Za-z0-9_-]{16,})',re.I)
ABS_PATH_RE=re.compile(r'(?:/Users/[^\s/]+|/home/[^\s/]+|[A-Z]:\\Users\\[^\s\\]+)')
def compact(text):return re.sub(r'\s+','',unicodedata.normalize('NFKC',text))
def identity_scan(text,denylist):
    normalized=compact(text);issues=[]
    if any(compact(x) and compact(x) in normalized for x in denylist):issues.append('identity_denylist_match')
    if ABS_PATH_RE.search(text):issues.append('personal_absolute_path')
    if SECRET_RE.search(text) or SECRET_RE.search(normalized):issues.append('possible_secret')
    return issues

PT_PER_MM=72/25.4

def inspect_pdf(pdf: Path, *, ai_status='used',brief_purpose=None,denylist=(),abstract_end=None,
                appendix_page=None,kind='paper',example=False,require_ai=True) -> dict:
    errors=[];warnings=[]
    def err(code,detail): errors.append({'code':code,'detail':detail})
    try: doc=fitz.open(pdf)
    except Exception as e: raise Blocked(f'Unreadable PDF: {pdf.name}') from e
    if doc.needs_pass:
        doc.close();raise Blocked('Encrypted PDF is not accepted')
    texts=[p.get_text(sort=True) for p in doc];joined='\n'.join(texts);whole=compact(joined)
    if pdf.stat().st_size>MAX_BYTES: err('file_too_large','File exceeds conservative 20,000,000-byte cap')
    if not texts: err('empty_pdf','No pages')
    if doc.embfile_count(): err('embedded_files','Unexpected attachments in PDF')
    if (doc.metadata or {}).get('author',''): err('author_metadata','PDF author field must be blank under this anonymous profile')
    all_metadata=str(doc.metadata)+doc.get_xml_metadata()
    for issue in identity_scan(joined+'\n'+all_metadata,list(denylist)): err(issue,'PDF text or metadata match')
    authored='\n'.join(texts[:appendix_page-1]) if type(appendix_page) is int and 2<=appendix_page<=len(texts) else joined
    if PLACEHOLDER_RE.search(authored): err('placeholder_pdf','Unfilled template text in authored PDF pages')
    if '\ufffd' in joined: err('replacement_character','Unmapped replacement character in PDF')
    try:
        for xref in range(1,doc.xref_length()):
            # PDF actions/JavaScript are not appropriate for an inert contest PDF.
            obj=doc.xref_object(xref,compressed=True)
            if re.search(r'/(JavaScript|JS|Launch|RichMedia)\b',obj):
                err('active_pdf','Active/action content present');break
    except Exception:
        warnings.append('Object-level PDF action scan incomplete; manual review needed')
    boxes=[]
    margin=25*PT_PER_MM;tol=1.0
    for index,p in enumerate(doc):
        if abs(p.rect.width-595.276)>1 or abs(p.rect.height-841.89)>1 or p.rotation:
            err('not_a4',f'Page {index+1} is not upright A4')
        # Verify selectable text and visible bounding boxes. Vector strokes/images additionally inspected below.
        bottom_items=[]
        for b in p.get_text('dict')['blocks']:
            if b.get('type')==1:
                rect=fitz.Rect(b['bbox']);value='[image]'
                entries=[(rect,value)]
            else:
                entries=[(fitz.Rect(s['bbox']),s['text']) for l in b.get('lines',[]) for s in l.get('spans',[]) if s['text'].strip()]
            for rect,value in entries:
                # A footer page number may have descenders below its baseline; give it a separate check.
                footer=value.strip()==str(index+1) and rect.y0>p.rect.height-45*PT_PER_MM
                if footer:
                    bottom_items.append(rect)
                    if abs((rect.x0+rect.x1)/2-p.rect.width/2)>9: err('footer_not_centered',f'Page {index+1}')
                    if rect.y1>p.rect.height-margin+tol: err('footer_margin',f'Page {index+1}')
                elif rect.x0<margin-tol or rect.x1>p.rect.width-margin+tol or rect.y0<margin-tol or rect.y1>p.rect.height-margin+tol:
                    boxes.append({'page':index+1,'bbox':list(rect),'kind':'text_or_image'})
        if kind=='paper' and not bottom_items: err('page_number',f'Page {index+1}: missing continuous centered Arabic footer')
        # Vector paths include rules and plots; hairline tolerances avoid false positives at exactly 25mm.
        for drawing in p.get_drawings():
            r=drawing['rect']
            if r.x0<margin-tol or r.x1>p.rect.width-margin+tol or r.y0<margin-tol or r.y1>p.rect.height-margin+tol:
                boxes.append({'page':index+1,'bbox':list(r),'kind':'vector'})
    if boxes: err('content_outside_margins',f'{len(boxes)} text/image/vector objects outside 25mm page margins')
    pages=len(doc);doc.close()
    body_pages=None
    if kind=='paper':
        if not texts or '摘要' not in compact(texts[0]) or '关键词' not in compact(texts[0]): err('abstract_first','First page must contain abstract and keywords')
        if abstract_end is not None and abstract_end!=1: err('abstract_overflow',f'Abstract ends on page {abstract_end}, expected 1')
        if abstract_end is None: warnings.append('Summary end label not available; one-page summary needs manual confirmation')
        for i,t in enumerate(texts):
            for line in t.splitlines():
                if compact(line) in ('目录','目次','Contents','TableofContents'): err('toc_present',f'Table of contents heading on page {i+1}')
        if any(word in compact(texts[0]) for word in ('承诺书','编号专用页')): err('front_pages','Electronic paper contains paper-only front pages')
        ap=appendix_page
        if type(ap) is not int or ap<3 or ap>pages: err('missing_appendix','Missing/invalid appendix boundary')
        else:
            if compact(APPENDIX_TITLE) not in compact(texts[ap-1]): err('appendix_label','Appendix label disagrees with visible heading')
            body_pages=ap-2
            if body_pages>30: err('body_overflow',f'Body + declaration + references = {body_pages} pages (conservative count)')
        # Match distinct visible heading lines, not incidental prose mentions.
        def heading_offsets(target):
            offsets=[];pos=0
            for line in joined.splitlines(keepends=True):
                if compact(line)==target: offsets.append(pos)
                pos+=len(line)
            return offsets
        joined=authored
        whole=compact(authored)
        ah=heading_offsets('AI工具使用声明');rh=heading_offsets('参考文献')
        if require_ai and (len(ah)!=1 or len(rh)!=1 or (ah and rh and ah[0]>=rh[0])): err('ai_order','Exactly one AI declaration must precede the references heading')
        if not example and require_ai:
            if ai_status=='unused':
                if whole.count(compact(NO_AI))!=1 or compact(USED_PREFIX) in whole: err('ai_declaration','Missing/contradictory no-AI declaration')
            else:
                expected=compact(USED_PREFIX+brief_purpose+USED_SUFFIX) if brief_purpose is not None else None
                if whole.count(compact(USED_PREFIX))!=1 or compact(NO_AI) in whole or (expected is not None and expected not in whole) or compact(USED_SUFFIX) not in whole:
                    err('ai_declaration','Missing/contradictory AI-used official wording')
        elif example: warnings.append('Example mode: not a contest submission, regardless of machine pass')
    return {'status':'FAIL' if errors else 'PASS','pages':pages,'body_pages':body_pages,
            'bytes':pdf.stat().st_size,'pdf_sha256':sha256(pdf),'errors':errors,'warnings':warnings,
            'margin_violations':boxes[:30],'release_ready':False,
            'scope':'Machine formatting checks only; full visual, scientific, local-rule and anonymity review remain human responsibilities.'}
