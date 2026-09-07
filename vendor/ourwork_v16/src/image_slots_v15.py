from __future__ import annotations
import base64, hashlib, json, mimetypes
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parents[1]


def _registry() -> Dict[str, Any]:
    p = ROOT / 'registry' / 'image_slots_v15.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def list_image_slots(template_id: str) -> Dict[str, Any]:
    reg = _registry(); item=reg.get(template_id,{})
    return {'template_id':template_id,'reference_page':item.get('reference_page'),'image_slots':item.get('image_slots',[]),'slot_count':item.get('slot_count',0),'auto_discovered_total':item.get('auto_discovered_total',0)}


def _resolve_path(path_like: str | Path) -> Path:
    p=Path(path_like)
    if p.exists(): return p
    return (ROOT/p).resolve()


def _mime_for(path: Path) -> str:
    mime,_=mimetypes.guess_type(str(path)); return mime or 'image/png'


def _safe_id(prefix: str, slot_name: str, key: str) -> str:
    h=hashlib.sha1((slot_name+'|'+key).encode('utf-8')).hexdigest()[:10]
    return f'{prefix}-{slot_name}-{h}'


def _trim_white_or_transparent(im: Image.Image, threshold: int = 248, pad_frac: float = 0.015) -> Tuple[Image.Image, Dict[str,Any]]:
    rgba=im.convert('RGBA'); w,h=rgba.size
    # alpha foreground
    alpha=rgba.getchannel('A')
    alpha_mask=alpha.point(lambda a: 255 if a>8 else 0)
    bbox_alpha=alpha_mask.getbbox()

    # non-white foreground. White/near-white borders are very common in paper plots/screenshots.
    rgb=rgba.convert('RGB')
    bg=Image.new('RGB',rgb.size,(255,255,255))
    diff=ImageChops.difference(rgb,bg).convert('L')
    nonwhite=diff.point(lambda v: 255 if v>(255-threshold) else 0)
    # remove isolated compression noise
    nonwhite=nonwhite.filter(ImageFilter.MaxFilter(3))
    bbox_white=nonwhite.getbbox()

    boxes=[b for b in (bbox_alpha,bbox_white) if b]
    if not boxes:
        return rgba, {'trimmed':False,'bbox':[0,0,w,h]}
    # For normal opaque screenshots alpha covers the whole canvas; prefer non-white bbox when it is meaningfully tighter.
    bbox=bbox_white if bbox_white else bbox_alpha
    if bbox_alpha and bbox_white:
        aw=(bbox_alpha[2]-bbox_alpha[0])*(bbox_alpha[3]-bbox_alpha[1]); ww=(bbox_white[2]-bbox_white[0])*(bbox_white[3]-bbox_white[1])
        if ww < aw*0.97: bbox=bbox_white
    x0,y0,x1,y1=bbox
    content_area=max(1,(x1-x0)*(y1-y0)); full=w*h
    if content_area<full*0.12:
        return rgba, {'trimmed':False,'bbox':[0,0,w,h],'reason':'content_too_small'}
    if x0<3 and y0<3 and x1>w-3 and y1>h-3:
        return rgba, {'trimmed':False,'bbox':[0,0,w,h]}
    px=max(2,int(w*pad_frac)); py=max(2,int(h*pad_frac))
    x0=max(0,x0-px); y0=max(0,y0-py); x1=min(w,x1+px); y1=min(h,y1+py)
    return rgba.crop((x0,y0,x1,y1)), {'trimmed':True,'bbox':[x0,y0,x1,y1],'original_size':[w,h],'trimmed_size':[x1-x0,y1-y0]}


def _load_processed_image(path: Path, spec: Dict[str,Any], slot: Dict[str,Any]):
    trim=str(spec.get('trim',slot.get('trim','none'))).lower()
    with Image.open(path) as src:
        im=src.convert('RGBA')
    meta={'trimmed':False,'original_size':[im.width,im.height]}
    if trim in ('auto','white','transparent'):
        im,meta=_trim_white_or_transparent(im,threshold=int(spec.get('trim_threshold',248)))
    return im,meta


