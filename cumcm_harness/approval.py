"""Digest-bound local HUMAN attestations, not a legal signature or proof of review.
The operator key must be outside agent environments and inaccessible to workers.
"""
from __future__ import annotations
import hmac, hashlib, time
from pathlib import Path
from .common import *

def request(root:Path,stage:str,target:str,items:list[str],reason:str):
    pending={'stage':stage,'target_digest':target,'required_items':sorted(set(items)),'reason':reason,
             'human_led_core_modeling':True,'visual_review_required':stage=='release'}
    write_json(root/'approvals'/f'{stage}.pending.json',pending)
    template={'target_digest':target,'team_led_core_modeling':False,'visual_review_done':False,
              'items':[{'id':i,'adopted':False,'modification':'PENDING','verification':'PENDING'} for i in pending['required_items']],
              'statement':'PENDING: describe the team decision and checks; no personal names in public report'}
    if not (root/'approvals'/f'{stage}.review-template.json').exists():write_json(root/'approvals'/f'{stage}.review-template.json',template)
    return pending

def sign(root:Path,stage:str,review:dict,key:str):
    if len(key)<32:raise IntegrityError('Operator key must contain at least 32 characters')
    pending=read_json(root/'approvals'/f'{stage}.pending.json')
    if review.get('target_digest')!=pending['target_digest']:raise IntegrityError('Human attestation refers to stale artifact')
    if review.get('team_led_core_modeling') is not True:raise IntegrityError('Team must attest leadership of core modeling')
    if stage=='release' and review.get('visual_review_done') is not True:raise IntegrityError('Human visual review required for contest release')
    ids=[x['id'] for x in review.get('items',[])]
    if sorted(ids)!=pending['required_items']:raise IntegrityError('Review every required AI output exactly once')
    if len(review.get('statement',''))<12 or 'PENDING' in canonical(review).decode():raise IntegrityError('Unfilled review template')
    for item in review['items']:
        if type(item.get('adopted'))!=bool or len(item.get('verification','').strip())<8 or not item.get('modification','').strip():
            raise IntegrityError('Each item needs adoption, modification and actual verification details')
    payload={'stage':stage,'review':review,'signed_at':time.time(),'scope_digest':digest(pending),'authority':'LOCAL_HUMAN_ATTESTATION'}
    record={'payload':payload,'signature':hmac.new(key.encode(),canonical(payload),hashlib.sha256).hexdigest()}
    write_json(root/'approvals'/f'{stage}.signed.json',record);return record

def require(root:Path,stage:str,pending:dict,key:str|None):
    p=root/'approvals'/f'{stage}.signed.json'
    if not p.exists() or not key:raise Blocked(f'HUMAN_REVIEW_REQUIRED: {stage}; edit the review-template JSON and use cumcm approve interactively')
    record=read_json(p);payload=record['payload']
    expected=hmac.new(key.encode(),canonical(payload),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,record['signature']) or payload['scope_digest']!=digest(pending):raise IntegrityError('Invalid or stale human signature')
    if payload['review']['target_digest']!=pending['target_digest']:raise IntegrityError('Changed human approval target')
    return payload
