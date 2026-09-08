"""R2 restricted REST request validator, invoked before auth/network execution.

Not a complete Exa OpenAPI validator, HTTP client, privacy filter, or harness.
No network or credential access. Validate BEFORE runtime auth injection.
Additional constraints (220 query characters, 2 variants, no subpages) are our
proposed policy, not Exa API limits. Integrate with the actual controller gates.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

BETA = 'dynamic-highlights-2026-08-28'
TYPES = {'auto', 'fast', 'instant', 'deep-lite', 'deep', 'deep-reasoning'}
CATEGORIES = {'company', 'people', 'publication', 'news', 'personal site', 'financial report'}
CONTENT_KEYS = {'text', 'highlights', 'summary', 'livecrawlTimeout', 'maxAgeHours',
                'subpages', 'subpageTarget', 'extras'}
SEARCH_KEYS = {'query', 'type', 'stream', 'numResults', 'category', 'userLocation',
               'includeDomains', 'excludeDomains', 'startPublishedDate',
               'endPublishedDate', 'moderation', 'additionalQueries',
               'systemPrompt', 'outputSchema', 'compliance', 'contents'}

class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def keys(value: Any, allowed: set[str], location: str) -> None:
    require(isinstance(value, dict), f'{location} must be an object')
    require(not (set(value) - allowed), f'{location}: unknown/unsupported field')


def integer(value: Any, minimum: int, maximum: int, location: str) -> None:
    require(type(value) is int and minimum <= value <= maximum, f'{location}: invalid integer')


def text(value: Any, minimum: int, maximum: int, location: str) -> None:
    require(isinstance(value, str) and minimum <= len(value.strip()) <= maximum,
            f'{location}: invalid text')


def nonnull(value: Any) -> None:
    require(value is not None, 'Omit optional fields instead of emitting null')
    if isinstance(value, float):
        require(math.isfinite(value), 'Nonfinite request value')
    if isinstance(value, dict):
        for child in value.values():
            nonnull(child)
    elif isinstance(value, list):
        for child in value:
            nonnull(child)


def flat_output_schema(schema: Any) -> None:
    """Our deliberately small subset: root object, scalars or arrays of strings."""
    keys(schema, {'type', 'properties', 'required', 'additionalProperties'}, 'outputSchema')
    require(schema.get('type') == 'object', 'Use a flat object in this policy')
    props = schema.get('properties')
    require(isinstance(props, dict) and 1 <= len(props) <= 10, '1..10 total properties required')
    require(not ({str(k).lower() for k in props} & {'citations', 'citation', 'confidence', 'verdict'}),
            'Use provider grounding separately; no citation/confidence/verdict fields')
    required = schema.get('required', [])
    if 'additionalProperties' in schema:
        require(type(schema['additionalProperties']) is bool, 'additionalProperties must be Boolean')
    require(isinstance(required, list) and all(isinstance(k, str) for k in required),
            'required must be a string list')
    require(len(required) == len(set(required)) and set(required) <= set(props), 'Invalid required set')
    for child in props.values():
        keys(child, {'type', 'items', 'description'}, 'property')
        kind = child.get('type')
        if 'description' in child:
            text(child['description'], 1, 1000, 'outputSchema description')
        require(kind in {'string', 'number', 'integer', 'boolean', 'array'}, 'Nested object is outside this policy')
        if kind == 'array':
            require(child.get('items') == {'type': 'string'}, 'Only flat arrays of strings here')
        else:
            require('items' not in child, 'Only arrays have items')


def validate_content(content: Any, headers: dict, *, endpoint: str) -> None:
    keys(content, CONTENT_KEYS, 'content parameters')
    dynamic = False
    if 'text' in content:
        val = content['text']
        require(type(val) is bool or isinstance(val, dict), 'Invalid text mode')
        if isinstance(val, dict):
            keys(val, {'maxCharacters', 'includeHtmlTags', 'verbosity', 'includeSections', 'excludeSections'}, 'text')
            if 'maxCharacters' in val:
                integer(val['maxCharacters'], 1, 60000, 'text.maxCharacters (local cap)')
            if 'includeHtmlTags' in val:
                require(type(val['includeHtmlTags']) is bool, 'includeHtmlTags must be Boolean')
            if 'verbosity' in val:
                require(val['verbosity'] in ('compact', 'standard', 'full'), 'Invalid verbosity')
            for key in ('includeSections', 'excludeSections'):
                if key in val:
                    require(isinstance(val[key], list) and all(x in {'header','navigation','banner','body','sidebar','footer','metadata'} for x in val[key]), 'Invalid text section list')
    if 'highlights' in content:
        val = content['highlights']
        require(type(val) is bool or isinstance(val, dict), 'Invalid highlights mode')
        if isinstance(val, dict):
            keys(val, {'query', 'dynamic', 'maxCharacters'}, 'highlights')
            if 'query' in val:
                text(val['query'], 4, 220, 'highlights.query')
            if 'dynamic' in val:
                require(type(val['dynamic']) is bool, 'dynamic must be Boolean')
            dynamic = val.get('dynamic') is True
            require(not (dynamic and 'maxCharacters' in val), 'dynamic:true conflicts with highlights.maxCharacters')
            if 'maxCharacters' in val:
                integer(val['maxCharacters'], 1, 60000, 'highlights.maxCharacters')
    if dynamic:
        require(endpoint == 'search', 'This policy only enables dynamic highlights on search')
        require(headers.get('Exa-Beta') == BETA, 'Dynamic Highlights requires the exact beta header')
    else:
        require('Exa-Beta' not in headers, 'Do not attach preview header to stable requests')
    if 'summary' in content:
        require(content['summary'] is False, 'Generated summaries are disabled in this policy')
    if 'maxAgeHours' in content:
        integer(content['maxAgeHours'], -1, 1_000_000, 'maxAgeHours')
    if 'livecrawlTimeout' in content:
        integer(content['livecrawlTimeout'], 1, 120_000, 'livecrawlTimeout milliseconds')
    if 'subpages' in content:
        integer(content['subpages'], 0, 0, 'subpages disabled by this policy')
    if 'subpageTarget' in content:
        raise ContractError('Subpage crawling requires an explicit new policy, not this profile')
    if 'extras' in content:
        keys(content['extras'], {'links', 'imageLinks'}, 'extras')
        for key, val in content['extras'].items():
            integer(val, 0, 20, 'extras.' + key)


def validate_request(endpoint: str, body: Any, public_headers: Any) -> None:
    """Checks wire shape, known options, and local policy invariants only."""
    require(endpoint in ('search', 'contents'), 'Unsupported endpoint')
    keys(public_headers, {'Content-Type', 'Exa-Beta'}, 'public_headers: auth is injected later')
    require(public_headers.get('Content-Type') == 'application/json', 'Require JSON Content-Type')
    nonnull(body)
    if endpoint == 'contents':
        keys(body, CONTENT_KEYS | {'urls'}, 'contents request')
        urls = body.get('urls')
        require(isinstance(urls, list) and 1 <= len(urls) <= 4, '1..4 URLs per fetch batch in this policy')
        require(all(isinstance(u, str) and u.startswith(('https://','http://')) for u in urls), 'HTTP(S) URLs required; apply real privacy/SSRF gate separately')
        require(len(urls) == len(set(urls)), 'Duplicate URL within batch')
        validate_content({k:v for k,v in body.items() if k != 'urls'}, public_headers, endpoint=endpoint)
        return
    keys(body, SEARCH_KEYS, 'search request')
    text(body.get('query'), 4, 220, 'query')
    kind = body.get('type', 'auto')
    require(kind in TYPES, 'Unsupported/legacy search type')
    require(body.get('stream', False) is False, 'SSE disabled: controller expects complete JSON')
    integer(body.get('numResults', 10), 1, 100, 'numResults')
    if 'category' in body:
        require(body['category'] in CATEGORIES, 'Unsupported/legacy category')
        if body['category'] in ('company','people'):
            require(not ({'startPublishedDate','endPublishedDate','excludeDomains'} & set(body)), 'Incompatible category filters')
    for name in ('includeDomains','excludeDomains'):
        if name in body:
            require(isinstance(body[name], list) and 1 <= len(body[name]) <= 1200 and all(isinstance(d,str) and d.strip() for d in body[name]), 'Invalid domain filter')
    if 'additionalQueries' in body:
        require(kind in {'deep-lite','deep','deep-reasoning'}, 'additionalQueries only in deep variants')
        require(isinstance(body['additionalQueries'],list) and 1 <= len(body['additionalQueries']) <= 2, '1..2 query variations in local policy')
        for query in body['additionalQueries']:
            text(query, 4, 220, 'additionalQueries')
    dates = {}
    for name in ('startPublishedDate','endPublishedDate'):
        if name in body:
            require(isinstance(body[name],str), 'ISO8601 date string required')
            try:
                parsed = datetime.fromisoformat(body[name].replace('Z','+00:00'))
            except ValueError:
                raise ContractError('Invalid ISO8601 date') from None
            dates[name] = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    if len(dates) == 2:
        require(dates['startPublishedDate'] <= dates['endPublishedDate'], 'Reversed date bounds')
    if 'outputSchema' in body:
        flat_output_schema(body['outputSchema'])
    if 'systemPrompt' in body:
        text(body['systemPrompt'], 1, 4000, 'systemPrompt')
    require('compliance' not in body, 'No enterprise compliance claim in this modeling profile')
    if 'moderation' in body:
        require(type(body['moderation']) is bool, 'moderation must be Boolean')
    if 'userLocation' in body:
        require(isinstance(body['userLocation'],str) and len(body['userLocation'])==2, 'Country code required')
    validate_content(body.get('contents', {}), public_headers, endpoint=endpoint)


def dynamic_fallback(body: dict, headers: dict, reason: str) -> tuple[dict, dict]:
    """A shape-only fallback. Caller must authorize, count, log, and execute it."""
    require(reason == 'UNSUPPORTED_DYNAMIC_HIGHLIGHTS', 'Only explicit capability errors can request this fallback')
    validate_request('search', body, headers)
    current_highlights = body.get('contents', {}).get('highlights')
    require(isinstance(current_highlights, dict) and current_highlights.get('dynamic') is True,
            'Not a dynamic request')
    out, hdr = copy.deepcopy(body), dict(headers)
    highlight = out['contents']['highlights']
    highlight.pop('dynamic')
    highlight['maxCharacters'] = 2000
    out['numResults'] = min(out.get('numResults', 10), 6)
    hdr.pop('Exa-Beta', None)
    validate_request('search', out, hdr)
    return out, hdr


def request_shape_digest(endpoint: str, body: dict, public_headers: dict) -> str:
    """Demonstrates including nonsecret feature headers. Not a full cache key."""
    validate_request(endpoint, body, public_headers)
    encoded = json.dumps({'endpoint':endpoint,'body':body,'feature_headers':public_headers},
                         sort_keys=True, ensure_ascii=False, separators=(',',':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()
