from __future__ import annotations
import re, math, html
from typing import Any, Dict, List, Tuple

PATH_RE = re.compile(r'<path\b[^>]*?/\s*>', re.S | re.I)


def _text(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get('text', v.get('value', '')))
    return str(v)


def _num(v: Any, default=None):
    try:
        return float(_text(v))
    except Exception:
        return default


def _esc(s: Any) -> str:
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')


def _patch_path_d(source: str, mapping: Dict[int, str]) -> str:
    if not mapping:
        return source
    patches=[]
    for idx,m in enumerate(PATH_RE.finditer(source)):
        if idx not in mapping:
            continue
        tag=m.group(0)
        new_d=mapping[idx]
        if re.search(r'\bd="[^"]*"', tag, re.S):
            new_tag=re.sub(r'\bd="[^"]*"', f'd="{new_d}"', tag, count=1, flags=re.S)
        else:
            new_tag=tag.replace('<path ', f'<path d="{new_d}" ', 1)
        patches.append((m.start(),m.end(),new_tag))
    out=source
    for s,e,repl in reversed(patches):
        out=out[:s]+repl+out[e:]
    return out


def _insert_layer(source: str, svg: str, layer_id='semantic-geometry-v9') -> str:
    if not svg:
        return source
    pos=source.lower().rfind('</svg>')
    if pos < 0:
        raise ValueError('Malformed SVG: closing </svg> not found')
    return source[:pos] + f'<g id="{layer_id}">{svg}</g>' + source[pos:]


def _wrap(text: str, max_chars: int) -> List[str]:
    paras=str(text).split('\n'); out=[]
    for p in paras:
        words=p.split()
        if not words:
            out.append(''); continue
        cur=''
        for w in words:
            if len(cur)+len(w)+(1 if cur else 0) <= max_chars:
                cur += (' ' if cur else '')+w
            else:
                if cur: out.append(cur)
                cur=w
        if cur: out.append(cur)
    return out or ['']


def _text_box(x,y,w,h,text,size=12,fill='#111',weight='normal',family='Arial, Liberation Sans, sans-serif',align='middle') -> str:
    size=float(size)
    while True:
        max_chars=max(3,int(w/max(3,size*.54)))
        lines=_wrap(str(text),max_chars)
        if max(len(z) for z in lines)*size*.54 <= w*.96 and len(lines)*size*1.15 <= h*.98:
            break
        size-=.35
        if size<=6.5:
            size=6.5; lines=_wrap(str(text),max(3,int(w/(size*.54)))); break
    if align=='start': tx=x+2
    elif align=='end': tx=x+w-2
    else: tx=x+w/2
    sy=y+h/2-(len(lines)-1)*size*.575+size*.33
    spans=''.join(f'<tspan x="{tx:.3f}" y="{(sy+i*size*1.15):.3f}" text-anchor="{align}">{_esc(line)}</tspan>' for i,line in enumerate(lines))
    return f'<text font-family="{_esc(family)}" font-size="{size:.3f}" font-weight="{_esc(weight)}" fill="{_esc(fill)}">{spans}</text>'


def _numeric_group(config: Dict[str,Any], name: str, slot_names: List[str]) -> List[float] | None:
    groups=config.get('slot_groups') or {}
    slots=config.get('slots') or {}
    vals=None
    if name in groups:
        vals=groups[name]
    elif any(k in slots for k in slot_names):
        vals=[slots.get(k) for k in slot_names]
    if vals is None:
        return None
    out=[]
    for v in vals:
        if v is None:
            out.append(float('nan'))
        else:
            n=_num(v,None)
            out.append(float('nan') if n is None else n)
    return out


def _plain_text_from_tag(tag: str) -> str:
    t=re.sub(r'<[^>]+>',' ',tag)
    return re.sub(r'\s+',' ',html.unescape(t)).strip()


