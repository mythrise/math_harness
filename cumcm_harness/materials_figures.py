"""Problem-specific OurWork view; original v16 engine remains unmodified."""
from __future__ import annotations
from pathlib import Path
import unicodedata
from .common import IntegrityError, digest, write_json, file_hash, ROOT
from .contracts import topo

FAMILY={'optimization':'优化','prediction':'预测','evaluation':'评价','graph':'图与路径',
        'dynamics':'机理动力学','simulation':'随机模拟','statistics':'统计','mixed':'混合模型'}


def chinese_font(text):
    """Choose an installed font only after verifying the actual required glyphs."""
    from matplotlib import font_manager
    from matplotlib.ft2font import FT2Font
    from .common import InfrastructureUnavailable
    names={font.name for font in font_manager.fontManager.ttflist}
    for family in ('Noto Sans CJK SC','Noto Sans CJK JP','WenQuanYi Zen Hei',
                   'Microsoft YaHei','SimHei','PingFang SC','Heiti SC','Arial Unicode MS'):
        if family not in names:continue
        face=FT2Font(font_manager.findfont(font_manager.FontProperties(family=family)))
        if all(ch.isspace() or face.get_char_index(ord(ch)) for ch in text):return family
    raise InfrastructureUnavailable('An installed Chinese font covering the figure glyphs is required; no font is bundled')


def _wrap(text,width=22):
    lines=[];line='';n=0
    for ch in text:
        k=2 if unicodedata.east_asian_width(ch) in ('W','F') else 1
        if n+k>width:lines.append(line);line='';n=0
        line+=ch;n+=k
    if line:lines.append(line)
    return lines


