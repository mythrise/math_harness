"""Separate development distribution from the <=20 MB contest support package."""
from __future__ import annotations
import json, re, shutil, zipfile, os
from pathlib import Path
from .common import *

BASIC=['README.md','reproduce.py','config.json','protocol.json','claims.json','input_manifest.json',
       'results/confirmation.json','results/development.json','ai_usage.json','AI工具使用详情.pdf',
       'source_inventory.json','support_inventory.json','manifest.json']
RESEARCH_FILES=['literature/accepted.json','literature/execution.json']
FIGURES=['ourwork.svg','ourwork.pdf','ourwork.png','ourwork.provenance.json',
         'confirmation.svg','confirmation.pdf','confirmation.png','confirmation.data.json','confirmation.provenance.json']

def planned_support_files(root:Path,source_files:list[str]):
    cfg=read_json(root/'config.json');files=BASIC+list(source_files)+['figures/'+f for f in FIGURES]
    files += [f for f in RESEARCH_FILES if (root/f).exists()]
    if cfg['input_data_origin']=='include-in-support':
        files += ['inputs/'+p.relative_to(root/'inputs').as_posix() for p in (root/'inputs').rglob('*') if p.is_file()]
    elif cfg['input_data_origin']!='contest-original':raise IntegrityError('Classify input_data_origin explicitly before packaging')
    for phase in ('development','confirmation'):
        base=root/'evaluation_inputs'/phase/'private'
        files += [f'private/{phase}/'+p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()]
    # Only completed jobs are releasable. Failed/unknown attempts remain in private audit.
    from .store import Store
    with Store(root).connect() as c:jobs=[r['id'] for r in c.execute('SELECT id FROM jobs WHERE status="DONE" ORDER BY id')]
    for job in jobs:
        base=root/'jobs'/job
        for area in ('solver','evaluation'):
            files += [f'jobs/{job}/{area}/'+p.relative_to(base/area).as_posix() for p in (base/area).rglob('*') if p.is_file()]
        files.append(f'jobs/{job}/receipt.json')
    return sorted(set(files))

def sanitize(value,root:Path):
    text=json.dumps(value,ensure_ascii=False,allow_nan=False)
    replacements={str(root.resolve()):'<WORKSPACE>',str(ROOT.resolve()):'<HARNESS_ROOT>',str(Path.home()):'<HOME>'}
    for old,new in sorted(replacements.items(),key=lambda kv:-len(kv[0])):text=text.replace(old,new)
    return json.loads(text)

def scan_release(folder:Path,denylist):
    for p in folder.rglob('*'):
        if not p.is_file():continue
        if p.suffix.lower() in ('.ttf','.otf','.ttc','.woff','.woff2','.eot'):raise IntegrityError('Font files cannot be distributed')
        if p.suffix.lower() in ('.py','.json','.csv','.txt','.md','.tex','.svg'):
            text=p.read_text('utf-8',errors='replace')
            if any(os.getenv(k) and os.environ[k] in text for k in ('EXA_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','CLAUDE_CODE_OAUTH_TOKEN')):raise Blocked('Credential detected in release file '+p.name)
            if any(s and s in text for s in denylist):raise Blocked('Anonymity denylist match in '+p.name)
            if re.search(r'(?<![A-Za-z])sk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}',text):raise Blocked('Possible credential in release file '+p.name)
        if p.name in ('.env','auth.json','credentials.json'):raise Blocked('Credential file cannot be packaged')

