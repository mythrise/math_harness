"""Fresh Claude CLI reviews of the exact bounded evaluator repair and receipts."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from cumcm_harness.common import digest, read_json, write_json
from cumcm_harness.providers import CLIProvider, review_quorum
from cumcm_harness.controller import REVIEW_STAGES

root=Path(__file__).resolve().parents[1]
base=root/'reports/heliostat-evaluator-repair/fable-review-v1'
if base.exists():raise SystemExit('Review output already exists; preserve it and use a new version')
source=root/'repairs/heliostat-evaluator-fable-v1'
artifact={'files':[{'path':n,'content':(source/n).read_text()} for n in ['evaluate.py','test_evaluator.py']],
          'execution_before':read_json(root/'reports/heliostat-evaluator-repair/before/result.json'),
          'execution_after':read_json(root/'reports/heliostat-evaluator-repair/after/result.json')}
packet={'artifact':artifact,'target_digest':digest(artifact),'review_stage':'source_code',
        'stage_requirements':{**REVIEW_STAGES['source_code'],
            'scope':'Review the bounded defect-repair patch and its regression adequacy. This is NOT permission to freeze the entire evaluator or certify full-field accuracy. Assess sun-disc weight shapes and normalization, +s shadow tracing, initialization of all mirror normals per instant, nearest cylinder side/cap contact and tie policy, arithmetic mean of per-mirror efficiency products, and schema-valid invalid-answer rejection.',
            'boundary':'Report any actual defect in those repairs. Separate source reasoning and supplied Docker execution receipts. Full-field runtime/convergence, FE ledger completeness, final report matching and optimization are outside this repair review and remain required later. Do not infer their completion. Editorial preferences are not correctness failures. Use explicit numeric/vector counterexamples when asserting a mathematical defect.'},
        'context':{'conventions':'s is unit direction from mirror TO SUN; incident propagation is -s, backward shadow query is +s. Mirror width axis horizontal. Receiver is opaque closed cylinder z=76..84, radius3.5, only first inward side contact receives; endcaps occlude and win rim ties. Efficiencies in the stated table are mirror-area-weighted then equally averaged over 60 sample instants, not DNI-weighted. Power is computed per instant with that instant DNI. Reflectance0.92 is applied once before averaging products.',
                   'scope_limit':'The after code is a repaired development draft, NOT a frozen production evaluator. The analytic aggregation test intentionally substitutes known component efficiencies to test only aggregation; the separate two-mirror 60-instant test uses the real optical method.'}}
write_json(base/'packet.json',packet)
def review(role):
    return CLIProvider('claude',model='claude-fable-5',timeout=300).invoke(role,'review',packet,base/role)
roles=['math_reviewer','experiment_reviewer']
with ThreadPoolExecutor(max_workers=2) as pool:
    records=list(pool.map(review,roles))
write_json(base/'records.json',records)
try:
    quorum=review_quorum(records,packet['target_digest'])
except Exception as exc:
    write_json(base/'summary.json',{'status':'NOT_ACCEPTED','scope':'BOUNDED_REPAIR_ONLY','error':str(exc),
               'verdicts':{r['receipt']['role']:r['result']['verdict'] for r in records}})
    raise
write_json(base/'summary.json',{**quorum,'scope':'BOUNDED_REPAIR_ONLY','full_scientific_acceptance':False})
print(json.dumps({'verdicts':{r['receipt']['role']:r['result']['verdict'] for r in records},'scope':'BOUNDED_REPAIR_ONLY'}))
