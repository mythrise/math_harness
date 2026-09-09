"""Codex transport projection; the original local contract stays authoritative."""
from copy import deepcopy
from jsonschema import Draft202012Validator


def source_bound_schema(name, schema, packet):
    """Constrain source-lane choices at transport without changing local policy.

    These enums guide generation, not evidence acceptance. An invalid source ID
    still reaches the controller's source checker and bounded chunk repair; it
    is never recast here as provider unavailability or automatically corrected.
    No packet-provided schema or arbitrary override is accepted.
    """
    out=deepcopy(schema)
    if name not in ('brief_outline','brief_facts'):return out
    sources=list(dict.fromkeys(u['id'] for u in packet.get('source_units',[])))
    if not sources:return out
    if name=='brief_outline':
        out['properties']['questions']['items']['properties']['source_unit_ids']['items']={'type':'string','enum':sources}
    else:
        available=list(dict.fromkeys([*sources,*[u['id'] for u in packet.get('context_units',[])]]))
        fact=out['properties']['facts']['items']['properties']
        fact['source_unit_ids']['items']={'type':'string','enum':available}
        questions=list(dict.fromkeys(q['id'] for q in packet.get('questions',[])))
        if questions:fact['question_ids']['items']={'type':'string','enum':questions}
        out['properties']['exclusions']['items']['properties']['source_unit_id']={'type':'string','enum':sources}
    return out


def codex_schema(schema):
    if not isinstance(schema, dict):
        return deepcopy(schema)
    out = deepcopy(schema)
    # Observed Codex structured-output rejection. Enforce uniqueness locally.
    out.pop('uniqueItems', None)
    for key in ('anyOf', 'oneOf', 'allOf'):
        if key in out:
            out['anyOf' if key == 'oneOf' else key] = [codex_schema(s) for s in out.pop(key)]
    for key in ('items', 'additionalProperties'):
        if isinstance(out.get(key), dict):
            out[key] = codex_schema(out[key])
    for key in ('$defs', 'definitions'):
        if key in out:
            out[key] = {k: codex_schema(v) for k, v in out[key].items()}
    if 'properties' in out:
        required = set(schema.get('required', []))
        out['properties'] = {
            k: codex_schema(v) if k in required else {'anyOf': [codex_schema(v), {'type': 'null'}]}
            for k, v in schema['properties'].items()
        }
        out['required'] = list(out['properties'])
    return out


def normalize_codex_response(value, schema):
    """Remove only transport-added optional nulls, never unknown or invalid data."""
    if not isinstance(schema, dict):
        return deepcopy(value)
    for key in ('oneOf', 'anyOf'):
        if key in schema:
            matches = []
            for branch in schema[key]:
                candidate = normalize_codex_response(value, branch)
                if Draft202012Validator(branch).is_valid(candidate):
                    matches.append(candidate)
            if matches and (key == 'anyOf' or len(matches) == 1):
                return matches[0]
            return deepcopy(value)
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        required = set(schema.get('required', []))
        return {
            k: normalize_codex_response(v, properties.get(k, {}))
            for k, v in value.items()
            if not (k in properties and k not in required and v is None
                    and not Draft202012Validator(properties[k]).is_valid(None))
        }
    if isinstance(value, list):
        return [normalize_codex_response(v, schema.get('items', {})) for v in value]
    return deepcopy(value)
