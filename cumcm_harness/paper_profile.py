"""PaperKit v1 layout adapted to the current isolated harness compiler.

Style source: user-supplied CUMCM2026_PaperKit_Harness_v1.0.0.
See third_party/paperkit_v1/THIRD_PARTY_NOTICES.md and UPSTREAM_MANIFEST.json.
Embedding the exact style in this module binds it to the existing runtime
source fingerprint; no external editable package can silently change a run.
"""
from __future__ import annotations
from pathlib import Path
from .common import atomic_write, file_hash, digest, IntegrityError

PROFILE='cumcm2026-paperkit/1.0.0-native'
STYLE_NAME='paperkit-cumcm2026.sty'
STYLE=r'''% Derived CUMCM profile based on bosprimigenious/ModelingPaperKit @ 47e9bc8.
% Adapted layout and public macro names; see THIRD_PARTY_NOTICES.md.
% This is NOT an official class. No font files are distributed.
\NeedsTeXFormat{LaTeX2e}
\ProvidesPackage{paperkit-cumcm2026}[2026/09/09 v1.0 CUMCM repaired profile]
\RequirePackage{iftex}
\RequireXeTeX
\RequirePackage{geometry}
% Body, header and footer are contained inside the reserved page area.
\geometry{a4paper,left=28mm,right=28mm,top=27mm,bottom=27mm,
  includefoot,headheight=0pt,headsep=0pt,footskip=9mm,bindingoffset=0pt}
\RequirePackage{amsmath,amssymb,amsthm,bm}
\RequirePackage{graphicx,float,caption,subcaption}
\RequirePackage{booktabs,array,tabularx,longtable,makecell}
\RequirePackage{enumitem,setspace,titlesec,etoolbox,xparse,xcolor}
\RequirePackage{listings,fvextra,xurl}
\RequirePackage{hyperref}
\RequirePackage[nameinlink,noabbrev]{cleveref}
\hypersetup{hidelinks,pdfauthor={},pdfsubject={},pdfkeywords={},
  pdfcreator={XeLaTeX},pdftitle={Mathematical Modeling Report}}
\urlstyle{same}
% ctex fontset=fandol works on TeX Live / Windows / macOS / Linux.
% Do not redefine \songti or \heiti: ctex already provides them.
\IfFontExistsTF{DejaVu Sans Mono}{\setmonofont{DejaVu Sans Mono}[Scale=MatchLowercase]}{}
\setstretch{1.0}
\raggedbottom
\setlength{\parindent}{2em}
\setlength{\parskip}{0.2em}
\emergencystretch=3em
\pagestyle{plain}
\makeatletter
\def\ps@plain{\let\@oddhead\@empty\let\@evenhead\@empty
  \def\@oddfoot{\hfil\small\thepage\hfil}\let\@evenfoot\@oddfoot}
\makeatother
% Keep numeric section references/subsections stable; display Chinese primary headings.
\titleformat{\section}{\centering\heiti\zihao{4}}{\chinese{section}、}{0em}{}
\titleformat{\subsection}{\raggedright\heiti\zihao{-4}}{\thesubsection}{0.6em}{}
\titleformat{\subsubsection}{\raggedright\heiti\zihao{-4}}{\thesubsubsection}{0.6em}{}
\titlespacing*{\section}{0pt}{0.8em}{0.55em}
\titlespacing*{\subsection}{0pt}{0.65em}{0.35em}
\titlespacing*{\subsubsection}{0pt}{0.5em}{0.25em}
\captionsetup{font=small,labelfont=bf,labelsep=quad,justification=centering,skip=4pt}
\captionsetup[figure]{position=bottom}
\captionsetup[table]{position=top}
\renewcommand{\tablename}{表}
\renewcommand{\figurename}{图}
\crefname{figure}{图}{图}\Crefname{figure}{图}{图}
\crefname{table}{表}{表}\Crefname{table}{表}{表}
\crefname{equation}{式}{式}\Crefname{equation}{式}{式}
\crefname{section}{节}{节}\Crefname{section}{节}{节}
\setlength{\textfloatsep}{10pt plus 3pt minus 3pt}
\setlength{\intextsep}{8pt plus 2pt minus 2pt}
\setlength{\LTcapwidth}{\textwidth}
\setlength{\tabcolsep}{4pt}
\renewcommand{\arraystretch}{1.16}
\setlist{topsep=0.3em,itemsep=0.1em,leftmargin=2em,parsep=0pt}
\newcommand{\topline}{\toprule}
\newcommand{\midline}{\midrule}
\newcommand{\bottomline}{\bottomrule}
\newcolumntype{Y}{>{\centering\arraybackslash}X}
\newcolumntype{J}{>{\raggedright\arraybackslash}X}
\newcommand{\keywords}[1]{\par\smallskip\noindent\textbf{关键词：}#1\par}
\lstset{basicstyle=\ttfamily\scriptsize,breaklines=true,breakatwhitespace=false,
  columns=fullflexible,showstringspaces=false,tabsize=4,frame=single,
  linewidth=0.96\linewidth,numbers=left,numberstyle=\tiny}
% Backwards-compatible plotting API: a missing file is now a build error, NOT a fake figure.
\NewDocumentCommand{\figplot}{mmmmmm}{%
  \begin{figure}[htbp]\centering
  \IfFileExists{#5}{\includegraphics[width=0.845\linewidth]{#5}}{%
    \PackageError{paperkit-cumcm2026}{Figure not found: #5}{Provide a real figure before building.}}
  \caption{#1}\label{#3}
  \ifblank{#6}{}{\par\small\noindent #6}\end{figure}}
\NewDocumentCommand{\FigPlotSubContent}{mmm}{\includegraphics[width=\linewidth]{#3}}
\providecommand{\dd}{\mathop{}\!\mathrm{d}}
\providecommand{\vect}[1]{\boldsymbol{#1}}
\providecommand{\mat}[1]{\mathbf{#1}}
\providecommand{\R}{\mathbb{R}}
\newcommand{\PaperKitTitle}[1]{%
  \begin{center}{\heiti\zihao{3}\parbox{0.97\linewidth}{\centering #1}}\par
  \vspace{0.25em}\rule{0.97\linewidth}{0.45pt}\end{center}}
% Deliberately no ToC configuration and no enlarged/negative summary-page geometry.
\endinput
'''
PREAMBLE=r'''\documentclass[UTF8,fontset=fandol,a4paper,zihao=-4]{ctexart}
\usepackage{paperkit-cumcm2026}
\usepackage{placeins}
\graphicspath{{figures/}}
\begin{document}
'''


def profile_digest():
    return digest({'profile':PROFILE,'module_sha256':file_hash(Path(__file__))})


def prepare_style(folder):
    target=Path(folder)/STYLE_NAME
    if target.is_symlink():raise IntegrityError('PaperKit style cannot be a symlink')
    if target.exists() and target.read_bytes()!=STYLE.encode('utf-8'):
        raise IntegrityError('PaperKit style differs from the frozen implementation')
    if not target.exists():atomic_write(target,STYLE)
    return target
