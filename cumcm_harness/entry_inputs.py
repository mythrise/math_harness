"""First-class three-mode input snapshots, separate from problem truth and data.

Mode is independent of practice/contest. Raw external chats remain private; only
source hashes and user-reported AI metadata enter release provenance.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from .common import Blocked, IntegrityError, digest, file_hash, read_json, write_json, atomic_write, tree_manifest, verify_tree
from .entry_documents import read_document,local_file,SECRET,sha_text

MODES=('scratch','idea','revise')
ENTRY_VERSION='cumcm-entry/1'
MAX_IDEA_FILES=6
MAX_IDEA_TOTAL=240000
META_KEYS={'tool','model','used_at','purpose','prompt_summary','output_summary','adoption','human_modification','human_verification'}


def external_metadata(path,count):
    if path is None:
        return [{'source_type':'unspecified_external_source','tool':'UNREPORTED','model':'UNREPORTED','used_at':'UNREPORTED',
            'purpose':'网页讨论与人工思路的初版建模建议','prompt_summary':'USER_RECORD_NOT_PROVIDED',
            'output_summary':'外部初版思路；尚未核验','adoption':'PENDING_REVIEW',
            'human_modification':'NOT_REPORTED','human_verification':'NOT_ATTESTED'} for _ in range(count)]
    path=local_file(path)
    value=read_json(path)
    if not isinstance(value,list) or len(value)!=count:raise IntegrityError('External AI metadata must be one ordered record per idea file')
    for row in value:
        if not isinstance(row,dict) or set(row)-{'source_type'}!=META_KEYS:raise IntegrityError('External AI record has missing/unknown fields')
        row.setdefault('source_type','unspecified_external_source')
        if row['source_type'] not in ('external_ai_chat','human_notes','mixed_human_ai','unspecified_external_source'):raise IntegrityError('Unknown external source type')
        if any(not isinstance(v,str) or not 1<=len(v)<=2000 or SECRET.search(v) for v in row.values()):raise IntegrityError('Invalid or sensitive external AI metadata')
    return value


def prepare_entry(mode,*,ideas=(),paper=None,metadata=None):
    if mode not in MODES:raise IntegrityError('Unknown input mode')
    if mode=='idea' and not ideas:raise Blocked('Idea mode needs at least one --prior-idea')
    if mode!='idea' and ideas:raise Blocked('--prior-idea is only accepted in idea mode')
    if mode=='revise' and paper is None:raise Blocked('Revise mode needs --paper')
    if mode!='revise' and paper is not None:raise Blocked('--paper belongs to revise mode; it cannot replace the official problem')
    if metadata is not None and not ideas:raise IntegrityError('External AI metadata without idea documents')
    if len(ideas)>MAX_IDEA_FILES:raise Blocked('At most six independent idea documents are accepted')
    documents=[];seen=set();total=0
    records=external_metadata(metadata,len(ideas))
    for i,path in enumerate(ideas):
        d=read_document(path,purpose='idea')
        if d['source_sha256'] in seen:raise IntegrityError('Duplicate idea document')
        seen.add(d['source_sha256']);total+=len(d['text'])
        if total>MAX_IDEA_TOTAL:raise Blocked('Combined external ideas exceed 240000 characters')
        documents.append({'id':f'idea_{i+1:02d}','input':Path(path),'document':d,'ai_record':records[i]})
    revision=None
    if mode=='revise':revision={'input':Path(paper),'document':read_document(paper,purpose='paper')}
    return {'mode':mode,'ideas':documents,'revision':revision}


def install_entry(root,prepared):
    """Only called during initialization, never retrofit an existing frozen run."""
    from .store import Store
    root=Path(root);store=Store(root)
    if (root/'entry.json').exists() or store.get('entry_inputs') is not None:raise IntegrityError('Entry mode already frozen')
    entry={'schema_version':ENTRY_VERSION,'input_mode':prepared['mode'],
        'ideas':[],'paper':None,'raw_external_content_is_authority':False,
        'original_problem_remains_authoritative':True,'full_research_required':prepared['mode']!='revise'}
    for row in prepared['ideas']:
        rel='entry/ideas/'+row['id']+'.'+row['document']['format']
        raw=row['input'].read_bytes()
        if __import__('hashlib').sha256(raw).hexdigest()!=row['document']['source_sha256']:raise IntegrityError('Idea changed while initializing')
        atomic_write(root/rel,raw)
        docrel='entry/ideas/'+row['id']+'.normalized.json';write_json(root/docrel,row['document'])
        entry['ideas'].append({'id':row['id'],'path':rel,'document_path':docrel,
            'source_sha256':row['document']['source_sha256'],'ai_record':row['ai_record'],
            'epistemic_status':'PROPOSAL_ONLY','read_warnings':row['document']['warnings']})
    if prepared['revision']:
        row=prepared['revision'];d=row['document'];rel='entry/paper/original.'+d['format']
        if file_hash(row['input'])!=d['source_sha256']:raise IntegrityError('Paper changed while initializing')
        atomic_write(root/rel,row['input'].read_bytes());write_json(root/'entry/paper/document.json',d)
        entry['paper']={'path':rel,'document_path':'entry/paper/document.json','source_sha256':d['source_sha256'],
            'scientific_status':'USER_SUPPLIED_NOT_REVALIDATED','read_warnings':d['warnings']}
    (root/'entry').mkdir(exist_ok=True)
    write_json(root/'entry.json',entry)
    frozen={'entry_digest':digest(entry),'files':tree_manifest(root/'entry')}
    store.set('entry_inputs',frozen)
    public={'schema_version':ENTRY_VERSION,'input_mode':entry['input_mode'],
        'entry_digest':digest(entry),'external_sources':[{'id':r['id'],'source_sha256':r['source_sha256'],
            'ai_record':r['ai_record'],'epistemic_status':'USER_REPORTED_EXTERNAL_MATERIAL_NOT_LIVE_CLI_RECEIPT'} for r in entry['ideas']],
        'paper_source_sha256':entry['paper']['source_sha256'] if entry['paper'] else None,
        'official_problem_not_replaced':True,'auto_submission':False}
    write_json(root/'input_provenance.json',public)
    store.set('entry_public_digest',digest(public))
    store.event('ENTRY_INPUTS_FROZEN',{'input_mode':entry['input_mode'],'entry_digest':digest(entry),
        'raw_chats_in_release':False})
    return entry


def load_entry(root,*,required=False):
    from .store import Store
    root=Path(root);store=Store(root);frozen=store.get('entry_inputs');path=root/'entry.json'
    if frozen is None and not path.exists():
        if required:raise IntegrityError('Missing frozen three-mode entry')
        return None
    if not frozen or not path.is_file():raise IntegrityError('Entry sidecar added/removed outside initialization')
    value=read_json(path)
    if value.get('schema_version')!=ENTRY_VERSION or value.get('input_mode') not in MODES or digest(value)!=frozen['entry_digest']:
        raise IntegrityError('Input mode or source manifest changed')
    verify_tree(root/'entry',frozen['files'])
    public=read_json(root/'input_provenance.json')
    if digest(public)!=store.get('entry_public_digest'):raise IntegrityError('Input disclosure changed after initialization')
    for row in value['ideas']+([value['paper']] if value['paper'] else []):
        if file_hash(root/row['path'])!=row['source_sha256']:raise IntegrityError('Imported source hash mismatch')
        doc=read_json(root/row['document_path'])
        if sha_text(doc['text'])!=doc['text_sha256']:raise IntegrityError('Normalized input hash mismatch')
    return value


def public_external_records(root):
    entry=load_entry(root)
    if not entry:return []
    records=[]
    for i,row in enumerate(entry['ideas']):
        meta=row['ai_record'];h=row['source_sha256']
        if meta.get('source_type')=='human_notes':continue
        records.append({'provider':meta['tool'],'transport':('USER_REPORTED_WEB_CHAT' if meta.get('source_type') in ('external_ai_chat','mixed_human_ai') else 'USER_REPORTED_EXTERNAL_SOURCE'),
            'role':'external_idea','invocation_id':'external-source-'+h[:24],
            'cli_version':'NOT_APPLICABLE','model_requested':'NOT_REPORTED',
            'model_reported':meta['model'],'response_digest':h,'prompt_sha256':'NOT_RECORDED_BY_HARNESS',
            'packet_digest':digest({'entry':digest(entry),'source':h}),'model_execution_status':'IMPORTED_NOT_EXECUTED_BY_HARNESS',
            'call_index':-len(entry['ideas'])+i,'skill_digest':'NOT_APPLICABLE','usage_disclosure':{
                'stage':'赛前或赛中网页端思路讨论','purpose':meta['purpose'],'response_contract':'external_source',
                'prompt_method':meta['prompt_summary'],'output_summary':meta['output_summary'],
                'skill_ids':[],'skill_digest':'NOT_APPLICABLE','actual_input_fields':[],
                'human_review':meta['human_verification'],'source':'USER_REPORTED_NOT_MACHINE_ATTESTED'},
            'external_user_record':copy.deepcopy(meta)})
    return records


def initialize(root,*,input_mode,problem=None,data=None,config,ideas=(),paper=None,metadata=None,
               confirmation=None,private_dev=None,private_confirm=None,sources=None,exa_policy=None,research_cutoff=None):
    """Validate all documents first; atomically publish a fresh workspace."""
    from .intake import create_workspace,read_problem
    from .store import Store
    from .controller import validate_config
    root=Path(root).expanduser().resolve();config=validate_config(copy.deepcopy(config))
    if root.exists():raise Blocked('Use a new absent workspace path; initialized runs are immutable')
    if data is not None:
        data_root=Path(data).resolve()
        if root.is_relative_to(data_root):raise IntegrityError('Workspace cannot be inside the input data directory')
        if any(Path(path).resolve().is_relative_to(data_root) for path in ideas):
            raise IntegrityError('Keep raw idea/chat files separate from official solver data')
    if problem is not None and any(file_hash(Path(problem))==file_hash(Path(path)) for path in ideas):
        raise IntegrityError('Official problem and preliminary idea must be separate sources')
    prepared=prepare_entry(input_mode,ideas=ideas,paper=paper,metadata=metadata)
    if input_mode=='idea' and config['mode']=='contest':
        for item in prepared['ideas']:
            meta=item['ai_record']
            if meta.get('source_type')!='human_notes' and (meta['tool']=='UNREPORTED' or meta['prompt_summary']=='USER_RECORD_NOT_PROVIDED'):
                raise Blocked('Contest idea mode requires truthful external AI tool/prompt records before initialization')
    if input_mode!='revise':
        if problem is None:raise Blocked('Scratch/idea requires the official --problem')
        if input_mode=='idea' and not config.get('materials_workflow'):raise Blocked('Idea mode requires materials_workflow=true for the complete preparation path')
    elif any(x is not None for x in (confirmation,private_dev,private_confirm,exa_policy,research_cutoff,sources)):
        raise Blocked('Revision is not research; reroute substantive changes to a fresh idea/scratch run')
    root.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.entry-staging-',dir=root.parent) as td:
        staging=Path(td)/'workspace'
        if input_mode=='revise':
            if data is not None:raise Blocked('Paper polishing does not silently use --data or revalidate experiments')
            staging.mkdir();write_json(staging/'config.json',config)
            text=read_problem(Path(problem)) if problem else 'No original problem supplied. Editorial-only review; do not assert complete problem coverage.'
            atomic_write(staging/'problem.md',text)
            store=Store(staging);store.set('revision_frozen',{'config':digest(config),'problem':sha_text(text)})
            store.set('status','REVISION_INITIALIZED')
        else:
            if data is None:
                data=Path(td)/'empty-data';data.mkdir()
            create_workspace(staging,Path(problem),Path(data),config,confirmation=confirmation,
                private_dev=private_dev,private_confirm=private_confirm,exa_policy=exa_policy,research_cutoff=research_cutoff)
            if sources is not None:
                from .paper import validate_sources
                registry=read_json(Path(sources));validate_sources(registry);write_json(staging/'sources.json',registry)
        entry=install_entry(staging,prepared)
        # Source paths in the entry are relative. No staging absolute path survives.
        os.replace(staging,root)
    return {'status':'INITIALIZED','workspace':str(root),'input_mode':input_mode,
        'entry_digest':digest(entry),'full_research_required':input_mode!='revise',
        'input_data_empty':data is None if input_mode=='revise' else not any((root/'inputs/development').iterdir())}
