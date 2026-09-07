from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUTO=ROOT/'registry'/'image_slots_auto_v14.json'
CURATED=ROOT/'registry'/'image_slots_v13.json'
OUT=ROOT/'registry'/'image_slots_v14.json'

ALIASES={
 'T01_policy_timeline': {
   'figure_1':'overview_figure','photo_1':'input_photo','photo_2':'output_photo',
   'icon_1':'identify_icon','icon_2':'process_icon','icon_3':'artifact_icon',
 },
 'T03_composite_pipeline': {'figure_1':'heritage_photo'},
 'T05_dual_column_model': {'content_image_1':'illustration'},
 'T06_literature_review_matrix': {'content_image_1':'reference_figure'},
 'T07_three_phase_board': {'content_image_1':'reference_figure'},
 'T12_network_views': {'figure_1':'detail_view'},
 'T13_trend_ribbon': {'figure_1':'trend_figure'},
}


def overlap(a,b):
    ix=max(0,min(a['x']+a['width'],b['x']+b['width'])-max(a['x'],b['x']))
    iy=max(0,min(a['y']+a['height'],b['y']+b['height'])-max(a['y'],b['y']))
    inter=ix*iy
    aa=max(1,a['width']*a['height']); bb=max(1,b['width']*b['height'])
    return inter/min(aa,bb)


def main():
    auto=json.loads(AUTO.read_text(encoding='utf-8')); curated=json.loads(CURATED.read_text(encoding='utf-8')) if CURATED.exists() else {}
    out={}
    for tid,data in auto.items():
        merged=[]
        # Curated semantic regions stay important, especially T02 where the source has no native picture placeholders.
        for s in curated.get(tid,{}).get('image_slots',[]):
            c=deepcopy(s); c.setdefault('source','curated_semantic_region'); c.setdefault('role','semantic_region'); c.setdefault('replaceable',True); c.setdefault('background','#ffffff'); c.setdefault('trim','auto'); merged.append(c)
        for s0 in data.get('image_slots',[]):
            # keep native replaceables, and T01's meaningful icon images
            keep=s0.get('replaceable',False) or (tid=='T01_policy_timeline' and s0.get('role')=='icon')
            if not keep: continue
            s=deepcopy(s0)
            s['name']=ALIASES.get(tid,{}).get(s['name'],s['name'])
            s['native']=True; s['replace_original']=True
            s.setdefault('background','#ffffff')
            if s.get('role') in ('figure','content_image','icon'): s.setdefault('trim','auto')
            # If a curated slot is essentially the same physical region, prefer the auto-discovered geometry but preserve curated name if exact alias absent.
            dup=None
            for i,c in enumerate(merged):
                if overlap(s,c)>0.88:
                    dup=i; break
            if dup is not None:
                old=merged[dup]
                # native auto geometry is more trustworthy than hand-entered geometry
                s['name']=old.get('name',s['name'])
                for k in ('fit','padding','clip','radius','stroke','stroke_width'):
                    if k in old: s[k]=old[k]
                merged[dup]=s
            else:
                merged.append(s)
        # T03: old curated slot was experimental and physically wrong; the native PPTX-discovered photo wins.
        if tid=='T03_composite_pipeline':
            merged=[m for m in merged if not (m.get('name')=='heritage_photo' and not m.get('native'))]
        # T02 semantic regions should remain; auto icons are not user image placeholders.
        out[tid]={'reference_page':data.get('reference_page'),'image_slots':merged,'auto_discovered_total':len(data.get('image_slots',[])),'slot_count':len(merged)}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
