from pathlib import Path
import hashlib,json,zipfile
R=Path(__file__).resolve().parent;D=R.parent
EXCLUDE_DIRS={'__pycache__','.pytest_cache','.git'}
def eligible(p):return not any(x in EXCLUDE_DIRS for x in p.relative_to(R).parts) and p.suffix not in ('.pyc','.nbc','.nbi') and p.name not in ('SHA256SUMS.txt','PACKAGE_INFO.json')
files=sorted(p for p in R.rglob('*')if p.is_file()and eligible(p))
manifest=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(R).as_posix()+'\n'for p in files)
(R/'SHA256SUMS.txt').write_text(manifest)
files.append(R/'SHA256SUMS.txt')
def small(p):
 rel=p.relative_to(R);parts=rel.parts
 if parts[0]!='results':return p.suffix!='.prof'
 if len(parts)==2:return p.suffix in ('.txt','.json','.csv')
 if parts[1]in ('analysis','references'):return True
 if parts[1]in ('profile','warmup'):return p.suffix in ('.txt','.json')
 return p.name in ('raw.csv','RUN_METADATA.json','ERRORS.json')
info={}
for name,selected in [('MOSAIC_v14_EFFICIENCY_LAB.zip',files),('MOSAIC_v14_SOURCE_AND_SUMMARY.zip',[p for p in files if small(p)and p.name!='SHA256SUMS.txt'])]:
 zpath=D/name
 with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
  for p in selected:z.write(p,arcname=R.name+'/'+p.relative_to(R).as_posix())
 with zipfile.ZipFile(zpath)as z:assert z.testzip()is None;count=len(z.infolist())
 digest=hashlib.sha256(zpath.read_bytes()).hexdigest();zpath.with_suffix(zpath.suffix+'.sha256').write_text(digest+'  '+name+'\n')
 info[name]=dict(bytes=zpath.stat().st_size,entries=count,sha256=digest,integrity_test=True)
(R/'PACKAGE_INFO.json').write_text(json.dumps(info,indent=2));(D/'MOSAIC_v14_PACKAGE_INFO.json').write_text(json.dumps(info,indent=2));print(json.dumps(info,indent=2))
