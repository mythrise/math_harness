"""Reissue one invalid mathematical review; never edit prior model output."""
from pathlib import Path
import json
from cumcm_harness.common import read_json,write_json
from cumcm_harness.providers import CLIProvider,review_quorum

root=Path(__file__).resolve().parents[1]
old=root/'reports/heliostat-evaluator-repair/fable-review-v1'
out=root/'reports/heliostat-evaluator-repair/fable-review-response-retry1'
if out.exists():raise SystemExit('Existing response evidence must not be overwritten')
packet=read_json(old/'packet.json')
packet['response_contract_feedback']={
    'error':'Prior response declared PASS with nonempty unverified; this is an invalid review response, not an accepted verdict.',
    'scope_rule':'Reassess the SAME artifact and the declared bounded repair scope. Required in-scope unknowns or actual defects still require FAIL/BLOCKED. Later full-field accuracy, FE ledger, production output and optimization checks belong in scope limitations; they are not acceptance criteria of this bounded repair review. Do not waive a real defect to get PASS.',
    'factual_correction':'The before run STOPPED after failing primitive tests. Missing/malformed/fabricated controls were run only AFTER the repair. Prior evidence incorrectly said they passed in BOTH runs. Read the supplied reports arrays, distinguish process success from test-case success, and correct this factual statement. Refer to function names and exact expressions rather than guessing source line numbers.'}
record=CLIProvider('claude',model='claude-fable-5',timeout=240).invoke('math_reviewer','review',packet,out)
other={'result':read_json(old/'experiment_reviewer/response.json'),'receipt':read_json(old/'experiment_reviewer/receipt.json')}
records=[record,other]
write_json(out/'records.json',records)
try:
    quorum=review_quorum(records,packet['target_digest'])
except Exception as exc:
    write_json(out/'summary.json',{'status':'NOT_ACCEPTED','error':str(exc)})
    raise
write_json(out/'summary.json',{**quorum,'scope':'BOUNDED_REPAIR_ONLY','full_scientific_acceptance':False})
print(json.dumps({**quorum,'scope':'BOUNDED_REPAIR_ONLY'}))