def _remove_first_text(source: str, value: str) -> str:
    text_re=re.compile(r'<text\b[^>]*>.*?</text>',re.S|re.I)
    needle=re.sub(r'\s+',' ',str(value)).strip()
    for m in text_re.finditer(source):
        if _plain_text_from_tag(m.group(0))==needle:
            return source[:m.start()]+source[m.end():]
    return source



def _remove_numeric_text_near_y(source: str, value: float, target_y: float) -> str:
    text_re=re.compile(r'<text\b[^>]*>.*?</text>',re.S|re.I)
    candidates=[]
    for m in text_re.finditer(source):
        plain=_plain_text_from_tag(m.group(0))
        try:
            num=float(plain)
        except Exception:
            continue
        if abs(num-value)>1e-8:
            continue
        ym=re.search(r'\by="([-0-9.]+)"',m.group(0))
        y=float(ym.group(1)) if ym else 1e9
        candidates.append((abs(y-target_y),m.start(),m.end()))
    if not candidates:
        return source
    _,st,en=min(candidates,key=lambda z:z[0])
    return source[:st]+source[en:]

def _bar_value_overlay(values, left=True, vmax=1.0) -> str:
    if values is None: return ''
    bgw=230.28; edge=349.20 if left else 512.76
    ys=[232.32,268.80,308.88,352.56,397.44] if left else [230.64,269.04,309.36,352.08,396.96]
    hs=[23.52,25.08,25.56,23.76,23.76] if left else [24.36,24.72,24.72,24.72,24.72]
    color='#02489d' if left else '#568036'
    parts=[]
    for i,v in enumerate(values[:5]):
        if math.isnan(v): continue
        frac=max(0,min(1,v/vmax)); width=bgw*frac
        label=f'{v:.2f}'
        if width>=42:
            tx=(edge-width+23) if left else (edge+width-23); fill='#ffffff'; anchor='middle'
        else:
            tx=(edge-width-5) if left else (edge+width+5); fill=color; anchor='end' if left else 'start'
        ty=ys[i]+hs[i]*.68
        parts.append(f'<text x="{tx:.3f}" y="{ty:.3f}" text-anchor="{anchor}" font-family="Arial, Liberation Sans, sans-serif" font-size="13" fill="{fill}">{label}</text>')
    return ''.join(parts)


def _t15_bars(source: str, config: Dict[str,Any]) -> str:
    left_names=[f'left_value_{i}' for i in range(1,6)]
    right_names=[f'right_value_{i}' for i in range(1,6)]
    left=_numeric_group(config,'left_values',left_names)
    right=_numeric_group(config,'right_values',right_names)
    geom=(config.get('geometry') or {}).get('bars') or {}
    if geom.get('left') is not None: left=[float(x) for x in geom['left']]
    if geom.get('right') is not None: right=[float(x) for x in geom['right']]
    if left is None and right is None: return source
    vmax=float(geom.get('max',1.0) or 1.0)
    bgw=230.28
    left_end=349.20; right_start=512.76
    # Physical path order differs from semantic row order for left row 2/3.
    left_paths=[12,14,13,15,16]; right_paths=[17,18,19,20,21]
    y_left=[232.32,268.80,308.88,352.56,397.44]
    h_left=[23.52,25.08,25.56,23.76,23.76]
    y_right=[230.64,269.04,309.36,352.08,396.96]
    h_right=[24.36,24.72,24.72,24.72,24.72]
    mapping={}
    if left is not None:
        for i,v in enumerate(left[:5]):
            if math.isnan(v): continue
            frac=max(0,min(1,v/vmax)); x0=left_end-bgw*frac
            mapping[left_paths[i]]=f'M{x0:.3f} {y_left[i]:.3f}H{left_end:.3f}V{y_left[i]+h_left[i]:.3f}H{x0:.3f}Z'
    if right is not None:
        for i,v in enumerate(right[:5]):
            if math.isnan(v): continue
            frac=max(0,min(1,v/vmax)); x1=right_start+bgw*frac
            mapping[right_paths[i]]=f'M{right_start:.3f} {y_right[i]:.3f}H{x1:.3f}V{y_right[i]+h_right[i]:.3f}H{right_start:.3f}Z'
    source=_patch_path_d(source,mapping)
    # Geometry-aware value labels: remove semantic labels at their original positions and redraw them at the new bar edge.
    if left is not None:
        for i,v in enumerate(left[:5]):
            if not math.isnan(v): source=_remove_numeric_text_near_y(source,v,y_left[i]+h_left[i]*.68)
    if right is not None:
        for i,v in enumerate(right[:5]):
            if not math.isnan(v): source=_remove_numeric_text_near_y(source,v,y_right[i]+h_right[i]*.68)
    layer=_bar_value_overlay(left,True,vmax)+_bar_value_overlay(right,False,vmax)
    return _insert_layer(source,layer,'T15-bar-value-labels')


