# Codex entrypoint: CUMCM-EgoHarness

## Local deployment

This project is installed at its root with an editable Python environment in `.venv/`.
Use `./scripts/cumcm COMMAND ...` or `.venv/bin/python -m cumcm_harness COMMAND ...`;
the system `python3` is too old for this package. Run tests with `.venv/bin/python -m pytest`.
Read `docs/LOCAL_CODEX_SETUP_CN.md` and `reports/local-deployment/` for this machine's
deployment status. The original `reports/TEST_REPORT_CN.md` describes the archive producer's run.
For the later Docker image and local Claude CLI configuration, read
`reports/live-configuration/STATUS.md`. Claude inherits user auth/model settings in
safe mode; CLI/image probes do not establish successful upstream model responses.
Paper compilation additionally requires `cumcm-egoharness-tex:0.3.1` built with
`Dockerfile.tex`; host XeLaTeX is not the execution backend. Read
`docs/AUDIT_56ADE25_REPAIR_CN.md` for isolated builds, typed failures, and Exa lease recovery.
PaperKit v1 template corrections are integrated natively; read
`docs/PAPERKIT_2026_INTEGRATION_CN.md`. Keep the style source fingerprint-bound,
use `scripts/validate_paperkit.py` for template regression, and preserve the
controller-supplied appendix boundary and explicit fixture/live distinction.

Read README.md, docs/ARCHITECTURE_CN.md and reports/TEST_REPORT_CN.md first.

Use the deterministic CLI; do not impersonate its DB, reviewer or human approvals.
- Initialize a new workspace with `python -m cumcm_harness init ...` after resolving real problem/data paths.
- Use `doctor --live`, then `run WORKSPACE`. `demo` is fixture-only, not live evidence.
- Solver/evaluator/model/paper schemas are in schemas/. Read each contract before emitting JSON.
- Do not modify frozen input, evaluator, seed sets, protocol, vendor source, completed job output or review receipts.
- Never run model-generated code outside the Docker executor, never use --yolo or permission bypass.
- Never execute `approve` for the operator, read their operator key, fabricate modification notes, or submit a paper.
- Preserve negative outcomes. Explicitly distinguish dev findings, confirmation findings, synthetic demos and live benchmarks.
- Any pending RUNNING step/job may already have incurred cost or external effects. Inspect/reconcile it before an explicit retry.
- Formal CUMCM work must be team-led and itemized-human-reviewed under 2026 rules. No public posting of live questions.
- If infrastructure is absent or independent checks remain unknown, return BLOCKED with evidence; never silently switch to a fixture.

Skills: `.agents/skills/cumcm-orchestrator`, `mosaic-multiobjective`, `deterministic-autoresearch`, `ourwork-svg-v16`, `cumcm-paper-2026`, `independent-review-board`, `modeling-contract`, `coding-experiments`.

## 0.2 Exa and availability policy

Read docs/EXA_RESILIENT_REVIEW_CN.md first. Use configs/exa-resilient.json for new online workspaces. Exa credentials may come from the parent EXA_API_KEY environment or an operator-authorized local private file managed by set-exa-key. Never copy the value into versioned files, workspace config, logs, model packets, containers or support bundles; never send private inputs to search. Exa provides literature, not empirical hypothesis tests. Use the literature-adversary skill and execute the declared hypothesis diagnostics.

Review seats are role-based Claude plus Codex. A terminated ProviderFailure may trigger a bounded recorded failover; a valid negative finding, stale digest or unknown process state may not. No fixture can pass a live gate. WAITING_REVIEW_PROVIDERS / WAITING_RESEARCH_PROVIDER preserve work for a later explicit run. Updated code requires a new workspace rather than editing an old fingerprint.

## 0.3 algorithm library

Read `.agents/skills/algorithm-library-upgrade/SKILL.md` and `docs/algorithm-upgrade/API_CN.md` when selecting the new algorithms. Method retrieval and partial structural screening are not execution approval. Keep original MOSAIC constraints, residual regression off by default, and external candidates `EXTERNAL_NOT_RUN`. Run new numerical validation with `scripts/validate_algorithm_upgrade.py` through Docker; it never establishes a live LLM/contest result. Use a new empty validation directory and preserve upstream and local result sets separately.

Only retrieved source IDs are citable in literature audits. Problem/experiment context is not empirical literature evidence. Complete failed dossiers remain in the object store; bounded repair packets retain objections without duplicating source bodies. Do not repeat an oversized request, weaken quotation checks or rewrite old workspaces to bypass a fingerprint.

For new Exa R2 tasks, read docs/EXA_R2_CN.md and use the explicit frozen sidecar
with configs/exa-modeling-compatible.json. Do not retrofit old workspaces.
Use exa-status to inspect all attempts before recover-exa; unknown inflight work
must be reconciled, not automatically repeated. Dynamic/deep remain opt-in.
R2 citations require source snapshot and original-text offsets plus semantic review.


## 0.4 materials contracts

Read `docs/MATERIALS_V040_INTEGRATION_CN.md` and `docs/materials-upgrade/SOURCE_ANALYSIS_CN.md`.
Use `configs/materials-practice.json` with a new frozen R2 sidecar for the explicit
materials workflow. Keep raw source anchors, development-only data audits,
reference-only catalog status, baseline feasibility and body-to-abstract evidence.
Role skills are first-party prompt inputs bound to the runtime and call digest;
never edit them during a run or use changed skills to replay an old fingerprint.
Use `scripts/validate_materials_pipeline.py` in Docker mode and `--r2` for combined
R2 acceptance, then `--replay`; this remains fixture model/HTTP evidence.
`scripts/validate_materials_live.py` uses real services on a fixed public synthetic
problem and must preserve typed failures and actual receipts. No fixture fallback.
The local submission manifest records MD5 and SHA-256 only; it never uploads or signs.
Keep release `0.5.0-rc1` distinct from a validated stable/contest release.

## 0.5 three input modes

Read `docs/THREE_INPUT_V050_INTEGRATION_CN.md` and `docs/THREE_INPUT_MODES_CN.md`.
Use the native `init --input-mode idea|scratch|revise` entry; mode is frozen and
separate from practice/contest. New init enables materials contracts by default.
Keep official inputs separate from external suggestions and claimed results.
Use `external-idea-intake` and `existing-paper-revision` skills for their lanes.
Unknown web provenance is UNREPORTED, never a fabricated LIVE_CLI receipt.
Idea/scratch require the original complete research gates; scientific revision
requires a new idea workspace. Editorial audit verifies exports against CAS.
DOCX review markup protects the whole prose; TeX command/math blocks are immutable.
Validate actual formatting with the separate Docker document/TeX validators.
Keep original upstream package evidence distinct from local tests and real calls.
