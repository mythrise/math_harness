from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
V14=ROOT/'registry'/'image_slots_v14.json'
CAP=ROOT/'registry'/'caption_regions_auto_v15.json'
OUT=ROOT/'registry'/'image_slots_v15.json'


def main():
    base=json.loads(V14.read_text(encoding='utf-8'));caps=json.loads(CAP.read_text(encoding='utf-8'))
    out=deepcopy(base)
    # Caption-derived semantic regions supersede the hand-entered T02 regions.
    t2=[r for r in caps.get('T02_two_stage_pipeline',{}).get('regions',[]) if r['width']>=120 and r['height']>=60 and r['name'] in {'panel_a','panel_b','panel_c','panel_d','panel_e'}]
    if t2:
        out.setdefault('T02_two_stage_pipeline',{})['image_slots']=t2
        out['T02_two_stage_pipeline']['slot_count']=len(t2)
        out['T02_two_stage_pipeline']['caption_auto']=True
    # T03: keep the actual native picture plus caption-inferred optional panel replacements.
    t3=out.setdefault('T03_composite_pipeline',{}).get('image_slots',[])
    existing={s['name'] for s in t3}
    for r in caps.get('T03_composite_pipeline',{}).get('regions',[]):
        if r['width']>=140 and r['height']>=70 and r['name'] not in existing:
            rr=deepcopy(r); rr['optional']=True; t3.append(rr)
    out['T03_composite_pipeline']['image_slots']=t3;out['T03_composite_pipeline']['slot_count']=len(t3)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
