"""Bounded local document import and source-preserving editorial changes.

No document code, macros, HTML, external relationship or archive member executes.
Unsupported math/image/table regions are retained rather than silently flattened.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import io
import re
import unicodedata
import zipfile
from lxml import etree as ET
from pathlib import Path
from .common import Blocked, IntegrityError, digest, file_hash, atomic_write

MAX_FILE_BYTES=12_000_000
MAX_TEXT=240_000
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M='http://schemas.openxmlformats.org/officeDocument/2006/math'
NS={'w':W,'m':M}
XML_SPACE='{http://www.w3.org/XML/1998/namespace}space'
SUFFIXES={'.md','.txt','.json','.docx','.pdf','.tex'}
SECRET=re.compile(r'(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:api[_ -]?key|access[_ -]?token|Authorization|密钥)\s*[:=：]\s*[\"\']?(?:Bearer\s+)?[A-Za-z0-9_-]{16,})',re.I)


def sha_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def local_file(path):
    path=Path(path).expanduser()
    if path.is_symlink() or not path.is_file():raise IntegrityError('Input must be a regular local file')
    if path.suffix.lower() not in SUFFIXES:raise Blocked('Supported document types: MD, TXT, JSON, DOCX, text PDF, TEX')
    if not 0<path.stat().st_size<=MAX_FILE_BYTES:raise Blocked('Input document exceeds the bounded import size or is empty')
    return path


def _xml(raw):
    try:
        node=ET.fromstring(raw,parser=ET.XMLParser(resolve_entities=False,no_network=True,load_dtd=False,huge_tree=False,recover=False))
    except ET.XMLSyntaxError as exc:raise IntegrityError('Unsafe or malformed document XML') from exc
    if node.getroottree().docinfo.doctype:raise IntegrityError('XML DTD refused in any encoding')
    return node

def _docx(raw):
    try:z=zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:raise IntegrityError('Not a valid DOCX ZIP') from exc
    infos=z.infolist();names=[i.filename for i in infos]
    if len(infos)>3000 or len(names)!=len(set(names)) or sum(i.file_size for i in infos)>50_000_000:
        raise IntegrityError('DOCX archive size/count/duplicate limit')
    for i in infos:
        n=i.filename
        if n.startswith('/') or '\\' in n or '..' in Path(n).parts or i.flag_bits&1 or ((i.external_attr>>16)&0o170000)==0o120000:
            raise IntegrityError('Unsafe DOCX archive entry')
        if n.lower().endswith(('.bin','.exe','.dll','.js')):raise Blocked('Embedded executable/OLE/macro package must be removed explicitly')
        if n.endswith(('.xml','.rels')):
            b=z.read(i)
            if b'<!DOCTYPE' in b.upper() or b'<!ENTITY' in b.upper():raise IntegrityError('XML entities/DTDs refused')
            parsed=_xml(b)
            if n.endswith('.rels'):
                for rel in parsed:
                    if rel.get('TargetMode')=='External' and not (rel.get('Type','').endswith('/hyperlink') and rel.get('Target','').startswith(('https://','http://'))):
                        raise Blocked('External DOCX templates/media are not safe editorial inputs')
    if 'word/document.xml' not in names:raise IntegrityError('Missing DOCX document.xml')
    return z,_xml(z.read('word/document.xml'))


def _plain_paragraph(p):
    # Preserve fields, equations, images, hyperlinks and their prose surroundings.
    refused={'drawing','pict','object','fldChar','instrText','hyperlink','tab','br','footnoteReference','endnoteReference','sdt','ins','del'}
    return not any(e.tag.startswith('{'+M+'}') or e.tag.split('}')[-1] in refused for e in p.iter())


def _math_ranges(text):
    """Locate complete and unfinished math before splitting editorial windows."""
    pairs={'$':'$', '$$':'$$', r'\(':r'\)', r'\[':r'\]'}
    opened=None;ranges=[]
    for match in re.finditer(r'(?<!\\)(\$\$|\$|\\[()\[\]])',text):
        token=match.group()
        if opened is None:
            if token in pairs:opened=(match.start(),pairs[token])
        elif token==opened[1]:
            ranges.append((opened[0],match.end()));opened=None
    if opened is not None:ranges.append((opened[0],len(text)))
    return ranges


def _split_plain(text,max_chars=1600):
    """Blocks retain exact offsets; no source text is silently dropped."""
    rows=[]
    for match in re.finditer(r'\S[\s\S]*?(?=\n\s*\n|\Z)',text):
        start,end=match.span()
        for pos in range(start,end,max_chars):
            stop=min(end,pos+max_chars)
            rows.append({'start':pos,'end':stop,'text':text[pos:stop]})
    return rows


def read_document(path,*,purpose='idea'):
    path=local_file(path);raw=path.read_bytes();kind=path.suffix.lower();warnings=[];regions=[]
    if kind=='.docx':
        z,root=_docx(raw)
        for name in z.namelist():
            if name.startswith(('word/header','word/footer','word/footnotes','word/endnotes','word/comments')) and name.endswith('.xml'):
                warnings.append('DOCX_PART_PRESERVED_NOT_PARSED:'+name)
        review_tags={'commentRangeStart','commentRangeEnd','commentReference',
                     'ins','del','moveFrom','moveTo','moveFromRangeStart','moveFromRangeEnd',
                     'moveToRangeStart','moveToRangeEnd','rPrChange','pPrChange','sectPrChange'}
        review_markup=any(e.tag.startswith('{'+W+'}') and e.tag.split('}')[-1] in review_tags for e in root.iter())
        # Review ranges can cross paragraphs/tables. Until their semantics are
        # resolved explicitly, retain the entire document without prose edits.
        if review_markup:warnings.append('DOCX_REVIEW_MARKUP_PRESENT_ALL_PROSE_PROTECTED')
        # Direct body paragraphs only; tables and mixed mathematical paragraphs stay immutable.
        body=root.find('w:body',NS);paragraphs=list(body.findall('w:p',NS)) if body is not None else []
        pieces=[]
        for index,p in enumerate(paragraphs):
            t=''.join(e.text or '' for e in p.iter('{'+W+'}t'))
            plain=_plain_paragraph(p)
            editable=bool(t.strip()) and plain and not review_markup
            if not plain:warnings.append('DOCX_COMPLEX_PARAGRAPH_PRESERVED_NOT_PARSED:'+str(index))
            if any(e.tag.startswith('{'+M+'}') for e in p.iter()):warnings.append('DOCX_MATH_PRESERVED_NOT_PARSED:'+str(index))
            if t.strip():
                if len(t)>12000:raise Blocked('DOCX paragraph exceeds 12000 characters; split it explicitly before import')
                start=sum(len(x)+2 for x in pieces);pieces.append(t)
                regions.append({'start':start,'end':start+len(t),'text':t,'docx_paragraph':index,'editable':editable})
        if body is not None and body.findall('w:tbl',NS):warnings.append('DOCX_TABLES_PRESERVED_NOT_EDITED')
        text='\n\n'.join(pieces);z.close()
        if body is not None and any(e.tag not in ('{'+W+'}p','{'+W+'}tbl','{'+W+'}sectPr') for e in body):
            warnings.append('DOCX_BODY_CONTAINER_PRESERVED_NOT_PARSED')
        if purpose=='idea' and warnings:
            raise Blocked('Idea DOCX contains unparsed equations/tables/fields or review markup; provide a verified Markdown transcription so ideas are not lost')
    elif kind=='.pdf':
        import fitz
        with fitz.open(stream=raw,filetype='pdf') as d:
            if d.needs_pass:raise Blocked('Encrypted PDF is unsupported')
            if len(d)>150:raise Blocked('PDF input exceeds 150-page bounded import')
            pages=[]
            for i,p in enumerate(d):
                t=p.get_text(sort=True)
                if len(t.strip())<20:raise Blocked('PDF has scanned/empty pages; provide a verified textual source')
                pages.append('[PAGE '+str(i+1)+']\n\n'+t)
            text='\n\n'.join(pages)
        warnings.append('PDF_TEXT_EXTRACTED_NOT_LAYOUT_OR_EQUATION_VERIFIED')
        warnings.append('PDF_ONLY_OUTPUT_IS_REVISED_MARKDOWN_NOT_A_REBUILT_CONTEST_PDF')
    else:
        try:text=raw.decode('utf-8-sig')
        except UnicodeError as exc:raise Blocked('Document must use UTF-8; convert explicitly without losing math') from exc
        if kind=='.json':
            import json
            try:value=json.loads(text,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
            except (ValueError,TypeError) as exc:raise IntegrityError('Malformed input JSON') from exc
            # Preserve JSON as source material, never load a supplied PASS or config as authority.
            if purpose=='paper':raise Blocked('Paper revision expects Markdown/TXT/DOCX/TEX/PDF, not a guessed paper JSON schema')
            warnings.append('JSON_IS_ADVISORY_TEXT_NOT_EXECUTABLE_CONFIG')
    if not text.strip() or len(text)>MAX_TEXT:raise Blocked('Document text is empty or exceeds 240000 characters')
    import os
    known=[v for k,v in os.environ.items() if k in ('EXA_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','CLAUDE_CODE_OAUTH_TOKEN') and len(v)>12]
    if '\x00' in text or SECRET.search(text) or any(k in text for k in known):raise Blocked('Remove credentials/control bytes from source material before import')
    code_ranges=[]
    if kind in ('.md','.txt'):
        opened=None
        for m in re.finditer(r'(?m)^\s*(```|~~~)[^\n]*',text):
            if opened is None:opened=(m.start(),m.group(1))
            elif opened[1]==m.group(1):code_ranges.append((opened[0],m.end()));opened=None
        if opened is not None:code_ranges.append((opened[0],len(text)))
    math_ranges=_math_ranges(text) if purpose=='paper' and kind!='.docx' else []
    if not regions:regions=[{**r,'editable':True} for r in _split_plain(text)]
    for i,row in enumerate(regions):
        row['id']='b'+str(i+1).zfill(4);row['sha256']=sha_text(row['text'])
        if purpose=='paper' and kind!='.docx':
            t=row['text']
            # Preserve fenced code, tables, math environments and all LaTeX control blocks.
            row['editable']=not any(x in t for x in ('```','~~~','\\begin','\\end','\\input','\\include')) and not t.lstrip().startswith(('|','[PAGE '))
            if kind=='.tex' and '\\' in t:row['editable']=False
            if any(row['start']<end and row['end']>start for start,end in code_ranges):row['editable']=False
            if any(row['start']<end and row['end']>start for start,end in math_ranges):row['editable']=False
    return {'format':kind[1:],'source_sha256':hashlib.sha256(raw).hexdigest(),
            'text':text,'text_sha256':sha_text(text),'blocks':regions,'warnings':sorted(set(warnings))}


PROTECTED=re.compile(r'\{\{(?:claim|cite):[^}]+\}\}|\$\$[\s\S]*?\$\$|(?<!\\)\$(?:\\.|[^$])*?\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|`[^`]*`|https?://[^\s<>]+|\[[0-9][0-9,，\-– ]*\]|\\[A-Za-z]+(?:\{[^{}]*\})*|[A-Za-z][A-Za-z0-9_./^-]*|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:\s*(?:%|‰|℃|万元|元|公里|米|千克|公斤|秒|分钟|小时|天|倍))?|[一二三四五六七八九十百千万]+(?:倍|成|元|小时|天)')


def protected_tokens(text):
    normalized=unicodedata.normalize('NFKC',text)
    tokens=Counter(PROTECTED.findall(normalized))
    # Conservative editorial guard, not a mathematical/semantic proof.
    for x in re.findall(r'>=|<=|!=|==|[<>≤≥≠=∈∉±]|不|未|无|否|不能|不可|可能|显著|证明|因果|相关|保证|确定|毫克|厘米|毫米|摄氏度',normalized):
        tokens['meaning:'+x]+=1
    return tokens


def validate_edit(before,after):
    if not isinstance(after,str) or not after.strip() or len(after)>max(3000,len(before)*2):raise IntegrityError('Invalid editorial replacement')
    if SECRET.search(after) or '\x00' in after or '^^' in after:raise IntegrityError('Unsafe editorial replacement')
    if protected_tokens(before)!=protected_tokens(after):raise IntegrityError('Editorial changes may not alter numbers, formulas, citations, code or technical tokens')
    if any(x in after for x in ('<script','javascript:','\\write','\\input','\\include')) and after!=before:raise IntegrityError('Editorial output contains executable markup')
    return after


def check_edits(document,edits):
    known={b['id']:b for b in document['blocks']};seen=set()
    for e in edits:
        if e['block_id'] not in known or e['block_id'] in seen:raise IntegrityError('Unknown/duplicate editorial block')
        b=known[e['block_id']];seen.add(e['block_id'])
        if not b['editable']:raise IntegrityError('Protected equation/table/field region is not editable')
        if e['before_sha256']!=b['sha256']:raise IntegrityError('Editorial patch is bound to another source version')
        validate_edit(b['text'],e['replacement'])
    return edits


def _replace_runs(paragraph,old,new):
    nodes=list(paragraph.iter('{'+W+'}t'));spans=[];pos=0
    for n in nodes:
        t=n.text or '';spans.append((pos,pos+len(t)));pos+=len(t)
    out=['']*len(nodes)
    def owner(index):
        return next((i for i,(a,b) in enumerate(spans) if a<=index<b),len(nodes)-1)
    for tag,a,b,c,d in SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
        if tag=='equal':
            for i,(s,e) in enumerate(spans):
                lo=max(a,s);hi=min(b,e)
                if lo<hi:out[i]+=old[lo:hi]
        elif tag in ('replace','insert'):
            out[owner(min(a,max(0,len(old)-1)))]+=new[c:d]
    for n,t in zip(nodes,out):n.text=t;n.set(XML_SPACE,'preserve')


def apply_edits(original,document,edits,destination):
    """Never overwrite source. DOCX assets and unedited XML entries remain exact."""
    original=Path(original);destination=Path(destination)
    if original.resolve()==destination.resolve():raise IntegrityError('Original paper may not be overwritten')
    if file_hash(original)!=document['source_sha256']:raise IntegrityError('Original paper changed after import')
    check_edits(document,edits);known={b['id']:b for b in document['blocks']}
    if document['format']=='docx':
        z,root=_docx(original.read_bytes());body=root.find('w:body',NS);ps=list(body.findall('w:p',NS))
        for e in edits:
            b=known[e['block_id']];p=ps[b['docx_paragraph']]
            if ''.join(n.text or '' for n in p.iter('{'+W+'}t'))!=b['text']:raise IntegrityError('DOCX paragraph alignment changed')
            _replace_runs(p,b['text'],e['replacement'])
        bio=io.BytesIO()
        with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as out:
            for info in z.infolist():
                out.writestr(info,ET.tostring(root,encoding='utf-8',xml_declaration=True) if info.filename=='word/document.xml' else z.read(info))
        z.close();atomic_write(destination,bio.getvalue())
    else:
        text=document['text']
        for e in sorted(edits,key=lambda x:known[x['block_id']]['start'],reverse=True):
            b=known[e['block_id']];text=text[:b['start']]+e['replacement']+text[b['end']:]
        atomic_write(destination,text)
    return {'path':destination.name,'sha256':file_hash(destination),'edits':len(edits),
            'semantic_equivalence':'INDEPENDENT_REVIEW_REQUIRED','scientific_revalidation':'NOT_RUN',
            'pdf_layout_preserved':False if document['format']=='pdf' else 'SOURCE_FORMAT_PRESERVED_NOT_RENDER_VERIFIED'}
