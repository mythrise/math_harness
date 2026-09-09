"""Self-developed CUMCM 2026 electronic-paper profile, NOT an official LaTeX class.
Measured values come from claim records; ordinary prose is escaped, equations
use a mathematical-command allowlist. Build receipts bind source and PDF hashes.
"""
from __future__ import annotations
import json, re, shutil, subprocess
from pathlib import Path
from .common import *
from .contracts import validate

RULES={
 'format_url':'https://www.mcm.edu.cn/html_cn/node/4cd596519c9eb9fbd866398f6df0caa3.html',
 'ai_url':'https://www.mcm.edu.cn/html_cn/node/fef94648f2836ab6cc81586f4c38512b.html',
 'checked_on':'2026-09-09','profile':'self-developed, based on official 2026 rules',
 'a4':True,'minimum_margin_mm':25,'abstract_first_page':True,'body_max_pages':30,
 'toc':False,'electronic_cover_pages':False,'paper_max_bytes':20_000_000,'support_max_bytes':20_000_000,
 'ai_statement_before_references':True,'ai_details_filename':'AI工具使用详情.pdf',
 'font_size_not_nationally_prescribed':True,'local_rules_require_human_confirmation':True}

def esc(text):
    chars={'\\':r'\textbackslash{}','{':r'\{','}':r'\}','%':r'\%','&':r'\&','#':r'\#','_':r'\_',
           '$':r'\$','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    return ''.join(chars.get(c,c) for c in str(text))

MATH_COMMANDS=set('alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega frac dfrac tfrac sqrt sum prod int iint iiint lim min max log ln exp sin cos tan abs left right big Big bigg Bigg mathbb mathcal mathrm mathbf mathit mathsf operatorname text vec hat widehat bar overline underline dot ddot tilde widetilde top bot cdot cdots ldots vdots ddots times div pm mp le leq ge geq ne neq approx sim simeq equiv propto in notin ni subset subseteq supset supseteq emptyset forall exists neg land lor cup cap setminus mid vert Vert lvert rvert lVert rVert to mapsto rightarrow leftarrow Rightarrow Leftrightarrow infinity infty partial nabla ell hbar degree circ prime perp parallel quad qquad displaystyle textstyle substack underbrace overbrace begin end'.split())
def equation(text):
    """Conservative math lexer, not a TeX sandbox. Compile in isolation as well.

    TeX expands ^^ character escapes before tokenization. A regex on only the
    apparent alphabetic commands cannot secure that input. Consume control symbols
    as complete tokens too, so a row break followed by y is not read as a y macro.
    """
    if (not isinstance(text,str) or len(text)>8000 or '^^' in text
        or any(x in text for x in ('%','#','\x00'))
        or any(ord(x)<32 and x not in '\n\r\t' for x in text)):
        raise IntegrityError('Unsafe/oversize equation')
    allowed_envs={'aligned','cases','matrix','pmatrix','bmatrix','smallmatrix'}
    allowed_symbols={'\\','{','}',',',';',':','!',' ','|','/','_','^','-','\n','\r','\t'}
    stack=[]
    for token in re.finditer(r'\\([A-Za-z]+|.)',text,re.S):
        command=token.group(1)
        if command not in MATH_COMMANDS and command not in allowed_symbols:
            raise IntegrityError('Unsupported equation macro: '+repr(command))
        if command in ('begin','end'):
            env=re.match(r'\s*\{([^{}]+)\}',text[token.end():])
            if not env or env.group(1) not in allowed_envs:
                raise IntegrityError('Unapproved math environment')
            name=env.group(1)
            if command=='begin':stack.append(name)
            elif not stack or stack.pop()!=name:raise IntegrityError('Unbalanced math environment')
    if stack:raise IntegrityError('Unbalanced math environment')
    return text

def tex_filename(rel):
    """Refuse TeX metacharacters in filenames inserted into trusted templates.
    This includes original attachment names; an operator may stage a safely named
    copy in a NEW workspace with an explicit filename map rather than lose data.
    """
    safe_rel(rel)
    if any(c in rel for c in '{}%#&$^~') or any(ord(c)<32 or ord(c)==127 for c in rel):
        raise IntegrityError('Unsafe filename for TeX source inclusion')
    return rel

TOKEN=re.compile(r'\{\{(claim|cite):([a-zA-Z][a-zA-Z0-9_-]*)\}\}')
def validate_sources(sources):
    from urllib.parse import urlsplit
    ids=set()
    for source in sources:
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,63}',source.get('id','')) or source['id'] in ids:raise IntegrityError('Invalid/duplicate source id')
        ids.add(source['id']);url=source.get('url','')
        if urlsplit(url).scheme not in ('http','https') or not urlsplit(url).netloc or any(c in url for c in '\\{}\r\n'):raise IntegrityError('Unsafe source URL')
        if not source.get('title') or source.get('verified') is not True or not source.get('verification_note'):raise IntegrityError('Sources require verified title, URL and evidence note')
    return {s['id']:s for s in sources}
