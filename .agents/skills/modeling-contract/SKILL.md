---
name: modeling-contract
description: Translate a real contest problem into a validated mathematical model and implementation DAG.
---

# 建模手

输入：冻结题面、公开开发数据画像、已核验资料、资源配置。输出必须符合 `schemas/plan.schema.json`，不是自由文本承诺。

每个子问题分别给出验收条件、变量/单位、假设依据、方程、可行域、目标方向、基准、核验方法。子任务依赖必须能拓扑排序；跨问题共享量说明来源。区分预测、解释、因果和优化，不把相关性当因果。

用 `python -m cumcm_harness methods '问题特征'` 获得候选方法卡。十类方法卡只是路由，不代表所有方法已实现。适用性证据决定选法；多目标问题先加载 mosaic-multiobjective，无法满足合同则提出单独验证的适配器，不强行四舍五入。

至少设计一个有竞争力的简单基准、一次单因素消融、一次关键参数敏感性。小实例能枚举时提供精确校验；连续模型需要残差/单位/极端条件/数值收敛检查。所有随机性、样本划分及评价预算显式化。

只准看开发数据；确认标签不得参与设计。正式参赛交给团队审核、修改并解释核心模型。无法辨识的参数和未验证假设保留在 limitations。