def package_workspace(root:Path,built,claims,protocol,rows,records,ai,*,contest=False,human=None):
    if contest and human is None:raise Blocked('No contest package without digest-bound human approval')
    cfg=read_json(root/'config.json');dest=root/'deliverables';dest.mkdir(exist_ok=True)
    support=root/'support'
    if support.exists():shutil.rmtree(support)
    support.mkdir();source_files=read_json(root/'paper/source_inventory.json')
    for rel in source_files:atomic_write(support/rel,(root/'paper'/rel).read_bytes())
    for rel in RESEARCH_FILES:
        if (root/rel).exists():atomic_write(support/rel,(root/rel).read_bytes())
    atomic_write(support/'reproduce.py',(ROOT/'scripts/reproduce_support.py').read_bytes())
    for f in FIGURES:atomic_write(support/'figures'/f,(root/'paper/figures'/f).read_bytes())
    if cfg['input_data_origin']=='include-in-support':shutil.copytree(root/'inputs',support/'inputs')
    for phase in ('development','confirmation'):
        base=root/'evaluation_inputs'/phase/'private'
        if list(base.rglob('*')):shutil.copytree(base,support/'private'/phase)
    public_config={**cfg,'identity_denylist':[]};write_json(support/'config.json',public_config)
    write_json(support/'protocol.json',protocol);write_json(support/'claims.json',claims)
    intake=read_json(root/'intake.json');write_json(support/'input_manifest.json',{k:intake[k] for k in ('development','confirmation','confirmation_scope')})
    write_json(support/'results/confirmation.json',read_json(root/'confirmation.json'))
    from .store import Store
    with Store(root).connect() as c:jobs=[dict(r) for r in c.execute('SELECT * FROM jobs WHERE status="DONE" ORDER BY id')]
    dev=[]
    for j in jobs:
        receipt=json.loads(j['receipt']);job=j['id']
        if receipt['result']['phase']=='development':dev.append(receipt['result'])
        for area in ('solver','evaluation'):shutil.copytree(root/'jobs'/job/area,support/'jobs'/job/area)
        write_json(support/'jobs'/job/'receipt.json',sanitize(receipt,root))
    write_json(support/'results/development.json',dev)
    public_fields=('provider','transport','role','invocation_id','cli_version','model_requested','model_reported','response_digest','prompt_sha256','packet_digest','usage','cost_usd','model_execution_status','call_index')
    write_json(support/'ai_usage.json',[{k:r[k] for k in public_fields if k in r} for r in records])
    atomic_write(support/'AI工具使用详情.pdf',(root/'paper/AI工具使用详情.pdf').read_bytes())
    write_json(support/'source_inventory.json',source_files)
    inventory=planned_support_files(root,source_files);write_json(support/'support_inventory.json',inventory)
    if inventory!=read_json(root/'paper/support_inventory.json'):raise IntegrityError('Support inventory drifted after PDF build; paper must be rebuilt/reviewed')
    atomic_write(support/'README.md','''# Frozen mathematical-modeling support bundle

This bundle contains actual solver outputs, independent evaluation, custom sources,
figures and AI usage disclosures. It does not certify that the mathematical model
is correct for an unstated domain or that this system outperforms other agents.

Read the code first. Use an isolated Python environment with numpy, scipy, pandas,
scikit-learn and numba; exact run versions are in jobs/*/receipt.json and the full
harness report. To reproduce the default baseline confirmation run:

```
python reproduce.py --trust-reviewed-code --candidate baseline --out reproduced
```

For a selected candidate, replace `baseline` with its frozen candidate ID (c0/c1),
and use `--variant full`. Use the exact seeds in protocol.json. Supply
`--original-input DIR` when original contest-provided input was intentionally
excluded; its hashes must match input_manifest.json. The reproducibility script
rejects changed files and out-of-protocol seeds. It never calls an LLM.

The results may be fixture-directed engineering demonstrations; consult
ai_usage.json and AI工具使用详情.pdf. A fixture is not a real Claude review.
''')
    scan_release(support,cfg['identity_denylist'])
    files=tree_manifest(support);write_json(support/'manifest.json',{'files':files,'self_hash_excluded':True,'paper_sha256':built['paper_sha256']})
    actual=sorted(tree_manifest(support))
    if actual!=inventory:raise IntegrityError('Support file list mismatch: '+str(set(actual)^set(inventory)))
    zip_path=dest/'support.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=8) as z:
        for p in sorted(support.rglob('*')):
            if p.is_file():
                info=zipfile.ZipInfo(p.relative_to(support).as_posix(),date_time=(2026,9,5,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                z.writestr(info,p.read_bytes())
    if zip_path.stat().st_size>20_000_000:
        zip_path.unlink();raise Blocked('Support exceeds 20 MB. Classify original contest inputs separately; do not silently omit essential researched data/code.')
    paper_path=dest/'paper.pdf';shutil.copy2(root/'paper/main.pdf',paper_path)
    if file_hash(paper_path)!=built['paper_sha256']:raise IntegrityError('PDF changed during packaging')
    return {'paper':'deliverables/paper.pdf','support':'deliverables/support.zip','paper_sha256':file_hash(paper_path),'support_sha256':file_hash(zip_path),
            'support_bytes':zip_path.stat().st_size,'paper_bytes':paper_path.stat().st_size,'file_count':len(actual),
            'contest_mode':contest,'official_submission_sent':False}
