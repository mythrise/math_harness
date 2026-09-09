"""Read-only development-data audit. No imputation, training or holdout access."""
from __future__ import annotations
import csv
import hashlib
import math
from pathlib import Path
from .common import IntegrityError, file_hash, safe_rel, digest


def audit_development(root:Path, *, max_rows=100000,max_bytes=50000000):
    if type(max_rows) is not int or max_rows<1 or type(max_bytes) is not int or max_bytes<1:raise IntegrityError('Positive data-audit limits required')
    root=Path(root)
    if not root.is_dir():raise IntegrityError('Development data directory missing')
    rows=[]
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise IntegrityError('Data audit refuses symlinks')
        if not p.is_file():continue
        rel=p.relative_to(root).as_posix();safe_rel(rel)
        item={'file':rel,'sha256':file_hash(p),'bytes':p.stat().st_size,'observed_rows':0,
              'coverage':'METADATA_ONLY','columns':[],'issues':[],'duplicates_observed':0}
        if p.suffix.lower()!='.csv':
            item['issues']=['NEEDS_FORMAT_SPECIFIC_REVIEW'];rows.append(item);continue
        if p.stat().st_size>max_bytes:
            item['issues']=['BYTE_BUDGET_EXCEEDED_NO_CONTENT_AUDIT'];rows.append(item);continue
        try:
            with p.open(encoding='utf-8-sig',newline='') as f:
                reader=csv.reader(f);header=next(reader)
                if not header or len(set(header))!=len(header):raise IntegrityError('Missing/duplicate CSV header')
                stats=[{'name':n,'missing':0,'finite_numeric':0,'text':0,'nonfinite':0,'min':None,'max':None} for n in header]
                seen=set();truncated=False
                for n,row in enumerate(reader):
                    if n>=max_rows:truncated=True;break
                    if len(row)!=len(header):raise IntegrityError('Ragged CSV row')
                    item['observed_rows']+=1
                    key=hashlib.sha256(repr(row).encode()).hexdigest()
                    if key in seen:item['duplicates_observed']+=1
                    seen.add(key)
                    for value,s in zip(row,stats):
                        if not value.strip() or value.strip().casefold() in ('na','null','none','nan'):
                            s['missing']+=1;continue
                        try:x=float(value)
                        except ValueError:s['text']+=1;continue
                        if not math.isfinite(x):s['nonfinite']+=1;continue
                        s['finite_numeric']+=1;s['min']=x if s['min'] is None else min(x,s['min']);s['max']=x if s['max'] is None else max(x,s['max'])
                item.update(columns=stats,coverage='ROW_LIMITED' if truncated else 'COMPLETE_CSV_SCAN')
                if truncated:item['issues'].append('REMAINDER_NOT_AUDITED')
                if any(s['nonfinite'] for s in stats):item['issues'].append('NONFINITE_VALUES')
                if item['duplicates_observed']:item['issues'].append('DUPLICATES_ARE_FLAGS_NOT_AUTOMATIC_DELETIONS')
        except (ValueError,UnicodeError,csv.Error,StopIteration) as exc:
            item['coverage']='PARSE_FAILED';item['issues']=['CSV_PARSE_REQUIRES_REVIEW:'+type(exc).__name__]
        if item['sha256']!=file_hash(p):raise IntegrityError('Data changed during audit')
        rows.append(item)
    if not rows:raise IntegrityError('No development files')
    return {'schema':'development-data-audit/1','manifest':{r['file']:r['sha256'] for r in rows},'files':rows,'input_manifest_digest':digest({r['file']:r['sha256'] for r in rows}),
            'confirmation_accessed':False,'raw_data_modified':False,
            'statistical_validation':'NOT_A_SCIENTIFIC_VALIDITY_TEST'}
