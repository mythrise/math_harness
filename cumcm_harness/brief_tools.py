"""Offline diagnosis of supplied failed briefs; never edits a frozen workspace."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .common import digest, read_json, write_json
from .materials_contracts import check_brief
from .brief_validation import diagnostics


def audit_brief(problem, brief):
    report=diagnostics(brief,problem)
    try:check_brief(brief,problem)
    except Exception as exc:
        report['schema_or_anchor_failure']={'type':type(exc).__name__,'detail':str(exc)}
        report['status']='FAIL'
    report.update(problem_digest=digest(problem),brief_digest=digest(brief),
                  semantic_evidence_review='NOT_RUN',input_modified=False)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--problem',required=True,type=Path,help='Exact frozen problem.md (not a re-extracted PDF)')
    p.add_argument('--brief',required=True,type=Path,help='Brief JSON object, not a process receipt')
    p.add_argument('--out',required=True,type=Path,help='New diagnostic JSON file outside the original workspace')
    a=p.parse_args(argv)
    if a.out.exists():p.error('Output exists; diagnostic reports do not overwrite evidence')
    if a.out.resolve() in (a.problem.resolve(),a.brief.resolve()):p.error('Output cannot replace an input')
    report=audit_brief(a.problem.read_text('utf-8'),read_json(a.brief))
    write_json(a.out,report);print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['status']=='STRUCTURAL_PASS_REVIEW_REQUIRED' else 2

if __name__=='__main__':raise SystemExit(main())
