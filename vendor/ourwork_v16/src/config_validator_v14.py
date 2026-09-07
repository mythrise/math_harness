from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict
from semantic_slots_v12 import list_template_slots
from image_slots_v14 import list_image_slots, _resolve_path

ROOT=Path(__file__).resolve().parents[1]
INV_DIR=ROOT/'registry'/'text_inventory_v5'
ALLOWED_TOP={'slots','slot_groups','slot_options','structures','geometry','meta','images'}

CAPACITY={
 'T02_two_stage_pipeline': {'header_blocks':(10,12)},
 'T03_composite_pipeline': {'header_blocks':(9,11)},
 'T20_milestone_timeline': {'milestones':(8,10)},
 'T01_policy_timeline': {'pipeline_blocks':(6,8)},
 'T15_comparison_bars': {'comparison_rows':(7,9)},
}


def _text(v):
    if isinstance(v,dict): return str(v.get('text',v.get('value','')))
    return str(v)


def _inventory(template_id:str):
    p=INV_DIR/f'{template_id}.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'raw_items':[]}


def lint_config(template_id:str,config:Dict[str,Any])->Dict[str,Any]:
    warnings=[];errors=[]
    unknown_top=[k for k in config if k not in ALLOWED_TOP]
    if unknown_top:warnings.append(f'Unknown top-level keys ignored by core engine: {unknown_top}')
    info=list_template_slots(template_id);slots={s['name']:s for s in info.get('slots',[])};groups=info.get('aliases',{})
    for k in (config.get('slots') or {}):
        if k not in slots:errors.append(f'Unknown slot: {k}')
    for k,v in (config.get('slot_groups') or {}).items():
        if k not in groups:errors.append(f'Unknown slot_group: {k}')
        elif not isinstance(v,(list,tuple)):errors.append(f'slot_group {k} must be a list')
        elif len(v)>len(groups[k]):errors.append(f'slot_group {k} accepts at most {len(groups[k])} values')
    for k in (config.get('slot_options') or {}):
        if k not in slots:errors.append(f'Unknown slot_options key: {k}')

    img_info=list_image_slots(template_id);image_slots={x['name']:x for x in img_info.get('image_slots',[])}
    for name,spec in (config.get('images') or {}).items():
        if name not in image_slots:
            errors.append(f'Unknown image slot: {name}. Available: {sorted(image_slots)}');continue
        if not isinstance(spec,dict):
            errors.append(f'image slot {name} must be an object');continue
        path=spec.get('path')
        if not path:errors.append(f'image slot {name} is missing path')
        elif not _resolve_path(path).exists():errors.append(f'image slot {name} path does not exist: {path}')
        fit=str(spec.get('fit',image_slots[name].get('fit','auto'))).lower()
        if fit not in {'cover','contain','stretch','auto'}:errors.append(f'image slot {name} has unsupported fit: {fit}')
        for key in ('focus_x','focus_y'):
            if key in spec:
                try:v=float(spec[key])
                except Exception:errors.append(f'image slot {name} {key} must be numeric');continue
                if not 0<=v<=1:errors.append(f'image slot {name} {key} must be in [0,1]')
        trim=str(spec.get('trim',image_slots[name].get('trim','none'))).lower()
        if trim not in {'none','auto','white','transparent'}:errors.append(f'image slot {name} has unsupported trim: {trim}')

    structures=config.get('structures') or {}
    for key,(recommended,hard) in CAPACITY.get(template_id,{}).items():
        if key in structures:
            n=len(structures[key])
            if n>hard:errors.append(f'{key} has {n} items; hard limit is {hard}')
            elif n>recommended:warnings.append(f'{key} has {n} items; recommended maximum is {recommended}, text may become small')

    inv=_inventory(template_id);raw={r['raw_id']:r for r in inv.get('raw_items',[])}
    for name,value in (config.get('slots') or {}).items():
        if name not in slots:continue
        target=slots[name].get('target') or {};ids=[target['raw_id']] if 'raw_id' in target else target.get('raw_ids',[]);boxes=[raw[i] for i in ids if i in raw]
        if not boxes:continue
        w=max(b['x1'] for b in boxes)-min(b['x0'] for b in boxes);fs=max(float(b.get('font_size',12)) for b in boxes);text=_text(value);est=len(text.replace('\n',' '))*fs*.50
        if est>w*2.8 and '\n' not in text:warnings.append(f'slot {name!r} is much longer than its reference box; auto-fit will shrink/wrap')
    return {'template_id':template_id,'ok':not errors,'errors':errors,'warnings':warnings,'image_slot_count':len(image_slots)}
