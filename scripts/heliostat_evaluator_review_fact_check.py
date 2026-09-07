"""Correct a factual statement in an otherwise positive review via a fresh CLI call."""
from pathlib import Path
import json
from cumcm_harness.common import read_json,write_json
from cumcm_harness.providers import CLIProvider,review_quorum

root=Path(__file__).resolve().parents[1]
base=root/'reports/heliostat-evaluator-repair'
out=base/'fable-review-factual-correction'
if out.exists():raise SystemExit('Refusing to overwrite completed or pending evidence')
packet=read_json(base/'fable-review-v1/packet.json')
packet['response_contract_feedback']={
    'required_correction':'Your prior experiment review said invalid-answer controls passed in both before and after runs. This is factually false: BEFORE contains only primitive execution and a failed preflight_contract; negative controls were NOT RUN because the primitive gate failed. AFTER contains successful primitives plus missing/malformed/fabricated controls. Re-read actual arrays and issue a complete corrected review with accurate evidence.',
    'boundary':'Review the same bounded repair artifact and all defined fixes. Preserve any actual defect or in-scope unknown as FAIL/BLOCKED. A PASS must have no P0/P1 and unverified=[]. Later production/full-field requirements belong in scope limitations, not in-scope unknowns. Cite function/expression names accurately instead of invented line numbers.'}
record=CLIProvider('claude',model='claude-fable-5',timeout=240).invoke('experiment_reviewer','review',packet,out)
math_dir=base/'fable-review-response-retry1'
math={'result':read_json(math_dir/'response.json'),'receipt':read_json(math_dir/'receipt.json')}
records=[math,record];write_json(out/'records.json',records)
quorum=review_quorum(records,packet['target_digest'])
write_json(out/'summary.json',{**quorum,'scope':'BOUNDED_REPAIR_ONLY','full_scientific_acceptance':False})
print(json.dumps({**quorum,'scope':'BOUNDED_REPAIR_ONLY'}))
