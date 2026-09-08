"""Versioned method cards: verified CPU adapters vs external, untested candidates.
Importing this module never downloads weights or mutates a legacy solver.
"""
from __future__ import annotations
from copy import deepcopy

VERSION='0.3.0-algorithms'
AS_OF='2026-09-08'

FAMILIES={
 'linear-programming':dict(entry='cumcm_harness.algopt.solve_linear',
    upgrade='Original-space residual checks, optional row scaling, solver statuses; retain HiGHS.',
    assumptions=['linear objective and constraints','continuous variables'],
    verifier=['original units feasibility','original objective recomputation','status/duals'],
    frontier=['llm-lns','llm4branch'],mechanism='Only extend LP inside a certified MILP/solver workflow, not a neural LP replacement.'),
 'mixed-integer':dict(entry='cumcm_harness.algopt.solve_linear',
    upgrade='Integer residuals and original dual bound; feasible-incumbent local neighborhoods.',
    assumptions=['linear model','continuous or general integer variables'],
    verifier=['integrality','feasibility','original vs local dual-bound scope','total seconds'],
    frontier=['llm-lns','llm4branch','encore'],mechanism='Propose free variables, solve bounded neighborhood, accept only an independently checked incumbent.'),
 'mosaic-multiobjective':dict(entry='cumcm_harness.algorithms.mosaic_solve',
    upgrade='Keep v14 solver frozen; add independent objective/front audit; new experts remain candidates.',
    assumptions=['original MOSAIC contract applies','minimization convention in front audit'],
    verifier=['exact FE ledger','objective recomputation','Pareto nondominance','held-out families'],
    frontier=['seemoo','cmoea-aop'],mechanism='Evidence-triggered residual experts, frozen inactive RNG trajectory, no untested automatic promotion.'),
 'regression':dict(entry='cumcm_harness.algpredict.fit_tabular',
    upgrade='Train-only OLS/Ridge/Huber/GBDT selection; optional crossfit residual; separate conformal calibration.',
    assumptions=['numeric finite features','declared IID/group/time dependence'],
    verifier=['train-only preprocessing','outer test error','calibration isolation','fit budget'],
    frontier=['tabpfn3','tabiclv2'],mechanism='Cheap shared predictor plus a validated residual expert; same output contract for optional foundation models.'),
 'time-series':dict(entry='cumcm_harness.algpredict.forecast_portfolio',
    upgrade='Nonoverlapping rolling-origin selection among trend, naive, seasonal and lagged models.',
    assumptions=['regular univariate series','specified season','sufficient historical validation windows'],
    verifier=['no future target leakage','future-known covariates only in future adapter','horizon MAE/MASE','wallclock'],
    frontier=['timesfm3','tirex2','toto2','chronos2'],mechanism='Choose by historical regime evidence, never assume a single foundation model dominates every horizon.'),
 'topsis':dict(entry='cumcm_harness.algdecision.fixed_topsis',
    upgrade='Fixed external scale and ideals; explicit preference weights; Dirichlet rank acceptability; AHP consistency.',
    assumptions=['anchors fixed independently of alternatives','weights are declared preferences'],
    verifier=['dominated alternative monotonicity','insertion invariance','ties','weight sensitivity'],
    frontier=['mcda-robustness'],mechanism='Robust decision support, not a fabricated ground-truth ranking or automatic normative preferences.'),
 'graph-path':dict(entry='cumcm_harness.alggraph.shortest_path',
    upgrade='Zero-edge-safe graph, negative-edge Bellman-Ford, checked A* hint with Dijkstra fallback.',
    assumptions=['explicit directed edge list','static edge weights'],
    verifier=['edge existence','recomputed path cost','negative cycles','heuristic consistency'],
    frontier=['dynaco','efloco'],mechanism='Neural routing is a separate NP-hard TSP/VRP branch, not replacement of exact shortest paths.'),
 'ode':dict(entry='cumcm_harness.algscience.checked_ivp',
    upgrade='Declared-stiffness DOP853/Radau, tolerance refinement, optional invariants and positivity checks.',
    assumptions=['explicit RHS and initial state','invariants declared when known'],
    verifier=['refinement diagnostic','RHS call budget','initial state','conservation'],
    frontier=['walrus','pdeformer2','physicscorrect'],mechanism='Surrogate proposes, numerical residual and boundary conditions verify; no rigorous-error claim from two tolerances.'),
 'monte-carlo':dict(entry='cumcm_harness.algscience.integrate_unit',
    upgrade='Replicated scrambled Sobol, independent-pilot control variates, honest total evaluation counts.',
    assumptions=['integration on unit hypercube','finite integrand','known control means when used'],
    verifier=['independent scramble error units','pilot cost','analytic examples','rare-event warnings'],
    frontier=['fm-isqmc'],mechanism='Learned sampling requires density/importance correction; never substitute biased generated samples for MC truth.'),
 'statistics':dict(entry='cumcm_harness.algscience.paired_summary',
    upgrade='Independent-unit aggregation, effect intervals, Holm/BH/BY, clustering diagnostics; separate classifier selection.',
    assumptions=['independent units declared','valid null p-values','no causal conclusion from prediction alone'],
    verifier=['unit of analysis','multiplicity','effect size','negative controls','calibration'],
    frontier=['score','tabpfn3','tabiclv2'],mechanism='Uncertainty and selection risk need independent statistical evidence, not model self-confidence.')
}

