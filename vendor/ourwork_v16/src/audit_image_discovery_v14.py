from __future__ import annotations
import csv,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUTO=ROOT/'registry'/'image_slots_auto_v14.json'


def query_images(svg:Path):
    out=subprocess.check_output(['inkscape','--query-all',str(svg)],text=True,stderr=subprocess.DEVNULL)
    arr=[]
    for line in out.splitlines():
        parts=line.split(',')
        if len(parts)!=5 or not parts[0].startswith('image_'):continue
        try:x,y,w,h=map(float,parts[1:])
        except:continue
        arr.append({'id':parts[0],'x':x,'y':y,'width':w,'height':h})
    return arr


def main():
    data=json.loads(AUTO.read_text(encoding='utf-8'));rows=[]
    for tid,item in data.items():
        page=item['reference_page'];svg=ROOT/'references'/'editable'/f'slide-{page:02d}.svg'
        if not svg.exists():continue
        qs=query_images(svg)
        for s in item['image_slots']:
            if abs(float(s.get('rotation',0)))>0.05:
                rows.append({'template_id':tid,'slot':s['name'],'page':page,'matched_id':'ROTATED_SKIP','max_abs_err_px':'','status':'skip_rotated'});continue
            best=None
            for q in qs:
                errs=[abs(float(s[k])-q[k]) for k in ('x','y','width','height')]
                score=sum(errs);mx=max(errs)
                if best is None or score<best[0]:best=(score,mx,q)
            if best is None:
                rows.append({'template_id':tid,'slot':s['name'],'page':page,'matched_id':'','max_abs_err_px':'','status':'no_query_image'});continue
            _,mx,q=best;status='pass' if mx<=2.5 else ('warn' if mx<=5.0 else 'mismatch')
            rows.append({'template_id':tid,'slot':s['name'],'page':page,'matched_id':q['id'],'max_abs_err_px':round(mx,3),'status':status})
    out=ROOT/'tests'/'v14';out.mkdir(parents=True,exist_ok=True)
    with (out/'image_discovery_audit.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['template_id','slot','page','matched_id','max_abs_err_px','status']);w.writeheader();w.writerows(rows)
    summary={'total':len(rows),'pass':sum(r['status']=='pass' for r in rows),'warn':sum(r['status']=='warn' for r in rows),'mismatch':sum(r['status']=='mismatch' for r in rows),'skip_rotated':sum(r['status']=='skip_rotated' for r in rows),'no_query_image':sum(r['status']=='no_query_image' for r in rows)}
    (out/'image_discovery_audit_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(summary)

if __name__=='__main__':main()
