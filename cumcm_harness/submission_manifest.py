"""Local immutable file hashes and manual submission timing; never uploads or signs."""
from __future__ import annotations
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from .common import IntegrityError, file_hash, read_json, write_json, digest

SCHEDULE={
 'competition_start':'2026-09-10T18:00:00+08:00',
 'md5_deadline':'2026-09-13T20:00:00+08:00',
 'upload_start':'2026-09-13T20:30:00+08:00',
 'upload_deadline':'2026-09-14T14:00:00+08:00',
 'source':'User-provided official notice, pages 3-5; verify the active competition client and local requirements.',
}


def phase_at(now):
    if now.tzinfo is None:raise IntegrityError('Submission time requires a timezone')
    dt={k:datetime.fromisoformat(v) for k,v in SCHEDULE.items() if k!='source'}
    if now<dt['competition_start']:return 'BEFORE_COMPETITION'
    if now<dt['md5_deadline']:return 'MD5_SUBMISSION_WINDOW'
    if now<dt['upload_start']:return 'MD5_CLOSED_UPLOAD_NOT_OPEN'
    if now<dt['upload_deadline']:return 'UPLOAD_MATCHING_MD5_FILES_ONLY'
    return 'SUBMISSION_WINDOW_CLOSED'


def _hashes(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise IntegrityError('Expected regular deliverable')
    before=path.stat();sha=hashlib.sha256();md5=hashlib.md5(usedforsecurity=False)
    if before.st_size>20_000_000:raise IntegrityError('Deliverable exceeds 20 MB')
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):sha.update(b);md5.update(b)
    after=path.stat()
    if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):
        raise IntegrityError('Deliverable changed while hashing')
    return {'bytes':after.st_size,'sha256':sha.hexdigest(),'md5':md5.hexdigest()}


def seal_deliverables(root,package,mode='practice'):
    root=Path(root).resolve();files={}
    for kind in ('paper','support'):
        rel=package[kind];path=root/rel
        if not path.resolve().is_relative_to(root):raise IntegrityError('Deliverable escapes workspace')
        h=_hashes(path)
        if h['sha256']!=package[kind+'_sha256']:raise IntegrityError('Delivered bytes differ from the accepted package')
        files[rel]=h
    seal={'schema_version':'cumcm-submission/1','files':files,'mode':mode,
          'schedule':SCHEDULE,'official_submission_sent':False,
          'md5_is_submission_compatibility_not_security':True,
          'manual_checks':['操作员在客户端核对并提交MD5；本程序未上传。',
            '文件上传必须与已提交MD5一致，自动保存或再导出也会改变文件。',
            '核对赛区要求、所有源程序、匿名与真实AI人工核验记录。']}
    path=root/'deliverables/submission-manifest.json'
    if path.exists():
        if read_json(path)!=seal:raise IntegrityError('Sealed deliverables changed; create and review a new revision, never silently reseal')
    else:write_json(path,seal)
    return {'path':'deliverables/submission-manifest.json','sha256':file_hash(path),'submitted':False}


def verify_seal(root,seal):
    root=Path(root).resolve()
    for rel,expected in seal['files'].items():
        from .common import safe_rel
        safe_rel(rel);path=root/rel
        if not path.resolve().is_relative_to(root) or _hashes(path)!=expected:
            raise IntegrityError('MD5/SHA256 frozen deliverable mismatch')
    return {'status':'BYTES_MATCH_LOCAL_SEAL','official_submission_verified':False}
