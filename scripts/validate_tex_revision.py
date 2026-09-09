"""Editorial revision of a real TeX prose fragment, then isolated PDF compilation.

Fixed responses exercise the controller, not scientific or live model validation.
The supplied whole-paper source is separately checked for safe editability; a
command-heavy source must stop without rewriting commands or following includes.
"""
from pathlib import Path
import argparse,shutil
from cumcm_harness.common import ROOT,Blocked,IntegrityError,file_hash,read_json,write_json,tree_manifest
from cumcm_harness.entry_documents import read_document,sha_text
from cumcm_harness.entry_inputs import initialize
from cumcm_harness.paper_revision import RevisionController
from cumcm_harness.providers import FixtureProvider
from cumcm_harness.controller import DEFAULT_CONFIG
from cumcm_harness.paper import compile_tex,render_pages


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--whole-source',type=Path)
    a=p.parse_args();out=a.out.resolve()
    if out.exists():raise Blocked('Use a new TeX revision validation directory')
    out.mkdir(parents=True)
    source=ROOT/'third_party/paperkit_v1/examples/used_ai/sections/evaluation.tex'
    fragment=source.read_text();source_hash=file_hash(source)
    fixed=r'''\documentclass[UTF8,fontset=fandol,a4paper]{ctexart}
\usepackage{amsmath,booktabs,graphicx}
\begin{document}
\section*{TeX 文字修订工程测试}

'''+fragment+r'''

\begin{equation}x = 1\label{eq:test}\end{equation}
\begin{tabular}{cc}\toprule 变量 & 原值\\\midrule $x$ & 1\\\bottomrule\end{tabular}
\par 公式见式\eqref{eq:test}，参考标记保留\cite{fixture}。
\footnote{原脚注不变。}
\begin{thebibliography}{9}\bibitem{fixture} 工程测试条目，非科研文献验证。\end{thebibliography}
\end{document}
'''
    before=out/'before';before.mkdir();(before/'main.tex').write_text(fixed)
    original_hash=file_hash(before/'main.tex');original=read_document(before/'main.tex',purpose='paper')
    protected=[b for b in original['blocks'] if not b['editable']]
    def response(role,schema,packet):
        if schema=='review':return {'target_digest':packet['target_digest'],'verdict':'PASS',
            'scope':'Fixed editorial engineering response only.','findings':[],
            'evidence':['Exact source preservation is checked by this validator.'],'unverified':[]}
        assert schema=='revision_patch'
        return {'source_sha256':packet['source_sha256'],
            'diagnosis':[{'location':'普通正文','issue':'语句连接调整','scope':'LANGUAGE'}],
            'edits':[{'block_id':b['id'],'before_sha256':b['sha256'],
                'replacement':b['text'].replace('本例公式简单','本例的公式简单'),
                'reason':'只调整普通文字连接，保留原有公式、数值、结论与局限。'}
                for b in packet['blocks'] if '本例公式简单' in b['text']],
            'research_requests':[],'limitations':['固定回复工程测试，未复核原实验。']}
    root=out/'revision';initialize(root,input_mode='revise',paper=before/'main.tex',config=DEFAULT_CONFIG)
    provider=FixtureProvider(response);c=RevisionController(root,fixture_provider=provider);result=c.run()
    after=out/'after';after.mkdir();shutil.copy2(root/'deliverables/revised.tex',after/'main.tex')
    text=(after/'main.tex').read_text()
    if text==fixed or any(b['text'] not in text for b in protected):raise IntegrityError('Expected prose edit or protected TeX changed')
    count=provider.count;identity=tree_manifest(root/'deliverables');c.run()
    if provider.count!=count or tree_manifest(root/'deliverables')!=identity:raise IntegrityError('Revision replay changed')
    builds={}
    for label,folder in [('before',before),('after',after)]:
        build=compile_tex(folder)
        pages=render_pages(folder/'main.pdf',folder/'renders')
        builds[label]={'build':build,'rendered_pages':len(pages),'visual_review':'REQUIRED_SEPARATELY'}
    whole=None
    if a.whole_source:
        d=read_document(a.whole_source,purpose='paper')
        whole={'source_sha256':file_hash(a.whole_source),'editable_blocks':sum(b['editable'] for b in d['blocks'])}
        if not whole['editable_blocks']:
            wr=out/'whole-revision';initialize(wr,input_mode='revise',paper=a.whole_source,config=DEFAULT_CONFIG)
            def never(*args):raise AssertionError('No editable block must stop before model calls')
            try:RevisionController(wr,fixture_provider=FixtureProvider(never)).run()
            except Blocked:whole['status']='EXPECTED_BLOCK_BEFORE_MODEL'
            else:raise IntegrityError('Unsafe whole source was not blocked')
        else:whole['status']='INSPECTED_ONLY_NOT_REVISED'
    if file_hash(source)!=source_hash or file_hash(before/'main.tex')!=original_hash:raise IntegrityError('Original source changed')
    write_json(out/'summary.json',{'status':'PASS','scope':'REAL_TEX_SOURCE_FRAGMENT_FIXED_REPLIES_DOCKER_COMPILATION',
        'source_sha256':source_hash,'source_unchanged':True,'revision_status':result['status'],
        'protected_blocks_unchanged':len(protected),'replay_unchanged':True,'builds':builds,
        'whole_source':whole,'real_model_calls':0,'science_revalidated':False})
    print('PASS: source fragment revised, protected TeX retained, both PDFs rendered')


if __name__=='__main__':main()
