"""Input contracts, source coverage and conservative (non-certifying) preflight."""
from __future__ import annotations
import re, json
from importlib.resources import files as resources
from jsonschema import Draft202012Validator
from pathlib import Path
from .common import Blocked, under, compact

AI_FILENAME='AI工具使用详情.pdf'
NO_AI='本参赛队在竞赛过程中未使用任何AI工具。'
USED_PREFIX='本参赛队在竞赛过程中使用了AI工具，主要用于'
USED_SUFFIX='，详细使用情况见支撑材料。'
APPENDIX_TITLE='附录：支撑材料与完整源程序'
MAX_BYTES=20_000_000   # conservative decimal threshold; official text only says 20 MB
CODE_SUFFIXES={'.py','.m','.r','.R','.jl','.cpp','.cc','.c','.h','.hpp','.java','.js','.ts','.sh','.sql','.sas','.sps','.do','.ipynb','.wl','.nb','.lua','.f','.f90','.for','.rs','.go','.vbs','.bas'}
TEXT_SUFFIXES=CODE_SUFFIXES|{'.json','.jsonl','.csv','.txt','.md','.yaml','.yml','.toml','.tex','.bib','.typ','.xml','.html','.css'}
FORBIDDEN_FILENAMES={'.env','.git','.svn','.DS_Store','credentials','id_rsa','id_ed25519'}
PLACEHOLDER_RE=re.compile(r'\[\[FILL[^\]]*\]\]|【(?:填写|待填|待补)[^】]*】|在此输入|关键词一|\bTODO\b|\bTBD\b',re.I)
# Defence in depth for author fragments, NOT a proof that arbitrary TeX is sandboxed.
TEX_BANNED=re.compile(r'\\(?:input|include|includeonly|openin|openout|read|write|special|directlua|luaexec|catcode|csname|endcsname|def|gdef|edef|xdef|let|futurelet|newread|newwrite|usepackage|RequirePackage|documentclass|AtBeginDocument|AtEndDocument|shipout|newgeometry|restoregeometry|geometry|enlargethispage|tableofcontents|addtocontents|pagenumbering|pagestyle|thispagestyle|setcounter|setlength|addtolength|renewcommand|providecommand|newcommand|NewDocumentCommand|inputminted|immediate|pdfobj|pdfxform|loop|repeat)(?![A-Za-z@])')
SECRET_RE=re.compile(r'(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:api[_-]?key|access[_-]?token)\s*[=:]\s*[\"\']?[A-Za-z0-9_-]{16,})',re.I)
ABS_PATH_RE=re.compile(r'(?:/Users/[^\s/]+|/home/[^\s/]+|[A-Z]:\\Users\\[^\s\\]+)')
EMAIL_RE=re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',re.I)

def require_text(value,field):
    if not isinstance(value,str) or not value.strip() or PLACEHOLDER_RE.search(value):
        raise Blocked(f'Missing/unfilled field: {field}')
    return value

def schema_check(name: str,data) -> None:
    schema=json.loads(resources('cumcm2026').joinpath('assets',name).read_text('utf-8'))
    errors=list(Draft202012Validator(schema).iter_errors(data))
    if errors: raise Blocked('Schema error: '+errors[0].message)

def validate_ai(ai: dict,expected_status: str) -> dict:
    schema_check('ai_usage.schema.json',ai)
    if not isinstance(ai,dict) or ai.get('status')!=expected_status:
        raise Blocked('AI status differs between project and usage record')
    if expected_status not in ('used','unused'):
        raise Blocked('AI status must be explicitly confirmed used/unused; unconfirmed cannot build')
    records=ai.get('records',[])
    if not isinstance(records,list): raise Blocked('AI records must be a list')
    if expected_status=='unused':
        if records: raise Blocked('No-AI declaration contradicts nonempty AI records')
        return ai
    require_text(ai.get('brief_purpose'),'ai.brief_purpose')
    if not records: raise Blocked('AI-used submission needs real usage records (or labelled example fixtures)')
    ids=set()
    for r in records:
        if not isinstance(r,dict): raise Blocked('Each AI record must be an object')
        rid=require_text(r.get('id'),'record.id')
        if rid in ids: raise Blocked('Duplicate AI record id')
        ids.add(rid)
        for key in ('tool','version_or_model','stage','purpose','prompting','process'):
            require_text(r.get(key),f'ai[{rid}].{key}')
        if r.get('language_polishing_only') is not True:
            for key in ('adoption','human_modification','human_verification'):
                require_text(r.get(key),f'ai[{rid}].{key}')
        # Uncertain versions are not silently invented by the generator.
        if r['version_or_model'].upper() in ('UNKNOWN','UNREPORTED','N/A'):
            raise Blocked('AI tool version/model unreported; supply an actual tool version or model')
    return ai

