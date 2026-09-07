from __future__ import annotations
import hashlib, json, math, re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from lxml import etree
from semantic_slots_v12 import expand_slots, list_template_slots

ROOT = Path(__file__).resolve().parents[1]
TEXT_RE = re.compile(r'<text\b[^>]*>.*?</text>', re.S | re.I)
DATA_IMAGE_RE = re.compile(r'(?:xlink:href|href)="(data:image/[^;]+;base64,[^"]+)"', re.S | re.I)
PATH_RE = re.compile(r'<path\b[^>]*?/\s*>', re.S | re.I)
IMAGE_TAG_RE = re.compile(r'<image\b[^>]*?/\s*>', re.S | re.I)


def normalize_text(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()


def parse_num_list(v: Optional[str]) -> List[float]:
    if not v:
        return []
    return [float(x) for x in re.split(r'[ ,]+', v.strip()) if x]



def font_family_fallback(family: Optional[str]) -> str:
    fam=(family or '').strip()
    if not fam:
        return 'Arial, Liberation Sans, sans-serif'
    if ',' in fam:
        return fam
    low=fam.lower()
    if 'times' in low or 'roman' in low or 'serif' in low:
        return f'{fam}, Times New Roman, Liberation Serif, serif'
    if any(k in low for k in ('calibri','arial','helvetica','aptos','sans')):
        return f'{fam}, Arial, Liberation Sans, sans-serif'
    # Keep the source font first; add neutral fallbacks only if it is unavailable.
    return f'{fam}, Arial, Liberation Sans, sans-serif'

def attr_escape(s: str) -> str:
    return (str(s).replace('&','&amp;').replace('"','&quot;').replace('<','&lt;').replace('>','&gt;'))


def text_escape(s: str) -> str:
    return (str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'))


def registry():
    p = ROOT / 'registry' / 'templates.json'
    return {x['id']: x for x in json.loads(p.read_text(encoding='utf-8'))}


def reference_svg_path(template_id: str) -> Path:
    page = int(registry()[template_id]['reference_page'])
    return ROOT / 'references' / 'editable' / f'slide-{page:02d}.svg'


@dataclass
class RawText:
    raw_id: str
    source_start: int
    source_end: int
    source: str
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    baseline_y: float
    font_size: float
    fill: Optional[str]
    family: Optional[str]
    weight: Optional[str]
    style: Optional[str]
    transform: Optional[str]
    attrs: Dict[str, str]
    tspan_attrs: Dict[str, str]

    @property
    def width(self): return self.x1-self.x0
    @property
    def height(self): return self.y1-self.y0
    @property
    def cx(self): return (self.x0+self.x1)/2
    @property
    def cy(self): return (self.y0+self.y1)/2


@dataclass
class TextBlock:
    block_id: str
    raws: List[RawText]
    text: str
    x0: float; y0: float; x1: float; y1: float
    font_size: float
    fill: Optional[str]
    family: Optional[str]
    weight: Optional[str]
    style: Optional[str]
    transform: Optional[str]
    @property
    def width(self): return self.x1-self.x0
    @property
    def height(self): return self.y1-self.y0
    @property
    def cx(self): return (self.x0+self.x1)/2
    @property
    def cy(self): return (self.y0+self.y1)/2


def parse_fragment(fragment: str, idx: int, start: int, end: int) -> Optional[RawText]:
    try:
        parser = etree.XMLParser(recover=True, huge_tree=True)
        el = etree.fromstring(fragment.encode('utf-8'), parser=parser)
    except Exception:
        return None
    attrs = dict(el.attrib)
    fs = float(attrs.get('font-size', '12'))
    fill = attrs.get('fill')
    family = attrs.get('font-family')
    weight = attrs.get('font-weight')
    style = attrs.get('font-style')
    transform = attrs.get('transform')
    tspans = [c for c in el if etree.QName(c).localname == 'tspan'] or [el]
    pieces=[]; minx=1e9; miny=1e9; maxx=-1e9; maxy=-1e9; first_tspan_attrs={}; baselines=[]
    for sp_i, sp in enumerate(tspans):
        txt = ''.join(sp.itertext())
        if not normalize_text(txt):
            continue
        if sp_i == 0:
            first_tspan_attrs = dict(sp.attrib)
        xs = parse_num_list(sp.get('x') or el.get('x'))
        ys = parse_num_list(sp.get('y') or el.get('y'))
        x = xs[0] if xs else 0.0
        y = ys[0] if ys else 0.0
        baselines.append(y)
        if len(xs) > 1:
            w = max(xs)-min(xs)+fs*0.58
        else:
            w = max(1.0, len(normalize_text(txt))*fs*0.54)
        minx=min(minx,x); maxx=max(maxx,x+w)
        miny=min(miny,y-fs*.9); maxy=max(maxy,y+fs*.35)
        pieces.append((y,normalize_text(txt)))
    if not pieces:
        return None
    pieces.sort(key=lambda z:z[0])
    return RawText(
        raw_id=f'r{idx:03d}', source_start=start, source_end=end, source=fragment,
        text='\n'.join(t for _,t in pieces), x0=minx,y0=miny,x1=maxx,y1=maxy,
        baseline_y=min(baselines), font_size=fs, fill=fill, family=family, weight=weight,
        style=style, transform=transform, attrs=attrs, tspan_attrs=first_tspan_attrs)


def extract_raw_texts(source: str) -> List[RawText]:
    raws=[]
    for i,m in enumerate(TEXT_RE.finditer(source)):
        r=parse_fragment(m.group(0),i,m.start(),m.end())
        if r: raws.append(r)
    return raws


def style_key(r):
    return (r.fill,r.family,r.weight,r.style,r.transform,round(r.font_size,2))


def build_blocks(raws: List[RawText]) -> List[TextBlock]:
    # Conservative grouping only: adjacent source order + vertical continuity + same style.
    blocks=[]
    for r in raws:
        target=None
        for b in reversed(blocks[-8:]):
            if (b.fill,b.family,b.weight,b.style,b.transform,round(b.font_size,2)) != style_key(r):
                continue
            vgap=r.y0-b.y1
            if not (0 <= vgap <= max(7.0,r.font_size*1.55)):
                continue
            overlap=max(0,min(b.x1,r.x1)-max(b.x0,r.x0))
            center_close=abs(b.cx-r.cx)<max(18,min(b.width,r.width)*.35)
            if overlap > min(b.width,r.width)*.18 or center_close or abs(b.x0-r.x0)<12:
                target=b; break
        if target is None:
            blocks.append(TextBlock(f'b{len(blocks):03d}',[r],r.text,r.x0,r.y0,r.x1,r.y1,r.font_size,r.fill,r.family,r.weight,r.style,r.transform))
        else:
            target.raws.append(r); target.text += '\n'+r.text
            target.x0=min(target.x0,r.x0); target.y0=min(target.y0,r.y0)
            target.x1=max(target.x1,r.x1); target.y1=max(target.y1,r.y1)
    return blocks


def image_data_hashes(source: str) -> List[str]:
    hashes=[]
    for m in DATA_IMAGE_RE.finditer(source):
        data=m.group(1)
        # ignore formatting whitespace in hash equivalence
        canonical=re.sub(r'\s+','',data)
        hashes.append(hashlib.sha256(canonical.encode()).hexdigest())
    return hashes


def wrap_words(text: str, max_chars: int) -> List[str]:
    paras=str(text).split('\n'); out=[]
    for p in paras:
        words=p.split()
        if not words:
            out.append(''); continue
        cur=''
        for w in words:
            if len(cur)+len(w)+(1 if cur else 0)<=max_chars:
                cur += (' ' if cur else '')+w
            else:
                if cur: out.append(cur)
                while len(w)>max_chars:
                    out.append(w[:max_chars]); w=w[max_chars:]
                cur=w
        if cur: out.append(cur)
    return out or ['']


def choose_box(target: TextBlock, rep: Dict[str,Any]) -> Tuple[float,float,float,float]:
    # Safe default: original text region. Expansion is deliberately mild to avoid covering nearby graphics.
    p=float(rep.get('padding',2.0))
    expand_x=float(rep.get('expand_x',max(8.0,target.width*.08)))
    expand_y=float(rep.get('expand_y',max(4.0,target.font_size*.25)))
    return target.x0-p-expand_x, target.y0-p-expand_y, target.x1+p+expand_x, target.y1+p+expand_y


def infer_anchor(target: TextBlock) -> str:
    # Titles and long sentences are usually left aligned; small labels preserve a centered look.
    if target.width>150 or len(normalize_text(target.text))>24:
        return 'start'
    return 'middle'


def fragment_for_replacement(target: TextBlock, rep: Dict[str,Any]) -> str:
    first=target.raws[0]
    attrs=dict(first.attrs)
    # Preserve every original font/transform attribute unless explicitly overridden.
    if rep.get('font_family'): attrs['font-family']=str(rep['font_family'])
    if rep.get('font_weight'): attrs['font-weight']=str(rep['font_weight'])
    if rep.get('font_style'): attrs['font-style']=str(rep['font_style'])
    if rep.get('fill'): attrs['fill']=str(rep['fill'])
    attrs['font-family']=font_family_fallback(attrs.get('font-family'))
    base_size=float(rep.get('font_size',first.font_size))
    x0,y0,x1,y1=choose_box(target,rep); w=max(5,x1-x0); h=max(5,y1-y0)
    new_text=str(rep.get('replace',''))
    fit_mode=rep.get('fit','auto')
    anchor=rep.get('align') or infer_anchor(target)

    # Estimate and fit conservatively, preserving original size whenever possible.
    size=base_size
    if fit_mode=='keep_size':
        lines=new_text.split('\n')
    else:
        while True:
            max_chars=max(3,int(w/max(3.0,size*.53)))
            lines=wrap_words(new_text,max_chars)
            est_w=max((len(x) for x in lines),default=1)*size*.53
            est_h=len(lines)*size*1.16
            if est_w<=w and est_h<=max(h,base_size*1.4): break
            size-=.35
            if size<=max(6.0,base_size*.62):
                size=max(6.0,base_size*.62)
                max_chars=max(3,int(w/max(3.0,size*.53)))
                lines=wrap_words(new_text,max_chars); break
    attrs['font-size']=f'{size:.3f}'.rstrip('0').rstrip('.')
    # text x/y are expressed in tspans, like the source reference.
    attrs.pop('x',None); attrs.pop('y',None)
    def _fmt_attr_name(k):
        if k == '{http://www.w3.org/XML/1998/namespace}space': return 'xml:space'
        if k.startswith('{http://www.w3.org/2000/xmlns/}'): return 'xmlns:' + k.split('}',1)[1]
        return k
    attr_str=' '.join(f'{_fmt_attr_name(k)}="{attr_escape(v)}"' for k,v in attrs.items())
    if anchor=='start': x=x0+1.0
    elif anchor=='end': x=x1-1.0
    else: x=(x0+x1)/2
    start_y=(y0+y1)/2 - (len(lines)-1)*size*.58 + size*.33
    tsp=[]
    for i,line in enumerate(lines):
        tsp.append(f'<tspan x="{x:.3f}" y="{(start_y+i*size*1.16):.3f}" text-anchor="{anchor}">{text_escape(line)}</tspan>')
    return f'<text {attr_str}>{"".join(tsp)}</text>'



def _svg_text_overlay(text: str, box, font_size: float, family='Calibri', weight='bold', fill='#000000', align='middle') -> str:
    x,y,w,h=[float(v) for v in box]
    size=float(font_size)
    # Conservative local fit: keep size when possible, otherwise wrap + shrink.
    while True:
        max_chars=max(3,int(w/max(3.0,size*.54)))
        lines=wrap_words(str(text), max_chars)
        est_w=max((len(line) for line in lines), default=1)*size*.54
        est_h=len(lines)*size*1.15
        if est_w<=w*0.96 and est_h<=h*1.18:
            break
        size-=.4
        if size<=7.0:
            size=7.0
            max_chars=max(3,int(w/max(3.0,size*.54)))
            lines=wrap_words(str(text), max_chars)
            break
    if align=='start':
        tx=x+2
    elif align=='end':
        tx=x+w-2
    else:
        tx=x+w/2
    start_y=y+h/2-(len(lines)-1)*size*.575+size*.34
    tsp=[]
    for i,line in enumerate(lines):
        tsp.append(f'<tspan x="{tx:.3f}" y="{(start_y+i*size*1.15):.3f}" text-anchor="{align}">{text_escape(line)}</tspan>')
    family=font_family_fallback(family)
    return f'<text font-family="{attr_escape(family)}" font-size="{size:.3f}" font-weight="{attr_escape(weight)}" fill="{attr_escape(fill)}">{"".join(tsp)}</text>'


def overlay_fragment(rep: Dict[str,Any]) -> str:
    ov=rep.get('overlay') or {}
    typ=ov.get('type')
    new_text=str(rep.get('replace',''))
    if typ=='ellipse_label':
        x,y,w,h=[float(v) for v in ov['ellipse']]
        cx=x+w/2; cy=y+h/2
        ellipse=f'<ellipse cx="{cx:.3f}" cy="{cy:.3f}" rx="{w/2:.3f}" ry="{h/2:.3f}" fill="{attr_escape(ov.get("fill","#FFFFFF"))}" stroke="none"/>'
        text=_svg_text_overlay(new_text, ov['text_box'], rep.get('font_size',ov.get('font_size',20)), rep.get('font_family',ov.get('font_family','Calibri')), rep.get('font_weight',ov.get('font_weight','bold')), rep.get('fill',ov.get('fill_text','#000000')), rep.get('align',ov.get('align','middle')))
        return ellipse+text
    if typ=='white_text':
        x,y,w,h=[float(v) for v in ov['text_box']]
        pad=float(ov.get('cover_pad',2.5))
        rect=f'<rect x="{x-pad:.3f}" y="{y-pad:.3f}" width="{w+2*pad:.3f}" height="{h+2*pad:.3f}" fill="{attr_escape(ov.get("cover_fill","#FFFFFF"))}" stroke="none"/>'
        text=_svg_text_overlay(new_text, ov['text_box'], rep.get('font_size',ov.get('font_size',20)), rep.get('font_family',ov.get('font_family','Calibri')), rep.get('font_weight',ov.get('font_weight','bold')), rep.get('fill',ov.get('fill_text','#000000')), rep.get('align',ov.get('align','middle')))
        return rect+text
    if typ=='path_text':
        return _svg_text_overlay(new_text, ov['text_box'], rep.get('font_size',ov.get('font_size',20)), rep.get('font_family',ov.get('font_family','Calibri')), rep.get('font_weight',ov.get('font_weight','bold')), rep.get('fill',ov.get('fill_text','#000000')), rep.get('align',ov.get('align','middle')))
    raise ValueError(f'Unsupported semantic overlay type: {typ!r}')

def inventory_for_template(template_id: str) -> Dict[str,Any]:
    source=reference_svg_path(template_id).read_text(encoding='utf-8')
    raws=extract_raw_texts(source); blocks=build_blocks(raws)
    return {
      'template_id':template_id,
      'reference_page':int(registry()[template_id]['reference_page']),
      'raw_items':[{'raw_id':r.raw_id,'text':r.text,'x0':round(r.x0,2),'y0':round(r.y0,2),'x1':round(r.x1,2),'y1':round(r.y1,2),'font_size':r.font_size,'fill':r.fill,'font_family':r.family,'font_weight':r.weight,'font_style':r.style,'transform':r.transform} for r in raws],
      'blocks':[{'block_id':b.block_id,'text':b.text,'raw_ids':[r.raw_id for r in b.raws],'x0':round(b.x0,2),'y0':round(b.y0,2),'x1':round(b.x1,2),'y1':round(b.y1,2),'font_size':b.font_size,'fill':b.fill,'font_family':b.family,'font_weight':b.weight,'font_style':b.style,'transform':b.transform} for b in blocks]
    }


def render_reference_editable(template_id: str, config: Optional[Dict[str,Any]]=None) -> str:
    config=config or {}
    source=reference_svg_path(template_id).read_text(encoding='utf-8')
    replacements=[]
    replacements.extend(expand_slots(template_id, config.get('slots'), config.get('slot_groups'), config.get('slot_options')))
    replacements.extend(config.get('text_replacements',[]))
    if not replacements:
        # Critical invariant: no-edit output is byte-for-byte identical to Reference SVG.
        return source
    raws=extract_raw_texts(source); blocks=build_blocks(raws)
    raw_by={r.raw_id:r for r in raws}; block_by={b.block_id:b for b in blocks}

    def _block_from_raws(sel_raws):
        sel_raws=sorted(sel_raws,key=lambda rr: rr.source_start)
        return TextBlock('+'.join(r.raw_id for r in sel_raws), sel_raws, '\n'.join(r.text for r in sel_raws), min(r.x0 for r in sel_raws), min(r.y0 for r in sel_raws), max(r.x1 for r in sel_raws), max(r.y1 for r in sel_raws), max(r.font_size for r in sel_raws), sel_raws[0].fill, sel_raws[0].family, sel_raws[0].weight, sel_raws[0].style, sel_raws[0].transform)

    def find_targets(rep):
        if rep.get('raw_ids'):
            ids=rep['raw_ids']
            if all(rid in raw_by for rid in ids):
                return [_block_from_raws([raw_by[rid] for rid in ids])]
            return []
        if rep.get('raw_id') in raw_by:
            r=raw_by[rep['raw_id']]
            return [_block_from_raws([r])]
        if rep.get('block_id') in block_by:
            return [block_by[rep['block_id']]]
        needle=normalize_text(rep.get('match','')).lower()
        if not needle: return []
        exact_raw=[]
        for r in raws:
            if normalize_text(r.text).lower()==needle:
                exact_raw.append(TextBlock(r.raw_id,[r],r.text,r.x0,r.y0,r.x1,r.y1,r.font_size,r.fill,r.family,r.weight,r.style,r.transform))
        if exact_raw:
            candidates=exact_raw
        else:
            exact_blocks=[b for b in blocks if normalize_text(b.text).lower()==needle]
            if exact_blocks:
                candidates=exact_blocks
            else:
                contains_raw=[]
                for r in raws:
                    if needle in normalize_text(r.text).lower():
                        contains_raw.append(TextBlock(r.raw_id,[r],r.text,r.x0,r.y0,r.x1,r.y1,r.font_size,r.fill,r.family,r.weight,r.style,r.transform))
                candidates=contains_raw or [b for b in blocks if needle in normalize_text(b.text).lower()]
        if rep.get('all_matches'):
            return candidates
        occ=max(1,int(rep.get('occurrence',1)))
        return [candidates[occ-1]] if len(candidates)>=occ else []

    patches=[]; used_raw_ids=set(); overlay_reps=[]
    for rep in replacements:
        if rep.get('overlay'):
            overlay_reps.append(rep)
            continue
        for t in find_targets(rep):
            raw_ids=[r.raw_id for r in t.raws]
            if any(rid in used_raw_ids for rid in raw_ids):
                continue
            used_raw_ids.update(raw_ids)
            ordered=sorted(t.raws,key=lambda r:r.source_start)
            first=ordered[0]
            patches.append((first.source_start, first.source_end, fragment_for_replacement(t,rep)))
            for extra in ordered[1:]:
                # Important: delete only the selected text element itself; never span across intervening SVG content.
                patches.append((extra.source_start, extra.source_end, ''))
    out=source
    for s,e,repl in sorted(patches,key=lambda z:z[0],reverse=True):
        out=out[:s]+repl+out[e:]
    if overlay_reps:
        # For pathized text recovered from PPTX (T16/T17), remove only the precomputed glyph paths.
        remove_indexes=set()
        for rep in overlay_reps:
            remove_indexes.update((rep.get('overlay') or {}).get('remove_path_indexes', []))
        if remove_indexes:
            path_patches=[]
            for idx,m in enumerate(PATH_RE.finditer(out)):
                if idx in remove_indexes:
                    path_patches.append((m.start(),m.end()))
            for s,e in sorted(path_patches, reverse=True):
                out=out[:s]+out[e:]
        remove_images=set()
        for rep in overlay_reps:
            remove_images.update((rep.get('overlay') or {}).get('remove_image_indexes', []))
        if remove_images:
            img_patches=[]
            for idx,m in enumerate(IMAGE_TAG_RE.finditer(out)):
                if idx in remove_images:
                    img_patches.append((m.start(),m.end()))
            for s,e in sorted(img_patches, reverse=True):
                out=out[:s]+out[e:]
        layer='<g id="semantic-overlays-v8">'+''.join(overlay_fragment(rep) for rep in overlay_reps)+'</g>'
        pos=out.lower().rfind('</svg>')
        if pos<0: raise ValueError('Malformed SVG: closing </svg> not found')
        out=out[:pos]+layer+out[pos:]
    return out


def semantic_slot_inventory(template_id: str) -> Dict[str,Any]:
    return list_template_slots(template_id)


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('--template',required=True); ap.add_argument('--config'); ap.add_argument('--out'); ap.add_argument('--inventory-out')
    a=ap.parse_args(); cfg=json.loads(Path(a.config).read_text(encoding='utf-8')) if a.config else {}
    if a.inventory_out: Path(a.inventory_out).write_text(json.dumps(inventory_for_template(a.template),ensure_ascii=False,indent=2),encoding='utf-8')
    if a.out: Path(a.out).write_text(render_reference_editable(a.template,cfg),encoding='utf-8')
