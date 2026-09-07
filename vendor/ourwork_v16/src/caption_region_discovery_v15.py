from __future__ import annotations
import argparse,json,re
from pathlib import Path
from typing import Any,Dict,List,Tuple
from lxml import etree
from pptx import Presentation

NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
CAPTION_RE=re.compile(r'^\(([a-z0-9]+)\)',re.I)


def loc(el):return etree.QName(el).localname

def fa(el,k,d=0):
 try:return float(el.get(k))
 except:return float(d)

def text_of(el):return ' '.join(t.strip() for t in el.xpath('.//*[local-name()="t"]/text()') if t.strip()).strip()

def xfrm(el,kind):
 path='p:grpSpPr/a:xfrm' if kind=='grpSp' else 'p:spPr/a:xfrm'
 x=el.find(path,NS)
 if x is None:return None
 off=x.find('a:off',NS);ext=x.find('a:ext',NS)
 if off is None or ext is None:return None
 return fa(off,'x'),fa(off,'y'),fa(ext,'cx'),fa(ext,'cy')


def collect(slide,sw,sh):
 shapes=[]
 def walk(el,ax=1,ay=1,bx=0,by=0,depth=0):
  kind=loc(el)
  if kind=='grpSp':
   xx=el.find('p:grpSpPr/a:xfrm',NS)
   if xx is None:return
   off=xx.find('a:off',NS);ext=xx.find('a:ext',NS);co=xx.find('a:chOff',NS);ce=xx.find('a:chExt',NS)
   if None in (off,ext,co,ce):return
   sx=fa(ext,'cx')/max(1,fa(ce,'cx'));sy=fa(ext,'cy')/max(1,fa(ce,'cy'))
   nax=ax*sx;nay=ay*sy;nbx=ax*(fa(off,'x')-fa(co,'x')*sx)+bx;nby=ay*(fa(off,'y')-fa(co,'y')*sy)+by
   for ch in el:
    if loc(ch) in ('sp','pic','grpSp','cxnSp','graphicFrame'):walk(ch,nax,nay,nbx,nby,depth+1)
   return
  if kind!='sp':return
  b=xfrm(el,kind)
  if not b:return
  x,y,w,h=b;X=(ax*x+bx)/sw*960;Y=(ay*y+by)/sh*540;W=abs(ax*w)/sw*960;H=abs(ay*h)/sh*540
  txt=text_of(el);geom=el.find('p:spPr/a:prstGeom',NS);prst=geom.get('prst') if geom is not None else ''
  shapes.append({'x':X,'y':Y,'width':W,'height':H,'text':txt,'prst':prst or '','depth':depth})
 sp=slide.element.find('.//p:spTree',NS)
 for ch in sp:
  if loc(ch) in ('sp','pic','grpSp','cxnSp','graphicFrame'):walk(ch)
 return shapes


def discover(pptx,refs):
 ppt=Presentation(str(pptx));sw,sh=float(ppt.slide_width),float(ppt.slide_height);page_to_tid={v:k for k,v in refs.items()};out={}
 for page,slide in enumerate(ppt.slides,start=1):
  if page not in page_to_tid:continue
  shapes=collect(slide,sw,sh);caps=[]
  for s in shapes:
   m=CAPTION_RE.match(s['text'])
   if m:caps.append((m.group(1).lower(),s))
  containers=[s for s in shapes if s['width']>350 and s['height']>90 and (s['width']*s['height'])>60000]
  regions=[]
  for label,c in caps:
   cx=c['x']+c['width']/2;cy=c['y']+c['height']/2
   cand=[]
   for con in containers:
    if con['x']<=cx<=con['x']+con['width'] and con['y']<=cy<=con['y']+con['height']:
     cand.append(con)
   if not cand:continue
   con=min(cand,key=lambda z:z['width']*z['height'])
   # caption-guided visual region immediately above the caption, bounded by its parent panel.
   desired_w=max(120,c['width']*1.12)
   x=max(con['x']+12,cx-desired_w/2);right=min(con['x']+con['width']-12,cx+desired_w/2);w=max(80,right-x)
   y=con['y']+max(12,con['height']*.10)
   # Keep inferred image regions below stage-title bars inside the same container.
   headers=[z for z in shapes if con['x']<=z['x']+z['width']/2<=con['x']+con['width'] and con['y']<=z['y']<=con['y']+con['height']*.28 and 'stage' in z['text'].lower()]
   if headers:
    y=max(y,max(z['y']+z['height'] for z in headers)+7)
   bottom=c['y']-7;h=bottom-y
   if h<35:continue
   regions.append({'name':f'panel_{label}','caption':c['text'],'x':round(x,3),'y':round(y,3),'width':round(w,3),'height':round(h,3),'fit':'contain','trim':'auto','padding':4,'clip':'rect','background':'#ffffff','role':'caption_region','replaceable':True,'source':'pptx_caption_auto','caption_label':label})
  out[page_to_tid[page]]={'reference_page':page,'regions':regions}
 return out


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pptx',required=True);ap.add_argument('--templates-json',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
 arr=json.loads(Path(a.templates_json).read_text(encoding='utf-8'));refs={x['id']:int(x['reference_page']) for x in arr};Path(a.out).write_text(json.dumps(discover(a.pptx,refs),ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
