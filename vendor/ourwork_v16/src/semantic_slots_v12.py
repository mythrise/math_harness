from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
REG_PATH = ROOT / 'registry' / 'semantic_slots_v12.json'


def load_slot_registry() -> Dict[str, Any]:
    return json.loads(REG_PATH.read_text(encoding='utf-8'))


def list_template_slots(template_id: str) -> Dict[str, Any]:
    reg = load_slot_registry()
    if template_id not in reg:
        raise KeyError(f'No semantic slot definition for template: {template_id}')
    return reg[template_id]


def expand_slot_groups(template_id: str, slot_groups: Dict[str, Any] | None) -> Dict[str, Any]:
    info = list_template_slots(template_id)
    aliases = info.get('aliases', {})
    expanded: Dict[str, Any] = {}
    for alias, values in (slot_groups or {}).items():
        if alias not in aliases:
            raise KeyError(f'Unknown slot group {alias!r} for {template_id}. Available: {sorted(aliases)}')
        names = aliases[alias]
        if not isinstance(values, (list, tuple)):
            raise TypeError(f'Slot group {alias!r} must be a list/tuple, got {type(values).__name__}')
        if len(values) > len(names):
            raise ValueError(f'Slot group {alias!r} accepts at most {len(names)} values, got {len(values)}')
        for name, value in zip(names, values):
            expanded[name] = value
    return expanded


def _value_and_options(value: Any) -> Tuple[str, Dict[str, Any]]:
    if isinstance(value, dict):
        if 'text' in value:
            text = value['text']
        elif 'value' in value:
            text = value['value']
        else:
            raise KeyError('Semantic slot object values must contain "text" or "value"')
        opts = {k:v for k,v in value.items() if k not in ('text','value')}
        return str(text), opts
    return str(value), {}


def expand_slots(
    template_id: str,
    slots: Dict[str, Any] | None = None,
    slot_groups: Dict[str, Any] | None = None,
    slot_options: Dict[str, Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    direct = dict(slots or {})
    direct.update(expand_slot_groups(template_id, slot_groups))
    info = list_template_slots(template_id)
    defs = {s['name']: s for s in info.get('slots', [])}
    unknown = [k for k in direct if k not in defs]
    if unknown:
        raise KeyError(f'Unknown semantic slots for {template_id}: {unknown}. Available: {sorted(defs)}')
    opts_map = slot_options or {}
    unknown_opts = [k for k in opts_map if k not in defs]
    if unknown_opts:
        raise KeyError(f'Unknown slot_options keys for {template_id}: {unknown_opts}')

    reps: List[Dict[str, Any]] = []
    for name, value in direct.items():
        d = defs[name]
        text, inline_opts = _value_and_options(value)
        # Semantic no-op optimization: unchanged values leave the Reference SVG byte-identical.
        if text == str(d.get('default_text', '')) and not inline_opts and not opts_map.get(name):
            continue
        rep = {'replace': text, 'slot_name': name}
        rep.update(d.get('target', {}))
        rep.update(d.get('render', {}))
        rep.update(opts_map.get(name, {}))
        rep.update(inline_opts)
        reps.append(rep)
    return reps


def example_config(template_id: str) -> Dict[str, Any]:
    info = list_template_slots(template_id)
    return {'slots': {slot['name']: slot['default_text'] for slot in info.get('slots', [])}}
