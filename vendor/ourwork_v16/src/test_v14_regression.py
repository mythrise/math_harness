from __future__ import annotations
import csv,json,hashlib
from pathlib import Path
from ourwork_v14 import render
from reference_editable_v12 import reference_svg_path
from image_slots_v14 import list_image_slots

ROOT=Path(__file__).resolve().parents[1]
REG=json.loads((ROOT/'registry'/'templates.json').read_text(encoding='utf-8'))
rows=[]
for t in REG:
    tid=t['id'];ref=reference_svg_path(tid).read_text(encoding='utf-8');out=render(tid,{},mode='reference_semantic_image',guard=True)
    rows.append({'template_id':tid,'byte_identity':ref==out,'image_slot_count':list_image_slots(tid)['slot_count']})
outdir=ROOT/'tests'/'v14';outdir.mkdir(parents=True,exist_ok=True)
with (outdir/'no_edit_regression.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['template_id','byte_identity','image_slot_count']);w.writeheader();w.writerows(rows)
summary={'templates':len(rows),'byte_identity_pass':sum(r['byte_identity'] for r in rows),'templates_with_image_slots':sum(r['image_slot_count']>0 for r in rows),'total_image_slots':sum(r['image_slot_count'] for r in rows)}
(outdir/'v14_regression_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(summary)
