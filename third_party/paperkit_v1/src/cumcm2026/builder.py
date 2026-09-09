"""Controlled materialization -> XeLaTeX -> PDF check -> allowlist ZIP.

TeX inputs must be trusted team-authored content. No solver execution, model calls,
network requests, signatures or contest uploads are performed here.
"""
from __future__ import annotations
import json, re, shutil, tempfile, zipfile, os
from pathlib import Path
from importlib.resources import files as resources
import fitz
from .common import Blocked, load, save, sha256, digest, esc, under, run_bounded, compact, profile_digest
from .validation import (validate_project, validate_ai, enumerate_sources, check_fragment, check_citations,
    identity_scan, MAX_BYTES, NO_AI, USED_PREFIX, USED_SUFFIX, AI_FILENAME, FORBIDDEN_FILENAMES, TEXT_SUFFIXES)
from .pdfcheck import inspect_pdf

REVIEW_KEYS=('team_led_core_model','all_ai_outputs_reviewed','scientific_results_verified',
             'code_inventory_complete_and_rerun','whole_pdf_visually_checked',
             'all_files_anonymous','local_rules_and_current_notices_checked','sources_and_rights_checked')

def asset(name: str) -> Path:
    return Path(str(resources('cumcm2026').joinpath('assets',name)))

def copy_style(folder: Path) -> None:
    shutil.copyfile(asset('paperkit-cumcm2026.sty'),folder/'paperkit-cumcm2026.sty')

def compile_tex(folder: Path,name: str) -> dict:
    exe=shutil.which('xelatex')
    if not exe: raise Blocked('XeLaTeX missing. Install a TeX distribution; no PDF was fabricated.')
    logdir=folder/'compile_logs';logdir.mkdir(exist_ok=True)
    for i in range(1,4):
        code,output=run_bounded([exe,'-no-shell-escape','-interaction=nonstopmode','-halt-on-error','-file-line-error',name],folder,180)
        (logdir/f'{Path(name).stem}-{i}.txt').write_text(output,'utf-8')
        if code: raise Blocked(f'XeLaTeX failed: see {logdir.name}/{Path(name).stem}-{i}.txt')
    log=(folder/Path(name).with_suffix('.log')).read_text('utf-8',errors='replace')
    bad_patterns=('Missing character:', 'There were undefined references','undefined citations',
                  'multiply defined','Overfull \\hbox','Overfull \\vbox')
    failures=[s for s in bad_patterns if s in log]
    if re.search(r'LaTeX Warning: (?:Reference|Citation).*undefined',log): failures.append('undefined reference/citation')
    if failures: raise Blocked('LaTeX quality gate: '+', '.join(failures))
    pdf=folder/Path(name).with_suffix('.pdf')
    if not pdf.is_file(): raise Blocked('Compiler returned without a PDF')
    # Remove identifying metadata before hashing and before generating review requests.
    with fitz.open(pdf) as doc:
        meta=doc.metadata
        for field in ('author','subject','keywords','creationDate','modDate'): meta[field]=''
        doc.set_metadata(meta);doc.del_xml_metadata()
        clean=pdf.with_suffix('.clean.pdf');doc.save(clean,garbage=4,deflate=True)
    os.replace(clean,pdf)
    _,version=run_bounded([exe,'--version'],folder,20)
    return {'engine':version.splitlines()[0],'passes':3,'shell_escape':False,
            'source_sha256':sha256(folder/name),'pdf_sha256':sha256(pdf),'errors':[],
            'trusted_tex_required':True}

def aux_page(folder: Path,label: str) -> int:
    text=(folder/'main_cumcm.aux').read_text('utf-8')
    m=re.search(r'\\newlabel\{'+re.escape(label)+r'\}\{\{[^}]*\}\{(\d+)\}',text)
    if not m: raise Blocked(f'Missing page boundary label {label}')
    return int(m.group(1))

def path_tex(rel: str) -> str:
    return r'\nolinkurl{'+rel+'}' if rel.isascii() else r'\texttt{'+esc(rel)+'}'

def text_write(path: Path,text: str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,'utf-8')

