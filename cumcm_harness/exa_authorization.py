"""Controller-owned outbound scope checks; no model can sign research approval."""
from __future__ import annotations
import ipaddress
import os
import re
import socket
import urllib.parse
from datetime import datetime, timezone
from . import approval
from .common import Blocked, IntegrityError, digest
from .credentials import get_exa_api_key
from .literature import public_url, validate_query
from .exa_policy import utc


def checked_url(value, *, resolve=False, resolver=socket.getaddrinfo):
    url=public_url(value);parts=urllib.parse.urlsplit(url)
    if parts.port not in (None,80,443):raise IntegrityError('Only standard public web source ports are allowed')
    if any(k.lower() in ('authorization','password','secret','signature','x-api-key') for k,v in urllib.parse.parse_qsl(parts.query)):
        raise IntegrityError('Credential-like source URL refused')
    if resolve:
        try:addresses=resolver(parts.hostname,parts.port or (443 if parts.scheme=='https' else 80),type=socket.SOCK_STREAM)
        except OSError:raise Blocked('Public source DNS could not be verified') from None
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise IntegrityError('Source DNS resolves to a private/reserved address')
    return url


def private_snippets(profiles):
    out=[]
    def collect(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('preview','content'):collect(item)
                elif isinstance(item,(dict,list)):collect(item)
        elif isinstance(value,list):
            for row in value:
                if isinstance(row,list):
                    text=' '.join(str(v) for v in row)
                    if len(text)>=12:out.append(text)
                collect(row)
        elif isinstance(value,str) and len(value)>=12:out.append(value)
    collect(profiles)
    return out


class ExaAuthorization:
    def __init__(self, root, snapshot, *, mode='practice', problem='', profiles=(), identities=(), approved_queries=(),
                 live=False, resolver=socket.getaddrinfo, now=None):
        self.root=root;self.snapshot=snapshot;self.policy=snapshot['policy'];self.mode=mode
        self.problem=problem;self.filenames=[p.get('name',p.get('path','')) for p in profiles]
        self.identities=list(identities);self.rows=private_snippets(list(profiles));self.approved_queries=approved_queries
        self.live=live;self.resolver=resolver;self.now=now or (lambda:datetime.now(timezone.utc))

    def text(self, text, *, query=False):
        if not isinstance(text,str):raise IntegrityError('Outbound text must be a string')
        if query:validate_query(text,problem=self.problem,filenames=self.filenames,
                                approved=self.approved_queries if self.mode=='contest' else None)
        else:
            if re.search(r'://|[\w.+-]+@[\w.-]+|(?:api[_ -]?key|token)\s*[:=]|[\\/]|\d{8,}',text,re.I):
                raise IntegrityError('Sensitive outbound research text')
            key=get_exa_api_key()
            if key and key in text:raise IntegrityError('Credential in outbound research text')
        lower=text.casefold()
        if any(str(x).casefold() in lower for x in self.identities if str(x).strip()):raise IntegrityError('Identity in outbound research text')
        if any(row.casefold() in lower for row in self.rows):raise IntegrityError('Input data row in outbound research text')
        # Catch embedded fragments as well as an entire verbatim query. This is
        # a conservative local filter, not a proof of perfect semantic DLP.
        compact=re.sub(r'\s+',' ',text)
        problem=re.sub(r'\s+',' ',self.problem)
        if len(compact)>=40 and any(compact[i:i+40] in problem for i in range(len(compact)-39)):
            raise IntegrityError('Verbatim problem fragment in outbound research text')
        if re.search(r'ignore (?:all |previous |the )?instructions|send .*?(?:password|api.?key)|忽略.{0,8}指令|发送.{0,12}密钥',lower):
            raise IntegrityError('Outbound instruction/credential redirection refused')

    def require_human(self):
        if self.mode!='contest':return
        scopes=self.policy['authorization_scopes']
        if not scopes:raise Blocked('Contest R2 requires explicit query/profile/date/domain/fetch scopes')
        target=digest({'run_id':self.snapshot['run_id'],'snapshot':self.snapshot,'scopes':scopes})
        pending=approval.request(self.root,'research',target,['scope:'+str(i) for i in range(len(scopes))],
                                 'Review exact abstract queries, date/domain/fetch scope and optional fallbacks before any Exa request')
        signed=approval.require(self.root,'research',pending,os.getenv('CUMCM_OPERATOR_KEY'))
        if not all(item['adopted'] for item in signed['review']['items']):raise Blocked('Every requested research scope must be adopted or removed in a new workspace')

    def check(self, request, *, for_network=False, origin=None, fallback=None):
        body=request['body'];profile=request['profile']
        for query in ([body['query']] if 'query' in body else [])+body.get('additionalQueries',[]):self.text(query,query=True)
        content=body.get('contents',{}) if request['endpoint']=='search' else body
        for field in ('highlights','summary'):
            if isinstance(content.get(field),dict) and 'query' in content[field]:self.text(content[field]['query'],query=True)
        if 'systemPrompt' in body:
            expected=self.policy['profiles']['deep_escalation']['request_template']['systemPrompt']
            if body['systemPrompt']!=expected:raise IntegrityError('systemPrompt must be controller-generated from the frozen policy')
            self.text(body['systemPrompt'])
        if 'outputSchema' in body:
            expected=self.policy['profiles']['deep_escalation']['request_template']['outputSchema']
            if body['outputSchema']!=expected:raise IntegrityError('Use the frozen four-field research navigation schema')
            for value in body['outputSchema']['properties'].values():
                if 'description' in value:self.text(value['description'])
        for url in body.get('urls',[]):checked_url(url,resolve=self.live and for_network,resolver=self.resolver)
        for key in ('includeDomains','excludeDomains'):
            for domain in body.get(key,[]):checked_url('https://'+domain,resolve=False)
        if profile=='implementation' and not body.get('includeDomains') and request['endpoint']=='search':
            raise Blocked('Implementation search requires explicit official repository/documentation domains in the frozen profile')
        if self.mode!='contest':return
        self.require_human()
        parent=origin or request
        queries=[parent['body'].get('query','')]+parent['body'].get('additionalQueries',[])
        for query in queries:
            matches=[scope for scope in self.policy['authorization_scopes'] if
                scope['query']==query and scope['profile']==parent['profile'] and
                scope['include_domains']==parent['body'].get('includeDomains',[]) and
                scope['exclude_domains']==parent['body'].get('excludeDomains',[]) and
                scope['start']==parent['body'].get('startPublishedDate','') and
                scope['end']==parent['body'].get('endPublishedDate','')]
            if len(matches)!=1:raise Blocked('Exa request is outside the signed query/profile/domain/time scope')
            scope=matches[0]
            if for_network and utc(scope['expiry'])<=self.now():raise Blocked('Exa scope approval expired; cached snapshots remain readable')
            if any(url not in scope['fetch_urls'] for url in body.get('urls',[])):raise Blocked('Source fetch is outside signed URL scope')
            if request.get('expanded') and not scope['allow_expanded_fetch']:raise Blocked('Expanded source read is outside signed scope')
            if fallback and not scope['allow_'+fallback+'_fallback']:raise Blocked('Exa fallback was not signed for this scope')
