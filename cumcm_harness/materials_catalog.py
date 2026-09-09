"""Bounded reference retrieval, separate from executable algorithm selection."""
from pathlib import Path
import re
from .common import ROOT, read_json, file_hash, IntegrityError

def retrieve_reference_models(query, limit=8, root=None):
    if not isinstance(query,str) or len(query)>20000:raise IntegrityError('Invalid reference query')
    if type(limit) is not int or not 1<=limit<=12:raise IntegrityError('Reference retrieval limit must be 1..12')
    path=Path(root or ROOT)/'docs/materials-upgrade/source-model-catalog.json'
    catalog=read_json(path)
    words=re.findall(r'[a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}',query.lower())
    # Chinese bigrams are deterministic retrieval hints, never a model-selection oracle.
    terms=set(words)
    for word in words:
        if re.fullmatch(r'[\u4e00-\u9fff]+',word):terms.update(word[i:i+2] for i in range(len(word)-1))
    ranked=[]
    for item in catalog['entries']:
        text=' '.join(str(item.get(k,'')) for k in ('name','category','subcategory','source_scope')).lower()
        score=sum(t in text for t in terms)
        if score:ranked.append((score,item))
    selected=[item for _,item in sorted(ranked,key=lambda x:(-x[0],x[1]['id']))[:limit]]
    return {'catalog_sha256':file_hash(path),'matches':selected,'status':'REFERENCE_ONLY_NOT_EXECUTABLE',
            'limits':'Lexical retrieval is not applicability evidence; source claims are not independently verified.'}
