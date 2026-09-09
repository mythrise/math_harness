"""Frozen original problem, visual PDF evidence and paragraph-scale source units.

PDF extraction is only an aid; page images are always retained in this lane.
There is no OCR, network access, formula completion or domain-specific fallback.
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from .common import (Blocked,IntegrityError,atomic_write,write_json,read_json,
                     file_hash,digest,tree_manifest,verify_tree)

ENGINE='source-ledger-v1'
MAX_PAGES=80
MAX_SOURCE_BYTES=20_000_000
MAX_SOURCE_CHARS=180_000
MAX_UNIT_CHARS=18_000

class NeedsSourceInput(Blocked):
    status='NEEDS_SOURCE_INPUT'


def read_source_problem(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise IntegrityError('Original problem must be a regular file')
    if not 0<path.stat().st_size<=MAX_SOURCE_BYTES:raise NeedsSourceInput('Original problem size exceeds the source-lane bound')
    if path.suffix.lower()!='.pdf':
        from .intake import read_problem
        return read_problem(path)
    import fitz
    with fitz.open(path) as doc:
        if doc.needs_pass:raise NeedsSourceInput('Encrypted problem PDF needs a readable original')
        if not 0<len(doc)<=MAX_PAGES:raise NeedsSourceInput('PDF page limit exceeded; prepare a explicitly scoped source package')
        pages=[]
        for i,p in enumerate(doc):
            text=p.get_text(sort=True)
            if not text.strip():text='[NO_EXTRACTABLE_TEXT: READ THE FROZEN PAGE IMAGE]'
            pages.append(f'[PAGE {i+1}]\n{text}')
    text='\n\n'.join(pages)
    if len(text)>MAX_SOURCE_CHARS:raise NeedsSourceInput('Problem text exceeds the bounded source ledger')
    return text


def snapshot_problem(root,original,problem_text):
    root=Path(root);original=Path(original);folder=root/'problem_source'
    if folder.exists():raise IntegrityError('Source snapshot must only be created during fresh initialization')
    source_hash=file_hash(original);kind=original.suffix.lower().lstrip('.')
    dest=folder/('original.'+kind);atomic_write(dest,original.read_bytes())
    if file_hash(dest)!=source_hash:raise IntegrityError('Original changed while being snapshotted')
    if read_source_problem(dest)!=problem_text:raise IntegrityError('Original source changed between extraction and snapshot')
    pages=[]
    if kind=='pdf':
        import fitz
        marks=list(re.finditer(r'(?m)^\[PAGE (\d+)\]\n',problem_text))
        with fitz.open(dest) as doc:
            if len(marks)!=len(doc):raise IntegrityError('PDF page/raw text boundary mismatch')
            if len(doc)>MAX_PAGES:raise NeedsSourceInput('Too many source pages')
            for i,p in enumerate(doc):
                start=marks[i].start();end=marks[i+1].start() if i+1<len(marks) else len(problem_text)
                if p.rect.width*p.rect.height>2_000_000:raise NeedsSourceInput('Oversized PDF page needs explicit source preparation')
                image=folder/f'page-{i+1:04d}.png'
                p.get_pixmap(matrix=fitz.Matrix(128/72,128/72),alpha=False).save(image)
                pages.append({'id':f'P{i+1:04d}','page':i+1,
                    'anchor':{'start':start,'end':end,'quote':problem_text[start:end]},
                    'image':image.relative_to(root).as_posix(),'image_sha256':file_hash(image),
                    'status':'EXTRACTED_TEXT_NOT_VISUALLY_VERIFIED'})
    else:
        pages=[{'id':'T0001','page':None,'anchor':{'start':0,'end':len(problem_text),'quote':problem_text},
                'image':None,'image_sha256':None,'status':'ORIGINAL_TEXT'}]
    value={'schema_version':ENGINE,'format':kind,'original_path':dest.relative_to(root).as_posix(),
           'original_sha256':source_hash,'problem_sha256':hashlib.sha256(problem_text.encode()).hexdigest(),
           'pages':pages,'image_text_relation':'VISUAL_REVIEW_REQUIRED_FOR_PDF','ocr_used':False}
    write_json(folder/'manifest.json',value)
    return tree_manifest(folder)


def load_snapshot(root,intake):
    root=Path(root)
    expected=intake.get('problem_source_manifest')
    if not expected:raise NeedsSourceInput('This workspace lacks frozen original-page evidence. Start a NEW source-ledger-v1 workspace; do not retrofit frozen inputs.')
    verify_tree(root/'problem_source',expected)
    value=read_json(root/'problem_source/manifest.json')
    if value['original_sha256']!=intake['problem_original_sha256']:
        raise IntegrityError('Source snapshot does not match the original input')
    if value['problem_sha256']!=file_hash(root/'problem.md'):
        raise IntegrityError('Source snapshot does not match the frozen problem text')
    if file_hash(root/value['original_path'])!=value['original_sha256']:
        raise IntegrityError('Frozen original bytes changed')
    return value


def paragraph_units(text,anchor,page_id,*,identity,visual=False):
    """Never split a mathematical paragraph at a fixed character position.

    Blank-line paragraphs remain intact. A very large paragraph stops rather
    than silently cutting a denominator/table into unrelated independent claims.
    """
    units=[]
    for m in re.finditer(r'\S[\s\S]*?(?=\n[ \t]*\n|\Z)',text):
        a,b=m.span();body=text[a:b]
        if not body.strip():continue
        if len(body)>MAX_UNIT_CHARS:raise NeedsSourceInput('One source paragraph is too large; provide a verified paragraph/table split without altering math')
        if visual:
            raw_anchor=anchor
        else:
            raw_anchor={'start':anchor['start']+a,'end':anchor['start']+b,'quote':body}
        units.append({'id':'S'+digest([identity,page_id,a,b,body])[:20],
            'page_id':page_id,'text':body,'text_sha256':hashlib.sha256(body.encode()).hexdigest(),
            'anchor':raw_anchor,'visual':visual,
            'text_location':{'start':a,'end':b},'source_status':'VISUALLY_REVIEWED_TRANSCRIPTION' if visual else 'ORIGINAL_TEXT'})
    if not units:raise NeedsSourceInput('Source has no usable text units')
    return units


def source_packet_units(units):
    """Complete unit text for model packets; original-page anchors stay frozen.

    A PDF unit's raw anchor contains its entire original page. Repeating that
    page once for every paragraph multiplies tokens and reintroduces garbled
    text-layer fragments. Models select IDs, while the controller supplies exact
    anchors from the immutable full ledger after validation.
    """
    return [{key:u[key] for key in ('id','page_id','text','text_sha256','visual','source_status')}
            for u in units]


def make_batches(units,*,max_units=4,max_chars=9000):
    if type(max_units) is not int or max_units<1 or type(max_chars) is not int or max_chars<1:
        raise IntegrityError('Positive batch bounds required')
    out=[];batch=[];chars=0
    for u in units:
        if batch and (len(batch)>=max_units or chars+len(u['text'])>max_chars):
            out.append(batch);batch=[];chars=0
        batch.append(u);chars+=len(u['text'])
    if batch:out.append(batch)
    return out
