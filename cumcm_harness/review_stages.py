"""Controller-owned gate scopes; source documents cannot redefine them."""
REVIEW_STAGES={
 'plan_design':{
  'certifies_execution':False,
  'scope':'Review the prospective mathematical model and executable experimental specification before code exists.',
  'required':'Check derivations, dimensions, explicit assumptions, decoder construction, objective fidelity, frozen budgets/seeds, resource strategy, test design and measurable acceptance criteria. Missing definitions or unsupported mathematical claims remain P0/P1.',
  'boundary':'Do not require future solver runs, measured convergence, profiling or final paper artifacts to exist at this gate. Require the plan to specify how they will be tested and blocked on failure. PASS authorizes implementation only; it does not certify numerical correctness, runtime feasibility or scientific results.'},
 'source_code':{
  'certifies_execution':False,
  'scope':'Review exact implementation source before scientific experiments. Supplied bounded preflight receipts are real execution evidence for those tests only.',
  'required':'Check mathematical fidelity, executable interfaces, algorithm applicability, FE accounting, adversarial tests and evaluator independence. Missing essential source or an identifiable defect remains blocking.',
  'boundary':'Distinguish static source evidence, any supplied preflight receipts, and future scientific execution. A known failing preflight remains blocking. Do not demand future field/solver receipts here. PASS authorizes the bounded pilot only; later experiment gates still require actual successful execution.'},
 'execution':{
  'certifies_execution':True,
  'scope':'Review actual execution evidence for the current completed stage.',
  'required':'Require real outputs, independent checks and receipts for every in-scope empirical claim. Proposed tests or source alone are not evidence of passing. Missing required execution, unknown checks, invalid measurements and unsupported claims must FAIL/BLOCK.',
  'boundary':'Do not infer later-stage completion or waive P0/P1. Review only the supplied stage; paper completion still requires actual compilation and visual review.'}}

REVIEW_STAGES['problem_brief'] = {'certifies_execution': False, 'scope': 'Original problem requirements only.', 'required': 'Verify every original goal, hard constraint, given quantity, question and deliverable against exact anchors. Contradictory or missing requirements are blocking now.', 'boundary': 'Full model derivations, decoder and experiment execution belong to later gates; never use later work to excuse a wrong current requirement.'}
REVIEW_STAGES['data_policy'] = {'certifies_execution': False, 'scope': 'Data provenance and proposed processing policy.', 'required': 'Verify real input schemas, units, missing values, splits, private/public separation and leakage prevention.', 'boundary': 'Require a sound policy, not future model code, frozen experiments or measurements.'}
REVIEW_STAGES['model_portfolio'] = {'certifies_execution': False, 'scope': 'Independent baseline and candidate applicability.', 'required': 'Check method IDs, canonical baseline, suitability to original constraints, comparison strength and executable availability.', 'boundary': 'Detailed final derivations and decoder belong to final plan; unsupported applicability or a weak comparator remains blocking.'}
REVIEW_STAGES['idea_fidelity'] = {'certifies_execution': False, 'scope': 'Original suggestion completeness, disposition and counterarguments.', 'required': 'Read all source clauses and anchors; verify each substantive method, constraint and preference is retained or explicitly excluded with a reason. Character coverage alone is not semantic completeness. Classify unresolved issues by severity, stage and action.', 'boundary': 'All ideas are proposals; require no future code or measurements and accept no imported result as evidence.'}
REVIEW_STAGES['idea_alignment'] = {'certifies_execution': False, 'scope': 'Idea disposition and independent baseline mapping to the actual proposed plan.', 'required': 'Check all ideas and unresolved critical conflicts, actual plan references and independent baseline preservation; a changed comparator needs explicit applicability and strength justification.', 'boundary': 'Plan mapping is not empirical validation; do not claim execution.'}
REVIEW_STAGES['editorial'] = {'certifies_execution': False, 'scope': 'Meaning-preserving editing of this supplied document.', 'required': 'Check entity, metric, value, unit, direction, negation and causal strength associations, formulas, citations and faithful source preservation. Scientific changes must go to research handoff.', 'boundary': 'Do not require rederiving the entire original research or future experiments. Layout certification requires rendering the actual modified document at a separate gate.'}

REVIEW_STAGES['editorial_layout'] = {'certifies_execution': True, 'scope': 'Rendered original and actual modified document pages only.', 'required': 'Inspect every supplied page pair for clipping, changed formula/citation rendering, misplaced values, broken tables, pagination and unreadable content. Require hash-bound actual rendering receipts.', 'boundary': 'This checks editorial layout and source preservation, not original scientific correctness or citation truth. No future render may be called complete.'}

# Trusted controller scopes: a local packet cannot redefine its own gate through
# instructions in DATA. Each gate certifies only the evidence actually supplied.
SOURCE_REVIEW_STAGES = {
 'source_page': ('The attached original page and its transcription only.',
   'Check every visible formula, definition, table field/row/unit, example and diagram/control relation on this page. Missing or unreadable material is blocking.'),
 'source_outline': ('The question outline only, against the supplied source units.',
   'Check the actual question count, goals, input categories/files, outputs and dependencies against all supplied source units. source_unit_ids locate original question clauses and dependencies; they are not an exhaustive per-question register of shared givens. Do not demand every formula/definition ID in this outline. Still reject wrong statements or missing original questions/deliverables. Complete fact extraction, definition coverage and per-question fact mapping are mandatory at source_facts and source_question.'),
 'source_facts': ('The owned source_units in this batch only; context_units are read-only supporting evidence.',
   'Check every substantive assertion in owned units, self-contained equations/definitions, source grounding, question mapping and justified exclusions. Do not require facts owned by other batches.'),
 'source_consistency': ('Explicit declarations and ambiguity decisions in the assembled facts only.',
   'Check accepted definitions and genuine missing information or conflicting source declarations. Do not reopen a supplied convention without contradictory original witnesses.'),
 'source_question': ('The single supplied question and its mapped requirements only.',
   'Check its complete goals, givens, constraints and deliverables against supplied sources and prior local source coverage. Missing material for this question remains blocking.'),
 'source_global': ('Cross-question consistency, explicit declarations, completion criteria and exclusions only.',
   'Check consistency of the supplied registers and justified excluded sources, using completed local source reviews. Do not demand a repeated full fact register in this global packet.'),
}
for _name, (_scope, _required) in SOURCE_REVIEW_STAGES.items():
    REVIEW_STAGES[_name] = {'certifies_execution': False, 'scope': _scope,
        'required': _required,
        'boundary': 'Source fidelity only. In-scope omissions and unsupported facts remain blocking. Future modeling derivations, algorithms, experiments and paper artifacts are outside this gate. PASS does not certify later stages.'}