def ai_tex(ai: dict,example: bool) -> str:
    lines=[r'\documentclass[UTF8,a4paper,zihao=-4,fontset=fandol]{ctexart}',
           r'\usepackage{paperkit-cumcm2026}',r'\begin{document}',r'\PaperKitTitle{AI工具使用详情}']
    if example: lines += [r'\noindent\textbf{工程示例：} 本文件中的调用条目是标记清楚的测试夹具，不表示这些工具实际参与了竞赛。\par']
    lines += [r'\section*{使用概况}',esc(ai['brief_purpose'])+r'\par',
        '以下按实际使用记录列出工具、目的、提示方式、使用过程及人工处理情况。未发生的环节不补造。']
    fields=[('tool','工具名称'),('version_or_model','版本或型号'),('stage','使用环节'),('purpose','具体目的'),
            ('prompting','主要提示方式'),('process','使用过程'),('adoption','采纳情况'),
            ('human_modification','人工修改'),('human_verification','人工核验')]
    for i,r in enumerate(ai['records'],1):
        lines += [r'\section*{'+esc(f'记录 {i}：{r["id"]}')+'}']
        for key,title in fields:
            value=r.get(key)
            if value: lines += [r'\noindent\textbf{'+title+'：}'+esc(str(value))+r'\par']
        if r.get('language_polishing_only') is True:
            lines.append('本条仅涉及语言润色；详细采纳、修改和核验情况适用规定中的润色例外，仍须确保内容准确。')
        for key,title in [('typical_prompt','典型输入（可选）'),('typical_output','典型输出（可选）'),('artifact','相关成果（可选）')]:
            if r.get(key): lines += [r'\noindent\textbf{'+esc(title)+'：}'+esc(str(r[key]))+r'\par']
    lines += [r'\end{document}']
    return '\n'.join(lines)

def check_support_file(p: Path,denylist: list[str]):
    if any(x in FORBIDDEN_FILENAMES for x in p.parts) or p.suffix.lower() in ('.zip','.rar','.7z','.gz','.tar','.exe','.dll','.so','.ttf','.otf','.ttc'):
        raise Blocked('Nested archive, binary executable, font or secret path excluded from support allowlist')
    if p.suffix.lower()=='.pdf':
        with fitz.open(p) as doc:
            if doc.needs_pass: raise Blocked('Encrypted support PDF')
            text='\n'.join(x.get_text() for x in doc)+str(doc.metadata)+doc.get_xml_metadata()
            if doc.embfile_count(): raise Blocked('Embedded files in support PDF')
            if (doc.metadata or {}).get('author'): raise Blocked('Support PDF author metadata not blank')
    elif p.suffix in TEXT_SUFFIXES or p.name in ('requirements.txt','Makefile'):
        try: text=p.read_text('utf-8')
        except UnicodeDecodeError as e: raise Blocked('Text source is not UTF-8') from e
    else:
        # Binary spreadsheet/image headers can still carry identities. Never promise this is full metadata inspection.
        text=p.read_bytes().decode('utf-8',errors='ignore')
    issues=identity_scan(text+'\n'+p.name,denylist)
    if issues: raise Blocked('Support anonymity/security check failed: '+', '.join(issues))

