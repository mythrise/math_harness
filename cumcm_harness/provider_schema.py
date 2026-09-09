"""Codex transport projection; the original local contract stays authoritative."""
from copy import deepcopy
from jsonschema import Draft202012Validator


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
