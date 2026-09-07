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