def _encode_payload(path: Path, im: Image.Image, meta: Dict[str,Any], spec: Dict[str,Any], slot: Dict[str,Any], render_w: float, render_h: float):
    # Downsample very large inputs to a sensible resolution for the actual SVG display size.
    # This avoids 20-50 MB embedded photos for 80 px placeholders while retaining print-quality detail.
    role=slot.get('role','')
    default_scale=4.0 if role in ('photo','figure','content_image','semantic_region') else 3.0
    embed_scale=float(spec.get('embed_scale',slot.get('embed_scale',default_scale)) or default_scale)
    cap=int(spec.get('max_embed_dim',2400) or 2400)
    target_w=max(64,min(cap,int(abs(render_w)*embed_scale+0.5)))
    target_h=max(64,min(cap,int(abs(render_h)*embed_scale+0.5)))
    ow,oh=im.size
    ratio=min(1.0,target_w/max(1,ow),target_h/max(1,oh))
    downsampled=ratio<0.985
    if downsampled:
        nw=max(1,int(ow*ratio));nh=max(1,int(oh*ratio));im=im.resize((nw,nh),Image.Resampling.LANCZOS)
    meta=dict(meta);meta.update({'downsampled':downsampled,'embedded_size':[im.width,im.height],'embed_scale':embed_scale})
    processed=bool(meta.get('trimmed')) or downsampled
    if not processed:
        raw=path.read_bytes();mime=_mime_for(path)
        return f'data:{mime};base64,{base64.b64encode(raw).decode("ascii")}',im.width,im.height,meta
    # Photos are much smaller as JPEG; diagrams/alpha assets remain PNG.
    has_alpha=im.getchannel('A').getextrema()[0] < 255
    buf=BytesIO()
    if role=='photo' and not has_alpha:
        im.convert('RGB').save(buf,format='JPEG',quality=int(spec.get('jpeg_quality',90)),optimize=True,progressive=True);mime='image/jpeg'
    else:
        im.save(buf,format='PNG',optimize=True);mime='image/png'
    raw=buf.getvalue()
    return f'data:{mime};base64,{base64.b64encode(raw).decode("ascii")}',im.width,im.height,meta

def _parse_align(value: str|None) -> Tuple[float,float]:
    table={'center':(.5,.5),'middle':(.5,.5),'left':(0,.5),'right':(1,.5),'top':(.5,0),'bottom':(.5,1),'top-left':(0,0),'left-top':(0,0),'top-right':(1,0),'right-top':(1,0),'bottom-left':(0,1),'left-bottom':(0,1),'bottom-right':(1,1),'right-bottom':(1,1)}
    return table.get((value or 'center').lower().strip(),(.5,.5))


def _effective_fit(slot: Dict[str,Any], spec: Dict[str,Any]) -> str:
    fit=str(spec.get('fit',slot.get('fit','auto'))).lower().strip()
    if fit!='auto': return fit
    role=slot.get('role','')
    return 'cover' if role=='photo' else 'contain'


def _placement(slot: Dict[str,Any], iw:float,ih:float,spec:Dict[str,Any]):
    pad=float(spec.get('padding',slot.get('padding',0)) or 0)
    x=float(slot['x'])+pad;y=float(slot['y'])+pad;w=max(1,float(slot['width'])-2*pad);h=max(1,float(slot['height'])-2*pad)
    fit=_effective_fit(slot,spec)
    if fit=='stretch': return x,y,w,h,x,y,w,h,fit
    scale=min(w/iw,h/ih) if fit=='contain' else max(w/iw,h/ih);rw,rh=iw*scale,ih*scale
    fx=spec.get('focus_x',slot.get('focus_x'));fy=spec.get('focus_y',slot.get('focus_y'));ax,ay=_parse_align(spec.get('align',slot.get('align')))
    fx=ax if fx is None else float(fx);fy=ay if fy is None else float(fy);fx=max(0,min(1,fx));fy=max(0,min(1,fy))
    if fit=='contain': rx=x+(w-rw)*fx;ry=y+(h-rh)*fy
    else: rx=x-(rw-w)*fx;ry=y-(rh-h)*fy
    return x,y,w,h,rx,ry,rw,rh,fit


def _clip(clip_id:str,slot:Dict[str,Any],x,y,w,h)->str:
    clip=slot.get('clip','rect');rad=float(slot.get('radius',slot.get('rx',0)) or 0)
    if clip=='ellipse': return f'<clipPath id="{clip_id}"><ellipse cx="{x+w/2:.3f}" cy="{y+h/2:.3f}" rx="{w/2:.3f}" ry="{h/2:.3f}"/></clipPath>'
    if clip=='rounded_rect' or rad>0: return f'<clipPath id="{clip_id}"><rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" rx="{rad:.3f}" ry="{rad:.3f}"/></clipPath>'
    return f'<clipPath id="{clip_id}"><rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}"/></clipPath>'


