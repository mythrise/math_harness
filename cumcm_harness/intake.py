"""Read-only problem ingestion. Scanned / unsupported sources fail visibly."""
from __future__ import annotations
import csv, shutil, zipfile
from pathlib import Path
from .common import *

def extract_zip(source:Path,destination:Path,*,max_bytes=500_000_000,max_files=5000):
    with zipfile.ZipFile(source) as z:
        members=z.infolist()
        if len(members)>max_files or sum(m.file_size for m in members)>max_bytes:raise Blocked('Archive expansion limit')
        for m in members:
            name=m.filename.rstrip('/')
            if not name:continue
            safe_rel(name)
            if ((m.external_attr>>16)&0o170000)==0o120000:raise IntegrityError('Archive symlink forbidden')
            if m.flag_bits&1:raise Blocked('Encrypted archive is unsupported')
            p=under(destination,name)
            if m.is_dir():p.mkdir(parents=True,exist_ok=True)
            else:atomic_write(p,z.read(m))

def profile(path:Path,*,expose_rows=True):
    info={'name':path.name,'bytes':path.stat().st_size,'sha256':file_hash(path),'type':path.suffix.lower()}
    if path.suffix.lower()=='.csv':
        with path.open('r',encoding='utf-8-sig',newline='') as f:
            reader=csv.reader(f);head=next(reader,[]);rows=[];count=0;missing=[0]*len(head)
            for row in reader:
                count+=1
                if len(row)!=len(head):raise Blocked(f'Ragged CSV row {count+1}: {path.name}')
                for j,x in enumerate(row):missing[j]+=not x.strip()
                if len(rows)<5 and expose_rows:rows.append(row)
        info.update(columns=head,rows=count,missing_by_column=dict(zip(head,missing)),preview=rows)
    elif path.suffix.lower() in ('.xlsx','.xlsm'):
        try:import openpyxl
        except ImportError as e:raise Blocked('Install excel extra to inspect spreadsheets') from e
        wb=openpyxl.load_workbook(path,read_only=True,data_only=False)
        info['sheets']=[{'name':w.title,'rows':w.max_row,'columns':w.max_column,
                         'preview':[[str(v) for v in row] for row in list(__import__('itertools').islice(w.values,5))] if expose_rows else []} for w in wb]
        wb.close();info['warning']='Formula cells are not recomputed by ingestion. Validate cached values or export raw source separately.'
    elif path.suffix.lower()=='.json':
        v=read_json(path);info['structure']=list(v)[:50] if isinstance(v,dict) else {'length':len(v) if isinstance(v,list) else 1}
        if expose_rows and path.stat().st_size<30000:info['content']=v
    return info

def read_problem(path:Path):
    suffix=path.suffix.lower()
    if suffix in ('.txt','.md'):text=path.read_text('utf-8')
    elif suffix=='.pdf':
        from pypdf import PdfReader
        pages=[p.extract_text() or '' for p in PdfReader(path).pages]
        if any(len(t.strip())<20 for t in pages):raise Blocked('PDF contains scanned/empty pages; provide verified transcription and inspect original figures')
        text='\n\n'.join(f'[PAGE {i+1}]\n{t}' for i,t in enumerate(pages))
    else:raise Blocked('Problem must be text, Markdown or text-extractable PDF')
    if len(text)>180000:raise Blocked('Problem too long for a single intake packet; split explicitly')
    if not text.strip():raise Blocked('Empty problem')
    return text

def copy_inputs(source:Path,destination:Path):
    if not source.is_dir():raise Blocked(f'Data directory not found: {source}')
    destination.mkdir(parents=True,exist_ok=True)
    tree_manifest(source) # validate no symlinks
    if sum(p.stat().st_size for p in source.rglob('*') if p.is_file())>2_000_000_000:raise Blocked('Input copy exceeds 2 GB; use explicit prepared dataset adapter')
    for p in source.rglob('*'):
        if p.is_file():
            q=under(destination,p.relative_to(source).as_posix());q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)

def create_workspace(root:Path,problem:Path,data:Path,config:dict,*,confirmation:Path|None=None,
                     private_dev:Path|None=None,private_confirm:Path|None=None,
                     exa_policy:dict|None=None,research_cutoff:str|None=None):
    from .controller import DEFAULT_CONFIG,validate_config
    config=validate_config({**DEFAULT_CONFIG,**config})
    if root.exists() and any(root.iterdir()):raise Blocked('Workspace must be new; use run/status to resume')
    snapshot=None
    if exa_policy is not None:
        if not config.get('literature_enabled') or config.get('network_policy')!='EXA_ABSTRACT_QUERIES':
            raise IntegrityError('Exa R2 policy requires the explicit online literature profile')
        from .exa_policy import freeze_policy
        snapshot=freeze_policy(exa_policy,cutoff=research_cutoff)
    elif research_cutoff is not None:raise IntegrityError('Research cutoff requires an Exa policy')
    root.mkdir(parents=True,exist_ok=True)
    text=read_problem(problem);atomic_write(root/'problem.md',text)
    public=root/'inputs/development';copy_inputs(data,public)
    confirm=root/'inputs/confirmation';copy_inputs(confirmation or data,confirm)
    for phase,private in (('development',private_dev),('confirmation',private_confirm)):
        ev=root/'evaluation_inputs'/phase;copy_inputs(root/'inputs'/phase,ev/'public')
        (ev/'private').mkdir(parents=True,exist_ok=True)
        if private:copy_inputs(private,ev/'private')
    info={'problem_sha256':file_hash(root/'problem.md'),'problem_original_sha256':file_hash(problem),
          'development':tree_manifest(public),'confirmation':tree_manifest(confirm),
          'eval_development':tree_manifest(root/'evaluation_inputs/development'),
          'eval_confirmation':tree_manifest(root/'evaluation_inputs/confirmation'),
          'confirmation_scope':'HELD_OUT_DATASET' if confirmation else 'SEED_REPLICATION_SAME_INSTANCE',
          'profiles':[profile(p) for p in sorted(public.rglob('*')) if p.is_file()],
          'private_schema':[profile(p,expose_rows=False) for p in sorted((root/'evaluation_inputs/development/private').rglob('*')) if p.is_file()]}
    write_json(root/'intake.json',info);write_json(root/'config.json',config)
    from .store import Store
    frozen={'intake':digest(info),'config':digest(config),'problem':file_hash(root/'problem.md')}
    if snapshot is not None:
        write_json(root/'exa-policy.json',snapshot);frozen['exa_policy']=digest(snapshot)
    store=Store(root);store.set('immutable_inputs',frozen)
    store.set('status','INITIALIZED');return info

def verify_inputs(root:Path):
    from .store import Store
    store=Store(root);frozen=store.get('immutable_inputs')
    i=read_json(root/'intake.json');c=read_json(root/'config.json')
    current={'intake':digest(i),'config':digest(c),'problem':file_hash(root/'problem.md')}
    if (root/'exa-policy.json').exists():
        from .exa_policy import load_frozen
        current['exa_policy']=digest(load_frozen(root))
    if current!=frozen:raise IntegrityError('Intake/config/problem/Exa policy changed after initialization')
    for key,folder in [('development','inputs/development'),('confirmation','inputs/confirmation'),
                        ('eval_development','evaluation_inputs/development'),('eval_confirmation','evaluation_inputs/confirmation')]:
        verify_tree(root/folder,i[key])
    return i,c
