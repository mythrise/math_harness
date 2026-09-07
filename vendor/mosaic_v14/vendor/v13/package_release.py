from pathlib import Path
import json,hashlib,zipfile,subprocess,sys,datetime,os
R=Path(__file__).resolve().parent;DATA=R.parent

def include(p):
 parts=p.relative_to(R).parts
 return p.is_file()and not any(x in ['__pycache__','.pytest_cache']for x in parts)and p.suffix not in ['.pyc','.nbi','.nbc','.pid']and p.name!='MANIFEST_SHA256.json'
files=sorted(p for p in R.rglob('*')if include(p))
manifest={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in files}
(R/'MANIFEST_SHA256.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
files.append(R/'MANIFEST_SHA256.json')
full=DATA/'MOSAIC_v13_HARNESS_LAB.zip'
with zipfile.ZipFile(full,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
 for p in files:z.write(p,R.name+'/'+str(p.relative_to(R)))
sha=hashlib.sha256(full.read_bytes()).hexdigest();Path(str(full)+'.sha256').write_text(sha+'  '+full.name+'\n')
print(json.dumps({'full_bytes':full.stat().st_size,'full_entries':len(files),'sha256':sha}),flush=True)
light=DATA/'MOSAIC_v13_SOURCE_AND_SUMMARY.zip'
with zipfile.ZipFile(light,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
 for p in files:
  rel=p.relative_to(R)
  if rel.parts[0]!='results'or (len(rel.parts)>1 and rel.parts[1]=='analysis')or p.name in ['DEVELOPMENT_SELECTION.csv','TESTS_ALL.txt']:
   if p.name=='MANIFEST_SHA256.json':continue
   z.write(p,R.name+'/'+str(rel))
 z.writestr(R.name+'/LIGHTWEIGHT_PACKAGE.txt','Source and summary only. Per-run X/F NPZ and full forecast logs are in MOSAIC_v13_HARNESS_LAB.zip. The full-file manifest is intentionally not included in this partial package.\n')
Path(str(light)+'.sha256').write_text(hashlib.sha256(light.read_bytes()).hexdigest()+'  '+light.name+'\n')
# Validate a fresh full extraction and its entire manifest, not a same-directory test.
target=DATA/'mosaic_v13_verified_extract';target.mkdir(exist_ok=True)
with zipfile.ZipFile(full)as z:
 assert z.testzip()is None;z.extractall(target)
E=target/R.name
m=json.loads((E/'MANIFEST_SHA256.json').read_text())
for rel,digest in m.items():assert hashlib.sha256((E/rel).read_bytes()).hexdigest()==digest
with open(DATA/'MOSAIC_v13_UNPACKED_TESTS.txt','w')as f:
 test=subprocess.run([sys.executable,'-m','pytest','-q','tests','vendor/baseline_v10/tests'],cwd=E,stdout=f,stderr=subprocess.STDOUT,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
print('UNPACKED TEST EXIT',test.returncode,flush=True)
info=dict(full_zip=str(full),full_bytes=full.stat().st_size,full_entries=len(files),sha256=sha,light_zip=str(light),light_bytes=light.stat().st_size,zip_integrity=True,manifest_verified_files=len(m),unpacked_test_exit=test.returncode,unpacked_test_output=(DATA/'MOSAIC_v13_UNPACKED_TESTS.txt').read_text(),verified_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(DATA/'MOSAIC_v13_PACKAGE_VERIFICATION.json').write_text(json.dumps(info,indent=2,ensure_ascii=False))
if test.returncode:raise RuntimeError('Unpacked tests failed')
print(json.dumps(info,indent=2),flush=True)
