"""Source snapshots preserve missing excerpts, versions, offsets and read limits."""
from __future__ import annotations
import copy
import re
from datetime import datetime, timezone
from .common import IntegrityError, digest
from .literature import public_url, check_audit
from .exa_policy import utc


def work_identity(item, url):
    doi=item.get('doi')
    if not doi:
        match=re.search(r'(?:doi\.org/|/doi/(?:abs/|full/)?)(10\.\d{4,9}/[^?#\s]+)',url,re.I)
        if match:doi=match.group(1)
    if isinstance(doi,str) and re.fullmatch(r'10\.\d{4,9}/\S+',doi,re.I):
        return 'doi:'+doi.lower().rstrip('.,;'),'DOI_IDENTIFIER_NOT_INDEPENDENT_WORK_VERIFICATION',item.get('version') or ''
    match=re.search(r'arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5}|[a-z.-]+/\d{7})(v\d+)?',url,re.I)
    if match:return 'arxiv:'+match.group(1),'ARXIV_BASE_ID',match.group(2) or 'VERSION_UNSPECIFIED'
    normalized=re.sub(r'\W+',' ',str(item.get('title','')).lower()).strip()
    authors=str(item.get('author') or item.get('authors') or '').lower()
    year=str(item.get('publishedDate') or '')[:4]
    return 'candidate:'+digest([normalized,authors,year])[:24],'TITLE_AUTHOR_YEAR_REQUIRES_REVIEW',str(item.get('version') or '')


def temporal_state(item, cutoff):
    published=item.get('publishedDate') or ''
    if not isinstance(published,str):raise IntegrityError('Publication date must be text or absent')
    if not published:return 'UNKNOWN_DATE'
    try:
        date=datetime.fromisoformat(published.replace('Z','+00:00'))
        if date.tzinfo is None:date=date.replace(tzinfo=timezone.utc)
    except ValueError:return 'UNKNOWN_DATE'
    return 'KNOWN_FUTURE_EXCLUDED' if date>utc(cutoff) else 'ESTIMATED_DATE_VERSION_UNVERIFIED'


def normalize_sources(payload, request, snapshot, *, live, response_digest=None,provenance=None,retrieved_at=None):
    if not isinstance(payload,dict) or not isinstance(payload.get('results'),list):raise IntegrityError('Exa results must be a list')
    body=request['body'];content=body.get('contents',{}) if request['endpoint']=='search' else body
    mode=content.get('highlights');dynamic=isinstance(mode,dict) and mode.get('dynamic') is True
    text_mode=content.get('text');text_limit=text_mode.get('maxCharacters',60000) if isinstance(text_mode,dict) else 60000
    high_limit=mode.get('maxCharacters',60000) if isinstance(mode,dict) else 60000
    result=[];seen=set()
    for item in payload['results']:
        if not isinstance(item,dict):raise IntegrityError('Malformed Exa result')
        url=public_url(item.get('url',''))
        text=item.get('text') or ''
        if not isinstance(text,str):raise IntegrityError('Exa source text must be a string')
        highlights=item.get('highlights') or []
        if not isinstance(highlights,list) or any(not isinstance(x,str) for x in highlights):raise IntegrityError('Malformed Exa highlights')
        original_length=len(text);text=text[:text_limit]
        # Original text and extractive highlights are distinct; neither summary
        # nor output.content can be copied into the text slot.
        excerpt='\n'.join(highlights)[:high_limit]
        work,basis,version=work_identity(item,url)
        proof=(provenance or {}).get(digest(item),{})
        identity={'source_url':url,'text_hash':digest(text),'highlights_hash':digest(excerpt),
                  'version':version,'published':item.get('publishedDate') or '',
                  'request_digest':digest(request),'response_digest':proof.get('response_digest') or response_digest or digest(payload),
                  'policy_digest':snapshot['policy_digest'],'cutoff':snapshot['research_cutoff']}
        snap=digest(identity)
        if snap in seen:continue
        seen.add(snap)
        kind='SOURCE_TEXT' if text else 'EXTRACTED_HIGHLIGHT' if excerpt else 'METADATA_ONLY'
        result.append({'id':'exa_'+snap[:24],'source_id':'exa_source_'+digest(url)[:20],
            'snapshot_id':snap,'work_id':work,'work_identity_basis':basis,'publication_version':version,
            'url':url,'title':str(item.get('title') or 'Untitled source'),
            'author':item.get('author') or item.get('authors') or '',
            'published':item.get('publishedDate') or '',
            'temporal_status':temporal_state(item,snapshot['research_cutoff']),
            'research_cutoff':snapshot['research_cutoff'],'text':text,'content_sha256':digest(text),
            'highlights':highlights,'highlight_text':excerpt,'highlight_mode':'DYNAMIC' if dynamic else 'PER_SOURCE',
            'generated_summary':item.get('summary'),'provider_output':copy.deepcopy(payload.get('output')),
            'generated_content_policy':'NAVIGATION_ONLY_NEVER_QUOTE_SOURCE',
            'evidence_kind':kind,'status':'CONTENT_LOCATED' if text else 'RETRIEVED_NOT_VALIDATED',
            'source_coverage_state':'BOUNDED_SOURCE_TEXT' if text else 'EXTRACTED_HIGHLIGHT_ONLY' if excerpt else 'RETRIEVED_NO_EXCERPT',
            'coverage':{'returned_text_characters':original_length,'stored_text_characters':len(text),
                        'requested_text_limit':text_limit if text_mode else None,
                        'limit_hit':bool(text_mode) and original_length>=text_limit,
                        'full_source_read':False,'text_offsets':[0,len(text)],
                        'provider_may_have_omitted_tables_figures_or_other_sections':True},
            'query_digest':digest(body.get('query',body.get('urls',[]))),
            'request_id':proof.get('request_id') or payload.get('requestId') or 'UNKNOWN','response_digest':identity['response_digest'],
            'retrieved_at':retrieved_at,
            'retrieval':'LIVE_EXA_HTTP' if live else 'FIXTURE_EXA_TRANSPORT'})
    # Keep versions and conflicting hashes as separate snapshots. A shared work
    # identity is a deduplication hint, never independent corroboration.
    works={}
    for source in result:works.setdefault(source['work_id'],[]).append(source)
    for group in works.values():
        for source in group:
            source['same_work_snapshots']=[s['snapshot_id'] for s in group]
            source['independent_source_count']=1
            source['version_or_content_conflict']=len({(s['publication_version'],s['content_sha256']) for s in group if s['text']})>1
    return result


