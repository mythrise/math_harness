from __future__ import annotations
import csv,json
from pathlib import Path
from ourwork_v16 import render
from reference_editable_v12 import reference_svg_path
from image_slots_v16 import list_image_slots
ROOT=Path(__file__).resolve().parents[1];REG=json.loads((ROOT/'registry/templates.json').read_text(encoding='utf-8'));rows=[]
for t in REG:
 tid=t['id'];ref=reference_svg_path(tid).read_text(encoding='utf-8');out=render(tid,{},mode='reference_semantic_image',guard=True);slots=list_image_slots(tid)
 rows.append({'template_id':tid,'byte_identity':ref==out,'image_slot_count':slots['slot_count']})
out=ROOT/'tests/v16';out.mkdir(parents=True,exist_ok=True)
with (out/'no_edit_regression.csv').open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
summary={'templates':len(rows),'byte_identity_pass':sum(r['byte_identity'] for r in rows),'templates_with_image_slots':sum(r['image_slot_count']>0 for r in rows),'total_image_slots':sum(r['image_slot_count'] for r in rows)};(out/'v16_regression_summary.json').write_text(json.dumps(summary,indent=2));print(summary)