def _header_reflow(source: str, config: Dict[str,Any], template_id: str) -> str:
    struct=(config.get('structures') or {}).get('header_blocks')
    if not struct: return source
    items=[]
    default_colors=['#4e927f','#96b89b','#dcdfd2','#ecd9cf','#fdcf9e','#efa484','#b6766c','#9cc2e5','#c5e0b4']
    for i,v in enumerate(struct):
        if isinstance(v,dict):
            items.append({'text':_text(v),'color':v.get('color',default_colors[i%len(default_colors)])})
        else:
            items.append({'text':str(v),'color':default_colors[i%len(default_colors)]})
    if not items: return source
    # Cover only the header blocks to the right of the original Our Work badge.
    x0=145; x1=955; y=60; h=49; gap=6
    n=len(items); bw=(x1-x0-gap*(n-1))/n
    parts=[f'<rect x="{x0-2}" y="{y-3}" width="{x1-x0+4}" height="{h+6}" fill="#FFFFFF" stroke="none"/>']
    for i,it in enumerate(items):
        x=x0+i*(bw+gap); c=it['color']
        parts.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{bw:.3f}" height="{h:.3f}" rx="6" fill="{_esc(c)}" stroke="none"/>')
        parts.append(_text_box(x+3,y+2,bw-6,h-4,it['text'],size=10.5,weight='bold'))
    return _insert_layer(source,''.join(parts),f'{template_id}-header-reflow')


def _t20_milestones(source: str, config: Dict[str,Any]) -> str:
    struct=(config.get('structures') or {}).get('milestones')
    if not struct: return source
    colors=['#b2dedd','#c3d2ec','#c3e0e6','#8cd9c9','#aec2e5','#b8d8ca','#b9cbe8','#91d5ce']
    default_ranges=[(.08,.69),(.08,.59),(0,.86),(.22,1.0),(.15,.91)]
    items=[]
    for i,v in enumerate(struct):
        if isinstance(v,dict):
            item={'text':_text(v),'start':v.get('start'),'end':v.get('end'),'color':v.get('color',colors[i%len(colors)])}
        else:
            item={'text':str(v),'start':None,'end':None,'color':colors[i%len(colors)]}
        if item['start'] is None or item['end'] is None:
            if i < len(default_ranges):
                item['start'],item['end']=default_ranges[i]
            else:
                # stagger additional rows deterministically
                item['start']=.04+.06*(i%4); item['end']=.82+.04*(i%4)
        items.append(item)
    n=len(items)
    x0=18; x1=940; top=140; bottom=382; gap=8
    row_h=min(36,max(22,(bottom-top-gap*(n-1))/max(1,n)))
    total_h=n*row_h+(n-1)*gap
    top=top+(bottom-top-total_h)/2
    parts=[f'<rect x="0" y="130" width="960" height="265" fill="#FFFFFF" stroke="none"/>']
    # restore the characteristic vertical guides
    for x,c in [(18,'#8ad9c7'),(474,'#d8e2f2'),(645,'#bdd7ee'),(898,'#adc1e5')]:
        parts.append(f'<line x1="{x}" y1="130" x2="{x}" y2="392" stroke="{c}" stroke-width="2" stroke-dasharray="8 7"/>')
    for i,it in enumerate(items):
        y=top+i*(row_h+gap); xs=x0+(x1-x0)*float(it['start']); xe=x0+(x1-x0)*float(it['end']); xe=max(xs+70,xe)
        notch=min(24,row_h*.55)
        pts=f'{xs+notch:.2f},{y:.2f} {xe:.2f},{y:.2f} {xe+notch:.2f},{y+row_h/2:.2f} {xe:.2f},{y+row_h:.2f} {xs+notch:.2f},{y+row_h:.2f} {xs:.2f},{y+row_h/2:.2f}'
        parts.append(f'<polygon points="{pts}" fill="{_esc(it["color"])}" stroke="none"/>')
        parts.append(_text_box(xs+notch+5,y+2,max(30,xe-xs-notch-8),row_h-4,it['text'],size=11,fill='#163642',weight='normal',align='start'))
    return _insert_layer(source,''.join(parts),'T20-milestone-reflow')


