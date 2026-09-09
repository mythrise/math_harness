"""Render the actual immutable editorial output before any release attestation."""
from pathlib import Path
import shutil
from .common import (digest,file_hash,tree_manifest,verify_tree,write_json,read_json,
    InfrastructureUnavailable,ExecutionFailure,IntegrityError)
from .entry_documents import apply_edits
from .sandbox import Executor,Limits

DOCUMENT_IMAGE='cumcm-egoharness:0.5.0-rc2-documents'


def render_actual_pair(before,after,folder):
    """No host office/TeX execution, no repository, credentials or network mounts."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    inputs=folder/'inputs';inputs.mkdir();code=folder/'code';code.mkdir()
    source_worker=Path(__file__).with_name('revision_render_worker.py')
    shutil.copy2(source_worker,code/'render.py')
    builds={}
    for label,source in (('before',Path(before)),('after',Path(after))):
        if source.suffix=='.tex':
            from .tex_sandbox import compile_isolated
            build=folder/('tex-'+label);build.mkdir();shutil.copy2(source,build/'main.tex')
            builds[label]=compile_isolated(build,'main.tex')
            shutil.copy2(build/'main.pdf',inputs/(label+'.pdf'))
        elif source.suffix=='.docx':shutil.copy2(source,inputs/(label+'.docx'))
        else:raise InfrastructureUnavailable('This input format needs a supplied editable DOCX or standalone TeX for layout validation')
    executor=Executor(image=DOCUMENT_IMAGE)
    receipt=executor.execute(code,'render.py',inputs,folder/'output',[],Limits(seconds=360,memory_mb=2048,output_bytes=80_000_000),logdir=folder/'logs')
    report=read_json(folder/'output/layout.json')
    report.update(source_sha256=file_hash(before),modified_sha256=file_hash(after),execution_receipt=receipt,tex_builds=builds,
        renderer_image=DOCUMENT_IMAGE,network='NONE',host_mounts='STAGED_INPUTS_AND_OUTPUT_ONLY')
    return report


def prepare_revision(store,source,document,edits,*,fixture):
    identity={'source_sha256':file_hash(source),'document_digest':digest(document),'edits':edits,
        'fixture':fixture,'renderer_contract':'actual-revision-layout/1','image':DOCUMENT_IMAGE}
    key=digest(identity);folder=store.root/'revision_prepared'/key
    def prepare():
        folder.mkdir(parents=True,exist_ok=False)
        suffix='.md' if document['format']=='pdf' else '.'+document['format']
        revised=folder/('revised'+suffix)
        result=apply_edits(source,document,edits,revised)
        layout={'status':'DRAFT_PENDING_LAYOUT','reason':'FIXTURE_AUTO_RENDER_NOT_RUN' if fixture else 'UNSUPPORTED_INPUT_FORMAT',
            'source_sha256':file_hash(source),'modified_sha256':file_hash(revised),'science_revalidated':False,'contest_ready':False}
        if not fixture and document['format'] in ('docx','tex'):
            try:layout=render_actual_pair(source,revised,folder/'render')
            except (InfrastructureUnavailable,ExecutionFailure) as exc:
                layout.update(reason=type(exc).__name__+': '+str(exc),retained_logs='render/',status='DRAFT_PENDING_LAYOUT')
        write_json(folder/'layout-report.json',layout)
        return {'directory':str(folder.relative_to(store.root)),'revised_name':revised.name,
            'edited':result,'layout':layout,'manifest':tree_manifest(folder)}
    result=store.step('revision:prepare:'+key,identity,prepare)
    verify_tree(store.root/result['directory'],result['manifest'])
    return result