def merge_sources(*collections):
    sources={}
    for collection in collections:
        for source in collection:
            key=source['id']
            if key in sources and sources[key]['snapshot_id']!=source['snapshot_id']:raise IntegrityError('Exa snapshot ID collision')
            sources[key]=copy.deepcopy(source)
    result=list(sources.values());works={}
    for source in result:works.setdefault(source['work_id'],[]).append(source)
    for group in works.values():
        conflict=len({(s['publication_version'],s['content_sha256']) for s in group if s['text']})>1
        for source in group:
            source['same_work_snapshots']=[s['snapshot_id'] for s in group]
            source['independent_source_count']=1
            source['version_or_content_conflict']=conflict
    return result


def source_packet(sources, max_characters=40000, *, windows=None):
    """Bound source characters explicitly; metadata is retained for every source.

    Prefix offsets are supplied so a critic can locate an exact original quote.
    A missing passage is a read-request obligation, never silently deemed absent.
    """
    if type(max_characters) is not int or not 1<=max_characters<=40000:raise IntegrityError('Invalid Exa packet limit')
    remaining=max_characters;out=[]
    for i,source in enumerate(sources):
        cap=remaining//max(1,len(sources)-i)
        text=source.get('text') or source.get('highlight_text') or ''
        window=(windows or {}).get(source['id'],source.get('requested_window',{}))
        start=window.get('offset',0)
        section=window.get('section')
        if section is not None:
            if not isinstance(section,str) or not section or section not in text:raise IntegrityError('Requested source section is absent')
            start=text.index(section)
        if type(start) is not int or not 0<=start<=len(text):raise IntegrityError('Invalid requested source offset')
        selected=text[start:start+cap];remaining-=len(selected)
        row={k:copy.deepcopy(v) for k,v in source.items() if k not in ('text','highlights','highlight_text','generated_summary','provider_output')}
        row.update(text=selected,packet_coverage={'characters':len(selected),'source_characters':len(text),
                   'truncated':len(selected)<len(text),'offset_start':start,'offset_end':start+len(selected),
                   'kind':'SOURCE_TEXT' if source.get('text') else 'EXTRACTED_HIGHLIGHT'})
        if source.get('generated_summary') or source.get('provider_output'):
            row['generated_navigation_available']=True
        out.append(row)
    return out


def locate_audit(cards, audit, sources):
    known={s['id']:s for s in sources};legacy=copy.deepcopy(audit);legacy.pop('clarification_responses',None);locations=[]
    for check in legacy['checks']:
        for ref in check['evidence']:
            source=known.get(ref['source_id'])
            if not source:raise IntegrityError('Unknown R2 source snapshot')
            if ref.pop('snapshot_id',None)!=source['snapshot_id']:raise IntegrityError('Stale Exa evidence snapshot')
            start=ref.pop('quote_start',None);end=ref.pop('quote_end',None)
            if type(start) is not int or type(end) is not int or not 0<=start<end<=len(source['text']):
                raise IntegrityError('Invalid original quote offsets')
            if source['evidence_kind']!='SOURCE_TEXT' or source['text'][start:end]!=ref['quote']:
                raise IntegrityError('Quote must locate exact source text, never a summary/highlight/synthesis')
            if source['temporal_status']=='KNOWN_FUTURE_EXCLUDED':raise IntegrityError('Future source cannot support an as-of research run')
            locations.append({'hypothesis_id':check['hypothesis_id'],**ref,'snapshot_id':source['snapshot_id'],
                              'quote_start':start,'quote_end':end,'source_sha256':source['content_sha256'],
                              'semantic_entailment':'REQUIRES_INDEPENDENT_REVIEW'})
    required_tests=check_audit(cards,legacy,sources)
    return required_tests,locations


def citation_export(source, locations):
    """The release gets short located quotations and metadata, not entire papers."""
    refs=[r for r in locations if r['source_id']==source['id']]
    return {k:copy.deepcopy(source[k]) for k in ('id','source_id','snapshot_id','work_id','url','title',
        'author','published','publication_version','temporal_status','content_sha256','coverage')} | {'quoted_evidence':refs}
