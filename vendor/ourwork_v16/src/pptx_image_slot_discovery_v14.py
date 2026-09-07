from __future__ import annotations
import argparse, json, re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lxml import etree
from pptx import Presentation

NS = {
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}


def _local(el) -> str:
    return etree.QName(el).localname


def _float_attr(el, key: str, default=0.0) -> float:
    try:
        return float(el.get(key))
    except Exception:
        return float(default)


def _xfrm_box(el, kind: str):
    if kind == 'grpSp':
        xfrm = el.find('p:grpSpPr/a:xfrm', NS)
    elif kind in ('sp','pic','cxnSp'):
        xfrm = el.find('p:spPr/a:xfrm', NS)
    else:
        xfrm = el.find('p:xfrm', NS) or el.find('.//a:xfrm', NS)
    if xfrm is None:
        return None
    off=xfrm.find('a:off',NS); ext=xfrm.find('a:ext',NS)
    if off is None or ext is None:
        return None
    return (_float_attr(off,'x'), _float_attr(off,'y'), _float_attr(ext,'cx'), _float_attr(ext,'cy'), _float_attr(xfrm,'rot',0)/60000.0)


def _name_descr(el, kind: str) -> Tuple[str,str]:
    if kind == 'pic': c=el.find('p:nvPicPr/p:cNvPr',NS)
    else: c=el.find('p:nvSpPr/p:cNvPr',NS)
    if c is None: return '', ''
    return c.get('name',''), c.get('descr','')


def _shape_has_blip_fill(el) -> bool:
    return el.find('p:spPr/a:blipFill/a:blip', NS) is not None


def _shape_clip(el) -> Tuple[str,float]:
    geom=el.find('p:spPr/a:prstGeom',NS)
    if geom is None: return 'rect',0.0
    prst=(geom.get('prst') or '').lower()
    if prst in ('roundrect','round1rect','round2samerect','round2diagrect'):
        return 'rounded_rect',6.0
    if prst == 'ellipse': return 'ellipse',0.0
    return 'rect',0.0


def _classify(slot: Dict[str,Any], canvas=(960.0,540.0)) -> Tuple[str,str,bool]:
    x,y,w,h=slot['x'],slot['y'],slot['width'],slot['height']
    area=max(0,w)*max(0,h); ratio=area/(canvas[0]*canvas[1])
    visible_w=max(0,min(canvas[0],x+w)-max(0,x)); visible_h=max(0,min(canvas[1],y+h)-max(0,y))
    visible_ratio=(visible_w*visible_h/area) if area>0 else 0
    if ratio>0.5 or visible_ratio<0.35:
        return 'background_or_reference','contain',False
    if slot.get('kind')=='picture_fill':
        if ratio>=0.004: return 'photo','cover',True
        return 'icon','contain',True
    if ratio>=0.05: return 'figure','contain',True
    if ratio>=0.008: return 'content_image','contain',True
    return 'icon','contain',False


def _slug(s: str) -> str:
    s=s.lower().strip(); s=re.sub(r'https?://\S+','',s); s=re.sub(r'[^a-z0-9]+','_',s).strip('_')
    return s[:36]


def _assign_names(slots: List[Dict[str,Any]]) -> None:
    counters={}
    for slot in sorted(slots,key=lambda d:(d['y'],d['x'])):
        role=slot['role']; counters[role]=counters.get(role,0)+1
        desc=_slug(slot.get('descr',''))
        base={'photo':'photo','figure':'figure','content_image':'content_image','icon':'icon'}.get(role,'background')
        if desc and len(desc)>=4: slot['auto_label_hint']=desc
        slot['name']=f'{base}_{counters[role]}'


def discover_pptx_images(pptx_path: str|Path, reference_pages: Dict[str,int]|None=None) -> Dict[str,Any]:
    ppt=Presentation(str(pptx_path)); sw,sh=float(ppt.slide_width),float(ppt.slide_height)
    canvas_w,canvas_h=960.0,540.0; page_to_tid={v:k for k,v in (reference_pages or {}).items()}; result={}

    def walk(el, slide_slots, ax=1.0, ay=1.0, bx=0.0, by=0.0, depth=0):
        kind=_local(el)
        if kind=='grpSp':
            xfrm=el.find('p:grpSpPr/a:xfrm',NS)
            if xfrm is None: return
            off=xfrm.find('a:off',NS); ext=xfrm.find('a:ext',NS); choff=xfrm.find('a:chOff',NS); chext=xfrm.find('a:chExt',NS)
            if None in (off,ext,choff,chext): return
            ox,oy=_float_attr(off,'x'),_float_attr(off,'y'); ecx,ecy=_float_attr(ext,'cx'),_float_attr(ext,'cy')
            cx,cy=_float_attr(choff,'x'),_float_attr(choff,'y'); ccx,ccy=max(1,_float_attr(chext,'cx')),max(1,_float_attr(chext,'cy'))
            sx,sy=ecx/ccx,ecy/ccy; nax,nay=ax*sx,ay*sy; nbx=ax*(ox-cx*sx)+bx; nby=ay*(oy-cy*sy)+by
            for ch in el:
                if _local(ch) in ('sp','pic','grpSp','cxnSp','graphicFrame'): walk(ch,slide_slots,nax,nay,nbx,nby,depth+1)
            return
        is_pic=(kind=='pic'); is_fill=(kind=='sp' and _shape_has_blip_fill(el))
        if not (is_pic or is_fill): return
        box=_xfrm_box(el,kind)
        if not box: return
        x,y,w,h,rot=box; X=ax*x+bx;Y=ay*y+by;W=abs(ax*w);H=abs(ay*h); name,descr=_name_descr(el,kind)
        clip,radius=_shape_clip(el) if is_fill else ('rect',0.0)
        slot={'x':round(X/sw*canvas_w,3),'y':round(Y/sh*canvas_h,3),'width':round(W/sw*canvas_w,3),'height':round(H/sh*canvas_h,3),'rotation':round(rot,3),'kind':'picture_fill' if is_fill else 'picture','pptx_name':name,'descr':descr,'clip':clip,'radius':radius,'depth':depth}
        role,fit,replaceable=_classify(slot,(canvas_w,canvas_h)); slot.update({'role':role,'fit':fit,'replaceable':replaceable,'source':'pptx_auto'})
        slide_slots.append(slot)

    for page_idx,slide in enumerate(ppt.slides, start=1):
        if reference_pages and page_idx not in page_to_tid: continue
        spTree=slide.element.find('.//p:spTree',NS); slots=[]
        for ch in spTree:
            if _local(ch) in ('sp','pic','grpSp','cxnSp','graphicFrame'): walk(ch,slots)
        _assign_names(slots); tid=page_to_tid.get(page_idx,f'slide_{page_idx:02d}')
        result[tid]={'reference_page':page_idx,'image_slots':slots,'replaceable_count':sum(1 for s in slots if s['replaceable'])}
    return result


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--pptx',required=True); ap.add_argument('--templates-json'); ap.add_argument('--out',required=True); args=ap.parse_args()
    refs=None
    if args.templates_json:
        arr=json.loads(Path(args.templates_json).read_text(encoding='utf-8')); refs={x['id']:int(x['reference_page']) for x in arr}
    Path(args.out).write_text(json.dumps(discover_pptx_images(args.pptx,refs),ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