def apply_semantic_geometry(template_id: str, source: str, config: Dict[str,Any]) -> str:
    # Data-driven local geometry. It is intentionally opt-in or inferred only when numeric data is supplied.
    if template_id=='T15_comparison_bars':
        source=_t15_bars(source,config)
    if template_id in ('T02_two_stage_pipeline','T03_composite_pipeline'):
        source=_header_reflow(source,config,template_id)
    if template_id=='T20_milestone_timeline':
        source=_t20_milestones(source,config)
    return source

# ---- v12 structural reflow additions ----
def _t01_pipeline_reflow(source: str, config: Dict[str,Any]) -> str:
    struct=(config.get('structures') or {}).get('pipeline_blocks')
    if not struct:
        return source
    items=[]
    colors=['#bcdedb','#9fccc8','#74b6b0','#3f978e','#287e77','#6aa9a4']
    for i,v in enumerate(struct):
        if isinstance(v,dict):
            items.append({'text':_text(v),'color':v.get('color',colors[i%len(colors)])})
        else:
            items.append({'text':str(v),'color':colors[i%len(colors)]})
    n=len(items)
    if not n:
        return source
    x0=250; x1=742; y=296; h=70; gap=20
    bw=(x1-x0-gap*(n-1))/n
    # Cover old blocks + old year labels, but preserve the source/final images.
    parts=[f'<rect x="215" y="{y-28}" width="553" height="{h+45}" fill="#FFFFFF" stroke="none"/>']
    years=(config.get('structures') or {}).get('pipeline_years') or []
    # reconnect source image -> first block
    ay=y+h/2
    parts.append(f'<line x1="210" y1="{ay:.3f}" x2="{x0-8:.3f}" y2="{ay:.3f}" stroke="#222" stroke-width="2"/>')
    parts.append(f'<polygon points="{x0-8:.3f},{ay-5:.3f} {x0:.3f},{ay:.3f} {x0-8:.3f},{ay+5:.3f}" fill="#222"/>')
    for i,it in enumerate(items):
        x=x0+i*(bw+gap)
        parts.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{bw:.3f}" height="{h:.3f}" rx="10" fill="{_esc(it["color"])}" stroke="none"/>')
        parts.append(_text_box(x+5,y+5,bw-10,h-10,it['text'],size=11,weight='bold'))
        if i<n-1:
            ax1=x+bw+3; ax2=x+bw+gap-3; ay=y+h/2
            parts.append(f'<line x1="{ax1:.3f}" y1="{ay:.3f}" x2="{ax2-8:.3f}" y2="{ay:.3f}" stroke="#222" stroke-width="2"/>')
            parts.append(f'<polygon points="{ax2-8:.3f},{ay-5:.3f} {ax2:.3f},{ay:.3f} {ax2-8:.3f},{ay+5:.3f}" fill="#222"/>')
            if i < len(years):
                parts.append(_text_box(ax1,y-22,max(26,ax2-ax1),18,str(years[i]),size=9,weight='bold'))
    # reconnect last block -> final image
    last_x=x0+(n-1)*(bw+gap)+bw
    parts.append(f'<line x1="{last_x+4:.3f}" y1="{ay:.3f}" x2="778" y2="{ay:.3f}" stroke="#222" stroke-width="2"/>')
    parts.append('<polygon points="770,326 778,331 770,336" fill="#222"/>')
    return _insert_layer(source,''.join(parts),'T01-pipeline-reflow')


