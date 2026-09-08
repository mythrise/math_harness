"""Use the user's OurWork SVG v16 runtime, not raster-generated diagrams."""
from __future__ import annotations
import sys, shutil, subprocess
from pathlib import Path
from .common import *

def ourwork():
    src=ROOT/'vendor/ourwork_v16/src'
    if str(src) not in sys.path:sys.path.insert(0,str(src))
    import ourwork_v16
    return ourwork_v16

def render_reference(template:str,config:dict,out:Path,*,export=True):
    runtime=ourwork();runtime.save(template,out,config,mode='reference_semantic_image',strict=True,guard=True)
    if export:runtime.export_inkscape(out,png_path=out.with_suffix('.png'),pdf_path=out.with_suffix('.pdf'))
    report={'engine':'OurWork SVG Production v16','mode':'reference_semantic_image','template':template,'config_digest':digest(config),
            'svg_sha256':file_hash(out),'pdf_sha256':file_hash(out.with_suffix('.pdf')) if export else None}
    write_json(out.with_suffix('.provenance.json'),report);return report

def framework(out:Path, *, questions=None):
    """New composition built with the exact SVG/node/arrow primitives supplied
    in the attachment. The original reference templates are never overwritten.
    """
    runtime=ourwork()
    from ourwork_v3 import SVG,node,arrow
    s=SVG(w=1160,h=760)
    family='Arial, Liberation Sans, sans-serif'
    s.text(580,40,'CUMCM-EgoHarness  |  Evidence before claims',size=25,weight='bold',family=family)
    s.text(580,69,'Exa evidence + adversarial assumptions + Claude / GPT review seats',size=15,family=family)
    node(s,390,92,380,56,'Research PI / Supreme Scheduler\nPriorities, budget, repair and stop decisions',size=16,weight='bold')
    for x in (200,580,960):
        s.polyline([(580,148),(580,167),(x,167),(x,187)],marker='arrow')
    columns=[(30,'MODELER / Codex',['Exa scout: evidence and method limits','Modeler: assumptions and equations','Exa adversary: counterexamples + tests','Frozen hypotheses + solver contracts']),
             (410,'CODER / Codex',['Generate isolated versioned code','MOSAIC or admissible algorithm skill','Independent tests + bounded execution','Immutable trials / seeds / raw outputs']),
             (790,'WRITER / Codex',['Read only validated claim records','Tables and vector OurWork figures','Chinese LaTeX + runnable code appendix','AI disclosure + anonymous release'])]
    for x,title,items in columns:
        s.rect(x,187,340,233,fill='#F7F9FB',stroke='#738496',rx=12)
        s.text(x+170,219,title,size=18,weight='bold',family=family)
        for i,text in enumerate(items):node(s,x+15,237+i*43,310,34,text,size=13,fill='#FFFFFF',stroke='#C6CDD6')
    arrow(s,371,301,406,301);arrow(s,751,301,786,301)
    for x in (200,580,960):arrow(s,x,422,x,452)
    s.rect(30,455,1100,98,fill='#F6F3EC',stroke='#9D8969',rx=10)
    s.text(580,483,'INDEPENDENT REVIEW BOARD',size=18,weight='bold',family=family)
    s.text(580,511,'Claude + GPT: math / experiments  |  GPT takeover on outage  |  GPT: rendered pages',size=16,family=family)
    s.text(580,537,'Two fresh seats per role. Transport failover never erases a valid negative review.',size=13,family=family)
    arrow(s,580,553,580,579)
    node(s,30,582,340,66,'DETERMINISTIC CORE\nDAG + CAS + SQLite + receipts',size=16,fill='#EAF1F4')
    node(s,410,582,340,66,'AUTORESEARCH\nDev selection -> freeze -> confirm',size=16,fill='#EAF1F4')
    node(s,790,582,340,66,'CONTEST HUMAN GATES\nTeam-led model + itemized review',size=16,fill='#EAF1F4')
    s.text(580,683,'Invalid results, missing reviews or stale evidence -> HOLD / REPAIR, never a fabricated PASS',size=15,weight='bold',family=family)
    s.text(580,716,'Practice can run unattended. Competition release requires real human attestations.',size=14,family=family)
    out.parent.mkdir(parents=True,exist_ok=True);atomic_write(out,s.to_string())
    runtime.export_inkscape(out,png_path=out.with_suffix('.png'),pdf_path=out.with_suffix('.pdf'))
    write_json(out.with_suffix('.provenance.json'),{'engine':'attached ourwork_v3.SVG primitives through v16 runtime',
              'source_sha256':file_hash(ROOT/'vendor/ourwork_v16/src/ourwork_v3.py'),'svg_sha256':file_hash(out),
              'note':'new composition; does not claim exact-reference layout'})
    return out

def score_plot(rows:list[dict],out:Path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    labels=sorted({r['candidate'] for r in rows});means=[];stds=[]
    for label in labels:
        v=[r['evaluation']['score'] for r in rows if r['candidate']==label]
        means.append(float(np.mean(v)));stds.append(float(np.std(v,ddof=1)) if len(v)>1 else 0.)
    fig,ax=plt.subplots(figsize=(7.3,3.6));x=np.arange(len(labels))
    ax.errorbar(x,means,yerr=stds,fmt='o',capsize=5)
    ax.set_xticks(x,labels);ax.set_ylabel(rows[0]['evaluation']['metric']);ax.set_xlabel('Frozen method / configuration')
    ax.set_title('Confirmation runs: mean and sample standard deviation')
    ax.grid(axis='y',alpha=.25);fig.tight_layout();out.parent.mkdir(parents=True,exist_ok=True)
    for suffix in ('.svg','.pdf','.png'):fig.savefig(out.with_suffix(suffix),dpi=180)
    plt.close(fig);write_json(out.with_suffix('.data.json'),rows)
    write_json(out.with_suffix('.provenance.json'),{'data_digest':digest(rows),'svg_sha256':file_hash(out.with_suffix('.svg')),
              'error_bar':'sample standard deviation, not confidence interval','groups':labels})