def build(project: Path,out: Path) -> dict:
    project=project.resolve();out=out.resolve();profile_at_start=profile_digest()
    if out.is_relative_to(project): raise Blocked('Build output must be outside the authoring project to avoid inventory pollution')
    if out.exists(): raise Blocked('Output path must be new/empty (prevents stale PDF reuse)')
    c=validate_project(load(project/'project.json'))
    ai=validate_ai(load(under(project,c['ai_usage'])),c['ai_status'])
    sources=enumerate_sources(project,c)
    denylist=c.get('identity_denylist',[])
    if not isinstance(denylist,list) or any(not isinstance(s,str) for s in denylist): raise Blocked('identity_denylist must be a string list')
    abstract=under(project,c['abstract']).read_text('utf-8');refs=under(project,c['references']).read_text('utf-8')
    fragments=[(s,under(project,s['path']).read_text('utf-8')) for s in c['sections']]
    for name,text in [(c['abstract'],abstract),(c['references'],refs)]+[(s['path'],t) for s,t in fragments]:
        check_fragment(text,name)
    check_citations(abstract+'\n'+'\n'.join(t for _,t in fragments),refs)
    if compact('AI工具使用声明') in compact(refs): raise Blocked('Remove the legacy AI statement from references; builder owns the declaration')
    used_inputs={c['abstract'],c['references'],c['ai_usage'],'project.json'}|{s['path'] for s in c['sections']}
    used_inputs.update(p.relative_to(project).as_posix() for p in sources)
    used_inputs.update(c['support_files']);used_inputs.update(c['figures'])
    input_hashes={x:sha256(under(project,x)) for x in sorted(used_inputs)}
    out.mkdir(parents=True)
    work=out/'build';work.mkdir();stage=work/'support';stage.mkdir()
    try:
        copy_style(work);shutil.copyfile(asset('main_cumcm.tex'),work/'main_cumcm.tex')
        text_write(work/'sections/abstract.tex',abstract)
        text_write(work/'sections/references.tex',refs)
        body=[]
        for i,(s,text) in enumerate(fragments):
            target=f'sections/body_{i:03d}.tex';text_write(work/target,text)
            body += [r'\section{'+esc(s['heading'])+'}',r'\input{'+target+'}']
        text_write(work/'generated/body.tex','\n'.join(body))
        text_write(work/'generated/meta.tex',r'\newcommand{\PaperTitle}{'+esc(c['title'])+'}\n'+r'\newcommand{\PaperKeywords}{'+esc('；'.join(c['keywords']))+'}\n')
        notice=(r'\par\smallskip\noindent\textbf{示例说明：} 本文是合成数据上的模板工程示例，不是国赛答卷，不得直接提交。' if c['example'] else '')
        text_write(work/'generated/example_notice.tex',notice)
        declaration=NO_AI if c['ai_status']=='unused' else USED_PREFIX+ai['brief_purpose']+USED_SUFFIX
        text_write(work/'generated/ai_statement.tex',r'\section*{AI工具使用声明}'+'\n'+esc(declaration)+'\n')
        if c['ai_status']=='used':
            text_write(work/'ai_details.tex',ai_tex(ai,c['example']))
            ai_compile=compile_tex(work,'ai_details.tex')
            ai_check=inspect_pdf(work/'ai_details.pdf',kind='ai_details',denylist=denylist,example=c['example'])
            if ai_check['status']!='PASS': raise Blocked('AI details PDF failed: '+json.dumps(ai_check['errors'],ensure_ascii=False))
            shutil.copyfile(work/'ai_details.pdf',stage/c.get('ai_details_filename',AI_FILENAME))
        else: ai_compile=ai_check=None
        for p in sources+[under(project,x) for x in c['support_files']]:
            rel=p.relative_to(project).as_posix()
            if (stage/rel).exists(): raise Blocked('Duplicate/colliding support path: '+rel)
            dest=stage/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
        for rel in c['figures']:
            p=under(project,rel)
            if not rel.startswith('figures/'): raise Blocked('Figure inputs must live under figures/')
            dest=work/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
            check_support_file(dest,denylist)
        support_inventory=sorted(p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file())
        for p in sorted(stage.rglob('*')):
            if p.is_file(): check_support_file(p,denylist)
        if sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())>256_000_000: raise Blocked('Uncompressed support resource cap exceeded')
        appendix=[]
        if support_inventory:
            appendix += [r'\subsection*{支撑材料文件列表}',r'\begin{longtable}{p{0.96\linewidth}}\toprule 文件路径\\\midrule\endhead']
            for rel in support_inventory: appendix.append(path_tex(rel)+r'\\')
            appendix += [r'\bottomrule\end{longtable}']
        else: appendix += ['本论文没有支撑材料。']
        if not c['program_used']: appendix += ['本论文没有用到程序。']
        else:
            appendix += [r'\subsection*{全部完整源程序与文本运行资源}',
                '下列内容与支撑材料中的对应文件逐字节绑定；运行所需依赖、输入与结果的一致性由另行复现和人工审查确认。']
            for p in sources:
                rel=p.relative_to(project).as_posix()
                appendix += [r'\par\noindent\textbf{文件：}'+path_tex(rel)+r'\par',
                    r'{\scriptsize\noindent SHA-256：\nolinkurl{'+sha256(p)+r'}\par}',
                    r'\VerbatimInput[breaklines=true,breakanywhere=true,fontsize=\scriptsize]{support/'+rel+'}']
        text_write(work/'generated/appendix.tex','\n'.join(appendix))
        receipt=compile_tex(work,'main_cumcm.tex')
        aend=aux_page(work,'abstract-end');astart=aux_page(work,'appendix-start');bstart=aux_page(work,'body-start')
        if aend!=1: raise Blocked('Abstract must fit exactly one page')
        if bstart!=2: raise Blocked('Body must start on electronic page 2')
        qa=inspect_pdf(work/'main_cumcm.pdf',ai_status=c['ai_status'],brief_purpose=ai.get('brief_purpose'),
            denylist=denylist,abstract_end=aend,appendix_page=astart,example=c['example'])
        save(out/'pdf_check.json',qa)
        if qa['status']!='PASS': raise Blocked('Paper PDF failed: '+json.dumps(qa['errors'],ensure_ascii=False))
        if profile_digest()!=profile_at_start: raise Blocked('Profile changed during build')
        # Catch races: never bind a paper generated from a moving input set.
        if any(sha256(under(project,r))!=h for r,h in input_hashes.items()): raise Blocked('Input changed during build')
        shutil.copyfile(work/'main_cumcm.pdf',out/'paper.pdf')
        zip_path=out/'support.zip'
        if support_inventory:
            with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
                for rel in support_inventory:
                    info=zipfile.ZipInfo(rel,date_time=(2026,9,9,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                    info.external_attr=0o644<<16;z.writestr(info,(stage/rel).read_bytes())
            if zip_path.stat().st_size>MAX_BYTES: raise Blocked('Compressed support exceeds 20,000,000 bytes')
        support_hashes={r:sha256(stage/r) for r in support_inventory}
        outputs={'paper.pdf':sha256(out/'paper.pdf')}
        if zip_path.exists(): outputs['support.zip']=sha256(zip_path)
        result={'schema_version':1,'profile_digest':profile_at_start,'status':'EXAMPLE_MACHINE_PASS_NOT_FOR_SUBMISSION' if c['example'] else 'MACHINE_PASS_HUMAN_REVIEW_REQUIRED',
            'release_ready':False,'example':c['example'],'ai_status':c['ai_status'],'ai_filename':c.get('ai_details_filename',AI_FILENAME),
            'ai_brief_purpose':ai.get('brief_purpose'), 'abstract_end_page':aend, 'appendix_start_page':astart,
            'project_digest':digest(input_hashes),'input_hashes':input_hashes,'outputs':outputs,'bundle_digest':digest(outputs),
            'support_inventory':support_inventory,'support_hashes':support_hashes,
            'source_inventory':{p.relative_to(project).as_posix():sha256(p) for p in sources},
            'build':receipt,'preflight':qa,'ai_build':ai_compile,'ai_preflight':ai_check,
            'rules_checked_on':'2026-09-09','official_certification':False,
            'limits':['No proof of scientific correctness, source completeness outside declared roots, true human review, or total anonymity.',
                      '20MB checked conservatively as decimal bytes. PDF/screenshot binary identity review remains manual.']}
        save(out/'build_report.json',result)
        save(out/'review.required.json',{'schema_version':1,'bundle_digest':result['bundle_digest'],
            'reviewer_alias':'','checked_at':'','checks':{k:False for k in REVIEW_KEYS},'notes':''})
        return result
    except Exception as e:
        save(out/'BLOCKED.json',{'status':'BLOCKED','error':str(e),'release_ready':False})
        raise

def verify_bundle(out: Path) -> dict:
    r=load(out/'build_report.json')
    if r.get('profile_digest')!=profile_digest(): raise Blocked('Build used a different implementation/style profile; rebuild or use the original pinned package')
    if r.get('preflight',{}).get('status')!='PASS': raise Blocked('Build preflight did not pass')
    expected=r.get('outputs',{})
    if not expected or any(not (out/name).is_file() or sha256(out/name)!=h for name,h in expected.items()):
        raise Blocked('Candidate artifact hash mismatch')
    if digest(expected)!=r['bundle_digest']: raise Blocked('Bundle digest mismatch')
    if 'support.zip' in expected:
        if (out/'support.zip').stat().st_size>MAX_BYTES: raise Blocked('ZIP exceeds size cap')
        with zipfile.ZipFile(out/'support.zip') as z:
            if z.testzip(): raise Blocked('Corrupt support archive')
            if z.namelist()!=r['support_inventory']: raise Blocked('ZIP/appendix manifest disagreement')
            import hashlib
            for name,h in r['support_hashes'].items():
                if hashlib.sha256(z.read(name)).hexdigest()!=h: raise Blocked('Support content mismatch')
    repeat=inspect_pdf(out/'paper.pdf',ai_status=r['ai_status'],brief_purpose=r.get('ai_brief_purpose'),
        abstract_end=r.get('abstract_end_page'),appendix_page=r.get('appendix_start_page'),example=r['example'])
    if repeat['status']!='PASS': raise Blocked('Rechecked PDF failed: '+str(repeat['errors']))
    return r

def release(out: Path,review_path: Path,destination: Path) -> dict:
    r=verify_bundle(out)
    if r['example']: raise Blocked('Examples/fixtures can never be released as contest deliverables')
    review=load(review_path)
    if review.get('bundle_digest')!=r['bundle_digest']: raise Blocked('Human review is not bound to this exact paper/support bundle')
    if not review.get('reviewer_alias') or not review.get('checked_at'): raise Blocked('Missing human review metadata')
    if any(review.get('checks',{}).get(k) is not True for k in REVIEW_KEYS): raise Blocked('Human review checklist is incomplete')
    if destination.exists(): raise Blocked('Release destination must be new')
    destination.mkdir(parents=True)
    for name in r['outputs']: shutil.copyfile(out/name,destination/name)
    report={'status':'LOCAL_EXPORT_AFTER_DECLARED_HUMAN_REVIEW','bundle_digest':r['bundle_digest'],
            'auto_submission':False,'human_identity_authenticated':False,'official_certification':False,
            'files':list(r['outputs'])}
    save(out/'release_receipt.json',report)
    return report

def make_print(paper: Path,commitment: Path,numbering: Path,out: Path, *,confirmed: bool) -> dict:
    if not confirmed: raise Blocked('Confirm that these are the actual current official front pages')
    if out.exists(): raise Blocked('Print destination already exists')
    for f in (paper,commitment,numbering):
        if not f.is_file(): raise Blocked('Print input missing')
    with fitz.open(commitment) as c,fitz.open(numbering) as n,fitz.open(paper) as p,fitz.open() as merged:
        if any(d.needs_pass for d in (c,n,p)): raise Blocked('Encrypted print inputs')
        if len(c)!=1 or len(n)!=1: raise Blocked('Commitment and numbering must each be one page')
        for front in (c,n):
            if abs(front[0].rect.width-595.276)>1 or abs(front[0].rect.height-841.89)>1: raise Blocked('Front pages must be A4')
        for d in (c,n,p): merged.insert_pdf(d)
        out.parent.mkdir(parents=True,exist_ok=True);merged.save(out)
        # Pixel comparison proves the paper portion was not reflowed/re-rendered differently by the merge.
        for i in range(len(p)):
            if merged[i+2].get_pixmap().samples != p[i].get_pixmap().samples:
                out.unlink(missing_ok=True);raise Blocked('Print/body visual mismatch')
    return {'status':'PRINT_MERGED','paper_sha256':sha256(paper),'commitment_sha256':sha256(commitment),
            'numbering_sha256':sha256(numbering),'print_sha256':sha256(out),
            'body_pixel_identical':True,'front_pages_officially_verified_by_tool':False}