def _t15_rows_reflow(source: str, config: Dict[str,Any]) -> str:
    rows=(config.get('structures') or {}).get('comparison_rows')
    if not rows:
        return source
    parsed=[]
    for r in rows:
        if not isinstance(r,dict):
            raise TypeError('comparison_rows entries must be objects with label/left/right')
        parsed.append({'label':str(r.get('label','')),'left':float(r.get('left',0)),'right':float(r.get('right',0))})
    n=len(parsed)
    if not n:
        return source
    maxv=max(1e-9,float((config.get('geometry') or {}).get('bars',{}).get('max',1.0)))
    top=215; bottom=430; gap=10
    rh=min(32,max(20,(bottom-top-gap*(n-1))/n))
    total=n*rh+(n-1)*gap; top=top+(bottom-top-total)/2
    left_bg=(118.92,349.2); right_bg=(512.76,743.04)
    bg='#f5f5f5'; blue='#02489d'; green='#568036'
    parts=[f'<rect x="105" y="205" width="655" height="240" fill="#FFFFFF" stroke="none"/>']
    for i,r in enumerate(parsed):
        y=top+i*(rh+gap); cy=y+rh/2
        parts.append(f'<rect x="{left_bg[0]}" y="{y}" width="{left_bg[1]-left_bg[0]}" height="{rh}" fill="{bg}"/>')
        parts.append(f'<rect x="{right_bg[0]}" y="{y}" width="{right_bg[1]-right_bg[0]}" height="{rh}" fill="{bg}"/>')
        lf=max(0,min(1,r['left']/maxv)); rf=max(0,min(1,r['right']/maxv))
        lx=left_bg[1]-(left_bg[1]-left_bg[0])*lf; rx=right_bg[0]+(right_bg[1]-right_bg[0])*rf
        parts.append(f'<rect x="{lx:.3f}" y="{y}" width="{left_bg[1]-lx:.3f}" height="{rh}" fill="{blue}"/>')
        parts.append(f'<rect x="{right_bg[0]}" y="{y}" width="{rx-right_bg[0]:.3f}" height="{rh}" fill="{green}"/>')
        parts.append(_text_box(360,y-2,145,rh+4,r['label'],size=14,weight='bold'))
        # numeric labels: inside when possible, outside if bar too short
        lw=left_bg[1]-lx; rw=rx-right_bg[0]
        if lw>=42: ltx=lx+23; lfill='#fff'; la='middle'
        else: ltx=lx-5; lfill=blue; la='end'
        if rw>=42: rtx=rx-23; rfill='#fff'; ra='middle'
        else: rtx=rx+5; rfill=green; ra='start'
        parts.append(f'<text x="{ltx:.3f}" y="{cy+4:.3f}" text-anchor="{la}" font-family="Arial, Liberation Sans, sans-serif" font-size="12" fill="{lfill}">{r["left"]:.2f}</text>')
        parts.append(f'<text x="{rtx:.3f}" y="{cy+4:.3f}" text-anchor="{ra}" font-family="Arial, Liberation Sans, sans-serif" font-size="12" fill="{rfill}">{r["right"]:.2f}</text>')
    return _insert_layer(source,''.join(parts),'T15-comparison-rows-reflow')

# Keep original apply function, then layer v12 additions.
_apply_v11 = apply_semantic_geometry
def apply_semantic_geometry(template_id: str, source: str, config: Dict[str,Any]) -> str:
    source=_apply_v11(template_id,source,config)
    if template_id=='T01_policy_timeline':
        source=_t01_pipeline_reflow(source,config)
    if template_id=='T15_comparison_bars' and (config.get('structures') or {}).get('comparison_rows'):
        source=_t15_rows_reflow(source,config)
    return source