def _fragment(template_id:str,slot:Dict[str,Any],spec:Dict[str,Any]) -> Tuple[str,str,Dict[str,Any]]:
    path=_resolve_path(spec['path'])
    if not path.exists(): raise FileNotFoundError(f'image path not found for slot {slot["name"]}: {path}')
    im,meta=_load_processed_image(path,spec,slot)
    iw,ih=im.size
    x,y,w,h,rx,ry,rw,rh,fit=_placement(slot,iw,ih,spec)
    href,_,_,meta=_encode_payload(path,im,meta,spec,slot,rw,rh)
    key=str(path)+json.dumps({k:spec.get(k) for k in ('fit','focus_x','focus_y','align','padding','trim')},sort_keys=True)
    clip_id=_safe_id(f'{template_id}-clip',slot['name'],key);img_id=_safe_id(f'{template_id}-img',slot['name'],key)
    defs=_clip(clip_id,slot,x,y,w,h);opacity=float(spec.get('opacity',1.0));rotation=float(spec.get('rotation',slot.get('rotation',0)) or 0);cx=float(slot['x'])+float(slot['width'])/2;cy=float(slot['y'])+float(slot['height'])/2
    body=[]
    bg=spec.get('background',slot.get('background','#ffffff' if slot.get('replace_original') else None))
    if bg and str(bg).lower() not in ('none','transparent'):
        body.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="{bg}" clip-path="url(#{clip_id})"/>')
    body.append(f'<image id="{img_id}" x="{rx:.3f}" y="{ry:.3f}" width="{rw:.3f}" height="{rh:.3f}" preserveAspectRatio="none" clip-path="url(#{clip_id})" opacity="{opacity:.4f}" xlink:href="{href}" href="{href}"/>')
    if slot.get('stroke') or slot.get('stroke_width'):
        stroke=slot.get('stroke','#fff');sw=float(slot.get('stroke_width',1));rad=float(slot.get('radius',0) or 0)
        body.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" rx="{rad:.3f}" ry="{rad:.3f}" fill="none" stroke="{stroke}" stroke-width="{sw:.3f}"/>')
    body_str=''.join(body)
    if abs(rotation)>1e-6: body_str=f'<g transform="rotate({rotation:.3f} {cx:.3f} {cy:.3f})">{body_str}</g>'
    meta.update({'slot':slot['name'],'source_path':str(path),'fit':fit,'placement':[round(rx,3),round(ry,3),round(rw,3),round(rh,3)],'clip_box':[round(x,3),round(y,3),round(w,3),round(h,3)],'rotation':rotation})
    return defs,body_str,meta



def expand_auto_images(template_id: str, config: Dict[str,Any] | None = None) -> Dict[str,Any]:
    """Expand top-level auto_images into the regular images mapping.

    auto_images accepts strings or objects with `path`. By default images are assigned
    to slots in visual reading order (top-to-bottom, left-to-right). `assignment=aspect`
    performs greedy aspect-ratio matching instead.
    """
    config=dict(config or {})
    pool=config.get('auto_images') or []
    if not pool:
        return config
    slots=list_image_slots(template_id).get('image_slots',[])
    options=config.get('auto_image_options') or {}
    requested=options.get('slots')
    if requested:
        sm={s['name']:s for s in slots}; slots=[sm[n] for n in requested if n in sm]
    else:
        slots=sorted([s for s in slots if not s.get('optional')],key=lambda z:(float(z['y']),float(z['x'])))
    items=[]
    for it in pool:
        items.append({'path':it} if isinstance(it,(str,Path)) else dict(it))
    explicit=dict(config.get('images') or {})
    slots=[s for s in slots if s['name'] not in explicit]
    mode=str(options.get('assignment','reading_order')).lower()
    assignments=[]
    if mode=='aspect':
        remaining=list(slots)
        for item in items:
            if not remaining:break
            p=_resolve_path(item['path'])
            try:
                with Image.open(p) as im: ar=im.width/max(1,im.height)
            except Exception: ar=1.0
            def cost(s):
                sar=float(s['width'])/max(1,float(s['height']))
                import math
                c=abs(math.log(max(.01,ar)/max(.01,sar)))
                role=item.get('role')
                if role and role!=s.get('role'):c+=1.0
                return c
            slot=min(remaining,key=cost);remaining.remove(slot);assignments.append((slot,item))
    else:
        assignments=list(zip(slots,items))
    for slot,item in assignments:
        explicit[slot['name']]=item
    config['images']=explicit
    config['_auto_image_assignments']=[{'slot':s['name'],'path':i.get('path')} for s,i in assignments]
    return config

def apply_image_slots(template_id:str,source:str,config:Dict[str,Any]|None=None)->str:
    config=expand_auto_images(template_id,config or {});images=config.get('images') or {}
    if not images:return source
    slots=list_image_slots(template_id).get('image_slots',[]);slot_map={s['name']:s for s in slots};defs=[];body=[]
    for name,spec in images.items():
        if name not in slot_map: continue
        d,b,_=_fragment(template_id,slot_map[name],spec);defs.append(d);body.append(b)
    if not body:return source
    layer='<defs>'+''.join(defs)+'</defs><g id="image-slots-v15">'+''.join(body)+'</g>'
    idx=source.lower().rfind('</svg>')
    if idx<0:raise ValueError('Malformed SVG: closing </svg> not found')
    return source[:idx]+layer+source[idx:]


def image_placement_report(template_id:str,config:Dict[str,Any]|None=None)->List[Dict[str,Any]]:
    config=expand_auto_images(template_id,config or {});images=config.get('images') or {};slot_map={s['name']:s for s in list_image_slots(template_id).get('image_slots',[])};out=[]
    for name,spec in images.items():
        if name not in slot_map:continue
        _,_,meta=_fragment(template_id,slot_map[name],spec);out.append(meta)
    return out
