"""Optional explicit receipt bridge to ego_agent_infra's documented stage-commit
endpoint. Not a replacement for Nexa/Agent Memory and not a claim of wire-compatible
RXP grants. No remote operation occurs during a normal local run.
"""
from __future__ import annotations
import json,os
from urllib.parse import urlsplit,quote
from urllib.request import Request,urlopen
from .common import Blocked,IntegrityError,canonical

def phase_payload(*,team_id,agent_id,user_id,session_id,task_id,stage_id,messages,evidence,decisions=None,blockers=None,next_actions=None):
    coords=locals().copy()
    for key in ('team_id','agent_id','user_id','session_id','task_id','stage_id'):
        if not isinstance(coords[key],str) or not coords[key].strip():raise IntegrityError('Missing isolation coordinate: '+key)
    if not messages or not any((evidence,decisions,blockers,next_actions)):raise IntegrityError('Stage commit needs messages and an auditable outcome')
    return {k:v for k,v in coords.items() if v is not None}

def commit(base_url:str,payload:dict,*,allow_network=False,token=None,timeout=20):
    if not allow_network:raise Blocked('Remote evidence export requires explicit operator opt-in')
    u=urlsplit(base_url)
    if u.scheme not in ('http','https') or not u.netloc or u.query or u.fragment:raise IntegrityError('Invalid ego base URL')
    if u.scheme=='http' and u.hostname not in ('localhost','127.0.0.1','::1'):raise IntegrityError('Use HTTPS for nonlocal receipt export')
    path='/api/v1/research/agents/'+quote(payload['agent_id'],safe='')+'/stages/commit'
    req=Request(base_url.rstrip('/')+path,data=canonical(payload),headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})},method='POST')
    with urlopen(req,timeout=timeout) as r:
        raw=r.read(2_000_001)
        if len(raw)>2_000_000:raise Blocked('Oversize ego receipt')
        return json.loads(raw)
