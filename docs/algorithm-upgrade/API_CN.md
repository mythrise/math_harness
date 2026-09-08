# 可执行接口与限制

所有新增源文件位于现有平面Python包 `cumcm_harness`，不用更改setuptools包发现规则；使用现有editable install。运行依赖沿用NumPy、SciPy、scikit-learn，没有额外大模型依赖。

| 模块／函数 | 输入与结果 | 关键边界 |
|---|---|---|
| `algopt.solve_linear` | `c,A,lower,upper,bounds,integrality,seconds` → x、目标、可行性、dual、状态 | 连续/一般整数；不支持半连续变量；原始约束验证 |
| `algopt.primal_check` | x与原问题数据 → 原量纲/整数残差 | 不等于最优性证明 |
| `algopt.milp_neighborhood` | 原问题＋可行incumbent＋free_indices | 局部最优不传播为全局bound |
| `algopt.pareto_audit` | 决策矩阵X、目标矩阵F、可信目标回调 | 仅检查返回集合内非支配，不证明完整前沿 |
| `algpredict.fit_tabular` | 训练X/y、task、IID/group/time、fit上限 | 返回模型与训练内证据；不接收外层测试标签；默认不启用残差 |
| `algpredict.ResidualRegressor` | alpha、seed | 内层crossfit仅IID；alpha=0完全不训练残差 |
| `algpredict.conformal_interval` | 预测值与独立校准残差 | 需明确exchangeable；不足样本返回无穷阈值 |
| `algpredict.forecast_portfolio` | 一维历史、horizon、season | 单变量规则采样；实际未来不可用于选择 |
| `algpredict.forecast_candidate` | 一个指定经典候选 | 用于基线及消融 |
| `algdecision.fixed_topsis` | X、非负权重、成本/效益方向、固定锚点 | 锚点外拒绝；不从当前方案重新估计尺度 |
| `algdecision.rank_acceptability` | 指标与Dirichlet权重假设 | 平局均分；概率是指定偏好分布下的接受度 |
| `algdecision.ahp_weights` | n≤10正互反矩阵 | 一致性比不是偏好真实性 |
| `alggraph.shortest_path` | n、(u,v,w)边列表、起终点、可选h | 正负边分别处理；h不一致则回退 |
| `algscience.checked_ivp` | 可信rhs、y0、times、stiff、预算、不变量 | 每次rhs计费；双容差不是严格误差界 |
| `algscience.project_linear_invariant` | x、A、b | 线性投影不保证正性、边界或动态正确性 |
| `algscience.integrate_unit` | 向量化fn、维度、replicate规模、控制变量 | 单位超立方积分；变换/Jacobian由问题代码正确提供 |
| `algscience.adjust_pvalues` | 有效p数组、holm/bh/by | 原p有效性与依赖条件由研究协议保证 |
| `algscience.paired_summary` | 配对结果、方向、独立单位ID | 按独立单位聚合；符号检验与均值区间是不同命题 |
| `algscience.cluster_diagnostics` | 数值X、kmeans/dbscan | 描述诊断，不是因果或语义簇证明 |
| `algpromotion.promotion_decision` | 完整确认记录和冻结协议 | 哈希、强基线、消融、预算、问题族、统计条件缺一HOLD |

## 预算说明

`fit_tabular` 连同残差内层拟合记录fit次数；三折、四个经典候选最多13次实际fit，增加交叉拟合残差最多32次，默认上限36。上限相同不代表实际计算量相同，本轮不声称等耗时优势。

`forecast_portfolio` 默认5个候选×3个原点＋1次重拟合=16。单一基线只需一次，因此性能对比必须附带计算差异。

`integrate_unit` 的真实积分函数调用数=replicates×points_per_rep＋pilot。控制函数调用另行计数。`checked_ivp` 的RHS预算覆盖两次求解及数值Jacobian所需调用。HiGHS的seconds是原生求解器限制，真正硬墙钟截止仍由外层Docker进程执行器负责。

## 提升协议最小字段

`candidate, baselines, independent_units, unit_families, development_families, metric, direction,
budget, evaluator_hash, candidate_hash, code_hashes, min_effect, alpha, required_ablations,
multiplicity_total, min_units, max_regression_fraction`。

结果记录包含 `method, unit, phase='confirmation', metric, budget, evaluator_hash, code_hash,
evaluation, evaluation_hash`。`evaluation` 至少含可信评价器产生的 `valid,score`，并由原harness保留实际执行回执。单纯生成这些字段不能建立真实性。

此门禁不会主动运行缺失的外部基线；它拒绝缺失矩阵。若有失效外部服务，基础设施层可恢复，但不得以替换弱基线填补比较。