def question_framework(out:Path,questions):
    if not 1<=len(questions)<=24:raise IntegrityError('Framework needs one to twenty-four actual questions')
    for q in questions:
        if not isinstance(q,dict) or q.get('family') not in FAMILY:raise IntegrityError('Unknown question family')
        if not isinstance(q.get('title'),str) or not q['title'].strip():raise IntegrityError('Question title missing')
    topo([{'id':q['id'],'depends_on':q.get('depends_on',[])} for q in questions])
    from .figures import ourwork
    runtime=ourwork()
    from ourwork_v3 import SVG,arrow
    w=980;detailed=len(questions)<=6;two_rows=4<=len(questions)<=6;h=680 if two_rows else 550
    svg=SVG(w,h,bg='#ffffff')
    font=chinese_font('本题建模求解与证据流程冻结题意与原始数据逐问目标口径单位和硬约束数据方案方法选择保持原始数据先基准后候选独立核验稳健性诊断重算目标约束结果正文摘要符号图表披露完整要求见合同复杂依赖按冻结执行完整边集图源旁注聚合视图仅展示概要执行另查回执'+''.join(q['title']+q['id']+FAMILY[q['family']] for q in questions))
    def text(x,y,t,size=24):svg.text(x,y,t,size=size,family=font,anchor='middle',fill='#182431')
    def box(x,y,bw,bh,title,details):
        svg.rect(x,y,bw,bh,fill='#f1f5f9',stroke='#42596b',sw=1.5,rx=8)
        text(x+bw/2,y+31,title,26)
        for i,t in enumerate(details):text(x+bw/2,y+62+i*27,t,22)
    text(w/2,39,'本题建模、求解与证据流程',30)
    box(45,68,400,100,'冻结题意与原始数据',['逐问目标、口径、单位和硬约束'])
    box(535,68,400,100,'数据方案与方法选择',['保持原始数据；先基准后候选'])
    arrow(svg,450,118,526,118)
    # The preparation feeds a question group, not arbitrarily the last question.
    svg.rect(20,202,940,318 if two_rows else 188,fill='none',stroke='#718096',sw=1.2,rx=8,dash='5,4')
    svg.polyline([(735,175),(735,187),(490,187),(490,199)],marker='arrow')
    positions={}
    if detailed:
        cols=3 if len(questions)>=3 else len(questions);bw=270 if cols==3 else 420
        gap=(w-80-cols*bw)/max(1,cols-1)
        for i,q in enumerate(questions):
            x=40+(i%cols)*(bw+gap);y=211+(i//cols)*130
            label=q['title'];lines=_wrap(label,24 if cols==3 else 36)
            # Explicit aggregation: the source title is never altered in provenance.
            if len(lines)>2:lines=['该问完整要求见正文','与逐问需求合同']
            box(x,y,bw,115,q['id']+' · '+FAMILY[q['family']],lines)
            positions[q['id']]=(x,y,bw,115)
        lower=485 if two_rows else 355
    else:
        ids='、'.join(q['id'] for q in questions)
        box(45,215,890,100,'逐问求解（聚合视图）',_wrap(ids,100)[:2])
        lower=355
    deps=[(p,q['id']) for q in questions for p in q.get('depends_on',[])]
    for a,b in deps:
        if a in positions and b in positions:
            ax,ay,aw,ah=positions[a];bx,by,bw,bh=positions[b]
            if ay==by and 0<bx-ax-aw<90:arrow(svg,ax+aw+4,ay+ah/2,bx-7,by+bh/2)
    detail='；'.join(a+' → '+b for a,b in deps) or '无声明的问间前置依赖'
    dep_lines=_wrap('依赖：'+detail,78)
    # Large dependency sets remain completely recorded in sidecar; overview says so explicitly.
    if len(dep_lines)>2:dep_lines=['复杂依赖按冻结逐问合同执行；完整边集见图源旁注']
    for i,line in enumerate(dep_lines):text(w/2,lower+26*i,line,20)
    svg.polyline([(490,lower+36),(490,lower+44),(245,lower+44),(245,lower+52)],marker='arrow')
    box(45,lower+55,400,95,'独立核验与稳健性诊断',['重算目标、约束和逐问结果'])
    box(535,lower+55,400,95,'证据与论文一致性',['正文、摘要、符号、图表与披露'])
    arrow(svg,450,lower+102,526,lower+102)
    text(w/2,h-17,'节点为模型合同视图；执行与数值结论须查询实际作业回执' if detailed else '聚合视图仅展示概要；完整问号与依赖见图源旁注；执行另查回执',18)
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(svg.to_string(),encoding='utf-8')
    runtime.export_inkscape(out,png_path=out.with_suffix('.png'),pdf_path=out.with_suffix('.pdf'))
    provenance={'source':'USER_PROVIDED_OURWORK_V16_PRIMITIVES','view':'ACTUAL_QUESTION_CONTRACT_NOT_SOFTWARE_AGENT_ARCHITECTURE',
        'engine_sha256':file_hash(ROOT/'vendor/ourwork_v16/src/ourwork_v3.py'),
        'question_contract_digest':digest(questions),'questions':questions,'dependency_edges':deps,
        'aggregated':not detailed,'font_family':font,'font_files_distributed':False,
        'svg_sha256':file_hash(out),'numerical_execution_certified_by_this_figure':False}
    write_json(out.with_suffix('.provenance.json'),provenance)
    return out


def confirmation_plot(rows,out,plan):
    """Labels are a presentation layer; underlying scores and IDs are unchanged."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import numpy as np
    if not rows:raise IntegrityError('Confirmation plot requires executed rows')
    groups=sorted({r['candidate'] for r in rows});data=[]
    metric=rows[0]['evaluation']['metric']
    if any(r['evaluation']['metric']!=metric for r in rows):raise IntegrityError('Plot mixes incompatible metrics')
    units=[q['unit'] for q in plan['questions'] if q['metric']==metric]
    if not units or len(set(units))!=1:raise IntegrityError('Plot metric/unit is not defined consistently by the plan')
    label_map={g:('基准方案' if g=='baseline' else '候选 '+g) for g in groups}
    for g in groups:
        v=np.asarray([r['evaluation']['score'] for r in rows if r['candidate']==g],float)
        if not np.isfinite(v).all():raise IntegrityError('Nonfinite score in figure')
        data.append((float(v.mean()),float(v.std(ddof=1)) if len(v)>1 else 0.))
    display={'normalized_hv':'归一化超体积','mae':'平均绝对误差','rmse':'均方根误差'}.get(metric,metric)
    unit={'ratio':'无量纲','units':'原题单位','minutes':'分钟'}.get(units[0],units[0])
    needed=display+unit+'已冻结的方法与配置确认实验均值与样本标准差基准方案候选'+''.join(label_map.values())
    font=chinese_font(needed)
    with plt.rc_context({'font.family':font,'axes.unicode_minus':False}):
        fig,ax=plt.subplots(figsize=(7.3,3.6))
        ax.errorbar(range(len(groups)),[d[0] for d in data],yerr=[d[1] for d in data],fmt='o',capsize=5)
        ax.set_xticks(range(len(groups)),[label_map[g] for g in groups]);ax.set_xlabel('已冻结的方法与配置')
        ax.set_ylabel(display+'（'+unit+'）');ax.set_title('确认实验：均值与样本标准差')
        ax.grid(axis='y',alpha=.25);fig.tight_layout();out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
        for ext in ('.svg','.pdf','.png'):fig.savefig(out.with_suffix(ext),dpi=240)
        plt.close(fig)
    write_json(out.with_suffix('.data.json'),rows)
    write_json(out.with_suffix('.provenance.json'),{'data_digest':digest(rows),'svg_sha256':file_hash(out.with_suffix('.svg')),
        'metric':metric,'source_unit':units[0],'label_map':label_map,'font_family':font,
        'error_bar':'sample standard deviation, not confidence interval','groups':groups,'no_synthetic_results_inserted':True})
