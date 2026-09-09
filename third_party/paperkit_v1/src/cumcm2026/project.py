from __future__ import annotations
from pathlib import Path
from .common import Blocked,save
from .builder import asset
import shutil

DEFAULT_SECTIONS=[('problem','问题重述'),('analysis','问题分析'),('assumptions','模型假设'),('notation','符号说明'),
                  ('model','模型建立'),('solution','模型求解'),('results','结果分析'),('validation','模型检验与灵敏度分析'),
                  ('evaluation','模型评价'),('conclusion','结论')]

def init_project(destination: Path) -> dict:
    if destination.exists(): raise Blocked('Project destination must be new')
    (destination/'sections').mkdir(parents=True)
    for name,heading in DEFAULT_SECTIONS:
        (destination/'sections'/f'{name}.tex').write_text(f'% {heading}\n[[FILL:填写本节实际内容；不适用请从project.json删除本节]]\n','utf-8')
    (destination/'sections/abstract.tex').write_text('[[FILL:填写真实摘要，含结果和适用范围]]\n','utf-8')
    (destination/'sections/references.tex').write_text(r'''% References only. The AI statement is generated BEFORE this file.
\begin{thebibliography}{99}
\bibitem{source1} [[FILL:实际使用并核验的文献，正文以cite引用]]
\end{thebibliography}
''','utf-8')
    cfg={'schema_version':1,'title':'[[FILL:论文标题]]','keywords':['[[FILL:关键词]]'],
         'abstract':'sections/abstract.tex','references':'sections/references.tex',
         'sections':[{'heading':h,'path':f'sections/{n}.tex'} for n,h in DEFAULT_SECTIONS],
         'program_used':False,'code_roots':[],'support_files':[],'figures':[],
         'ai_status':'unconfirmed','ai_usage':'ai_usage.json','ai_details_filename':'AI工具使用详情.pdf',
         'example':False,'identity_denylist':[]}
    save(destination/'project.json',cfg)
    save(destination/'ai_usage.json',{'status':'unconfirmed','brief_purpose':'','records':[]})
    (destination/'README.md').write_text('先填写 project.json 和 sections/*.tex。不得把 unconfirmed 自动改为 unused。\n使用 AI 时填写 ai_usage.json；程序放 code_roots；资料逐项加入 support_files。\n运行 cumcm-paper build --project 本目录 --out 一个全新目录。\n','utf-8')
    shutil.copyfile(asset('main_cumcm.tex'),destination/'main_cumcm.tex')
    return {'status':'INITIALIZED_NOT_READY','project':str(destination),'ai_status':'unconfirmed'}
