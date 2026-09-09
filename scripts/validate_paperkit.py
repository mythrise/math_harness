#!/usr/bin/env python3
"""PaperKit reference tests and native template compilation, all TeX in Docker.

No model/provider calls, operator approvals or contest submission. Each output
directory is new; inputs, reports and failed compiler receipts remain inspectable.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from cumcm_harness.common import ROOT, Blocked, PaperCompilationFailure, file_hash, read_json, write_json, digest
from cumcm_harness.process import clean_env, run_process
from cumcm_harness.paper import PREAMBLE, compile_tex, preflight, render_pages
from cumcm_harness.paper_layout import inspect_pdf
from cumcm_harness.paper_profile import profile_digest

REFERENCE_ENTRY=r'''
import sys,json
from pathlib import Path
sys.path.insert(0,'/reference/src')
import pytest
result=pytest.main(['/reference/tests','-q','-p','no:cacheprovider',
    '--basetemp=/tmp/paperkit-tests','--junitxml=/out/reference-tests.xml'])
if result:raise SystemExit(result)
from cumcm2026.builder import build,verify_bundle
from cumcm2026.common import save,profile_digest
reports={}
for name in ('used_ai','unused_ai_no_program'):
    destination=Path('/out')/name
    build(Path('/reference/examples')/name,destination)
    reports[name]=verify_bundle(destination)
save(Path('/out/reference.json'),{'profile_digest':profile_digest(),'examples':reports})
'''


def reference_tests(root,image):
    reference=ROOT/'third_party/paperkit_v1'
    manifest=read_json(reference/'UPSTREAM_MANIFEST.json')
    for name,sha in manifest['files'].items():
        if file_hash(reference/name)!=sha:raise Blocked('Upstream reference changed: '+name)
    image_id=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
    out=root/'reference';out.mkdir()
    name='cumcm-paperkit-'+digest(str(root))[:16]
    cmd=['docker','run','--rm','--name',name,'--network','none','--read-only','--cap-drop','ALL',
         '--security-opt','no-new-privileges','--pids-limit','128','--cpus','2','--memory','2048m',
         '--memory-swap','2048m','--user',f'{os.getuid()}:{os.getgid()}',
         '--tmpfs','/tmp:rw,noexec,nosuid,size=512m',
         '--mount',f'type=bind,src={reference},dst=/reference,readonly',
         '--mount',f'type=bind,src={out},dst=/out',
         '-e','HOME=/tmp','-e','TEXMFVAR=/tmp/texmf-var','-e','TEXMFCONFIG=/tmp/texmf-config',
         '--workdir','/tmp',image_id,'-c',REFERENCE_ENTRY]
    try:
        receipt=run_process(cmd,cwd=root,out=root/'reference-logs',env=clean_env(),timeout=600,
                            output_watch=(out,100_000_000,3000))
    finally:
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
    write_json(root/'reference-receipt.json',receipt)
    if receipt['status']!='EXITED' or receipt['returncode']:
        raise Blocked('PaperKit reference validation failed; inspect preserved logs')
    suites=ET.parse(out/'reference-tests.xml').getroot()
    cases=list(suites.iter('testcase'))
    if not cases or any(list(c) for c in cases):
        raise Blocked('Reference tests must all pass with no skipped or failed cases')
    for name,sha in manifest['files'].items():
        if file_hash(reference/name)!=sha:raise Blocked('Reference changed during tests')
    return {'status':'PASS','test_count':len(cases),'image_id':image_id,
            'reference_manifest_sha256':file_hash(reference/'UPSTREAM_MANIFEST.json'),
            'receipt_sha256':file_hash(root/'reference-receipt.json'),
            'examples':read_json(out/'reference.json')}


def document(*,long_title=False,missing_figure=False):
    title=('复杂任务中的数学建模、误差检验与可复核分析：'+'较长标题的排版稳定性验证'*5
           if long_title else '模板工程验证示例')
    body=PREAMBLE+r'\PaperKitTitle{'+title+r'''}
\section*{摘要}
本文件是模板工程测试，不是实际竞赛解答。使用固定内容检查标题换行、页边距、连续页码与声明位置。
\keywords{模板；工程验证}\label{abstract-end}\clearpage
\section{问题重述}
本文只检查排版，不提供真实科学结论，不代表参赛作品或人工审查结论。
\begin{equation}y = ax+b\end{equation}
\begin{table}[htbp]\centering\caption{合成排版示例}
\begin{tabular}{cc}\toprule 符号 & 含义\\\midrule $x$ & 输入\\ $y$ & 输出\\\bottomrule\end{tabular}
\end{table}
'''
    if missing_figure:body+=r'\figplot{缺失资产测试}{}{missing}{}{absent.pdf}{}'+'\n'
    return body+r'''
\FloatBarrier\section*{AI工具使用声明}
本参赛队在竞赛过程中使用了AI工具，主要用于模板工程测试，详细使用情况见支撑材料。
\section*{参考文献}
本工程测试不引用外部研究成果。
\clearpage\appendix\section*{附录：支撑材料与完整源程序}\label{harness-appendix-start}
本工程测试的固定源文件与构建回执保留在验收目录中；没有运行比赛求解器。
\end{document}
'''


def native_tests(root):
    results={}
    for name in ('native','long-title','missing-figure'):
        folder=root/name;folder.mkdir()
        (folder/'main.tex').write_text(document(long_title=name=='long-title',missing_figure=name=='missing-figure'))
        if name=='missing-figure':
            try:compile_tex(folder)
            except PaperCompilationFailure as error:
                results[name]={'status':'EXPECTED_FAILURE','error':str(error)}
            else:raise Blocked('Missing figure incorrectly compiled')
            continue
        build=compile_tex(folder)
        aux=(folder/'main.aux').read_text()
        match=re.search(r'\\newlabel\{harness-appendix-start\}\{\{[^}]*\}\{(\d+)\}',aux)
        if not match:raise Blocked('Native appendix boundary missing')
        qa=preflight(folder/'main.pdf',trusted_appendix_page=int(match.group(1)))
        if qa['status']!='PASS':raise Blocked('Native template failed: '+str(qa['failures']))
        # A second request must reuse the same compiler receipt and PDF bytes.
        replay=compile_tex(folder)
        if replay!=build:raise Blocked('Native compiler replay changed evidence')
        write_json(folder/'build.json',build);write_json(folder/'preflight.json',qa)
        render_pages(folder/'main.pdf',folder/'rendered')
        results[name]={'status':'PASS','paper_sha256':file_hash(folder/'main.pdf'),
                      'pages':qa['pages'],'body_pages':qa['body_pages'],'compiler_replay_identical':True}
    return results


def starter_tests(root):
    source=(ROOT/'templates/cumcm2026-starter.tex').read_text()
    results={}
    for name,ai,program,support,valid in (
        ('unconfirmed','unconfirmed','unconfirmed','unconfirmed',False),
        ('used-no-program','used','unused','provided',True),
        ('unused-no-materials','unused','unused','none',True),
        ('used-without-support','used','unused','none',False)):
        folder=root/('starter-'+name);folder.mkdir()
        text=source
        for key,value in (('PaperAIStatus',ai),('PaperProgramStatus',program),('PaperSupportStatus',support)):
            text=text.replace('\\newcommand{\\'+key+'}{unconfirmed}','\\newcommand{\\'+key+'}{'+value+'}')
        text=text.replace('题目标题','模板状态分支工程测试').replace('按真实使用记录填写简要用途','模板工程验证')
        (folder/'main.tex').write_text(text)
        try:build=compile_tex(folder)
        except PaperCompilationFailure as error:
            if valid:raise
            results[name]={'status':'EXPECTED_FAILURE','error':str(error)};continue
        if not valid:raise Blocked('Unconfirmed/contradictory starter incorrectly compiled')
        aux=(folder/'main.aux').read_text()
        end=re.search(r'\\newlabel\{abstract-end\}\{\{[^}]*\}\{(\d+)\}',aux)
        appendix=re.search(r'\\newlabel\{harness-appendix-start\}\{\{[^}]*\}\{(\d+)\}',aux)
        if not end or not appendix:raise Blocked('Starter lacks page-boundary labels')
        qa=inspect_pdf(folder/'main.pdf',ai_status=ai,abstract_end=int(end.group(1)),appendix_page=int(appendix.group(1)))
        if qa['status']!='PASS':raise Blocked('Starter layout failed: '+str(qa['errors']))
        write_json(folder/'build.json',build);write_json(folder/'preflight.json',qa)
        render_pages(folder/'main.pdf',folder/'rendered')
        results[name]={'status':'PASS','paper_sha256':file_hash(folder/'main.pdf'),'pages':qa['pages'],
                       'scope':'LAYOUT_BRANCH_FIXTURE_NOT_A_CONTEST_DELIVERABLE'}
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--reference-image',default='cumcm-paperkit-validation:1.0.0')
    args=p.parse_args();root=args.out.resolve()
    if root.exists():raise Blocked('Use a new output directory; old results cannot be overwritten')
    root.mkdir(parents=True)
    reference=reference_tests(root,args.reference_image)
    native=native_tests(root)
    starter=starter_tests(root)
    for relative in ('used_ai/paper.pdf','used_ai/build/support/AI工具使用详情.pdf','unused_ai_no_program/paper.pdf'):
        pdf=root/'reference'/relative
        render_pages(pdf,pdf.parent/(pdf.stem+'-rendered'))
    report={'status':'PASS','scope':'SYNTHETIC_TEMPLATE_VALIDATION_WITH_REAL_DOCKER_TEX_NOT_LIVE_CONTEST',
            'native_profile_digest':profile_digest(),'reference':reference,'native':native,'starter':starter,
            'human_review':'NOT_SIGNED','model_calls':0,'auto_submission':False}
    write_json(root/'summary.json',report)
    print('PASS: reference tests, both reference examples, native layout, long title, missing asset and exact compile replay')


if __name__=='__main__':main()