def bind_prose(text,claims,*,numeric_guard=True,sources=None):
    clean=TOKEN.sub('',text)
    numbers=re.findall(r'(?<![A-Za-z])\b\d+(?:\.\d+)?\b',clean)
    if numeric_guard and any(x not in ('2026',) for x in numbers):raise IntegrityError('Unbound numeric prose; use {{claim:ID}} or equation fields')
    out=[];pos=0
    for m in TOKEN.finditer(text):
        kind,key=m.groups();out.append(esc(text[pos:m.start()]))
        if kind=='claim':
            if key not in claims:raise IntegrityError('Unknown claim token: '+key)
            finite(claims[key]['value']);out.append(esc(f'{claims[key]["value"]:.6g}'))
        else:
            if not sources or key not in sources or not sources[key].get('verified'):raise IntegrityError('Unknown/unverified citation: '+key)
            out.append(r'\cite{'+key+'}')
        pos=m.end()
    out.append(esc(text[pos:]));return ''.join(out)

def claim_registry(rows,selection,inference):
    import numpy as np
    claims={};labels=sorted({r['candidate'] for r in rows})
    for label in labels:
        values=[r for r in rows if r['candidate']==label]
        key='mean_'+label.replace('-','_')
        claims[key]={'value':float(np.mean([r['evaluation']['score'] for r in values])),
            'unit':rows[0]['evaluation']['metric'],'description':f'Confirmation mean for {label}',
            'maturity':'MEASURED_SCOPE_ONLY','scope':rows[0]['scope'],
            'evidence':[{'job_id':r['job_id'],'evaluation_digest':digest(r['evaluation']),'selector':'score'} for r in values]}
    claims['mean_improvement']={'value':inference['mean_improvement'],'unit':rows[0]['evaluation']['metric'],
        'description':'paired candidate minus baseline in improvement direction','maturity':'MEASURED_SCOPE_ONLY',
        'scope':rows[0]['scope'],'evidence':[{'job_id':r['job_id'],'evaluation_digest':digest(r['evaluation']),'selector':'score'} for r in rows]}
    if inference['ci95']:
        for k,v in zip(('ci_low','ci_high'),inference['ci95']):claims[k]={**claims['mean_improvement'],'value':v,'description':'paired percentile bootstrap '+k}
    # A single representative (median score, deterministic tie break), never the best run.
    final_label=selection['winner'] if inference['decision']=='KEEP_CANDIDATE' else 'baseline'
    available=[r for r in rows if r['candidate']==final_label]
    representative=sorted(available,key=lambda r:(r['evaluation']['score'],r['seed']))[len(available)//2]
    for m in representative['evaluation']['measurements']:
        key='result_'+m['id'];claims[key]={'value':m['value'],'unit':m['unit'],'description':m['description'],
            'question_id':m['question_id'],'maturity':'MEASURED_SCOPE_ONLY','scope':representative['scope'],
            'evidence':[{'job_id':representative['job_id'],'evaluation_digest':digest(representative['evaluation']),'selector':'measurements.'+m['id']}]}
    return claims,representative

from .paper_profile import PREAMBLE, prepare_style, PROFILE, profile_digest


def compile_tex(folder:Path,main='main.tex'):
    from .tex_sandbox import compile_isolated
    prepare_style(folder)
    sandbox=compile_isolated(folder,main)
    pdf=folder/Path(main).with_suffix('.pdf')
    if not pdf.is_file():raise IntegrityError('Compiler exited without PDF')
    log=folder/Path(main).with_suffix('.log')
    if not log.is_file():raise PaperCompilationFailure('Required compiler log is missing')
    text=log.read_text('utf-8',errors='replace')
    markers=('Missing character:', 'LaTeX Warning: Reference', 'undefined references', 'undefined citations', r'Overfull \hbox', r'Overfull \vbox')
    if any(marker in text for marker in markers):raise PaperCompilationFailure('PDF contains missing glyphs, unresolved references/citations or overfull boxes')
    return {'source_sha256':file_hash(folder/main),'pdf_sha256':file_hash(pdf),
            'engine':'XeLaTeX','shell_escape':False,'passes':2,'paperkit_profile':PROFILE,'paperkit_profile_digest':profile_digest(),'overfull_boxes':text.count(r'Overfull \hbox'),
            'compiler_version':text.splitlines()[0] if text else 'UNREPORTED','sandbox':sandbox}

def preflight(pdf:Path, *, denylist=(),require_ai=True,trusted_appendix_page=None,demo=False):
    import fitz
    r=fitz.open(pdf);texts=[p.get_text() or '' for p in r];whole='\n'.join(texts)
    failures=[];warnings=[]
    if pdf.stat().st_size>RULES['paper_max_bytes']:failures.append('paper exceeds 20 MB')
    for i,p in enumerate(r):
        w,h=float(p.rect.width),float(p.rect.height)
        if abs(w-595.276)>2 or abs(h-841.89)>2:failures.append(f'page {i+1} is not A4')
    if not texts or '摘要' not in texts[0].replace(' ',''):failures.append('first page must be abstract')
    # A model may put the appendix heading in ordinary body prose. That text
    # must not control page-limit enforcement or the visual-review page range.
    appendix=None
    if (type(trusted_appendix_page) is not int
        or not 2<=trusted_appendix_page<=len(texts)):
        failures.append('missing/invalid trusted appendix page from compiler label')
    else:
        appendix=trusted_appendix_page-1
        if '附录：支撑材料与完整源程序' not in re.sub(r'\s+','',texts[appendix]):
            failures.append('trusted appendix label does not match its rendered page')
        if appendix-1>30:failures.append('body exceeds 30 pages (excluding first abstract page)')
    if len(texts)>1 and '问题重述' not in texts[1].replace(' ',''):warnings.append('check that abstract occupies exactly one page')
    compact=whole.replace(' ','')
    if require_ai and ('AI工具使用声明' not in compact or compact.find('AI工具使用声明')>compact.find('参考文献')):failures.append('AI declaration missing/misordered')
    for x in denylist:
        if x and (x in whole or x in str(r.metadata)):failures.append('identity denylist match')
    if r.metadata and r.metadata.get('author'):failures.append('nonempty PDF author metadata')
    if re.search(r'目\s*录\s*\n',whole):warnings.append('possible forbidden table of contents; inspect')
    from .paper_layout import inspect_pdf
    aux=pdf.with_suffix('.aux')
    labels=aux.read_text('utf-8',errors='replace') if aux.exists() else ''
    end=re.search(r'\\newlabel\{abstract-end\}\{\{[^}]*\}\{(\d+)\}',labels)
    extra=inspect_pdf(pdf,denylist=denylist,require_ai=require_ai,example=demo,
        abstract_end=int(end.group(1)) if end else None,appendix_page=trusted_appendix_page)
    failures.extend(e['code']+': '+e['detail'] for e in extra['errors'])
    warnings.extend(extra['warnings'])
    return {'status':'PASS' if not failures else 'FAIL','pages':len(r),'body_pages':appendix-1 if appendix is not None else None,
            'paperkit_checks':extra,'release_ready':False,
            'bytes':pdf.stat().st_size,'failures':failures,'warnings':warnings,'pdf_sha256':file_hash(pdf),
            'visual_check':'REQUIRED_SEPARATELY','anonymity':'denylist/metadata checks do not prove complete anonymity'}

def render_pages(pdf:Path,out:Path,*,page_indices=None):
    try:import fitz
    except ImportError as e:raise InfrastructureUnavailable('Install PyMuPDF for rasterized visual review') from e
    out.mkdir(parents=True,exist_ok=True);doc=fitz.open(pdf);paths=[]
    indices=range(len(doc)) if page_indices is None else sorted(set(page_indices))
    for i in indices:
        if type(i) is not int or not 0<=i<len(doc):raise IntegrityError('Invalid PDF page index')
        p=out/f'page-{i+1:03d}.png';doc[i].get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(p);paths.append(p)
    doc.close();return paths

def build_paper(root:Path,draft:dict,claims:dict,rows:list[dict], *, ai_records:list[dict],code_bundles:dict,
                source_registry=(),demo=False,build_dir=None):
    validate('paper',draft)
    known=validate_sources(source_registry)
    referenced={m.group(2) for text in [draft['abstract']]+[x['text'] for x in draft['sections']]+draft['limitations'] for m in TOKEN.finditer(text) if m.group(1)=='cite'}
    if referenced!=set(draft['citation_ids']):raise IntegrityError('Bibliography must exactly match inline citation tokens')
    for k in draft['citation_ids']:
        if k not in known or not known[k].get('verified'):raise IntegrityError('Unverified citation: '+k)
    folder=Path(build_dir) if build_dir is not None else root/'paper';folder.mkdir(parents=True,exist_ok=True);figdir=folder/'figures';figdir.mkdir(exist_ok=True)
    from .figures import framework,score_plot
    framework(figdir/'ourwork.svg');score_plot(rows,figdir/'confirmation')
    # Appendix includes generated source and the actually loaded custom dependencies.
    files=[]
    for label,b in code_bundles.items():
        for f in b['files']:
            if f['path'].endswith(('.py','.json','.csv','.txt','.md')):
                rel=f'code/{label}/{safe_rel(f["path"])}';atomic_write(folder/rel,f['content']);files.append(rel)
    dependencies={}
    for row in rows:
        for stage in ('solver','evaluation'):
            p=root/'jobs'/row['job_id']/stage/'custom_dependencies.json'
            if not p.is_file():raise IntegrityError('Missing mandatory custom dependency receipt for '+stage)
            dependencies.update(read_json(p))
    for rel,h in sorted(dependencies.items()):
        p=under(ROOT,rel)
        if file_hash(p)!=h:raise IntegrityError('Custom dependency changed before paper build')
        target='code/dependencies/'+rel;atomic_write(folder/target,p.read_bytes());files.append(target)
    atomic_write(folder/'code/reproduce.py',(ROOT/'scripts/reproduce_support.py').read_bytes());files.append('code/reproduce.py')
    source_files=sorted(set(files));write_json(folder/'source_inventory.json',source_files)
    from .packaging import planned_support_files
    inventory=planned_support_files(root,source_files)
    write_json(folder/'support_inventory.json',inventory)
    write_json(folder/'claims.json',claims);write_json(folder/'ai_records.json',ai_records)
    lines=[PREAMBLE,r'\PaperKitTitle{'+esc(draft['title'])+'}',r'\section*{摘要}',
           bind_prose(draft['abstract'],claims,sources=known),r'\par\noindent\textbf{关键词：}'+esc('；'.join(draft['keywords']))]
    if demo:lines.append(r'\par\medskip\noindent\textbf{演示说明：} 本文是合成问题上的工程演示，不是当届国赛解答。模型调用与独立审查为显式测试夹具；数值计算为实际运行。')
    lines.append(r'\label{abstract-end}\clearpage')
    for sec in draft['sections']:
        for cid in sec['claim_ids']:
            if cid not in claims:raise IntegrityError('Section cites nonexistent evidence')
        lines += [r'\section{'+esc(sec['heading'])+'}',bind_prose(sec['text'],claims,sources=known)]
        for eq in sec['equations']:lines += [r'\begin{equation}',equation(eq),r'\end{equation}']
    lines += [r'\section{经过计算的证据与结果}',r'\begin{longtable}{p{.42\linewidth}rp{.19\linewidth}}\toprule 证据标识 & 数值 & 单位\\\midrule\endhead']
    for key,c in claims.items():lines.append(esc(key)+' & '+f'{c["value"]:.6g}'+' & '+esc(c['unit'])+r'\\')
    lines += [r'\bottomrule\end{longtable}',
              r'\begin{figure}[htbp]\centering\includegraphics[width=.97\linewidth]{confirmation.pdf}\caption{确认阶段的实际得分。误差棒为样本标准差，不是置信区间。}\end{figure}',
              r'\begin{figure}[htbp]\centering\includegraphics[width=.98\linewidth]{ourwork.pdf}\caption{'+esc(draft['figure_caption'])+r'}\end{figure}',
              r'\section{适用范围与不足}']
    for t in draft['limitations']:lines.append(bind_prose(t,claims,sources=known)+r'\par')
    lines += [r'\FloatBarrier',r'\section*{AI工具使用声明}',
        ('本工程演示由人工智能辅助构建；本次演示的 Codex 与 Claude 子进程没有实际调用，审查夹具不能代替独立模型审查或人工核验。实际使用情况与状态见支撑材料。' if demo else
         '本参赛队在竞赛过程中使用了AI工具，主要用于问题分析、建模建议、代码生成与调试、实验审查、绘图和论文起草，详细使用情况见支撑材料。'),
        (r'\renewcommand{\refname}{参考文献}' if draft['citation_ids'] else r'\section*{参考文献}')]
    if draft['citation_ids']:
        lines.append(r'\begin{thebibliography}{99}')
        for cid in draft['citation_ids']:
            s=known[cid];lines.append(r'\bibitem{'+cid+'} '+esc(s['title'])+'. '+r'\url{'+s['url']+'}.')
        lines.append(r'\end{thebibliography}')
    else:lines.append('本演示的算法来源为随包提供的 MOSAIC 实现，问题为合成实例；未编造外部参考文献。正式研究应补入经过核验且在正文引用的文献。')
    lines += [r'\clearpage\appendix\section*{附录：支撑材料与完整源程序}\label{harness-appendix-start}',
              '支撑材料包含运行配置、数据清单、实际数值结果、评测器、求解器、定制算法依赖、证据映射、图表源数据和人工智能使用详情。原始附件是否包含在支撑材料中，以数据来源配置与清单为准。',
              r'\subsection*{源程序文件清单}']
    for rel in inventory:
        tex_filename(rel)
        rendered=r'\nolinkurl{'+rel+'}' if rel.isascii() else r'\texttt{'+esc(rel)+'}'
        lines.append(r'\noindent{\footnotesize '+rendered+r'}\par')
    for rel in source_files:
        tex_filename(rel)
        lines += [r'\subsection*{源程序与运行资源}',r'\noindent{\footnotesize\nolinkurl{'+rel+r'}}\par']
        if Path(rel).suffix.lower() in ('.py','.json','.csv','.txt','.md','.yaml','.yml'):
            lines.append(r'\VerbatimInput[breaklines=true,breakanywhere=true,fontsize=\scriptsize]{'+rel+'}')
        else:
            lines.append('二进制运行资源已按原始字节收入支撑材料；文件摘要：'+r'\nolinkurl{'+file_hash(folder/rel)+'}.')
    lines.append(r'\end{document}');atomic_write(folder/'main.tex','\n'.join(lines))
    build=compile_tex(folder)
    aux=(folder/'main.aux').read_text('utf-8',errors='replace')
    abstract_end=re.search(r'\\newlabel\{abstract-end\}\{\{[^}]*\}\{(\d+)\}',aux)
    if not abstract_end or abstract_end.group(1)!='1':raise PaperCompilationFailure('Abstract must fit on the first page')
    appendix_label=re.search(r'\\newlabel\{harness-appendix-start\}\{\{[^}]*\}\{(\d+)\}',aux)
    if not appendix_label:raise PaperCompilationFailure('Missing trusted appendix boundary label')
    build['appendix_start_page']=int(appendix_label.group(1))
    qa=preflight(folder/'main.pdf',denylist=read_json(root/'config.json')['identity_denylist'],
                 trusted_appendix_page=build['appendix_start_page'],demo=demo)
    write_json(folder/'build.json',build);write_json(folder/'preflight.json',qa)
    if qa['status']!='PASS':raise PaperCompilationFailure('Paper preflight failed: '+str(qa['failures']))
    return {'paper_sha256':file_hash(folder/'main.pdf'),'build':build,'preflight':qa,'claims_digest':digest(claims),'source_inventory':source_files}

def build_ai_details(folder:Path,records:list[dict],human:dict|None,*,demo=False):
    lines=[PREAMBLE,r'\PaperKitTitle{AI工具使用详情}',
        '本文件记录工具、使用阶段、主要提示方式，以及输出的采纳、修改和核验情况。工具回执中的未运行或未报告字段按实际状态保留，不以推测填充。',
        r'\section*{使用与核验状态}',
        ('工程测试模式：下列多角色回执来自预先编写的测试夹具，不是实际 Codex 或 Claude 调用。数值实验独立执行，但尚无正式参赛人工签核。' if demo else
         '实际工具调用见下列记录。人工核验仅按签核文件中的真实声明记录，不由智能体自动补签。')]
    from .providers import ROLES
    adopted={i['id']:i for i in human.get('review',{}).get('items',[])} if human else {}
    for idx,r in enumerate(records,1):
        key=r.get('response_digest','');rev=adopted.get(key)
        lines += [r'\subsection*{'+esc(f'调用 {idx}：{r["role"]}')+'}',
           esc(f'工具：{r["provider"]}；运行方式：{r["transport"]}；版本：{r.get("cli_version","UNREPORTED")}。')+r'\par',
           esc(f'指定模型：{r.get("model_requested","UNREPORTED")}；回执报告模型：{r.get("model_reported","UNREPORTED")}。')+r'\par',
           '主要提示方式与用途：'+esc(ROLES.get(r['role'],r['role']))+r'\par',
           '输入由题目、当前阶段合同和冻结证据构成；输入与输出分别由摘要绑定。'+r'\par',
           r'\noindent{\footnotesize\nolinkurl{output_sha256='+key+r'}}\par']
        if rev:lines.append(esc(f'采纳：{rev["adopted"]}；人工修改：{rev["modification"]}；人工核验：{rev["verification"]}')+r'\par')
        else:lines.append('采纳、人工修改和核验：尚未取得对应的逐项人工签核；不能据此认定满足正式提交条件。'+r'\par')
    lines.append(r'\end{document}');atomic_write(folder/'ai_details.tex','\n'.join(lines));receipt=compile_tex(folder,'ai_details.tex')
    from .paper_layout import inspect_pdf
    qa=inspect_pdf(folder/'ai_details.pdf',kind='ai_details',require_ai=False)
    write_json(folder/'ai_details_preflight.json',qa)
    if qa['status']!='PASS':raise PaperCompilationFailure('AI details preflight failed: '+str(qa['errors']))
    receipt['paperkit_checks']=qa
    dest=folder/'AI工具使用详情.pdf';shutil.copy2(folder/'ai_details.pdf',dest);return {'path':dest.name,'sha256':file_hash(dest),'build':receipt}
