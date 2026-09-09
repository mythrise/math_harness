"""Opt-in, hash-guarded integration. Modifies ONLY the inspected paper.py.

Backups are local; all workspaces, approval files, keys, configuration and vendors
remain untouched. Installation changes source fingerprint: use a NEW workspace.
"""
from __future__ import annotations
import hashlib, os
from pathlib import Path
from .common import Blocked, save, load, sha256, profile_digest

INSPECTED_BLOB='2e3043de9325704e484351cf400f8df7e8be3815'
OLD_STATEMENT='本研究使用了人工智能工具，辅助问题分析、建模建议、代码生成与调试、实验审查、绘图和论文起草。具体工具版本、主要提示方式、采纳、修改与人工核验情况见支撑材料中的使用详情。'
NEW_STATEMENT='本参赛队在竞赛过程中使用了AI工具，主要用于问题分析、建模建议、代码生成与调试、实验审查、绘图和论文起草，详细使用情况见支撑材料。'
HOOK='''\n# BEGIN CUMCM2026_PAPERKIT_ADAPTER_v1\nfrom cumcm2026.harness_adapter import attach as _paperkit_attach\n_paperkit_attach(globals(), expected_profile_digest='PROFILE_DIGEST_PLACEHOLDER')\n# END CUMCM2026_PAPERKIT_ADAPTER_v1\n'''

def git_blob(data: bytes) -> str:
    return hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()

def make_patch(data: bytes) -> bytes:
    text=data.decode('utf-8')
    if 'CUMCM2026_PAPERKIT_ADAPTER_v1' in text: raise Blocked('Adapter already installed')
    if text.count(OLD_STATEMENT)!=1: raise Blocked('Expected original AI declaration not found exactly once')
    for signature in ('def build_paper(', 'def build_ai_details(', 'def preflight(', 'def compile_tex('):
        if signature not in text: raise Blocked('Harness function contract changed')
    return (text.replace(OLD_STATEMENT,NEW_STATEMENT)+HOOK.replace('PROFILE_DIGEST_PLACEHOLDER',profile_digest())).encode('utf-8')

def install(root: Path, *,apply=False) -> dict:
    root=root.resolve();paper=root/'cumcm_harness/paper.py'
    if not paper.is_file() or paper.is_symlink(): raise Blocked('Expected regular cumcm_harness/paper.py')
    data=paper.read_bytes();observed=git_blob(data)
    if observed!=INSPECTED_BLOB:
        raise Blocked(f'Harness source changed: expected Git blob {INSPECTED_BLOB}, observed {observed}. Re-review before adapting; no files changed.')
    patched=make_patch(data)
    info={'status':'DRY_RUN','changed_file':'cumcm_harness/paper.py','expected_original_blob':INSPECTED_BLOB,
          'before_sha256':hashlib.sha256(data).hexdigest(),'after_sha256':hashlib.sha256(patched).hexdigest(),
          'profile_digest':profile_digest(),'new_workspace_required':True,'credentials_modified':False,'controller_modified':False,
          'warning':'Keep this package installed in the same Python/TeX environment, including any Docker image.'}
    if apply:
        backup=root/'.paperkit-backups'/INSPECTED_BLOB
        if backup.exists(): raise Blocked('Backup directory already exists; inspect previous installation')
        backup.mkdir(parents=True);(backup/'paper.py').write_bytes(data)
        temp=paper.with_suffix('.paperkit.tmp');temp.write_bytes(patched);os.chmod(temp,paper.stat().st_mode);os.replace(temp,paper)
        info['status']='INSTALLED';save(backup/'receipt.json',info)
    return info

def uninstall(root: Path) -> dict:
    root=root.resolve();paper=root/'cumcm_harness/paper.py';backup=root/'.paperkit-backups'/INSPECTED_BLOB
    receipt=load(backup/'receipt.json')
    if sha256(paper)!=receipt['after_sha256']: raise Blocked('Installed file changed; refusing to overwrite later edits')
    original=(backup/'paper.py').read_bytes()
    if git_blob(original)!=INSPECTED_BLOB: raise Blocked('Backup integrity failed')
    paper.write_bytes(original)
    # Archive the used backup so a reviewed reinstall can create a fresh receipt.
    import uuid
    archived=backup.with_name(backup.name+'.restored.'+uuid.uuid4().hex[:12])
    backup.rename(archived)
    return {'status':'RESTORED','original_blob':INSPECTED_BLOB,'new_workspace_required':True}
