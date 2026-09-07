---
name: deterministic-autoresearch
description: Conduct bounded hypothesis-to-code trials with frozen evaluation, complete seed matrices and confirmation gates.
---

# 确定性 autoresearch

核心代码 `research.py` / `controller.py` / `store.py`。LLM 可提出假设、改代码、解释失败；不得修改确定性裁决。

流程：冻结评价标准 → 基准通过最小实测 → 开发候选与消融/敏感性 → 完整矩阵核验 → 根据开发结果选择 → 冻结胜者 → 仅胜者及基准进入独立确认 → 证据主张表 → 写作。

每次候选只提出可证伪的机制与对照。按题目预注册最低有意义效应、开发/确认种子、预算、重复单元、资源与退出条件。任何确认信息不得回灌同一研究协议。随机种子重复不等于跨任务独立。

实验ID包括代码、评测器、数据、协议、seed、variant、环境和后端摘要。相同完成ID复用；未知RUNNING不擅自重跑；源码变更使旧验收失效；并行首发包由内容锁保护。

主指标使用实际评测结果，负例必须获得明确 valid=false。完整主方法种子缺失时不择优汇总。配对bootstrap只在预设重复单元上计算；小样本和同实例结论要标范围，不产生普适SOTA。

早停保留基准与失败证据，不能为了好看的论文隐藏失败。失败经验只可作为项目级候选记忆；跨任务独立验证后才考虑升级算法skill。没有无约束无限循环、自动修改评测器或自我批准机制。
