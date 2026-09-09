"""Exact source-clause accounting; semantic completeness still needs independent review."""
import re
from .common import IntegrityError,digest


def source_units(blocks):
    units=[]
    for b in blocks:
        # Clauses are navigation units, not a claim that punctuation proves semantics.
        for m in re.finditer(r'[^。！？；;，,\n]+[。！？；;，,\n]*',b['text']):
            if not m.group().strip():continue
            units.append({'id':'unit_'+digest([b['id'],m.start(),m.end()])[:24],
                'block_id':b['id'],'start':m.start(),'end':m.end(),'quote':m.group()})
    return units


def check_coverage(rows,blocks,items):
    units={u['id']:u for u in source_units(blocks)};known={i['id']:i for i in items}
    ids=[r['unit_id'] for r in rows]
    if len(ids)!=len(set(ids)) or set(ids)!=set(units):raise IntegrityError('Every source clause requires exactly one coverage disposition')
    used=set()
    for r in rows:
        u=units[r['unit_id']];refs=r['item_ids']
        if len(refs)!=len(set(refs)) or not set(refs)<=known.keys():raise IntegrityError('Unknown or duplicate coverage item')
        if r['disposition'] in ('EXTRACTED','MERGED'):
            if not refs:raise IntegrityError('Extracted clause needs anchored items')
            spans=[]
            for key in refs:
                item=known[key]
                if item['block_id']!=u['block_id'] or item['start']>=u['end'] or item['end']<=u['start']:raise IntegrityError('Coverage item does not overlap its original clause')
                spans.append((item['start'],item['end']));used.add(key)
            for offset,char in enumerate(u['quote'],u['start']):
                if char.isalnum() and not any(a<=offset<z for a,z in spans):raise IntegrityError('Extraction omitted substantive source characters; retain a separate disposition')
        elif refs:raise IntegrityError('Excluded or unread clauses cannot claim extracted items')
    if used!=set(known):raise IntegrityError('Every idea must be linked to its source coverage ledger')
    return rows