# External candidates are real literature references, NOT available model implementations.
# Current licenses must be accepted at provisioning time; no credentials/weights distributed.
EXTERNAL={
 'tabpfn3':('TabPFN-3','2026-05','https://priorlabs.ai/technical-reports/tabpfn-3','https://github.com/PriorLabs/TabPFN','WEIGHTS_RESTRICTED_VERIFY','tabular synthetic prior in-context learning'),
 'tabiclv2':('TabICLv2','2026-02','https://arxiv.org/abs/2602.11139','https://github.com/soda-inria/tabicl','VERIFY_UPSTREAM','large-context synthetic-prior tabular model'),
 'timesfm3':('TimesFM 3.0','2026-08','https://github.com/google-research/timesfm','https://github.com/google-research/timesfm','WEIGHTS_NONCOMMERCIAL_NONPRODUCTION_VERIFY','multivariate + past/future-known covariates'),
 'tirex2':('TiRex-2','2026-07','https://arxiv.org/abs/2607.01204','https://github.com/NX-AI/tirex-2','VERIFY_OPEN_VS_PRO','xLSTM recurrent multivariate prior; streaming implementation is Pro-dependent'),
 'toto2':('Toto 2.0','2026-05','https://arxiv.org/abs/2605.20119','https://github.com/DataDog/toto','APACHE2_RECHECK_CHECKPOINT','multi-size forecasting; observability and synthetic pretraining'),
 'chronos2':('Chronos-2','2025-10','https://arxiv.org/abs/2510.15821','https://github.com/amazon-science/chronos-forecasting','VERIFY_UPSTREAM','group attention and covariate context sharing'),
 'llm-lns':('LLM-LNS (ICML 2025)','2025-07','https://proceedings.mlr.press/v267/ye25j.html','https://proceedings.mlr.press/v267/ye25j.html','VERIFY_UPSTREAM','LLM-evolved large neighborhoods'),
 'llm4branch':('LLM4Branch','2026-05','https://arxiv.org/abs/2605.10401','https://github.com/hzn18/LLM4Branch','VERIFY_UPSTREAM','interpretable programs plus parameter search for branching'),
 'encore':('EnCore','2026-08-20','https://arxiv.org/abs/2608.19953','https://github.com/lamda-bbo/EnCore','VERIFY_UPSTREAM','early feasible incumbent consistency for local search'),
 'seemoo':('SEEMOO','2026-01-31','https://arxiv.org/abs/2602.00540',None,'VERIFY_UPSTREAM','RL scheduling of surrogate experts'),
 'cmoea-aop':('CMOEA-AOP','2026-03','https://arxiv.org/abs/2603.16401',None,'VERIFY_UPSTREAM','constrained operator portfolios'),
 'mcda-robustness':('MCDA robustness coefficients','2025-07','https://doi.org/10.1007/s10462-025-11307-6',None,'OPEN_ARTICLE_NOT_CODE_LICENSE','rank stability and preference sensitivity'),
 'dynaco':('DyNACO','2026-06','https://arxiv.org/abs/2606.04039',None,'VERIFY_UPSTREAM','dynamic neural correction of classical ACO stagnation'),
 'efloco':('EFLOCO (AAAI 2026)','2026-03','https://ojs.aaai.org/index.php/AAAI/article/view/41035',None,'VERIFY_UPSTREAM','few-step discrete flow matching for TSP/ATSP'),
 'walrus':('Walrus','2025-11','https://arxiv.org/abs/2511.15684','https://github.com/PolymathicAI/walrus','MIT_RECHECK_CHECKPOINT','continuum dynamics prior, adaptive stride and patch jitter'),
 'pdeformer2':('PDEformer-2','2025-07','https://arxiv.org/abs/2507.15409','https://github.com/functoreality/pdeformer-2','VERIFY_UPSTREAM','explicit PDE-conditioned solution operator'),
 'physicscorrect':('PhysicsCorrect','2025-07','https://arxiv.org/abs/2507.02227','https://github.com/summerwine668/PhysicsCorrect','VERIFY_UPSTREAM','training-free numerical residual projection'),
 'fm-isqmc':('FM-ISQMC','2026-01','https://arxiv.org/abs/2601.01072',None,'VERIFY_UPSTREAM','flow transport with importance correction and RQMC'),
 'score':('SCoRE','2026-03','https://arxiv.org/abs/2603.24704','https://github.com/Tian-Bai/SCoRE','VERIFY_UPSTREAM','selective risk control with conformal e-values'),
 'alphaevolve':('AlphaEvolve','2025-05','https://arxiv.org/abs/2506.13131',None,'NOT_DISTRIBUTED_HERE','evolve algorithms under external machine evaluation'),
 'engram':('Engram','2026-01','https://arxiv.org/abs/2601.07372','https://github.com/deepseek-ai/Engram','VERIFY_UPSTREAM','conditional lookup versus dynamic computation')
}