def validate_project(c: dict) -> dict:
    schema_check('project.schema.json',c)
    if c.get('schema_version')!=1: raise Blocked('Unsupported project schema_version')
    for key in ('title','abstract','references','ai_usage'):
        require_text(c.get(key),key)
    if not isinstance(c.get('keywords'),list) or not c['keywords']: raise Blocked('keywords must be a nonempty list')
    for k in c['keywords']: require_text(k,'keyword')
    if not isinstance(c.get('sections'),list) or not c['sections']: raise Blocked('sections cannot be empty')
    for sec in c['sections']:
        if not isinstance(sec,dict): raise Blocked('section must be an object')
        require_text(sec.get('heading'),'section.heading');require_text(sec.get('path'),'section.path')
        if compact(sec['heading']) in ('AI工具使用声明','参考文献','摘要','附录','目录'):
            raise Blocked('Reserved section heading is generated by the builder')
    for key in ('program_used','example'):
        if type(c.get(key)) is not bool: raise Blocked(f'{key} must be an explicit Boolean')
    for key in ('code_roots','support_files','figures'):
        if not isinstance(c.get(key),list): raise Blocked(f'{key} must be a list')
    if c['program_used'] != bool(c['code_roots']):
        raise Blocked('program_used must agree with declared code_roots')
    if c.get('ai_status') not in ('used','unused'): raise Blocked('Confirm ai_status used/unused before building')
    filename=c.get('ai_details_filename',AI_FILENAME)
    if filename not in (AI_FILENAME,'AI 工具使用详情.pdf'):
        raise Blocked('Unsupported AI details filename; document local override if needed')
    if filename!=AI_FILENAME and not c.get('ai_filename_override_reason'):
        raise Blocked('Spaced filename requires an explicit local confirmation note')
    return c

def strip_comments(text: str) -> str:
    return '\n'.join(re.split(r'(?<!\\)%',line,maxsplit=1)[0] for line in text.splitlines())

def check_fragment(text: str,name: str) -> None:
    active=strip_comments(text)
    if PLACEHOLDER_RE.search(active): raise Blocked(f'Unfilled placeholder in {name}')
    if TEX_BANNED.search(active): raise Blocked(f'Unsafe/reserved TeX command in author fragment {name}')
    if re.search(r'\\(?:begin|end)\s*\{document\}',active): raise Blocked('Document boundaries are builder-owned')
    if '^^' in active or '\x00' in active: raise Blocked('TeX character-code escape/NUL rejected')

def check_citations(text: str,refs: str) -> None:
    used=set()
    for m in re.finditer(r'\\(?:cite|citep|citet)(?:\[[^\]]*\])?\{([^}]+)\}',strip_comments(text)):
        used.update(x.strip() for x in m.group(1).split(','))
    defined=re.findall(r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}',strip_comments(refs))
    if len(defined)!=len(set(defined)): raise Blocked('Duplicate bibliography keys')
    if used!=set(defined): raise Blocked(f'Citations/bibliography mismatch: missing={sorted(used-set(defined))}, unused={sorted(set(defined)-used)}')
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.:-]*',x) for x in defined): raise Blocked('Unsafe bibliography key')

def identity_scan(text: str,denylist: list[str]) -> list[str]:
    issues=[]
    normalized=compact(text)
    if any(x and compact(x) in normalized for x in denylist): issues.append('identity_denylist_match')
    if ABS_PATH_RE.search(text): issues.append('personal_absolute_path')
    if SECRET_RE.search(text) or SECRET_RE.search(normalized): issues.append('possible_secret')
    return issues

def enumerate_sources(root: Path,c: dict) -> list[Path]:
    files=[]
    for rel in c['code_roots']:
        p=under(root,rel)
        found=[p] if p.is_file() else sorted(p.rglob('*'))
        for f in found:
            under(root,f.relative_to(root).as_posix())
            if f.is_dir(): continue
            if any(x in FORBIDDEN_FILENAMES for x in f.relative_to(root).parts): raise Blocked('Secret/cache path in source inventory')
            # Every byte-text file in a declared source root is reproduced. Binary models/data belong in support_files.
            try: f.read_text('utf-8')
            except UnicodeDecodeError: raise Blocked(f'Binary in code_roots; classify as support data: {f.name}')
            if f.name.endswith(('.pyc','.log','.aux','.synctex.gz')): raise Blocked('Build cache in source root')
            files.append(f)
    if len(files)!=len(set(files)): raise Blocked('Overlapping source roots')
    if c['program_used'] and not files: raise Blocked('Program used but source roots are empty')
    for rel in c['support_files']:
        p=under(root,rel)
        if p.is_dir(): raise Blocked('support_files must explicitly name files, not directories')
        if p.suffix in CODE_SUFFIXES and p not in files: raise Blocked('Executable source hidden in support_files instead of code_roots')
    # An explicit, inspectable exclusion is required for executable-looking files
    # elsewhere in the project. This is coverage, not proof of actual use.
    exclusions=c.get('excluded_code_files',{})
    if not isinstance(exclusions,dict): raise Blocked('excluded_code_files must be a path-to-reason object')
    for rel,reason in exclusions.items():
        under(root,rel);require_text(reason,'code exclusion reason')
    for candidate in root.rglob('*'):
        if candidate.is_file() and candidate.suffix in CODE_SUFFIXES and candidate not in files:
            rel=candidate.relative_to(root).as_posix()
            if rel not in exclusions: raise Blocked('Unclassified executable-looking file: '+rel)
    return sorted(files)
