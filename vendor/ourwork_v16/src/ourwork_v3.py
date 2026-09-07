from __future__ import annotations
import json, math, random, re, shutil
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Tuple

W, H = 960, 540
ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / 'registry' / 'templates.json'


def _num(v, d=0.0):
    try: return float(v)
    except Exception: return d


def _hex(v, fallback='#000000'):
    if isinstance(v,str) and re.fullmatch(r'#[0-9A-Fa-f]{6}',v): return v
    return fallback


def _lighten(hexcol: str, amt: float=0.25) -> str:
    h=hexcol.lstrip('#'); r,g,b=int(h[:2],16),int(h[2:4],16),int(h[4:],16)
    r=int(r+(255-r)*amt); g=int(g+(255-g)*amt); b=int(b+(255-b)*amt)
    return f'#{r:02X}{g:02X}{b:02X}'


def _darken(hexcol: str, amt: float=0.2) -> str:
    h=hexcol.lstrip('#'); r,g,b=int(h[:2],16),int(h[2:4],16),int(h[4:],16)
    r=int(r*(1-amt)); g=int(g*(1-amt)); b=int(b*(1-amt))
    return f'#{r:02X}{g:02X}{b:02X}'


def wrap_lines(text: str, max_chars: int) -> List[str]:
    text=str(text)
    if '\n' in text:
        out=[]
        for p in text.split('\n'):
            out.extend(wrap_lines(p,max_chars))
        return out or ['']
    words=text.split()
    if not words: return ['']
    lines=[]; cur=''
    for w in words:
        if len(cur)+len(w)+(1 if cur else 0)<=max_chars:
            cur += (' ' if cur else '')+w
        else:
            if cur: lines.append(cur)
            # very long token
            while len(w)>max_chars:
                lines.append(w[:max_chars]); w=w[max_chars:]
            cur=w
    if cur: lines.append(cur)
    return lines