def external_manifest():
    return [{'id':key,'name':v[0],'first_release':v[1],'paper':v[2],'upstream':v[3],
             'license_note':v[4],'mechanism':v[5],'status':'EXTERNAL_NOT_RUN',
             'checkpoint_digest':None,'code_revision':None,'runtime_entry':None}
            for key,v in EXTERNAL.items()]


def enrich_method(card):
    c=deepcopy(card)
    if c['id'] in FAMILIES:
        c['legacy_implementation']=c.get('implementation')
        c['legacy_assumptions']=deepcopy(c.get('assumptions',[]))
        c['legacy_checks']=deepcopy(c.get('checks',[]))
        c['implementation']=FAMILIES[c['id']]['entry']
        c['assumptions']=deepcopy(FAMILIES[c['id']]['assumptions'])
        c['checks']=deepcopy(FAMILIES[c['id']]['verifier'])
        if c['id']=='mosaic-multiobjective':
            c['assumptions']=list(dict.fromkeys(c['legacy_assumptions']+c['assumptions']))
            c['checks']=list(dict.fromkeys(c['legacy_checks']+c['checks']))
        c['algorithm_upgrade']={**deepcopy(FAMILIES[c['id']]),'version':VERSION,
            'status':'LOCAL_ADAPTER_WITH_TESTS_NOT_GLOBAL_PROMOTION',
            'external_models':'NOT_INSTALLED_NOT_RUN',
            'skill':'.agents/skills/algorithm-library-upgrade/SKILL.md'}
    return c


def select_algorithms(contract):
    """Structured admission before heuristic ranking. The text router alone cannot
    establish that a method fits the problem. Returns a plan, does not execute it.
    """
    if not isinstance(contract,dict):raise ValueError('Problem contract must be a dict')
    family=contract.get('family')
    if family not in FAMILIES:raise ValueError('Unknown family')
    if family=='linear-programming' and (contract.get('nonlinear') or contract.get('integer')):
        raise ValueError('Not a continuous linear program')
    if family=='mixed-integer' and contract.get('nonlinear'):raise ValueError('MILP does not support nonlinear constraints')
    if family=='mosaic-multiobjective' and (contract.get('n_objectives',2)<2 or contract.get('stochastic',False)):
        raise ValueError('Original deterministic multiobjective contract required')
    if family=='graph-path' and contract.get('task','shortest_path')!='shortest_path':
        raise ValueError('TSP/VRP is not a shortest-path problem; provision a separate candidate')
    if family=='topsis' and not contract.get('anchors_fixed',False):raise ValueError('Fixed external anchors required')
    if family=='time-series' and contract.get('multivariate',False):raise ValueError('Local adapter is univariate; provision and validate a multivariate model separately')
    return dict(family=family,**deepcopy(FAMILIES[family]),
                admission_scope='PARTIAL_STRUCTURAL_SCREEN_NOT_EXECUTION_APPROVAL',
                external_status='EXTERNAL_NOT_RUN',promotion='REQUIRES_INDEPENDENT_BENCHMARK')
