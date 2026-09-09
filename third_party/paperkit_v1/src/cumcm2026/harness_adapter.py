"""Small additive hook for the inspected mythrise/math_harness paper.py interface.

Leaves claim binding, citations, code collection, return contracts, approval/HMAC,
controller step receipts and packaging to the original harness. No model calls.
"""
from __future__ import annotations
from functools import wraps
from pathlib import Path
import re
from .builder import copy_style
from .pdfcheck import inspect_pdf
from .common import profile_digest

PREAMBLE=r'''\documentclass[UTF8,fontset=fandol,a4paper,zihao=-4]{ctexart}
\usepackage{paperkit-cumcm2026}
\graphicspath{{figures/}}
\begin{document}
'''

def attach(namespace: dict, *,expected_profile_digest: str | None=None) -> None:
    actual=profile_digest()
    if expected_profile_digest is not None and expected_profile_digest!=actual:
        raise RuntimeError('PaperKit profile changed since installation; re-review and reinstall before a new workspace')
    if namespace.get('_PAPERKIT_2026_ATTACHED'): return
    required=('build_paper','build_ai_details','compile_tex','preflight','Blocked','PREAMBLE')
    if any(k not in namespace for k in required): raise RuntimeError('Unrecognized harness paper module contract')
    original_compile=namespace['compile_tex'];original_preflight=namespace['preflight']
    namespace['PREAMBLE']=PREAMBLE
    @wraps(original_compile)
    def compile_tex(folder,main='main.tex'):
        if profile_digest()!=actual:
            raise namespace['Blocked']('PaperKit source/style changed during the run')
        copy_style(Path(folder))
        result=original_compile(folder,main)
        log_path=Path(folder)/Path(main).with_suffix('.log')
        if not log_path.is_file(): raise namespace['Blocked']('PaperKit: required build log missing')
        log=log_path.read_text('utf-8',errors='replace')
        for marker in ('Overfull \\hbox','Overfull \\vbox','Missing character:', 'undefined references', 'undefined citations'):
            if marker in log: raise namespace['Blocked']('PaperKit strict LaTeX gate: '+marker)
        result['paperkit_profile']='cumcm2026-paperkit/1.0.0'
        result['paperkit_profile_digest']=actual
        return result
    @wraps(original_preflight)
    def preflight(pdf, *,denylist=(),require_ai=True):
        # Preserve original checks and the return fields relied on by controller/packaging.
        old=original_preflight(pdf,denylist=denylist,require_ai=require_ai)
        import fitz
        with fitz.open(pdf) as doc:
            text='\n'.join(p.get_text() for p in doc)
        example='本工程演示' in text or '本次演示' in text
        aux=Path(pdf).with_suffix('.aux')
        end=None
        if aux.exists():
            m=re.search(r'\\newlabel\{abstract-end\}\{\{[^}]*\}\{(\d+)\}',aux.read_text('utf-8',errors='replace'))
            if m:end=int(m.group(1))
        extra=inspect_pdf(Path(pdf),denylist=denylist,abstract_end=end,ai_status='used',example=example,require_ai=require_ai)
        old['paperkit_checks']=extra
        old['failures']=list(old.get('failures',[]))+[e['code']+': '+e['detail'] for e in extra['errors']]
        old['warnings']=list(old.get('warnings',[]))+extra['warnings']
        old['status']='FAIL' if old['failures'] else 'PASS'
        old['release_ready']=False
        return old
    namespace['compile_tex']=compile_tex
    namespace['preflight']=preflight
    namespace['_PAPERKIT_2026_ATTACHED']=True
