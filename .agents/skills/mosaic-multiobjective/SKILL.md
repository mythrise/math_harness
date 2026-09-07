---
name: mosaic-multiobjective
description: Use the user-supplied unmodified MOSAIC v14 multiobjective optimizer under its explicit applicability contract.
---

# MOSAIC v14 多目标优化

## 绑定来源
实际执行 `vendor/mosaic_v14/mosaic_solve.py`，通过 `cumcm_harness.algorithms.mosaic_solve` 包装。`vendor/MANIFEST.json` 记录原始字节摘要。运行前执行 `python -m cumcm_harness verify-vendor`。不得把别的GA/NSGA-II冒充这份算法。

## 接口
```python
from cumcm_harness.algorithms import mosaic_solve
run = mosaic_solve(
    problem, representation="ordered_subset", codec=problem.codec,
    constraints="feasible_decoder", deterministic=True,
    strategy="fast_h0", seed=101, budget=192, population=32,
)
result, ledger = run.result, run.ledger
assert ledger.spent == result.evaluations == 192
```
`problem` 必须满足附件 Problem 接口；可运行样例见 `examples/demo_source/main.py`。变量、目标方向、边界、codec、目标个数必须先审查。当前优化约定是向量最小化，最大化目标须明确变号，论文恢复原单位。

## 分支选择
- incumbent：未修改默认入口，保留原旧版连续盒约束后端。
- incumbent_cached / fast_h0：仅确定性双目标 ordered-subset，并且 codec **精确类型**为附件 OrderedSubsetCodec 或 RGVCodec。一般约束与任意新 codec 不自动支持。
- local24 / refit32：实验性分支，必须 `research_opt_in=True`；不能因为单个有利结果自动改生产默认。

保留可行解及全量付费评价账本，每个前沿点必须能追溯到已评价点；参考点外部冻结。重算目标、约束和非支配关系，逐种子保持相同FE与一致初始化/后处理协议。小有限域用独立枚举的精确前沿做质量上界，枚举费用与搜索预算分开报告。

消融入口 `mosaic_infill_ablation` 只关闭对应引擎的 infill enabled，其余配置保持一致；它不等同于把整个求解器换成随机搜索。种群敏感性仍保持相同 FE。

## 返回解释与边界
工程执行等价加速不等于新算法质量提升。附件 STATUS.json 中的历史统计是上传包自带记录，本次复跑数量另看 reports；不要把原有1884次记录冒充此次新跑。算法不适用时返回理由，转交建模手选择经审查的独立适配器，不静默降级。

扩展协议详见 docs/EXTENDING_CN.md。所有声称改进的机制需要同预算强基线、消融及独立确认，未测性能写 NOT_ESTABLISHED。