class SVG:
    def __init__(self,w=W,h=H,bg='#ffffff'):
        self.w=w; self.h=h; self.parts=[]
        self.defs=[
            '<marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="strokeWidth"><path d="M0 0L9 4.5L0 9Z" fill="#4F4F4F"/></marker>',
            '<marker id="arrowGreen" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="strokeWidth"><path d="M0 0L9 4.5L0 9Z" fill="#548235"/></marker>',
            '<marker id="arrowBlue" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="strokeWidth"><path d="M0 0L9 4.5L0 9Z" fill="#2E75B6"/></marker>',
            '<marker id="arrowRed" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="strokeWidth"><path d="M0 0L9 4.5L0 9Z" fill="#D9534F"/></marker>',
            '<linearGradient id="tealGrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#8CD9C9"/><stop offset="1" stop-color="#AEC2E5"/></linearGradient>',
            '<filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="2" dy="3" stdDeviation="3" flood-color="#000" flood-opacity=".22"/></filter>',
        ]
        self.rect(0,0,w,h,fill=bg,stroke='none',rx=0)
    def add(self,s): self.parts.append(s)
    def rect(self,x,y,w,h,fill='none',stroke='#333333',sw=1.3,rx=5,dash=None,opacity=1.0,shadow=False):
        da=f' stroke-dasharray="{dash}"' if dash else ''
        fil=' filter="url(#shadow)"' if shadow else ''
        self.add(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"{da}{fil}/>')
    def line(self,x1,y1,x2,y2,stroke='#4F4F4F',sw=1.5,dash=None,marker=None,opacity=1.0):
        da=f' stroke-dasharray="{dash}"' if dash else ''
        ma=f' marker-end="url(#{marker})"' if marker else ''
        self.add(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"{da}{ma}/>')
    def polyline(self,pts,stroke='#4F4F4F',sw=1.5,dash=None,marker=None,fill='none',opacity=1.0):
        da=f' stroke-dasharray="{dash}"' if dash else ''
        ma=f' marker-end="url(#{marker})"' if marker else ''
        p=' '.join(f'{x:.2f},{y:.2f}' for x,y in pts)
        self.add(f'<polyline points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"{da}{ma}/>')
    def polygon(self,pts,fill='none',stroke='#333',sw=1.2,opacity=1.0):
        p=' '.join(f'{x:.2f},{y:.2f}' for x,y in pts)
        self.add(f'<polygon points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>')
    def circle(self,cx,cy,r,fill='none',stroke='#333',sw=1.2,opacity=1.0,shadow=False):
        fil=' filter="url(#shadow)"' if shadow else ''
        self.add(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"{fil}/>')
    def ellipse(self,cx,cy,rx,ry,fill='none',stroke='#333',sw=1.2,opacity=1.0):
        self.add(f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>')
    def path(self,d,fill='none',stroke='#333',sw=1.5,marker=None,opacity=1.0,dash=None):
        ma=f' marker-end="url(#{marker})"' if marker else ''
        da=f' stroke-dasharray="{dash}"' if dash else ''
        self.add(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"{ma}{da}/>')
    def text(self,x,y,text,size=14,fill='#111111',anchor='middle',weight='normal',family='Times New Roman, Liberation Serif, serif',italic=False,rotate=None,opacity=1.0):
        rot=f' transform="rotate({rotate} {x:.2f} {y:.2f})"' if rotate is not None else ''
        it='italic' if italic else 'normal'
        self.add(f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" font-family="{family}" font-size="{size}" font-style="{it}" font-weight="{weight}" fill="{fill}" opacity="{opacity}"{rot}>{escape(str(text))}</text>')
    def text_box(self,x,y,w,h,text,size=13,fill='#111',weight='normal',family='Times New Roman, Liberation Serif, serif',anchor='middle',italic=False,max_lines=None):
        # approximate wrapping; then shrink until it fits vertically/horizontally
        size=float(size)
        max_chars=max(4,int(w/(size*0.53)))
        lines=wrap_lines(str(text),max_chars)
        if max_lines and len(lines)>max_lines:
            lines=lines[:max_lines-1]+[' '.join(lines[max_lines-1:])]
        while (len(lines)*size*1.18>h or max(len(s) for s in lines)*size*.53>w) and size>7:
            size-=.5; max_chars=max(4,int(w/(size*.53))); lines=wrap_lines(str(text),max_chars)
            if max_lines and len(lines)>max_lines: lines=lines[:max_lines]
        start=y+h/2-(len(lines)-1)*size*.58+size*.34
        for i,line in enumerate(lines):
            tx=x+w/2 if anchor=='middle' else x
            self.text(tx,start+i*size*1.16,line,size=size,fill=fill,anchor=anchor,weight=weight,family=family,italic=italic)
    def to_string(self):
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}"><defs>{"".join(self.defs)}</defs>{"".join(self.parts)}</svg>'


def node(svg:SVG,x,y,w,h,text,fill='#DCE6F1',stroke='#7F8C8D',size=13,weight='normal',rx=5,dash=None,text_fill='#111'):
    svg.rect(x,y,w,h,fill=fill,stroke=stroke,rx=rx,dash=dash)
    svg.text_box(x+4,y+3,w-8,h-6,text,size=size,fill=text_fill,weight=weight)


def arrow(svg:SVG,x1,y1,x2,y2,color='#4F4F4F',marker='arrow',sw=1.5,dash=None):
    svg.line(x1,y1,x2,y2,stroke=color,sw=sw,marker=marker,dash=dash)


def elbow(svg:SVG,pts,color='#4F4F4F',marker='arrow',sw=1.4,dash=None):
    svg.polyline(pts,stroke=color,sw=sw,marker=marker,dash=dash)


def header(svg:SVG,title:str):
    if title:
        svg.text(26,29,title,size=18,anchor='start',weight='bold',family='Arial, Liberation Sans, sans-serif',fill='#222')


# ---------------- Auto-layout template renderers ----------------

def T01(cfg):
    svg=SVG(); header(svg,cfg.get('title','Policy development and strategy flow'))
    years=cfg.get('years',['1992','2004','2012','2021'])
    stages=cfg.get('stages',['Strategy I\nProtection Priority Scheme','Strategy II\nTraditional Dichotomy Method','Strategy III\nEnvironmental Sensitive Division','Strategy IV\nHuman-land Relationship'])
    colors=cfg.get('colors',['#F3D990','#B9CBE1','#B6D1A2','#E7C2A8'])
    x0=120; topy=50; gap=38; bw=140
    n=max(1,len(stages)); avail=760; bw=min(155,(avail-gap*(n-1))/n); gap=(avail-bw*n)/(n-1) if n>1 else 0
    for i,s in enumerate(stages):
        x=x0+i*(bw+gap); node(svg,x,topy,bw,48,s,fill=colors[i%len(colors)],stroke='#777',size=11,weight='bold',rx=5)
        if i<len(years): svg.text(x-16,topy+31,years[i],size=10,anchor='end')
        if i<n-1: arrow(svg,x+bw,topy+24,x+bw+gap-4,topy+24)
    # lower algorithm blocks
    sections=cfg.get('sections',[
      {'title':'Identify','items':['Low Priority','Medium Priority','High Priority']},
      {'title':'Evaluate','items':['Economy Development Area','Ecological Preservation Area']},
      {'title':'Combine','items':['Ecology Aspects','Economy Aspects','Coupled Analysis']},
      {'title':'Our Work','items':['Human-land Relationship Balance','State-of-the-art Method']},
    ])
    bx=72; by=145; secw=200; sech=300; sgap=22
    for i,sec in enumerate(sections):
        x=bx+i*(secw+sgap)
        svg.rect(x,by,secw,sech,fill='#FFFFFF',stroke='#3B9C92',dash='7 5',rx=12)
        svg.text(x+secw/2,by+27,sec.get('title',''),size=14,weight='bold',fill='#333')
        items=sec.get('items',[])
        inner_y=by+60
        for j,it in enumerate(items):
            hh=min(52,(sech-85)/max(1,len(items))-8)
            node(svg,x+22,inner_y+j*(hh+10),secw-44,hh,it,fill=_lighten(colors[i%len(colors)],.35),stroke=_darken(colors[i%len(colors)],.1),size=10)
            if j<len(items)-1: arrow(svg,x+secw/2,inner_y+j*(hh+10)+hh,x+secw/2,inner_y+(j+1)*(hh+10)-2,color='#777')
        if i<len(sections)-1: arrow(svg,x+secw,by+sech/2,x+secw+sgap-5,by+sech/2,color='#777')
    return svg.to_string()


def T02(cfg):
    svg=SVG(); header(svg,cfg.get('title','Overview of our work'))
    top=cfg.get('top_blocks',['Literature\nReview','Data Collection\nData Processing','HRCA Model I','MSS Model II','LTP Model III','Model\nTesting','A Letter'])
    cols=cfg.get('colors',['#4E927F','#96B89B','#DCDFD2','#ECD9CF','#FDCF9E','#EFA484','#B6766C'])
    node(svg,25,48,90,42,'Our Work',fill='#F4E6C7',stroke='#C8B783',size=13,weight='bold')
    x0=128; aw=795; n=len(top); gap=5; bw=(aw-gap*(n-1))/max(1,n)
    for i,t in enumerate(top): node(svg,x0+i*(bw+gap),48,bw,42,t,fill=cols[i%len(cols)],stroke=_darken(cols[i%len(cols)],.15),size=9.5,weight='bold',rx=3)
    svg.rect(28,108,905,190,fill='#fff',stroke='#4E927F',dash='6 5',rx=22)
    svg.text(480,103,cfg.get('stage1','Stage-I: Site selection / analysis'),size=11,weight='bold',fill='#588E31')
    # review list
    checklist=cfg.get('checklist',['Review','Data','HRCA','MSS','LTP','Testing','Letter'])
    for i,t in enumerate(checklist):
        y=132+i*21; node(svg,115,y,45,17,f'Step{i+1}',fill=cols[i%len(cols)],stroke='#888',size=6.5,rx=1)
        svg.text(170,y+12,t,size=8,anchor='start'); svg.text(214,y+12,'✓',size=12,fill='#00B050',weight='bold')
    arrow(svg,220,205,340,205,color='#B86029',marker='arrowRed',sw=2)
    arrow(svg,560,205,675,205,color='#B86029',marker='arrowRed',sw=2)
    svg.text(370,281,cfg.get('analysis_label','(a) Coupling Analysis Model'),size=10)
    svg.text(695,281,cfg.get('raster_label','(b) Rasterization / Mapping'),size=10)
    svg.rect(28,312,905,192,fill='#fff',stroke='#4E927F',dash='6 5',rx=22)
    svg.text(480,328,cfg.get('stage2','Stage-II: Decisions on preservation and protection'),size=11,weight='bold',fill='#588E31')
    labels=cfg.get('stage2_blocks',['Prediction Results Analysis','Multiple-objective Optimization','Strategy Selection Model'])
    for i,l in enumerate(labels):
        x=90+i*290; node(svg,x,382,230,50,l,fill='#FFFFFF',stroke='none',size=10)
        if i<2: arrow(svg,x+230,407,x+280,407,color='#B86029',marker='arrowRed',sw=2)
    return svg.to_string()


def T03(cfg):
    svg=SVG(); header(svg,cfg.get('title','Composite multi-model framework'))
    top=cfg.get('top_blocks',['Literature\nReview','Data Collection\nData Processing','UD Model I','REDE Model II','CBC Model III','Model\nTesting','A Letter'])
    cols=['#4E927F','#96B89B','#DCDFD2','#ECD9CF','#FDCF9E','#EFA484','#B6766C']
    node(svg,18,43,82,39,'Our Work',fill='#F4E6C7',stroke='#C8B783',size=11,weight='bold')
    x0=112; n=len(top); gap=5; bw=(830-gap*(n-1))/n
    for i,t in enumerate(top): node(svg,x0+i*(bw+gap),43,bw,39,t,fill=cols[i%len(cols)],stroke=_darken(cols[i%len(cols)],.15),size=8.3,weight='bold',rx=3)
    # top two model panels
    panel_y=102; panel_h=205
    svg.rect(20,panel_y,450,panel_h,fill='#fff',stroke='#000',dash='8 5',rx=0)
    svg.rect(490,panel_y,450,panel_h,fill='#fff',stroke='#000',dash='8 5',rx=0)
    svg.text(245,294,cfg.get('left_title','(a) Decision Model'),size=10,weight='bold')
    svg.text(715,294,cfg.get('right_title','(b) Evaluation Model'),size=10,weight='bold')
    left_items=cfg.get('left_items',['Risk Coefficient','Insurance Claim','Premium Rate','Policy Effectiveness'])
    for i,t in enumerate(left_items): node(svg,80,126+i*39,130,27,t,fill='#CFE6B9',stroke='none',size=8)
    node(svg,235,158,120,54,cfg.get('left_core','Underwriting\nDecision Model'),fill='#B5D69E',stroke='none',size=9,weight='bold')
    node(svg,370,126,77,52,cfg.get('region_a','Asia:\nOkinawa'),fill='#D9EBB8',stroke='none',size=9)
    node(svg,370,211,77,52,cfg.get('region_b','North America:\nFlorida'),fill='#D9EBB8',stroke='none',size=8)
    arrow(svg,210,184,235,184); arrow(svg,355,184,370,153)
    # right model chain
    rt=cfg.get('right_chain',['History Extreme Weather Events','LSTM','Predicted Extreme Weather Events','TOPSIS','EWM','Scores of Top Regions'])
    positions=[(515,126,140,45),(670,126,78,45),(765,126,150,45),(515,202,100,38),(630,202,70,38),(715,199,200,45)]
    for (x,y,w,h),t in zip(positions,rt): node(svg,x,y,w,h,t,fill='#F7D8C4' if y<190 else '#F6C189',stroke='#C5590F',size=7.7)
    # bottom two panels
    svg.rect(20,325,450,185,fill='#EAF0FF',stroke='#000',dash='8 5',rx=0)
    svg.rect(490,325,450,185,fill='#FFF1B9',stroke='#000',dash='8 5',rx=0)
    bottom_left=cfg.get('bottom_left',['Use 0-1 variables','Minimize Maintenance Cost','Set Reasonable Constraints','Goal Programming Model','Future Protection Planning'])
    for i,t in enumerate(bottom_left):
        x=40+(i%3)*137; y=350+(i//3)*62; node(svg,x,y,120,48,t,fill='#CCD9F6',stroke='none',size=7.7)
    bottom_right=cfg.get('bottom_right',['Weight','Historical Value','Cultural Value','Community Value','Economic Value','Protection Level'])
    for i,t in enumerate(bottom_right):
        x=515+(i%3)*132; y=350+(i//3)*62; node(svg,x,y,115,48,t,fill='#FFE699',stroke='none',size=7.7)
    return svg.to_string()


def T04(cfg):
    svg=SVG(); header(svg,cfg.get('title','Four problem / task panel'))
    panels=cfg.get('panels',[
        {'title':'Problem1: Predict the number of reported results','theme':'#FFE699','nodes':['ARIMA model','LSTM model','Predict interval','Attributes of the word','Hard Mode']},
        {'title':'Problem3: Classify words by difficulty','theme':'#F8CBAD','nodes':['History and new attributes','PCA','GMM','Word semantics','Classify']},
        {'title':'Problem2: Predict distribution','theme':'#C5E0B4','nodes':['Future word','Future date','Linear models','Tree models','Stacking model']},
        {'title':'Problem4: Interesting features','theme':'#B4C6E7','nodes':['Number over time','Hard Mode over time','Result distribution','Letter position']},
    ])
    positions=[(35,60),(505,60),(35,290),(505,290)]
    for idx,(p,(x,y)) in enumerate(zip(panels,positions)):
        svg.text(x,y-9,p.get('title',''),size=11,anchor='start',weight='bold',italic=True)
        svg.rect(x,y,420,190,fill='#FFFFFF',stroke='#111',sw=2,dash='7 5',rx=0)
        nodes=p.get('nodes',[]); theme=p.get('theme','#D9EAD3')
        if idx in (0,2):
            for i,t in enumerate(nodes[:4]): node(svg,x+22,y+30+i*33,120,24,t,fill=_lighten(theme,.18),stroke='none',size=8.5)
            if len(nodes)>4: node(svg,x+225,y+70,150,55,nodes[4],fill=_darken(theme,.15),stroke='none',size=9,text_fill='#fff' if idx==0 else '#333')
            arrow(svg,x+142,y+96,x+225,y+96)
        else:
            grid=[(x+28,y+36),(x+185,y+36),(x+185,y+92),(x+300,y+36),(x+300,y+92)]
            for i,t in enumerate(nodes[:5]):
                xx,yy=grid[i]; node(svg,xx,yy,120 if i<3 else 90,30,t,fill=_lighten(theme,.12),stroke='none',size=8.2)
                if i<4: pass
            if len(nodes)>=3: arrow(svg,x+245,y+67,x+245,y+90)
    return svg.to_string()


def T05(cfg):
    svg=SVG(); header(svg,cfg.get('title','Ecological mechanism and model application'))
    left_title=cfg.get('left_title','Plant Community Succession\nModel Based on Ecological Niche')
    right_title=cfg.get('right_title','Application of the Model')
    svg.rect(165,52,330,400,fill='#fff',stroke='#2A72B5',dash='8 5',rx=0)
    svg.rect(525,52,330,400,fill='#fff',stroke='#EA7425',dash='8 5',rx=0)
    node(svg,185,72,290,52,left_title,fill='#FFFFFF',stroke='#2A72B5',size=12,weight='bold')
    node(svg,548,72,284,52,right_title,fill='#FFFFFF',stroke='#EA7425',size=12,weight='bold')
    layers=cfg.get('left_layers',[
      {'label':'Initial Conditions / Niche','items':['Initial Conditions','Species Niche Characteristics']},
      {'label':'Internal Effects','items':['Reproduction','Mortality']},
      {'label':'External Effects','items':['Irregular Weather Cycles','Degree of Drought','Duration of Drought']},
    ])
    y=140
    for li,L in enumerate(layers):
        hh=86 if li<2 else 118
        svg.rect(183,y,294,hh,fill='#fff',stroke='#2A72B5',dash='6 4',rx=12)
        svg.text(330,y+14,L.get('label',''),size=9,weight='bold',fill='#2A72B5')
        items=L.get('items',[]); bw=(250-8*(len(items)-1))/max(1,len(items));
        for j,it in enumerate(items): node(svg,205+j*(bw+8),y+30,bw,38,it,fill='#FFFFFF',stroke='#2A72B5',size=8)
        y+=hh+12
    apps=cfg.get('applications',['Effect of Number of Species','Impact of Types of Species','Effects of Drought Severity','Impact of Pollution and Habitat Reduction','Measures to Extend Community Life'])
    for i,t in enumerate(apps): node(svg,555,143+i*56,270,42,t,fill='#FFFFFF',stroke='#EA7425',size=8.5)
    svg.rect(165,466,690,56,fill='#fff',stroke='#6A9C47',dash='8 5',rx=0)
    node(svg,290,478,150,32,cfg.get('sensitivity','Sensitivity Analysis'),fill='#fff',stroke='#6A9C47',size=9.5,weight='bold')
    arrow(svg,450,494,495,494,color='#6A9C47',marker='arrowGreen')
    node(svg,505,478,220,32,cfg.get('strengths','Strengths and Weaknesses'),fill='#fff',stroke='#6A9C47',size=9.5,weight='bold')
    return svg.to_string()


def T06(cfg):
    svg=SVG(); header(svg,cfg.get('title','Literature Review Framework'))
    svg.ellipse(122,170,74,110,fill='#FFF9F6',stroke='#D88764',sw=2)
    svg.text_box(57,100,130,140,'Literature\nReview\nFramework',size=17,fill='#C55A34',weight='bold')
    branches=cfg.get('branches',[
      {'title':'Composition of\nLight Pollution','color':'#B3CFC4','sub':['All Day','Only Night'],'strength':['Data is Complete and Accurate','Fully Exploit Artificial Light Influence'],'weak':['Difficult to Eliminate Natural Light','Lack of Daytime Artificial Light Data']},
      {'title':'Determination of\nData Space','color':'#94C3D9','sub':['2-D','3-D'],'strength':['Sample','Independent'],'weak':['Dependent on Device Performance','Comprehensive']},
      {'title':'Effect on\nBiological Populations','color':'#CAC4E0','sub':['Microcosmic','Macroscopic'],'strength':['Precision','Concise and Universal'],'weak':['Limited and Complex','Rough']},
    ])
    bx=[300,520,740]
    for i,(b,x) in enumerate(zip(branches,bx)):
        # big branch arrow
        svg.path(f'M{195+i*6} {155+i*3} L{x+67} 92',stroke=b.get('color','#94C3D9'),sw=7,opacity=.65); svg.polygon([(x+67,92),(x+53,86),(x+58,101)],fill=b.get('color','#94C3D9'),stroke='none',opacity=.75)
        node(svg,x,120,150,55,b.get('title',''),fill=b.get('color','#94C3D9'),stroke='#555',size=9.2)
        subs=b.get('sub',[])
        for j,s in enumerate(subs): node(svg,x+j*80,205,70,42,s,fill=_lighten(b.get('color','#94C3D9'),.08),stroke='#777',size=8)
        for j,s in enumerate(b.get('strength',[])[:2]): node(svg,x+j*80,275,70,58,s,fill=_lighten(b.get('color','#94C3D9'),.08),stroke='#777',size=7)
        for j,s in enumerate(b.get('weak',[])[:2]): node(svg,x+j*80,385,70,70,s,fill=_lighten(b.get('color','#94C3D9'),.15),stroke='#777',size=6.7)
    svg.text(32,305,'Strengths',size=10,anchor='start',weight='bold')
    svg.text(32,415,'Weaknesses',size=10,anchor='start',weight='bold')
    svg.line(70,352,930,352,stroke='#87C6E3',dash='9 5 2 5',sw=1.7)
    return svg.to_string()


def T07(cfg):
    svg=SVG(); header(svg,cfg.get('title','Data preparation, model construction and application'))
    mode=cfg.get('mode','board')
    if mode=='cards':
        cards=cfg.get('cards',[{'bullets':['China','Canada'],'label':'Transporter'} for _ in range(8)])
        cols=4; x0=85; y0=85; cw=180; ch=180; gx=25; gy=35
        for i,c in enumerate(cards[:8]):
            r=i//cols; cc=i%cols; x=x0+cc*(cw+gx); y=y0+r*(ch+gy)
            svg.rect(x,y,cw,ch,fill='#fff',stroke='#98BEBB',sw=1.4,rx=20)
            bullets=c.get('bullets',[])
            for j,t in enumerate(bullets[:4]): svg.text(x+18,y+35+j*24,'• '+str(t),size=12,anchor='start',weight='bold')
            svg.rect(x,y+ch-60,cw,60,fill='#9CC4C1',stroke='none',rx=0)
            svg.text(x+18,y+ch-25,c.get('label','Transporter'),size=14,anchor='start',fill='white')
            svg.circle(x+cw-20,y+ch-30,34,fill='#F5F5F5',stroke='#9CC4C1',sw=1.2)
            svg.text(x+cw-20,y+ch-26,c.get('icon','◌'),size=18,fill='#6F9794')
        return svg.to_string()
    cols=cfg.get('columns',[
      {'title':'Data Preparation & Processing','color':'#FFE699','groups':[('Model Constructing',['Network','Single G-T-I-D','Data correlation','Adjacency matrix','G']),('Priority / Dynamics',['Priority Selection','System Dynamics','Row Parameter','score','Method'])]},
      {'title':'Application of the model','color':'#F8CBAD','groups':[('Network in Different regions',['Network / Priority Selection']),('Correction in different cases',['SDG implementation','International Opportunities/crises','One-way impact','Can be achieved','G’=G+cΔ','Impact on UN'])]},
    ])
    xcols=[155,500]; widths=[300,300]
    for ci,c in enumerate(cols):
        x=xcols[ci]; w=widths[ci]
        svg.rect(x,55,w,405,fill='#fff',stroke='#2E75B6' if ci==0 else '#C5590F',dash='8 5',rx=0)
        node(svg,x+20,72,w-40,38,c.get('title',''),fill=c.get('color','#D9EAD3'),stroke='none',size=11,weight='bold')
        if ci==0:
            groups=c.get('groups',[]); gy=130
            for gi,(gtitle,items) in enumerate(groups):
                node(svg,x+25,gy,w-50,32,gtitle,fill='#2E75B6' if gi==0 else '#8FAADC',stroke='none',size=9.5,text_fill='#fff')
                for j,it in enumerate(items): node(svg,x+30+(j%2)*125,gy+48+(j//2)*48,110,32,it,fill='#9DC3E6',stroke='none',size=7.5)
                gy+=190
        else:
            groups=c.get('groups',[]); gy=130
            for gi,(gtitle,items) in enumerate(groups):
                node(svg,x+25,gy,w-50,34,gtitle,fill='#F8CBAD' if gi==0 else '#A9D18E',stroke='none',size=8.8,text_fill='#fff' if gi==0 else '#234')
                for j,it in enumerate(items): node(svg,x+32+(j%2)*120,gy+50+(j//2)*48,105,32,it,fill='#C5E0B4',stroke='none',size=7.4)
                gy+=125 if gi==0 else 200
    node(svg,285,475,390,36,cfg.get('footer','Promote to other organizations'),fill='#A5A5A5',stroke='none',size=10,text_fill='#fff')
    return svg.to_string()

def T08(cfg):
    svg=SVG(); header(svg,cfg.get('title','Task chain workflow'))
    node(svg,8,196,65,70,cfg.get('left_input','Given\nData'),fill='#65CFC1',stroke='none',size=10,weight='bold')
    node(svg,8,310,65,60,cfg.get('left_team','Team'),fill='#65CFC1',stroke='none',size=10,weight='bold')
    node(svg,895,196,58,90,cfg.get('right_output','Target\nand\nAction'),fill='#6FD6CE',stroke='none',size=9.5,weight='bold')
    tasks=cfg.get('tasks',[
      {'title':'TASK 1 Network analysis','items':['Pass quality network','Dyadic Configurations','Triadic Configurations','Team formation','Time and Space']},
      {'title':'TASK 2 Performance indicators','items':['Indicators determine','Quantification','TOPSIS + AHP','3D dynamic model']},
      {'title':'TASK 3 Team formation & Training','items':['Formation utilization','Effective formations','Five success measures']},
      {'title':'TASK 4 Good social team','items':['Obtained indicators','Additional indicators']},
    ])
    x0=92; y0=130; totalw=790; gap=8; n=len(tasks); tw=(totalw-gap*(n-1))/n
    for i,t in enumerate(tasks):
        x=x0+i*(tw+gap); svg.rect(x,y0,tw,290,fill='#fff',stroke='#8497B0',dash='6 4',rx=0)
        svg.text_box(x+6,y0+8,tw-12,38,t.get('title',''),size=9,fill='#278A78',weight='bold')
        items=t.get('items',[]); iy=y0+60; ih=min(43,(330-iy+y0)/max(1,len(items)))
        for j,it in enumerate(items):
            node(svg,x+18,iy+j*(ih+10),tw-36,ih,it,fill='#FFFFFF',stroke='#767171',size=7.7,rx=0)
            if j<len(items)-1: arrow(svg,x+tw/2,iy+j*(ih+10)+ih,x+tw/2,iy+(j+1)*(ih+10)-2,color='#ACACAC',sw=1)
        if i<n-1: arrow(svg,x+tw,y0+145,x+tw+gap-2,y0+145,color='#8497B0')
    arrow(svg,73,230,x0,230); arrow(svg,x0+totalw,230,895,230)
    return svg.to_string()


def T09(cfg):
    svg=SVG(); header(svg,cfg.get('title','Supervision system'))
    svg.rect(65,95,830,330,fill='#fff',stroke='#000',sw=1.5,dash='7 5',rx=0)
    svg.path('M840 348V310H98V235H840V197L920 273Z',fill='#00B050',stroke='none',opacity=.16)
    svg.path('M840 236V198H98V122H840V84L920 160Z',fill='#D68081',stroke='none',opacity=.28)
    headers=cfg.get('headers',['Appearance factors','Supervision system','Operation'])
    for x,t in zip([140,440,740],headers): svg.text(x,122,t,size=14,fill='#1E386B',weight='bold')
    svg.text(135,205,cfg.get('abnormal_symbol','T_wait'),size=28,italic=True)
    svg.text(135,345,cfg.get('normal_symbol','A_i'),size=28,italic=True)
    ab=cfg.get('abnormal',['At least one abnormal','Warning / Analyze data','Coordinate personnel assignments','Reasonable site planning'])
    xs=[220,360,575,748]; ws=[115,180,160,135]
    for i,t in enumerate(ab): node(svg,xs[i],160,ws[i],82,t,fill='none',stroke='#FF0000',size=10,rx=0,dash='6 4')
    no=cfg.get('normal',['All normal','Pass','Continue monitoring']); xs2=[220,390,615]; ws2=[115,160,245]
    for i,t in enumerate(no): node(svg,xs2[i],300,ws2[i],70,t,fill='none',stroke='#548235',size=11,rx=0,dash='6 4')
    svg.text(12,270,'Feedback',size=11,anchor='start',fill='#FF0000',weight='bold')
    elbow(svg,[(65,245),(25,245),(25,335),(65,335)],color='#548235',marker='arrowGreen',sw=2)
    return svg.to_string()


def T10(cfg):
    svg=SVG(); header(svg,cfg.get('title','Feature taxonomy matrix'))
    columns=cfg.get('columns',['Pop/Rock','R&B','Jazz'])
    row_groups=cfg.get('rows',[
      {'label':'Retention','color':'#2E75B6','features':['danceability','energy','valence','tempo']},
      {'label':'Synthesis by PCA','color':'#E37C79','features':['loudness','mode','acousticness','key','instrumentalness']},
      {'label':'Rejection by correlation analysis','color':'#70AD47','features':['liveness','speechiness','explicit']},
    ])
    x0=245; right=890; colw=(right-x0)/max(1,len(columns))
    for i,c in enumerate(columns): svg.text(x0+i*colw+colw/2,72,c,size=13,fill='#333',weight='bold')
    y=95
    heights=[120,150,110]
    for r,row in enumerate(row_groups):
        hh=heights[r] if r<len(heights) else 120
        svg.rect(70,y,820,hh,fill=_lighten(row.get('color','#999'),.88),stroke=row.get('color','#999'),dash='7 5',rx=0)
        svg.text_box(82,y+15,150,hh-30,row.get('label',''),size=15,fill=row.get('color','#999'),weight='bold',anchor='middle')
        feats=row.get('features',[])
        for c in range(len(columns)):
            for j,f in enumerate(feats): svg.text(x0+c*colw+colw/2,y+26+j*20,f,size=9)
        y+=hh+15
    return svg.to_string()


def T11(cfg):
    svg=SVG(); header(svg,cfg.get('title','D&A system capability map'))
    cx,cy=480,290
    outer=cfg.get('outer',['Educational background','Collection efficiency','Response speed','Storage','Position','Process visualization','Process reengineering','Process coverage','Number of people','IT capability','Cost'])
    inner=cfg.get('inner',['People','Technologies','Process'])
    outer_col=cfg.get('outer_color','#2CA2BE'); inner_col=cfg.get('inner_color','#517293'); center_col=cfg.get('center_color','#DD7195')
    n=len(outer); r1=138; r2=205
    for i,t in enumerate(outer):
        a0=-math.pi/2+i*2*math.pi/n; a1=-math.pi/2+(i+1)*2*math.pi/n
        p1=(cx+r1*math.cos(a0),cy+r1*math.sin(a0)); p2=(cx+r2*math.cos(a0),cy+r2*math.sin(a0)); p3=(cx+r2*math.cos(a1),cy+r2*math.sin(a1)); p4=(cx+r1*math.cos(a1),cy+r1*math.sin(a1))
        d=f'M {p1[0]} {p1[1]} L {p2[0]} {p2[1]} A {r2} {r2} 0 0 1 {p3[0]} {p3[1]} L {p4[0]} {p4[1]} A {r1} {r1} 0 0 0 {p1[0]} {p1[1]} Z'
        svg.path(d,fill=outer_col,stroke='white',sw=3)
        am=(a0+a1)/2; tx=cx+171*math.cos(am); ty=cy+171*math.sin(am)
        svg.text_box(tx-43,ty-20,86,40,t,size=8,fill='white')
    r0=72; r1i=135; m=len(inner)
    for i,t in enumerate(inner):
        a0=-math.pi/2+i*2*math.pi/m; a1=-math.pi/2+(i+1)*2*math.pi/m
        p1=(cx+r0*math.cos(a0),cy+r0*math.sin(a0)); p2=(cx+r1i*math.cos(a0),cy+r1i*math.sin(a0)); p3=(cx+r1i*math.cos(a1),cy+r1i*math.sin(a1)); p4=(cx+r0*math.cos(a1),cy+r0*math.sin(a1))
        d=f'M {p1[0]} {p1[1]} L {p2[0]} {p2[1]} A {r1i} {r1i} 0 0 1 {p3[0]} {p3[1]} L {p4[0]} {p4[1]} A {r0} {r0} 0 0 0 {p1[0]} {p1[1]} Z'
        svg.path(d,fill=inner_col,stroke='white',sw=3)
        am=(a0+a1)/2; svg.text(cx+105*math.cos(am),cy+105*math.sin(am),t,size=13,fill='white',weight='bold',rotate=math.degrees(am)+90)
    svg.circle(cx,cy,68,fill=center_col,stroke='white',sw=4); svg.text_box(cx-55,cy-40,110,80,cfg.get('center','D&A\nsystem'),size=18,fill='white',weight='bold')
    return svg.to_string()


def T12(cfg):
    mode=cfg.get('mode','inset'); svg=SVG(); header(svg,cfg.get('title','Network views'))
    random.seed(int(cfg.get('seed',7)))
    if mode=='hierarchy':
        cx,cy=260,300
        for i in range(80):
            ang=2*math.pi*i/80; rr=150*(.12+.88*(i%13)/13); ex=cx+rr*math.cos(ang); ey=cy+rr*math.sin(ang)
            svg.path(f'M {cx} {cy} Q {(cx+ex)/2+40*math.sin(ang)} {(cy+ey)/2-30*math.cos(ang)} {ex} {ey}',stroke='#9CC4DE',sw=.8,opacity=.35)
        for i in range(15):
            a=2*math.pi*i/15; svg.circle(cx+160*math.cos(a),cy+160*math.sin(a),5,fill='#6D9FC8',stroke='none')
        pts=[(670,440),(850,440),(760,120)]; svg.polygon(pts,fill='#E8F1F8',stroke='#5B8BB4',sw=1.6)
        for y in [335,255]:
            f=(440-y)/(440-120); lx=670+(760-670)*f; rx=850+(760-850)*f; svg.line(lx,y,rx,y,stroke='#5B8BB4')
        svg.text(760,415,cfg.get('level1','400 Person'),size=12,fill='#3F65A8'); svg.text(760,320,cfg.get('level2','7 Person'),size=12,fill='#3F65A8'); svg.text(760,220,cfg.get('level3','Top Artist'),size=11,fill='#3F65A8')
        svg.path('M450 215 C520 180 565 180 625 220',stroke='#5B8BB4',sw=5,opacity=.8); svg.path('M450 390 C520 430 565 430 625 392',stroke='#5B8BB4',sw=5,opacity=.8)
    else:
        cx,cy=300,300; nodes=[]; n=int(cfg.get('nodes',55))
        for i in range(n):
            a=2*math.pi*i/n; rr=150*(.55+.45*random.random()); nodes.append((cx+rr*math.cos(a),cy+rr*math.sin(a),5+6*random.random()))
        inner=[(cx+random.uniform(-90,90),cy+random.uniform(-90,90),4+4*random.random()) for _ in range(18)]; alln=nodes+inner
        for i in range(len(alln)):
            for j in range(i+1,min(i+12,len(alln))):
                if random.random()<.19: svg.line(alln[i][0],alln[i][1],alln[j][0],alln[j][1],stroke='#68ACD5',sw=.8,opacity=.35)
        for x,y,r in alln: svg.circle(x,y,r,fill='#AACFE5',stroke='#5C8DB7',sw=.8)
        svg.rect(590,120,300,160,fill='#fff',stroke='#2A8E83',dash='8 5',rx=0)
        small=[(630+(i%4)*60,155+(i//4)*55) for i in range(8)]
        for i,(x,y) in enumerate(small):
            svg.circle(x,y,5,fill='#AACFE5',stroke='#5C8DB7')
            if i>0: svg.line(small[i-1][0],small[i-1][1],x,y,stroke='#68ACD5',sw=1)
        svg.path('M430 175 C520 160 545 155 590 165',stroke='#2A8E83',sw=1.5,dash='5 4'); svg.path('M430 375 C520 360 545 245 590 240',stroke='#2A8E83',sw=1.5,dash='5 4')
        svg.text(740,302,cfg.get('detail_label','Detailed Structure'),size=12,weight='bold')
        levels=cfg.get('legend',['[0,2.0]','[2.0,4.0]','[4.0,6.0]','[6.0,8.0]','[8.0,10.0]'])
        for i,t in enumerate(levels): svg.rect(650,335+i*28,28,18,fill=['#EBEBF4','#D3E5F1','#9AC4DE','#7DB3D5','#4F96C7'][i],stroke='#555',rx=0); svg.text(688,349+i*28,t,size=8,anchor='start')
    return svg.to_string()


def T13(cfg):
    svg=SVG(); header(svg,cfg.get('title','Trend ribbon timeline'))
    path=cfg.get('path','M110 330 C220 250 310 270 390 320 C500 385 590 245 685 230 C770 215 820 245 880 180')
    svg.path(path,stroke='#6F8FC5',sw=14,opacity=.18); svg.path(path,stroke='#6F8FC5',sw=1.5,opacity=.75)
    items=cfg.get('items',[
      ['1960-1971','Moody Blues',120,350],['1963-1971','The Beatles',205,285],['1965-1967','The Byrds',300,375],['1969-1982','Led Zeppelin',350,235],['1972-1980','Eagles',455,390],['1975-1989','Rush',500,240],['1973-1992','Queen',600,360],['2000-2007','Linkin Park',670,230],['2010-2016','Rihanna',785,175],['2006-2019','Taylor Swift',850,330]
    ])
    for yr,name,x,y in items:
        svg.circle(x,y,4,fill='#3F65A8',stroke='none'); svg.text_box(x-42,y+7,84,64,f'{yr}\n{name}',size=9,fill='#111')
    return svg.to_string()


def T14(cfg):
    svg=SVG(); header(svg,cfg.get('title','Queue process'))
    svg.rect(50,60,860,410,fill='#fff',stroke='#5B79A6',dash='7 5',rx=0)
    stages=cfg.get('stages',['Input process','Queue through customs','Through customs','Waiting for unloading','Discharge container'])
    cols=cfg.get('stage_colors',['#7097A6','#7097A6','#7DA2B1','#D68081','#C6A477'])
    x0=85; avail=770; n=len(stages); gap=8; sw=(avail-gap*(n-1))/n
    for i,t in enumerate(stages):
        x=x0+i*(sw+gap); svg.rect(x,100,sw,310,fill='#fff',stroke='#111',dash='6 4',rx=0); svg.text_box(x+3,242,sw-6,65,t,size=12,weight='bold')
        # icon grid
        for r in range(3):
            for c in range(2):
                px=x+15+c*(sw-35); py=130+r*77
                svg.polygon([(px,py+14),(px+10,py),(px+20,py+14)],fill=cols[i%len(cols)],stroke='none'); svg.rect(px+2,py+14,16,15,fill=cols[i%len(cols)],stroke='none',rx=0)
        if i<n-1: arrow(svg,x+sw,255,x+sw+gap-1,255,color='#666')
    svg.text(220,90,'Queue 1',size=15,weight='bold'); svg.text(535,90,'Queue 2',size=15,weight='bold')
    node(svg,870,220,70,55,cfg.get('output','Process'),fill='#D4E7EE',stroke='none',size=13,weight='bold',text_fill='#E44')
    return svg.to_string()


def T15(cfg):
    svg=SVG(); header(svg,cfg.get('title','Paired comparison'))
    mode=cfg.get('mode','paired')
    if mode=='impact_scale':
        levels=cfg.get('levels',[
          [3,'Indivisible','Greatly facilitating the impact on another goal'],[2,'Reinforcing','Help achieve another goal'],[1,'Enabling','Create conditions for further achievement'],[0,'Consistent','No significant positive or negative interactions'],[-1,'Constraining','Limits options on another goal'],[-2,'Counteracting','Clashes with another goal'],[-3,'Cancelling','Seriously impeding achievement']
        ])
        xs=[90,215,340,480,610,735,860]; cols=['#5FA9C5','#92C7D9','#C8E2EA','#000000','#F3C6B7','#EEA590','#E77D6B']
        svg.line(55,280,910,280,stroke='#697784',sw=2)
        for i,(val,name,desc) in enumerate(levels):
            x=xs[i]; h=45+abs(val)*20 if val!=0 else 58; y=280-h if val>0 else 280
            svg.rect(x-22,y,44,h,fill=cols[i],stroke='none',rx=0)
            svg.text(x, y+30 if val>0 else y+35, f'{val:+d}' if val else '0', size=18, fill='white' if i in (0,1,3,5,6) else '#111',weight='bold')
            svg.text_box(x-55,165 if val>=0 else 300,110,50,name,size=11,fill='#2E75B6' if val>0 else '#C55A34' if val<0 else '#111',weight='bold')
            svg.text_box(x-62,345 if val<0 else 320 if val>0 else 155,124,120,desc,size=8,italic=True)
        return svg.to_string()
    if mode=='ranking':
        labels=cfg.get('labels',[f'Item {i+1}' for i in range(12)]); vals=cfg.get('values',[.95,.88,.82,.76,.70,.65,.59,.54,.47,.40,.33,.25]); col=cfg.get('bar_color','#63C6A7')
        order=sorted(zip(labels,vals),key=lambda x:x[1],reverse=True)
        x0=230; y0=75; rowh=min(34,420/max(1,len(order)))
        for i,(lab,v) in enumerate(order):
            y=y0+i*rowh; svg.text(x0-12,y+rowh*.65,lab,size=9,anchor='end'); svg.rect(x0,y+5,600, max(8,rowh-10),fill='#F3F3F3',stroke='none',rx=0); svg.rect(x0,y+5,600*float(v),max(8,rowh-10),fill=col,stroke='none',rx=0); svg.text(x0+600*float(v)+6,y+rowh*.65,f'{float(v):.3f}',size=8,anchor='start')
        svg.line(x0,505,x0+600,505,stroke='#777',sw=1)
        return svg.to_string()
    if mode=='polar_pair':
        vals1=cfg.get('left_values',[.7,.5,.4,.8,.6,.5,.3,.7,.8,.6,.4,.5,.7,.6,.5,.4,.8]); vals2=cfg.get('right_values',[.6,.6,.5,.7,.8,.4,.5,.6,.7,.8,.6,.5,.8,.7,.6,.5,.7]); labels=cfg.get('labels',[f'{i+1}' for i in range(max(len(vals1),len(vals2)))])
        for ci,(cx,vals,ttl) in enumerate([(300,vals1,cfg.get('left_title','Before')), (670,vals2,cfg.get('right_title','After'))]):
            cy=285; n=len(vals); r0=40; maxr=145
            for i,v in enumerate(vals):
                a0=-math.pi/2+i*2*math.pi/n; a1=a0+2*math.pi/n*.72; rr=r0+(maxr-r0)*float(v)
                p1=(cx+r0*math.cos(a0),cy+r0*math.sin(a0)); p2=(cx+rr*math.cos(a0),cy+rr*math.sin(a0)); p3=(cx+rr*math.cos(a1),cy+rr*math.sin(a1)); p4=(cx+r0*math.cos(a1),cy+r0*math.sin(a1)); d=f'M{p1[0]} {p1[1]}L{p2[0]} {p2[1]}A{rr} {rr} 0 0 1 {p3[0]} {p3[1]}L{p4[0]} {p4[1]}A{r0} {r0} 0 0 0 {p1[0]} {p1[1]}Z'; svg.path(d,fill='#2CA2BE',stroke='white',sw=.8)
                am=(a0+a1)/2; svg.text(cx+(maxr+18)*math.cos(am),cy+(maxr+18)*math.sin(am),labels[i] if i<len(labels) else str(i+1),size=6)
            svg.circle(cx,cy,r0-3,fill='#F4F4F4',stroke='#AAA',sw=.8); svg.text(cx,cy+4,ttl,size=10,weight='bold')
        return svg.to_string()
    labels=cfg.get('labels',['Maturity','People','Technology','Process','Efficiency'])
    left=cfg.get('left',[.43,.58,.40,.49,.30]); right=cfg.get('right',[.71,.68,.81,.76,.65])
    left_name=cfg.get('left_name','Original'); right_name=cfg.get('right_name','Changed')
    lc=cfg.get('left_color','#02489D'); rc=cfg.get('right_color','#568036')
    svg.text(270,120,left_name,size=18,weight='bold'); svg.text(480,105,cfg.get('center_label','D&A'),size=16,weight='bold'); svg.text(690,120,right_name,size=18,weight='bold')
    barw=190
    for i,l in enumerate(labels):
        y=155+i*58
        svg.rect(110,y,barw,26,fill='#F5F5F5',stroke='none',rx=0); svg.rect(110+barw*(1-left[i]),y,barw*left[i],26,fill=lc,stroke='none',rx=0)
        svg.text(105+barw,y+18,f'{left[i]:.2f}'.rstrip('0').rstrip('.'),size=9,fill='white',anchor='end')
        svg.text(480,y+18,l,size=12,weight='bold')
        svg.rect(660,y,barw,26,fill='#F5F5F5',stroke='none',rx=0); svg.rect(660,y,barw*right[i],26,fill=rc,stroke='none',rx=0)
        svg.text(665+barw*right[i]-5,y+18,f'{right[i]:.2f}'.rstrip('0').rstrip('.'),size=9,fill='white',anchor='end')
    return svg.to_string()

def T16(cfg):
    svg=SVG(); header(svg,cfg.get('title','Radial bubble relationship model'))
    center=cfg.get('center','Maturity'); core=cfg.get('core',[['People',470,175,'#77DED4'],['Process',350,315,'#77DED4'],['Technology',610,315,'#77DED4']])
    outer=cfg.get('outer',[['Personal',350,115],['Team',600,90],['Convenience',770,235],['Accuracy',750,390],['Security',620,455],['Data surplus',255,425],['Processing efficiency',210,250]])
    cx,cy=480,285
    # edges behind
    for name,x,y,col in core: svg.line(cx,cy,x,y,stroke='#AFC0DD',sw=15,opacity=.75)
    edge_map={'People':['Personal','Team'],'Process':['Data surplus','Processing efficiency'],'Technology':['Convenience','Accuracy','Security']}
    loc={n:(x,y) for n,x,y in outer}; coreloc={n:(x,y) for n,x,y,c in core}
    for c,outs in edge_map.items():
        if c in coreloc:
            for o in outs:
                if o in loc: svg.line(coreloc[c][0],coreloc[c][1],loc[o][0],loc[o][1],stroke='#B9C8DF',sw=12,opacity=.6)
    svg.circle(cx,cy,47,fill='#91A6E0',stroke='#6E83C0',sw=1.2,shadow=False); svg.text_box(cx-42,cy-25,84,50,center,size=13,weight='bold')
    for name,x,y,col in core: svg.circle(x,y,38,fill=col,stroke='#57BDB5',sw=1.0,shadow=False); svg.text_box(x-34,y-22,68,44,name,size=10,weight='bold')
    for name,x,y in outer: svg.circle(x,y,40,fill='#D4E6F0',stroke='#B9CBD7',sw=1,shadow=False); svg.text_box(x-35,y-28,70,56,name,size=9)
    return svg.to_string()


def _cube(svg,x,y,s,dx=55,dy=-38,fill='#FFF2CC',stroke='#FFC000',opacity=.35):
    A=(x,y); B=(x+s,y); C=(x+s,y+s); D=(x,y+s); A2=(x+dx,y+dy); B2=(x+s+dx,y+dy); C2=(x+s+dx,y+s+dy); D2=(x+dx,y+s+dy)
    svg.polygon([A,B,C,D],fill=fill,stroke=stroke,opacity=opacity); svg.polygon([A2,B2,C2,D2],fill=fill,stroke=stroke,opacity=opacity)
    for p,q in [(A,A2),(B,B2),(C,C2),(D,D2)]: svg.line(p[0],p[1],q[0],q[1],stroke=stroke,sw=1)
    return (A,B,C,D,A2,B2,C2,D2)


def T17(cfg):
    svg=SVG(); header(svg,cfg.get('title','3D decision space'))
    mode=cfg.get('mode','layers')
    if mode=='triangle':
        A=(480,75); B=(820,455); C=(140,455); O=(480,330)
        svg.polygon([A,B,C],fill='#FFFFFF',stroke='#777',sw=1.2,opacity=1)
        svg.polygon([O,A,C],fill='#D9F0EC',stroke='none',opacity=.8); svg.polygon([O,A,B],fill='#F1F2FA',stroke='none',opacity=.8); svg.polygon([O,B,C],fill='#E9EFF8',stroke='none',opacity=.8)
        for P in [A,B,C]: svg.line(O[0],O[1],P[0],P[1],stroke='#111',sw=1.6)
        svg.circle(O[0],O[1],14,fill='#FFFFFF',stroke='#111',sw=1.2)
        labs=cfg.get('vertices',['b','a','c']); svg.text(A[0],A[1]-12,labs[0],size=14,weight='bold'); svg.text(B[0]+12,B[1]+5,labs[1],size=14,weight='bold'); svg.text(C[0]-12,C[1]+5,labs[2],size=14,weight='bold')
        areas=cfg.get('areas',['Area1','Area2','Area3']); svg.text(265,275,areas[0],size=14,italic=True); svg.text(480,490,areas[1],size=14,italic=True); svg.text(700,275,areas[2],size=14,italic=True)
        svg.text(400,300,'1',size=16,weight='bold'); svg.text(480,390,'2',size=16,weight='bold'); svg.text(560,300,'3',size=16,weight='bold')
        return svg.to_string()
    if mode=='ternary_scatter':
        A=(480,70); B=(820,465); C=(140,465); svg.polygon([A,B,C],fill='#fff',stroke='#111',sw=1.5)
        # grid by interpolation
        for k in range(1,5):
            t=k/5
            svg.line(C[0]+(A[0]-C[0])*t,C[1]+(A[1]-C[1])*t,B[0]+(A[0]-B[0])*t,B[1]+(A[1]-B[1])*t,stroke='#CFCFCF',sw=.8,dash='4 4')
            svg.line(A[0]+(B[0]-A[0])*t,A[1]+(B[1]-A[1])*t,C[0]+(B[0]-C[0])*t,C[1]+(B[1]-C[1])*t,stroke='#CFCFCF',sw=.8,dash='4 4')
            svg.line(A[0]+(C[0]-A[0])*t,A[1]+(C[1]-A[1])*t,B[0]+(C[0]-B[0])*t,B[1]+(C[1]-B[1])*t,stroke='#CFCFCF',sw=.8,dash='4 4')
        random.seed(int(cfg.get('seed',6)))
        groups=cfg.get('groups',[{'n':18,'center':[.72,.18,.10],'color':'#111','shape':'square'},{'n':18,'center':[.15,.70,.15],'color':'#111','shape':'circle'}])
        for gi,g in enumerate(groups):
            ca,cb,cc=g.get('center',[.33,.33,.34]);
            for _ in range(int(g.get('n',15))):
                aa=max(.02,ca+random.uniform(-.08,.08)); bb=max(.02,cb+random.uniform(-.08,.08)); cc2=max(.02,1-aa-bb); sm=aa+bb+cc2; aa/=sm; bb/=sm; cc2/=sm
                x=aa*A[0]+bb*B[0]+cc2*C[0]; y=aa*A[1]+bb*B[1]+cc2*C[1]
                if g.get('shape')=='square': svg.rect(x-3,y-3,6,6,fill=g.get('color','#111'),stroke='none',rx=0)
                else: svg.circle(x,y,3.2,fill=g.get('color','#111'),stroke='none')
        svg.text(480,500,cfg.get('axis_bottom','Component A'),size=11); svg.text(105,300,cfg.get('axis_left','Component B'),size=11,rotate=-60); svg.text(850,300,cfg.get('axis_right','Component C'),size=11,rotate=60)
        return svg.to_string()
    if mode=='scatter3d':
        # isometric 3D box with two point classes
        x0,y0=160,390; sx,sy=560,0; dx,dy=120,-85; vz=-260
        svg.line(x0,y0,x0+sx,y0+sy,stroke='#111'); svg.line(x0,y0,x0+dx,y0+dy,stroke='#111'); svg.line(x0,y0,x0,y0+vz,stroke='#111')
        svg.line(x0+dx,y0+dy,x0+sx+dx,y0+dy,stroke='#777',dash='4 3'); svg.line(x0+sx,y0,x0+sx+dx,y0+dy,stroke='#777',dash='4 3'); svg.line(x0,y0+vz,x0+dx,y0+dy+vz,stroke='#777',dash='4 3'); svg.line(x0+dx,y0+dy+vz,x0+sx+dx,y0+dy+vz,stroke='#777',dash='4 3'); svg.line(x0+sx+dx,y0+dy,x0+sx+dx,y0+dy+vz,stroke='#777',dash='4 3')
        random.seed(int(cfg.get('seed',3)))
        for cls,col,center in [(0,'#1747F0',(.25,.25,.55)),(1,'#E11E2C',(.70,.58,.10))]:
            for _ in range(int(cfg.get('n_per_class',35))):
                a=max(0,min(1,center[0]+random.uniform(-.16,.16))); b=max(0,min(1,center[1]+random.uniform(-.18,.18))); c=max(0,min(1,center[2]+random.uniform(-.10,.10)))
                x=x0+a*sx+b*dx; y=y0+b*dy+c*vz; svg.circle(x,y,3.2,fill=col,stroke='none')
        svg.text(760,430,cfg.get('x_label','PbO+BaO'),size=10); svg.text(130,330,cfg.get('y_label','SiO₂'),size=10,rotate=-30); svg.text(120,120,cfg.get('z_label','K₂O'),size=10)
        return svg.to_string()
    if mode=='rays':
        _cube(svg,245,160,230,55,-40,fill='#E2F0D9',stroke='#4472C4',opacity=.32); ox,oy=330,325
        random.seed(int(cfg.get('seed',8))); count=int(cfg.get('rays',34)); col=cfg.get('ray_color','#F06C8C')
        for _ in range(count):
            ex=ox+random.uniform(-85,140); ey=oy+random.uniform(-150,90); svg.line(ox,oy,ex,ey,stroke=col,sw=1.2,marker='arrowRed',opacity=.8); svg.circle(ex,ey,3,fill=col,stroke='none')
        axes=cfg.get('axes',['Convenience','Accuracy','Security']); svg.text(205,445,axes[0],size=12); svg.text(560,335,axes[1],size=12); svg.text(245,105,axes[2],size=12)
    else:
        _cube(svg,120,165,210,55,-40); _cube(svg,560,110,150,45,-33); _cube(svg,560,330,150,45,-33,stroke='#E36A6A')
        svg.text(420,175,cfg.get('upper_label','Upper layer'),size=15,weight='bold'); arrow(svg,380,180,545,180)
        svg.text(420,390,cfg.get('lower_label','Lower layer'),size=15,weight='bold'); arrow(svg,380,395,545,395)
        axes=cfg.get('axes',['Convenience','Accuracy','Security']); svg.text(95,440,axes[0],size=13); svg.text(355,350,axes[1],size=13); svg.text(120,105,axes[2],size=13)
    return svg.to_string()

def T18(cfg):
    svg=SVG(); header(svg,cfg.get('title','Goal pathway network'))
    mode=cfg.get('mode','pathway')
    if mode=='matrix':
        rows=cfg.get('rows',[
          {'color':'#E5243B','items':['1','2','13'],'count':3},
          {'color':'#F36D25','items':['3','6','8','9','10','14','15'],'count':7},
          {'color':'#F9C900','items':['4','5','7','11','12','16','17'],'count':7},
          {'color':'#E98AA5','items':[],'count':0},
        ])
        y=105
        for r,row in enumerate(rows):
            col=row.get('color','#999'); svg.rect(80,y,790,72,fill=_lighten(col,.90),stroke='none',rx=0)
            svg.circle(42,y+36,5,fill=col,stroke='none')
            items=row.get('items',[]); x=110
            for code in items:
                svg.rect(x,y+10,58,52,fill=col,stroke='none',rx=0); svg.text(x+29,y+31,f'G{code}',size=10,fill='white',weight='bold'); svg.text(x+29,y+49,'GOAL',size=6,fill='white'); x+=66
            svg.text(905,y+48,str(row.get('count',len(items))),size=30,fill=_darken(col,.1),anchor='middle')
            y+=90
        return svg.to_string()
    goals=cfg.get('goals',[
      ['SDG 13','Climate Action'],['SDG 1','No Poverty'],['SDG 2','Zero Hunger'],['SDG 5','Gender Equality'],['SDG 12','Responsible Consumption'],['SDG 4','Quality Education'],['SDG 10','Reduced Inequality'],['SDG 3','Good Health'],['SDG 9','Industry & Infrastructure'],['SDG 8','Decent Work'],['SDG 16','Peace & Justice'],['SDG 17','Partnerships'],['SDG 6','Clean Water'],['SDG 7','Clean Energy'],['SDG 14','Life Below Water'],['SDG 11','Sustainable Cities'],['SDG 15','Life on Land']
    ])
    # auto snake grid 5 columns
    cols=5; x0=85; y0=90; cw=165; rh=105
    coords=[]
    for i,g in enumerate(goals):
        r=i//cols; c=i%cols
        if r%2==1: c=cols-1-c
        x=x0+c*cw; y=y0+r*rh; coords.append((x,y))
        svg.text_box(x-55,y-35,110,30,g[1],size=7.5)
        # capsule with two-tone
        svg.rect(x-48,y,96,26,fill='#64C6C0',stroke='none',rx=13,shadow=True); svg.rect(x-48,y,54,26,fill='#D8A900',stroke='none',rx=13); svg.text(x,y+18,g[0],size=9,fill='white',weight='bold')
    for i in range(len(coords)-1):
        x1,y1=coords[i]; x2,y2=coords[i+1]; elbow(svg,[(x1+50,y1+13),((x1+x2)/2,y1+13),((x1+x2)/2,y2+13),(x2-50,y2+13)],color='#CFCFCF',marker='arrow',sw=1.8)
    svg.text(480,505,cfg.get('footer','Ultimately improving the lives of many people around the world'),size=12,italic=True,fill='#555')
    return svg.to_string()

def T19(cfg):
    svg=SVG(); header(svg,cfg.get('title','LSTM network architecture'))
    layers=cfg.get('layers',['SequenceInputLayer','LstmLayer','DropoutLayer','FullyConnectedLayer','RegressionLayer'])
    colors=cfg.get('colors',['#D2E3F3','#AACFE5','#68ACD5','#3888C0','#105CA4'])
    x0=20; y=70; gap=13; bw=(760-gap*(len(layers)-1))/len(layers)
    for i,t in enumerate(layers):
        node(svg,x0+i*(bw+gap),y,bw,44,t,fill=colors[i%len(colors)],stroke='none',size=8.8,text_fill='#173A5E' if i<2 else '#fff')
        if i<len(layers)-1: arrow(svg,x0+i*(bw+gap)+bw,y+22,x0+(i+1)*(bw+gap)-2,y+22)
    # LSTM cell large box
    svg.rect(80,145,690,340,fill='#fff',stroke='#AACFE5',dash='7 5',rx=50)
    # horizontal state line
    svg.line(120,205,720,205,stroke='#4472C4',sw=1.4,marker='arrowBlue')
    # gates
    gates=[('Forget Gate',200,345),('Input Gate',400,345),('Output Gate',590,345)]
    for label,x,yy in gates:
        node(svg,x-55,yy,110,48,label,fill='#D2E3F3',stroke='#4472C4',size=8)
        svg.rect(x-15,yy-55,30,30,fill='#BEE59F',stroke='none',rx=15); svg.text(x,yy-35,'×',size=15)
        svg.line(x,yy-25,x,yy,stroke='#4472C4',sw=1.2,marker='arrowBlue')
    svg.circle(365,205,18,fill='#BEE59F',stroke='none'); svg.text(365,211,'+',size=16)
    svg.circle(490,260,18,fill='#BEE59F',stroke='none'); svg.text(490,266,'×',size=16)
    svg.circle(590,260,18,fill='#BEE59F',stroke='none'); svg.text(590,266,'tanh',size=7)
    # parameter table
    px=795; py=145; pw=145
    node(svg,px,py,pw,52,'Parameter Settings',fill='#5B77BF',stroke='none',size=10,text_fill='#fff',weight='bold',rx=0)
    params=cfg.get('params',[['Initial learning rate','0.005'],['Hidden units','2000'],['Dropout probability','0.2']])
    for i,(k,v) in enumerate(params):
        yy=py+52+i*82; svg.rect(px,yy,pw,82,fill='#D9E2F3',stroke='#fff',sw=1,rx=0); svg.text_box(px+5,yy+5,95,72,k,size=8); svg.text(px+120,yy+45,v,size=8)
    return svg.to_string()


def T20(cfg):
    svg=SVG(); header(svg,cfg.get('title','Milestone roadmap'))
    mode=cfg.get('mode','timeline')
    if mode=='arc_arrow':
        # broad descending arc, styled like page 35
        svg.path('M250 120 C430 140 420 390 250 430',stroke='#63AFA9',sw=42,opacity=.82)
        svg.polygon([(205,400),(305,445),(245,510)],fill='#71CFC8',stroke='#4B8D88',sw=1.5)
        labels=cfg.get('labels',['Level 1','Level 2','Level 3','Level 4','Level 5']); cols=['#E0F0D2','#C9E2DF','#A7CECB','#6EA7A1','#2F7772']
        for i,t in enumerate(labels):
            x=550+i*26; y=120+i*78; node(svg,x,y,220,46,t,fill=cols[i%len(cols)],stroke='none',size=11,weight='bold' if i==len(labels)-1 else 'normal')
            svg.line(360,y+23,x,y+23,stroke='#6EA7A1',sw=1,dash='6 4'); svg.circle(360,y+23,5,fill='#B7DAD5',stroke='white',sw=1)
        return svg.to_string()
    years=cfg.get('years',[str(y) for y in range(2024,2035)])
    x0=40; x1=920; y=78
    svg.line(x0,y,x1,y,stroke='#8AD9C7',sw=12)
    for i,yr in enumerate(years):
        x=x0+(x1-x0)*i/max(1,len(years)-1); svg.text(x,y-24,yr,size=9,fill='#385E8E'); svg.circle(x,y,7,fill='#FFFFFF' if i%2==0 else '#7DA3C9',stroke='#8AD9C7',sw=1)
    items=cfg.get('items',[
      {'text':'People have equitable access to safe drinking water','start':.10,'end':.67,'color':'#B2DEDD'},
      {'text':'Restore degraded forests, lands and soils','start':.12,'end':.65,'color':'#C3D2EC'},
      {'text':'Increase the share of renewable energy in the global energy mix','start':.02,'end':.86,'color':'#C3E0E6'},
      {'text':'Marine waste pollution and nutrient salt pollution disappeared','start':.22,'end':.95,'color':'#8CD9C9'},
      {'text':'Sustainable management and efficient use of natural resources','start':.13,'end':.87,'color':'#AEC2E5'},
    ])
    yy=125
    step=min(54, 292/max(1,len(items)))
    h=max(24,min(38,step-6))
    for i,it in enumerate(items):
        xs=x0+(x1-x0)*it.get('start',0); xe=x0+(x1-x0)*it.get('end',1)
        pts=[(xs+18,yy),(xe,yy),(xe+22,yy+h/2),(xe,yy+h),(xs+18,yy+h),(xs,yy+h/2)]
        svg.polygon(pts,fill=it.get('color','#B2DEDD'),stroke='none',opacity=.96); svg.text_box(xs+18,yy+2,max(30,xe-xs-18),h-4,it.get('text',''),size=min(8,max(6.5,h*.26)),fill='#234')
        yy+=step
    fy=448; pts=[(40,fy),(875,fy),(920,fy+28),(875,fy+56),(40,fy+56),(0,fy+28)]
    svg.polygon(pts,fill='url(#tealGrad)',stroke='none'); svg.text_box(110,fy+6,720,44,cfg.get('footer','Goals to be achieved in 10 years'),size=16,fill='#111',weight='bold')
    return svg.to_string()


AUTO_RENDERERS={
 'T01_policy_timeline':T01,
 'T02_two_stage_pipeline':T02,
 'T03_composite_pipeline':T03,
 'T04_four_problem_panel':T04,
 'T05_dual_column_model':T05,
 'T06_literature_review_matrix':T06,
 'T07_three_phase_board':T07,
 'T08_task_chain':T08,
 'T09_supervision_state':T09,
 'T10_taxonomy_matrix':T10,
 'T11_donut_capability':T11,
 'T12_network_views':T12,
 'T13_trend_ribbon':T13,
 'T14_queue_process':T14,
 'T15_comparison_bars':T15,
 'T16_radial_bubble':T16,
 'T17_cube_ray':T17,
 'T18_sdg_network':T18,
 'T19_lstm_architecture':T19,
 'T20_milestone_timeline':T20,
}


def registry():
    return {x['id']:x for x in json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))}


def reference_path(template_id:str, exact=False)->Path:
    r=registry()[template_id]; page=int(r['reference_page'])
    sub='exact' if exact else 'editable'
    return ROOT/'references'/sub/f'slide-{page:02d}.svg'


def render(template_id:str, config:Dict[str,Any]|None=None, mode='auto', exact_reference=False)->str:
    config=config or {}
    if mode=='reference':
        return reference_path(template_id, exact=exact_reference).read_text(encoding='utf-8')
    if template_id not in AUTO_RENDERERS: raise KeyError(template_id)
    return AUTO_RENDERERS[template_id](config)


def save(template_id:str, out:Path|str, config:Dict[str,Any]|None=None, mode='auto', exact_reference=False):
    out=Path(out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(render(template_id,config,mode,exact_reference),encoding='utf-8'); return out


def render_from_json(config_path:Path|str,out:Path|str):
    d=json.loads(Path(config_path).read_text(encoding='utf-8')); tid=d.pop('template_id'); mode=d.pop('mode','auto'); return save(tid,out,d,mode=mode)

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--template',required=True); ap.add_argument('--config'); ap.add_argument('--mode',default='auto',choices=['auto','reference']); ap.add_argument('--out',required=True); ap.add_argument('--exact-reference',action='store_true')
    a=ap.parse_args(); cfg=json.loads(Path(a.config).read_text()) if a.config else {}; save(a.template,a.out,cfg,mode=a.mode,exact_reference=a.exact_reference)
